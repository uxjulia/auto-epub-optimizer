"""
Split oversized EPUB spine XHTML files into smaller real spine entries.
"""

import copy
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, unquote

from lxml import etree


NS_OPF = 'http://www.idpf.org/2007/opf'
NS_XHTML = 'http://www.w3.org/1999/xhtml'
XHTML_MEDIA_TYPES = {'application/xhtml+xml', 'text/html'}
HREF_ATTRS = {'href', 'src', '{http://www.w3.org/1999/xlink}href'}


@dataclass
class SectionSplitReport:
    files_split: int = 0
    sections_added: int = 0
    links_rewritten: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.files_split > 0 or self.links_rewritten > 0

    def summary(self) -> str:
        if self.files_split == 0:
            return "no long sections found"
        total_sections = self.files_split + self.sections_added
        return f"split {self.files_split} long section(s) into {total_sections} smaller sections"


def split_long_spine_sections(epub_dir: str, opf_path: str, word_threshold: int) -> SectionSplitReport:
    report = SectionSplitReport()
    if word_threshold <= 0:
        return report

    tree = etree.parse(opf_path)
    root = tree.getroot()
    manifest = _find_element(root, 'manifest')
    spine = _find_element(root, 'spine')
    if manifest is None or spine is None:
        report.warnings.append("No OPF manifest/spine found")
        return report

    opf_dir = Path(opf_path).parent
    manifest_items = [item for item in manifest if _is_element(item)]
    spine_items = [itemref for itemref in spine if _is_element(itemref)]
    id_to_item = {item.get('id', ''): item for item in manifest_items}
    existing_ids = {item.get('id', '') for item in manifest_items}
    relocation_map: dict[tuple[str, str], Path] = {}
    split_outputs: list[Path] = []

    for itemref in spine_items:
        idref = itemref.get('idref', '')
        item = id_to_item.get(idref)
        if item is None:
            continue
        media_type = (item.get('media-type') or '').lower()
        if media_type not in XHTML_MEDIA_TYPES:
            continue

        href = unquote(item.get('href', ''))
        if not href:
            continue
        xhtml_path = (opf_dir / href).resolve()
        if not xhtml_path.exists():
            continue

        try:
            split_result = _split_xhtml_file(xhtml_path, word_threshold)
        except Exception as exc:
            report.warnings.append(f"Skipped {href}: {exc}")
            continue

        if len(split_result.parts) <= 1:
            continue

        report.files_split += 1
        report.sections_added += len(split_result.parts) - 1
        split_outputs.extend(split_result.parts)
        rel_original = _normalized_relpath(xhtml_path, opf_dir)

        for anchor, part_path in split_result.anchor_to_part.items():
            relocation_map[(rel_original, anchor)] = part_path

        original_index = list(spine).index(itemref)
        for part_index, part_path in enumerate(split_result.parts[1:], start=2):
            part_href = _normalized_relpath(part_path, opf_dir)
            part_id = _unique_id(f"{idref}-ci-section-{part_index}", existing_ids)
            new_item = etree.Element(item.tag)
            new_item.set('id', part_id)
            new_item.set('href', quote(part_href, safe='/:@'))
            new_item.set('media-type', item.get('media-type') or 'application/xhtml+xml')
            manifest.append(new_item)

            new_itemref = etree.Element(itemref.tag)
            for attr, value in itemref.attrib.items():
                if attr != 'idref':
                    new_itemref.set(attr, value)
            new_itemref.set('idref', part_id)
            spine.insert(original_index + part_index - 1, new_itemref)

    if report.files_split == 0:
        return report

    tree.write(opf_path, xml_declaration=True, encoding='utf-8', pretty_print=True)

    rewrite_paths = _manifest_text_paths(opf_path)
    for path in split_outputs:
        if path not in rewrite_paths:
            rewrite_paths.append(path)
    for path in rewrite_paths:
        if path.exists():
            report.links_rewritten += _rewrite_anchor_refs(path, opf_dir, relocation_map)

    return report


@dataclass
class _SplitResult:
    parts: list[Path]
    anchor_to_part: dict[str, Path]


def _split_xhtml_file(path: Path, word_threshold: int) -> _SplitResult:
    parser = etree.XMLParser(recover=True, remove_blank_text=False)
    tree = etree.parse(str(path), parser)
    root = tree.getroot()
    body = _find_element(root, 'body')
    if body is None:
        return _SplitResult([path], {})
    if _node_word_count(body) <= word_threshold:
        return _SplitResult([path], {})

    split_chain: list[etree._Element] = []
    body_nodes = list(body)
    if len(body_nodes) <= 1:
        split_chain = _find_split_chain(body, word_threshold)
        if not split_chain:
            return _SplitResult([path], {})
        body_nodes = list(split_chain[-1])

    chunks: list[list[etree._Element]] = []
    current: list[etree._Element] = []
    current_words = 0

    for node in body_nodes:
        node_words = _node_word_count(node)
        if current and current_words + node_words > word_threshold:
            chunks.append(current)
            current = []
            current_words = 0
        current.append(node)
        current_words += node_words

    if current:
        chunks.append(current)

    if len(chunks) <= 1:
        return _SplitResult([path], {})

    anchor_to_part: dict[str, Path] = {}
    output_paths: list[Path] = []

    for index, chunk in enumerate(chunks, start=1):
        part_path = path if index == 1 else path.with_name(f"{path.stem}__ci_section_{index}{path.suffix}")
        part_tree = _build_part_tree(root, body, chunk, body.text if index == 1 else None, split_chain, index == 1)
        part_tree.write(str(part_path), xml_declaration=True, encoding='utf-8', pretty_print=True)
        output_paths.append(part_path.resolve())

        for node in chunk:
            for anchor in _anchors_in_node(node):
                anchor_to_part[anchor] = part_path.resolve()

    return _SplitResult(output_paths, anchor_to_part)


def _build_part_tree(root, body, chunk, body_text, split_chain=None, include_preceding_siblings=False):
    new_root = etree.Element(root.tag, nsmap=root.nsmap)
    for attr, value in root.attrib.items():
        new_root.set(attr, value)

    head = _find_element(root, 'head')
    if head is not None:
        new_root.append(copy.deepcopy(head))

    new_body = etree.SubElement(new_root, body.tag)
    for attr, value in body.attrib.items():
        new_body.set(attr, value)
    new_body.text = body_text
    container = new_body
    for wrapper in split_chain or []:
        if include_preceding_siblings:
            parent = wrapper.getparent()
            for sibling in list(parent) if parent is not None else []:
                if sibling is wrapper:
                    break
                container.append(copy.deepcopy(sibling))
        next_container = etree.SubElement(container, wrapper.tag)
        for attr, value in wrapper.attrib.items():
            next_container.set(attr, value)
        container = next_container
    for node in chunk:
        container.append(copy.deepcopy(node))

    return etree.ElementTree(new_root)


def _find_split_chain(body, word_threshold: int) -> list[etree._Element]:
    best = None
    best_child_count = 0
    for node in body.iter():
        if node is body or not _is_element(node):
            continue
        child_count = len(list(node))
        if child_count <= best_child_count or _node_word_count(node) <= word_threshold:
            continue
        best = node
        best_child_count = child_count

    if best is None:
        return []

    chain: list[etree._Element] = []
    node = best
    while node is not None and node is not body:
        chain.append(node)
        node = node.getparent()
    chain.reverse()
    return chain


def _anchors_in_node(node) -> set[str]:
    anchors = set()
    if not _is_element(node):
        return anchors
    for el in node.iter():
        if not _is_element(el):
            continue
        for attr in ('id', 'name'):
            value = el.get(attr)
            if value:
                anchors.add(value)
    return anchors


def _word_count(text: str | None) -> int:
    return len(re.findall(r'\S+', text or ''))


def _node_word_count(node) -> int:
    if not _is_element(node):
        return 0
    if _local_name(node.tag) in {'script', 'style'}:
        return 0
    return _word_count(' '.join(node.itertext()))


def _manifest_text_paths(opf_path: str) -> list[Path]:
    tree = etree.parse(opf_path)
    root = tree.getroot()
    manifest = _find_element(root, 'manifest')
    if manifest is None:
        return []

    opf_dir = Path(opf_path).parent
    paths: list[Path] = [Path(opf_path).resolve()]
    for item in manifest:
        if not _is_element(item):
            continue
        href = unquote(item.get('href', ''))
        media_type = (item.get('media-type') or '').lower()
        ext = Path(href).suffix.lower()
        if media_type in XHTML_MEDIA_TYPES or media_type in {'application/x-dtbncx+xml', 'text/css'} or ext in {
            '.xhtml', '.html', '.htm', '.ncx', '.xml', '.css'
        }:
            paths.append((opf_dir / href).resolve())
    return paths


def _rewrite_anchor_refs(path: Path, opf_dir: Path, relocation_map: dict[tuple[str, str], Path]) -> int:
    try:
        parser = etree.XMLParser(recover=True, remove_blank_text=False)
        tree = etree.parse(str(path), parser)
    except Exception:
        return 0

    updated = 0
    root = tree.getroot()
    if root is None:
        return 0
    for el in root.iter():
        if not _is_element(el):
            continue
        for attr in list(el.attrib.keys()):
            if _local_attr(attr) not in HREF_ATTRS and attr not in HREF_ATTRS:
                continue
            value = el.get(attr)
            new_value = _relocated_ref(value, path, opf_dir, relocation_map)
            if new_value != value:
                el.set(attr, new_value)
                updated += 1

    if updated:
        tree.write(str(path), xml_declaration=True, encoding='utf-8', pretty_print=True)
    return updated


def _relocated_ref(value: str | None, source_path: Path, opf_dir: Path, relocation_map: dict[tuple[str, str], Path]) -> str | None:
    if not value or '#' not in value:
        return value
    base, anchor = value.split('#', 1)
    if not anchor:
        return value
    if re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', base):
        return value

    source_dir = source_path.parent
    target_path = (source_dir / unquote(base)).resolve() if base else source_path.resolve()
    target_rel = _normalized_relpath(target_path, opf_dir)
    relocated = relocation_map.get((target_rel, unquote(anchor)))
    if relocated is None or relocated == target_path:
        return value

    rel_from_source = os.path.relpath(relocated, source_dir).replace(os.sep, '/')
    return f"{quote(rel_from_source, safe='/:@')}#{anchor}"


def _find_element(root, local_name):
    el = root.find(f'.//{{{NS_OPF}}}{local_name}')
    if el is not None:
        return el
    el = root.find(f'.//{{{NS_XHTML}}}{local_name}')
    if el is not None:
        return el
    el = root.find(f'.//{local_name}')
    if el is not None:
        return el
    for child in root.iter():
        tag = child.tag if isinstance(child.tag, str) else ''
        if tag.endswith('}' + local_name) or tag == local_name:
            return child
    return None


def _is_element(node) -> bool:
    return isinstance(node.tag, str)


def _local_name(tag: str) -> str:
    return tag.split('}', 1)[1] if tag.startswith('{') else tag


def _local_attr(attr: str) -> str:
    return attr.split('}', 1)[1] if attr.startswith('{') else attr


def _normalized_relpath(path: Path, root: Path) -> str:
    return os.path.relpath(path.resolve(), root.resolve()).replace(os.sep, '/')


def _unique_id(base: str, existing_ids: set[str]) -> str:
    candidate = ''.join(ch if ch.isalnum() or ch in '-_.' else '-' for ch in base) or 'ci-section'
    if candidate not in existing_ids:
        existing_ids.add(candidate)
        return candidate
    index = 2
    while f"{candidate}-{index}" in existing_ids:
        index += 1
    value = f"{candidate}-{index}"
    existing_ids.add(value)
    return value

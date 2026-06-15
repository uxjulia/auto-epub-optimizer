"""
HTML cleaner for Xteink X4 EPUB Optimizer.
Handles: HTML repair, unused CSS removal, embedded font removal, whitespace/page-break normalization.
"""

import re
from pathlib import Path
from typing import Optional

from lxml import etree
import cssutils
import logging

# Suppress cssutils noisy logging
cssutils.log.setLevel(logging.CRITICAL)

XHTML_NS = 'http://www.w3.org/1999/xhtml'
FONT_EXTENSIONS = {'.ttf', '.otf', '.woff', '.woff2', '.eot'}
FONT_MEDIA_TYPES = {
    'application/font-woff', 'application/font-woff2',
    'font/woff', 'font/woff2', 'font/ttf', 'font/otf',
    'application/vnd.ms-opentype', 'application/x-font-ttf',
    'application/x-font-otf', 'application/font-sfnt',
}
HORIZONTAL_WHITESPACE = frozenset({' ', '\t', '\u00a0'})
CROSSINK_FLATTENABLE_CSS_PROPERTIES = frozenset({
    'text-align',
    'font-style',
    'font-weight',
    'text-decoration',
    'text-decoration-line',
    'text-indent',
    'margin',
    'margin-top',
    'margin-right',
    'margin-bottom',
    'margin-left',
    'padding',
    'padding-top',
    'padding-right',
    'padding-bottom',
    'padding-left',
    'height',
    'width',
    'display',
    'background',
    'background-color',
    'direction',
    'vertical-align',
})


def repair_html(html_bytes: bytes) -> bytes:
    """
    Repair malformed HTML/XHTML using lxml's recovery parser.
    Returns well-formed XHTML bytes.
    """
    # Try parsing as proper XML first
    try:
        tree = etree.fromstring(html_bytes)
        # Already valid - just re-serialize cleanly
        return etree.tostring(tree, encoding='unicode', pretty_print=True).encode('utf-8')
    except etree.XMLSyntaxError:
        pass

    # Fall back to HTML parser with recovery
    parser = etree.HTMLParser(recover=True, encoding='utf-8')
    try:
        tree = etree.fromstring(html_bytes, parser)
    except Exception:
        # Completely broken - return as-is
        return html_bytes

    if tree is None:
        return html_bytes

    # Re-serialize as XHTML
    result = etree.tostring(tree, encoding='unicode', pretty_print=True, method='html')
    return result.encode('utf-8')


def remove_unused_css(css_text: str, used_classes: set, used_ids: set, used_elements: set) -> tuple[str, int]:
    """
    Remove CSS rules that don't match any elements in the EPUB content.
    Returns (cleaned CSS text, count of removed rules).
    """
    try:
        sheet = cssutils.parseString(css_text)
    except Exception:
        return css_text, 0

    removed = 0
    rules_to_remove = []

    for rule in sheet:
        if rule.type != rule.STYLE_RULE:
            continue

        # Check if any selector in this rule matches used elements
        selector_text = rule.selectorText
        if not _selector_matches_used(selector_text, used_classes, used_ids, used_elements):
            rules_to_remove.append(rule)
            removed += 1

    for rule in rules_to_remove:
        sheet.deleteRule(rule)

    return sheet.cssText.decode('utf-8') if isinstance(sheet.cssText, bytes) else sheet.cssText, removed


def _selector_matches_used(selector_text: str, used_classes: set, used_ids: set, used_elements: set) -> bool:
    """Check if a CSS selector potentially matches any used classes, IDs, or elements."""
    # Always keep universal selectors, pseudo-elements, @-rules
    if selector_text.strip() in ('*', 'html', 'body'):
        return True

    # Split compound selectors
    selectors = re.split(r'\s*,\s*', selector_text)

    for sel in selectors:
        # Extract classes
        classes = re.findall(r'\.([a-zA-Z_][\w-]*)', sel)
        if classes and any(c in used_classes for c in classes):
            return True

        # Extract IDs
        ids = re.findall(r'#([a-zA-Z_][\w-]*)', sel)
        if ids and any(i in used_ids for i in ids):
            return True

        # Extract element names
        elements = re.findall(r'(?:^|[\s>+~])([a-zA-Z][\w-]*)', sel.strip())
        if elements and any(e.lower() in used_elements for e in elements):
            return True

        # Keep pseudo-class/element rules and attribute selectors
        if '::' in sel or ':' in sel or '[' in sel:
            return True

    return False


def collect_used_selectors(xhtml_bytes: bytes) -> tuple[set, set, set]:
    """
    Parse XHTML and collect all used CSS classes, IDs, and element names.
    Returns (classes, ids, elements).
    """
    classes = set()
    ids = set()
    elements = set()

    try:
        parser = etree.HTMLParser(recover=True)
        tree = etree.fromstring(xhtml_bytes, parser)
    except Exception:
        return classes, ids, elements

    for el in tree.iter():
        # Element name (strip namespace)
        tag = el.tag
        if isinstance(tag, str):
            tag = tag.split('}')[-1] if '}' in tag else tag
            elements.add(tag.lower())

        # Classes
        class_attr = el.get('class', '')
        if class_attr:
            for cls in class_attr.split():
                classes.add(cls)

        # IDs
        id_attr = el.get('id', '')
        if id_attr:
            ids.add(id_attr)

    return classes, ids, elements


def remove_embedded_fonts_from_css(css_text: str) -> tuple[str, int]:
    """
    Remove @font-face rules from CSS.
    Returns (cleaned CSS, count of removed @font-face rules).
    """
    try:
        sheet = cssutils.parseString(css_text)
    except Exception:
        return css_text, 0

    removed = 0
    rules_to_remove = []

    for rule in sheet:
        if rule.type == rule.FONT_FACE_RULE:
            rules_to_remove.append(rule)
            removed += 1

    for rule in rules_to_remove:
        sheet.deleteRule(rule)

    # Also remove font-family declarations that reference custom fonts
    result = sheet.cssText.decode('utf-8') if isinstance(sheet.cssText, bytes) else sheet.cssText
    return result, removed


def find_font_files(file_list: list[str]) -> list[str]:
    """Find all font files in the EPUB by extension and media type."""
    fonts = []
    for filepath in file_list:
        ext = Path(filepath).suffix.lower()
        if ext in FONT_EXTENSIONS:
            fonts.append(filepath)
    return fonts


def is_font_media_type(media_type: str) -> bool:
    """Check if a media type string indicates a font file."""
    return media_type.lower() in FONT_MEDIA_TYPES


def _local_name(tag) -> str:
    if not isinstance(tag, str):
        return ''
    return tag.split('}')[-1].lower() if '}' in tag else tag.lower()


def _split_css_selector_list(selector_text: str) -> list[str]:
    selectors = []
    current = []
    quote = None
    paren_depth = 0

    for ch in selector_text:
        if quote:
            current.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in ('"', "'"):
            quote = ch
            current.append(ch)
            continue
        if ch == '(':
            paren_depth += 1
        elif ch == ')' and paren_depth > 0:
            paren_depth -= 1
        if ch == ',' and paren_depth == 0:
            selector = ''.join(current).strip()
            if selector:
                selectors.append(selector)
            current = []
        else:
            current.append(ch)

    selector = ''.join(current).strip()
    if selector:
        selectors.append(selector)
    return selectors


def _parse_simple_crossink_selector(selector_part: str) -> Optional[dict]:
    part = selector_part.strip().lower()
    if not part or re.search(r'[#:\[\]>+~*]', part):
        return None
    match = re.fullmatch(r'([a-z][a-z0-9_-]*)?(?:\.([a-z_][a-z0-9_-]*))?', part)
    if not match or (not match.group(1) and not match.group(2)):
        return None
    return {'tag': match.group(1), 'class': match.group(2)}


def _parse_crossink_selector(selector: str) -> Optional[list[dict]]:
    parts = re.split(r'\s+', selector.strip())
    if len(parts) < 1 or len(parts) > 2:
        return None
    parsed = [_parse_simple_crossink_selector(part) for part in parts]
    if any(part is None for part in parsed):
        return None
    return parsed


def _crossink_selector_priority(parsed_selector: list[dict]) -> int:
    subject = parsed_selector[-1]
    if len(parsed_selector) == 2:
        return 1
    if subject['tag'] and subject['class']:
        return 3
    if subject['class']:
        return 2
    return 0


def _element_matches_simple_crossink_selector(element, selector: dict) -> bool:
    if selector['tag'] and _local_name(element.tag) != selector['tag']:
        return False
    if selector['class']:
        classes = (element.get('class') or '').lower().split()
        if selector['class'] not in classes:
            return False
    return True


def _element_matches_crossink_selector(element, parsed_selector: list[dict]) -> bool:
    if not _element_matches_simple_crossink_selector(element, parsed_selector[-1]):
        return False
    if len(parsed_selector) == 1:
        return True

    ancestor_selector = parsed_selector[0]
    parent = element.getparent()
    while parent is not None:
        if _element_matches_simple_crossink_selector(parent, ancestor_selector):
            return True
        parent = parent.getparent()
    return False


def build_crossink_css_plan(css_texts: list[str]) -> dict:
    """
    Parse CSS into the selector/property subset CrossInk firmware understands.
    Returns {rules, can_drop_css}; CSS can be dropped only when every supported
    declaration came from a selector shape CrossInk can resolve.
    """
    rules = []
    can_drop_css = True

    for css_text in css_texts:
        try:
            sheet = cssutils.parseString(css_text)
        except Exception:
            can_drop_css = False
            continue

        for rule in sheet:
            if rule.type != rule.STYLE_RULE:
                continue

            declarations = []
            for prop in rule.style.getProperties(all=True):
                name = (prop.name or '').lower()
                value = (prop.value or '').strip()
                if name in CROSSINK_FLATTENABLE_CSS_PROPERTIES and value:
                    declarations.append(f'{name}:{value}')

            if not declarations:
                continue

            for selector in _split_css_selector_list(rule.selectorText):
                parsed_selector = _parse_crossink_selector(selector)
                if parsed_selector is None:
                    can_drop_css = False
                    continue
                rules.append({
                    'selector': parsed_selector,
                    'declarations': declarations,
                    'priority': _crossink_selector_priority(parsed_selector),
                })

    return {'rules': rules, 'can_drop_css': can_drop_css and bool(rules)}


def flatten_crossink_css_in_xhtml(xhtml_bytes: bytes, css_plan: dict) -> tuple[bytes, int, int]:
    """
    Inline CrossInk-supported stylesheet declarations into matching XHTML nodes.
    Inline styles are appended after selector priorities are ordered to match
    the firmware's resolver: element, descendant, class, element.class.
    """
    rules = css_plan.get('rules') or []
    if not rules:
        return xhtml_bytes, 0, 0

    try:
        tree = etree.fromstring(xhtml_bytes)
    except etree.XMLSyntaxError:
        parser = etree.HTMLParser(recover=True)
        tree = etree.fromstring(xhtml_bytes, parser)
        if tree is None:
            return xhtml_bytes, 0, 0

    flattened = 0
    for element in tree.iter():
        if not isinstance(element.tag, str):
            continue
        declarations = []
        for priority in range(4):
            for rule in rules:
                if rule['priority'] == priority and _element_matches_crossink_selector(element, rule['selector']):
                    declarations.extend(rule['declarations'])
        if not declarations:
            continue

        existing_style = (element.get('style') or '').strip()
        merged_style = ';'.join(declarations)
        if existing_style:
            merged_style = f'{merged_style};{existing_style}'
        element.set('style', merged_style)
        flattened += 1

    removed_links = 0
    if css_plan.get('can_drop_css'):
        for element in list(tree.iter()):
            if _local_name(element.tag) != 'link':
                continue
            rel = (element.get('rel') or '').lower().split()
            link_type = (element.get('type') or '').lower()
            href = (element.get('href') or '').lower()
            if 'stylesheet' in rel or link_type == 'text/css' or href.endswith('.css'):
                parent = element.getparent()
                if parent is not None:
                    parent.remove(element)
                    removed_links += 1

    if flattened == 0 and removed_links == 0:
        return xhtml_bytes, 0, 0

    result = etree.tostring(tree, encoding='unicode', pretty_print=True)
    return result.encode('utf-8'), flattened, removed_links


def _has_text_content(text: Optional[str]) -> bool:
    """
    Treat visible text as content, and also preserve pure horizontal whitespace.

    This keeps markup like <span>          </span> intact while still allowing
    newline-only formatting whitespace to count as empty.
    """
    if not text:
        return False

    if text.strip():
        return True

    return all(ch in HORIZONTAL_WHITESPACE for ch in text)


def normalize_whitespace(xhtml_bytes: bytes) -> tuple[bytes, int]:
    """
    Strip excessive blank paragraphs and empty divs from XHTML content.
    Returns (cleaned bytes, count of removed elements).
    """
    try:
        tree = etree.fromstring(xhtml_bytes)
    except etree.XMLSyntaxError:
        parser = etree.HTMLParser(recover=True)
        tree = etree.fromstring(xhtml_bytes, parser)
        if tree is None:
            return xhtml_bytes, 0

    removed = 0
    ns = XHTML_NS

    # Find consecutive empty paragraphs (more than 2 in a row)
    empty_streak = []
    for el in tree.iter():
        tag = el.tag.split('}')[-1] if '}' in str(el.tag) else str(el.tag)

        if tag in ('p', 'div'):
            has_text_content = _has_text_content(el.text)
            has_children = len(el) > 0

            # Check if truly empty (no direct text, no child elements)
            if not has_text_content and not has_children:
                empty_streak.append(el)
            else:
                # Reset streak, remove excess empties (keep max 1)
                if len(empty_streak) > 1:
                    for empty_el in empty_streak[1:]:
                        parent = empty_el.getparent()
                        if parent is not None:
                            # Preserve tail text
                            if empty_el.tail:
                                prev = empty_el.getprevious()
                                if prev is not None:
                                    prev.tail = (prev.tail or '') + empty_el.tail
                                else:
                                    parent.text = (parent.text or '') + empty_el.tail
                            parent.remove(empty_el)
                            removed += 1
                empty_streak = []

    # Handle remaining streak
    if len(empty_streak) > 1:
        for empty_el in empty_streak[1:]:
            parent = empty_el.getparent()
            if parent is not None:
                if empty_el.tail:
                    prev = empty_el.getprevious()
                    if prev is not None:
                        prev.tail = (prev.tail or '') + empty_el.tail
                    else:
                        parent.text = (parent.text or '') + empty_el.tail
                parent.remove(empty_el)
                removed += 1

    result = etree.tostring(tree, encoding='unicode', pretty_print=True)
    return result.encode('utf-8'), removed


# Attributes to keep during stripping (essential for EPUB rendering)
KEEP_ATTRS = frozenset({
    'class', 'id', 'href', 'src', 'style', 'alt', 'title',
    'type', 'name', 'content', 'charset', 'http-equiv',
    'xmlns', 'version', 'media-type', 'properties',
    'rel', 'media', 'width', 'height', 'colspan', 'rowspan',
    'scope', 'headers', 'border', 'cellpadding', 'cellspacing',
})

# Attribute prefixes to always strip
STRIP_ATTR_PREFIXES = ('data-', 'aria-', 'epub:')


def strip_unnecessary_attributes(xhtml_bytes: bytes) -> tuple[bytes, int]:
    """
    Strip decorative/accessibility attributes that e-ink readers ignore.
    Reduces file size and parsing overhead for the 380KB-RAM ESP32-C3.

    Keeps: class, id, href, src, style, alt, title, xmlns, and other
    essential XHTML/EPUB attributes.

    Returns (cleaned bytes, count of removed attributes).
    """
    try:
        tree = etree.fromstring(xhtml_bytes)
    except etree.XMLSyntaxError:
        parser = etree.HTMLParser(recover=True)
        tree = etree.fromstring(xhtml_bytes, parser)
        if tree is None:
            return xhtml_bytes, 0

    removed = 0

    for el in tree.iter():
        if not isinstance(el.tag, str):
            continue

        attrs_to_remove = []
        for attr in el.attrib:
            # Get local attribute name (strip namespace)
            attr_local = attr.split('}')[-1] if '}' in attr else attr

            # Skip namespace declarations
            if attr.startswith('{') and attr_local in ('xmlns',):
                continue

            # Check if it's a kept attribute
            if attr_local.lower() in KEEP_ATTRS:
                continue

            # Check for namespace-prefixed essential attrs (xlink:href etc)
            if attr_local in ('href', 'src', 'type', 'lang'):
                continue

            # Strip known-useless prefixes
            if any(attr_local.lower().startswith(p) for p in STRIP_ATTR_PREFIXES):
                attrs_to_remove.append(attr)
                continue

            # Strip other non-essential attributes
            if attr_local.lower() in ('role', 'tabindex', 'accesskey', 'draggable',
                                       'contenteditable', 'spellcheck', 'autocorrect',
                                       'autocapitalize', 'autofocus', 'dir',
                                       'translate', 'inputmode', 'enterkeyhint',
                                       'hidden', 'inert', 'popover'):
                attrs_to_remove.append(attr)

        for attr in attrs_to_remove:
            del el.attrib[attr]
            removed += 1

    if removed > 0:
        result = etree.tostring(tree, encoding='unicode', pretty_print=True)
        return result.encode('utf-8'), removed

    return xhtml_bytes, removed


def add_chapter_page_breaks(xhtml_bytes: bytes) -> bytes:
    """
    Add CSS page-break-before to chapter headings (h1, h2) if not already present.
    This ensures proper chapter separation on e-readers.
    """
    try:
        tree = etree.fromstring(xhtml_bytes)
    except etree.XMLSyntaxError:
        return xhtml_bytes

    # Find <head> to inject CSS if needed
    head = tree.find('.//{http://www.w3.org/1999/xhtml}head')
    if head is None:
        head = tree.find('.//head')
    if head is None:
        return xhtml_bytes

    # Check if page-break CSS already exists
    existing_styles = head.findall('.//{http://www.w3.org/1999/xhtml}style')
    if not existing_styles:
        existing_styles = head.findall('.//style')

    has_page_break = False
    for style in existing_styles:
        if style.text and 'page-break-before' in style.text:
            has_page_break = True
            break

    if not has_page_break:
        # Add page-break style
        ns = tree.tag.split('}')[0] + '}' if '}' in tree.tag else ''
        style_el = etree.SubElement(head, f'{ns}style', type='text/css')
        style_el.text = '\nh1, h2 { page-break-before: always; }\n'

    return etree.tostring(tree, encoding='unicode', pretty_print=True).encode('utf-8')

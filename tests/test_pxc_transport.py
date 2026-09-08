import importlib.util
import json
import struct
import sys
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / 'cli' / 'epubkit_pipeline'
if not PIPELINE.exists():
    PIPELINE = ROOT / 'app' / 'optimizer' / 'epubkit_pipeline'

def module(name):
    spec = importlib.util.spec_from_file_location(name, PIPELINE / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

sys.path.insert(0, str(PIPELINE))
transport = module('pxc_transport')
packager = module('epub_packager')

class PxcTransportTest(unittest.TestCase):
    def test_shared_golden_and_decode(self):
        root = Path(__file__).parent / 'pxc_golden'
        raw = (root / 'pixels.pxc').read_bytes()
        encoded = transport.encode_pxc2(raw)
        self.assertEqual(encoded, (root / 'deflate.pxc2').read_bytes())
        decoded, offset, sequence = bytearray(), 32, 0
        while offset < len(encoded):
            codec, flags, size, count, seq, crc = struct.unpack_from('<BBHHHI', encoded, offset)
            self.assertEqual(seq, sequence)
            self.assertEqual(flags, 0)
            data = encoded[offset + 12:offset + 12 + count]
            block = data if codec == 0 else zlib.decompress(data, -15)
            self.assertEqual(len(block), size)
            self.assertEqual(zlib.crc32(block), crc)
            decoded.extend(block)
            offset += 12 + count
            sequence += 1
        self.assertEqual(bytes(decoded), raw[4:])

    def test_manifest_identity_and_image_producer(self):
        import io
        from PIL import Image
        import image_processor
        import epub_structure
        buffer = io.BytesIO()
        Image.new('L', (127, 131), 128).save(buffer, format='PNG')
        payload, width, height = image_processor.build_crossink_pxc_bytes(buffer.getvalue())
        self.assertEqual(payload[:4], b'PXC2')
        entry = dict(href='EPUB/image.jpg', pxc='META-INF/crossink/pxc/x.pxc2', width=width, height=height,
                     pxcFormat='pxc2', pxcBytes=len(payload), pixelCrc32=struct.unpack_from('<I', payload, 24)[0])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            opf = root / 'content.opf'
            opf.write_text('<package xmlns="http://www.idpf.org/2007/opf"><manifest/><spine/></package>')
            epub_structure.write_crossink_optimizer_manifest(temp, str(opf), [entry])
            manifest = (root / 'META-INF/crossink/optimizer-v1.json').read_bytes()
            index = (root / 'META-INF/crossink/optimizer-images-v1.idx').read_bytes()
            self.assertEqual(struct.unpack_from('<I', index, 16)[0], zlib.crc32(manifest))
            self.assertEqual(struct.unpack_from('<I', index, 20)[0], len(manifest))
            self.assertEqual(json.loads(manifest)['images'], [entry])

    def test_index_bounds(self):
        entry = dict(href='EPUB/image.jpg', pxc='META-INF/crossink/pxc/x.pxc2', width=127, height=131,
                     pxcBytes=3000, pixelCrc32=42, pxcFormat='pxc2')
        for count in [0, 1, 89, 256]:
            entries = [dict(entry, href=f'EPUB/{i}.jpg') for i in range(count)]
            manifest = json.dumps(dict(images=entries)).encode()
            index = transport.encode_index(manifest, entries)
            self.assertEqual(len(index), 32 + 208 * count)
            self.assertEqual(struct.unpack_from('<I', index, 28)[0], zlib.crc32(index[:28]))
            self.assertEqual(struct.unpack_from('<I', index, 24)[0], zlib.crc32(index[32:]))
        for path in ['../x', '/x', 'a\\b', 'a%00b', 'a'*129, '']:
            self.assertEqual(transport.index_entries([dict(entry, href=path)]), [])
        self.assertEqual(len(transport.index_entries([entry, entry])), 1)
        with self.assertRaises(ValueError):
            transport.encode_index(b'{}', [entry, entry])

    def test_zip_methods(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source'
            source.mkdir()
            paths = ['META-INF/container.xml', 'META-INF/crossink/optimizer-v1.json',
                     'META-INF/crossink/optimizer-images-v1.idx', 'META-INF/crossink/pxc/x.pxc2',
                     'EPUB/chapter.xhtml', 'EPUB/image.jpg']
            for path in paths:
                dest = source / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(b'test')
            output = Path(tmp) / 'book.epub'
            packager.package_epub(str(source), str(output))
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.namelist()[0], 'mimetype')
                self.assertEqual(archive.getinfo('mimetype').compress_type, zipfile.ZIP_STORED)
                for path in paths:
                    expected = zipfile.ZIP_STORED if '/crossink/' in path else zipfile.ZIP_DEFLATED
                    self.assertEqual(archive.getinfo(path).compress_type, expected)

if __name__ == '__main__':
    unittest.main()

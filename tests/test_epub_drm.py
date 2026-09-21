from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli" / "epubkit_pipeline"))

from epub_packager import has_drm


ADOBE_FONT_OBFUSCATION = "http://ns.adobe.com/pdf/enc#RC"
DRM_ENCRYPTION = "http://www.w3.org/2001/04/xmlenc#aes256-cbc"


class EpubDrmTests(unittest.TestCase):
    def test_allows_adobe_obfuscated_font_with_dat_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "font-obfuscated.epub"
            write_encrypted_epub(path, ADOBE_FONT_OBFUSCATION, "fonts/00001.dat")

            self.assertFalse(has_drm(path))

    def test_rejects_encrypted_book_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "drm.epub"
            write_encrypted_epub(path, DRM_ENCRYPTION, "text/chapter.xhtml")

            self.assertTrue(has_drm(path))


def write_encrypted_epub(path: Path, algorithm: str, uri: str) -> None:
    encryption = f'''<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container"
        xmlns:enc="http://www.w3.org/2001/04/xmlenc#">
      <enc:EncryptedData>
        <enc:EncryptionMethod Algorithm="{algorithm}"/>
        <enc:CipherData><enc:CipherReference URI="{uri}"/></enc:CipherData>
      </enc:EncryptedData>
    </encryption>'''
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("META-INF/encryption.xml", encryption)


if __name__ == "__main__":
    unittest.main()

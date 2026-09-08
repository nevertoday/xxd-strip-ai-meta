import importlib.util
import pathlib
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / 'scripts/clean_image_provenance.py'
spec = importlib.util.spec_from_file_location('cleaner', SCRIPT)
cleaner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cleaner
spec.loader.exec_module(cleaner)


def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))


class CleanupTest(unittest.TestCase):
    def test_png_cleanup_backup_and_dry_run(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / 'sample.png'
            pixels = zlib.compress(b'\x00\xff\x00\x00')
            original = (b'\x89PNG\r\n\x1a\n'
                        + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
                        + chunk(b'tEXt', b'Comment\x00OpenAI gpt-image prompt')
                        + chunk(b'IDAT', pixels) + chunk(b'IEND', b''))
            path.write_bytes(original)
            self.assertTrue(cleaner.verify_files(cleaner.require_exiftool(), [path], 100, None))
            subprocess.run([sys.executable, str(SCRIPT), str(path), '--dry-run'], check=True)
            self.assertEqual(path.read_bytes(), original)
            subprocess.run([sys.executable, str(SCRIPT), str(path), '--backup'], check=True)
            self.assertEqual(path.with_name('sample.png_original').read_bytes(), original)
            cleaned = path.read_bytes()
            self.assertNotIn(b'OpenAI', cleaned)
            self.assertIn(chunk(b'IDAT', pixels), cleaned)
            self.assertFalse(cleaner.verify_files(cleaner.require_exiftool(), [path], 100, None))


if __name__ == '__main__':
    unittest.main()

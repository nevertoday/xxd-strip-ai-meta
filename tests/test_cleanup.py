import importlib.util
import json
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
    def test_jpeg_cleanup_preserves_orientation_and_image_data(self):
        exiftool = cleaner.require_exiftool()
        fixture = pathlib.Path(__file__).parent / 'fixtures/oriented.jpg'
        # A non-square, asymmetric JPEG with EXIF orientation and an sRGB profile.
        for orientation, drop_profile in ((2, False), (6, True), (None, False)):
            with self.subTest(orientation=orientation, drop_profile=drop_profile):
                with tempfile.TemporaryDirectory() as folder:
                    path = pathlib.Path(folder) / 'sample.jpg'
                    path.write_bytes(fixture.read_bytes())
                    value = '' if orientation is None else str(orientation)
                    subprocess.run([exiftool, '-overwrite_original',
                                    f'-EXIF:Orientation#={value}', str(path)], check=True)
                    original = path.read_bytes()
                    profile = subprocess.check_output([exiftool, '-b', '-ICC_Profile', str(path)])
                    self.assertTrue(profile)
                    command = [sys.executable, str(SCRIPT), str(path), '--backup']
                    if drop_profile:
                        command.append('--drop-color-profile')
                    subprocess.run(command, check=True)
                    tags = json.loads(subprocess.check_output(
                        [exiftool, '-j', '-n', '-EXIF:Orientation', '-Software', str(path)]))[0]
                    self.assertEqual(tags.get('Orientation'), orientation)
                    self.assertNotIn('Software', tags)
                    self.assertEqual(path.with_name('sample.jpg_original').read_bytes(), original)
                    cleaned = path.read_bytes()
                    # The baseline JPEG scan and its compressed pixels remain unchanged.
                    self.assertEqual(cleaned[cleaned.index(b'\xff\xda'):],
                                     original[original.index(b'\xff\xda'):])
                    cleaned_profile = subprocess.check_output(
                        [exiftool, '-b', '-ICC_Profile', str(path)])
                    self.assertEqual(cleaned_profile, b'' if drop_profile else profile)

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

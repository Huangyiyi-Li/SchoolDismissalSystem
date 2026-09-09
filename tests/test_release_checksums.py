import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from src.app_info import APP_VERSION, WINDOWS_SETUP_NAME, WINDOWS_ZIP_NAME


class ReleaseChecksumTests(unittest.TestCase):
    def test_release_manifests_match_download_names_and_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (WINDOWS_SETUP_NAME, WINDOWS_ZIP_NAME):
                (root / name).write_bytes(b'release artifact')
            result = subprocess.run(
                [sys.executable, '-m', 'tools.prepare_release_checksums', '--dist', directory],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            digest = hashlib.sha256(b'release artifact').hexdigest()
            for name, suffix in ((WINDOWS_SETUP_NAME, 'setup-x64.exe'), (WINDOWS_ZIP_NAME, 'windows-x64.zip')):
                download_name = f'school-dismissal-v{APP_VERSION}-{suffix}'
                self.assertEqual((root / f'{name}.sha256').read_text(), f'{digest}  {download_name}\n')
                self.assertEqual((root / name).read_bytes(), b'release artifact')

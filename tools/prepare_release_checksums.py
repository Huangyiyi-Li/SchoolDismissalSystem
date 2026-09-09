"""Prepare manifests for the ASCII filenames used by GitHub Release assets."""

import argparse
import hashlib
from pathlib import Path

from src.app_info import APP_VERSION, WINDOWS_SETUP_NAME, WINDOWS_ZIP_NAME


def prepare_release_checksums(dist):
    dist = Path(dist)
    artifacts = (
        (WINDOWS_ZIP_NAME, f"school-dismissal-v{APP_VERSION}-windows-x64.zip"),
        (WINDOWS_SETUP_NAME, f"school-dismissal-v{APP_VERSION}-setup-x64.exe"),
    )
    for local_name, download_name in artifacts:
        with (dist / local_name).open("rb") as artifact:
            digest = hashlib.file_digest(artifact, "sha256").hexdigest()
        (dist / f"{local_name}.sha256").write_text(
            f"{digest}  {download_name}\n", encoding="ascii"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", default="dist", type=Path)
    prepare_release_checksums(parser.parse_args().dist)

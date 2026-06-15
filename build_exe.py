import hashlib
import shutil
import zipfile
from pathlib import Path

from src.app_info import (
    APP_NAME,
    WINDOWS_EXE_NAME,
    WINDOWS_SHA256_NAME,
    WINDOWS_ZIP_NAME,
)


PROJECT_ROOT = Path(__file__).resolve().parent
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
LOGO_PATH = PROJECT_ROOT / "assets" / "branding" / "logo-vertical.png"
ICON_PATH = BUILD_DIR / "branding" / "app.ico"
ICON_SIZES = (16, 32, 48, 64, 128, 256)


def generate_windows_icon():
    from PIL import Image

    ICON_PATH.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(LOGO_PATH) as source:
        source = source.convert("RGBA")
        canvas_size = max(source.size)
        canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
        offset = (
            (canvas_size - source.width) // 2,
            (canvas_size - source.height) // 2,
        )
        canvas.alpha_composite(source, offset)
        canvas.save(ICON_PATH, format="ICO", sizes=[(size, size) for size in ICON_SIZES])


def run_pyinstaller():
    import PyInstaller.__main__

    PyInstaller.__main__.run(
        [
            str(PROJECT_ROOT / "main.py"),
            f"--name={APP_NAME}",
            "--noconfirm",
            "--clean",
            "--windowed",
            "--onefile",
            "--hidden-import=sqlite3",
            "--hidden-import=pyttsx3.drivers",
            "--hidden-import=pyttsx3.drivers.sapi5",
            "--hidden-import=requests",
            f"--icon={ICON_PATH}",
            f"--add-data={PROJECT_ROOT / 'src'};src",
            f"--add-data={PROJECT_ROOT / 'assets'};assets",
        ]
    )


def create_release_files():
    exe_path = DIST_DIR / WINDOWS_EXE_NAME
    zip_path = DIST_DIR / WINDOWS_ZIP_NAME
    sha256_path = DIST_DIR / WINDOWS_SHA256_NAME

    if not exe_path.exists():
        raise FileNotFoundError(f"Build output not found: {exe_path}")

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(exe_path, arcname=WINDOWS_EXE_NAME)

    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sha256_path.write_text(f"{digest}  {WINDOWS_ZIP_NAME}\n", encoding="utf-8")
    return exe_path, zip_path, sha256_path


def main():
    shutil.rmtree(DIST_DIR, ignore_errors=True)
    shutil.rmtree(BUILD_DIR, ignore_errors=True)

    print("Generating Windows icon...")
    generate_windows_icon()
    print("Building executable...")
    run_pyinstaller()
    outputs = create_release_files()
    print("Build complete:")
    for output in outputs:
        print(f"  {output}")


if __name__ == "__main__":
    main()

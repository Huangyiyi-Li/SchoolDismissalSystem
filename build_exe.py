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
LED_BRIDGE_DIR = PROJECT_ROOT / "led-bridge"
LED_BRIDGE_REQUIRED_JARS = {
    "bx06-0.6.5-SNAPSHOT.jar",
    "bx06.message-0.6.5-SNAPSHOT.jar",
    "jaxb-core-2.2.11.jar",
    "jaxb-impl-2.2.11.jar",
    "rxtx-2.1.7.jar",
    "simple-xml-2.7.1.jar",
    "slf4j-api-1.7.30.jar",
    "slf4j-simple-1.7.30.jar",
    "stax-1.2.0.jar",
    "stax-api-1.0.1.jar",
    "uia-comm-0.5.3-SNAPSHOT.jar",
    "uia-message-0.6.0.jar",
    "uia-utils-0.3.1.jar",
    "xpp3-1.1.3.3.jar",
}


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

    bridge_jar = LED_BRIDGE_DIR / "led-bridge.jar"
    dependencies = sorted((LED_BRIDGE_DIR / "lib").glob("*.jar"))
    runtime_dir = LED_BRIDGE_DIR / "runtime"
    java_exe = runtime_dir / "bin" / "java.exe"
    if not bridge_jar.exists():
        raise FileNotFoundError(
            "LED Bridge not built. Run led-bridge/build.bat before build_exe.py"
        )
    dependency_names = {dependency.name for dependency in dependencies}
    missing_dependencies = sorted(LED_BRIDGE_REQUIRED_JARS - dependency_names)
    if missing_dependencies:
        raise FileNotFoundError(
            "ONBON LED Bridge dependencies are missing: "
            + ", ".join(missing_dependencies)
        )
    if not java_exe.exists():
        raise FileNotFoundError(
            "Bundled Java runtime is missing: led-bridge/runtime/bin/java.exe"
        )

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(exe_path, arcname=WINDOWS_EXE_NAME)
        archive.write(bridge_jar, arcname="led-bridge/led-bridge.jar")
        archive.write(LED_BRIDGE_DIR / "README.md", arcname="led-bridge/README.md")
        for dependency in dependencies:
            archive.write(dependency, arcname=f"led-bridge/lib/{dependency.name}")
        for runtime_file in sorted(runtime_dir.rglob("*")):
            if runtime_file.is_file():
                archive.write(
                    runtime_file,
                    arcname=f"led-bridge/runtime/{runtime_file.relative_to(runtime_dir)}",
                )

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

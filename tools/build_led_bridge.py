"""Build the ONBON Java bridge with JAVA_HOME or JDK tools from PATH."""

import os
import shutil
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BRIDGE_DIR = PROJECT_ROOT / "led-bridge"


def _jdk_tool(java_home, name):
    suffix = ".exe" if os.name == "nt" else ""
    return Path(java_home) / "bin" / f"{name}{suffix}"


def build_bridge(bridge_dir=DEFAULT_BRIDGE_DIR, java_home=None, runner=subprocess.run):
    bridge_dir = Path(bridge_dir).resolve()
    java_home_value = java_home or os.environ.get("JAVA_HOME")
    if java_home_value:
        resolved_java_home = Path(java_home_value).resolve()
        javac = _jdk_tool(resolved_java_home, "javac")
        jar = _jdk_tool(resolved_java_home, "jar")
        location_hint = f"JAVA_HOME={resolved_java_home}"
    else:
        javac_path = shutil.which("javac")
        jar_path = shutil.which("jar")
        javac = Path(javac_path) if javac_path else Path("__missing_javac__")
        jar = Path(jar_path) if jar_path else Path("__missing_jar__")
        location_hint = "JAVA_HOME is unset and JDK tools were not both found on PATH"
    if not javac.is_file() or not jar.is_file():
        raise FileNotFoundError(
            f"Cannot find both javac and jar ({location_hint})"
        )

    sources = sorted((bridge_dir / "src").rglob("*.java"))
    if not sources:
        raise FileNotFoundError(f"No Java sources found under {bridge_dir / 'src'}")

    output = bridge_dir / "led-bridge.jar"
    classes_dir = bridge_dir / "build" / "classes"
    if output.exists():
        output.unlink()
    shutil.rmtree(classes_dir, ignore_errors=True)
    classes_dir.mkdir(parents=True, exist_ok=True)

    runner(
        [
            str(javac),
            "-encoding",
            "UTF-8",
            "-source",
            "8",
            "-target",
            "8",
            "-cp",
            str(bridge_dir / "lib" / "*"),
            "-d",
            str(classes_dir),
            *[str(source) for source in sources],
        ],
        check=True,
    )
    runner(
        [
            str(jar),
            "cfe",
            str(output),
            "cn.xxt.dismissal.led.OnbonLedBridge",
            "-C",
            str(classes_dir),
            ".",
        ],
        check=True,
    )
    if not output.is_file():
        raise FileNotFoundError(f"Java build completed without output: {output}")
    print(f"Built {output}")
    return output


if __name__ == "__main__":
    build_bridge()

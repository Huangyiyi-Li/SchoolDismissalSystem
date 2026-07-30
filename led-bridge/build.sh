#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

JAVA_HOME_VALUE=${JAVA_HOME:-}
if [ -z "$JAVA_HOME_VALUE" ]; then
    JAVA_HOME_VALUE=$(/usr/libexec/java_home 2>/dev/null || true)
fi
if [ -z "$JAVA_HOME_VALUE" ]; then
    echo "JAVA_HOME is not set and no local JDK was found." >&2
    exit 1
fi

mkdir -p build/classes
find src -name '*.java' -type f | sort > build/sources.txt
"$JAVA_HOME_VALUE/bin/javac" \
    -encoding UTF-8 \
    -source 8 \
    -target 8 \
    -cp "lib/*" \
    -d build/classes \
    @build/sources.txt
"$JAVA_HOME_VALUE/bin/jar" \
    cfe led-bridge.jar cn.xxt.dismissal.led.OnbonLedBridge \
    -C build/classes .

echo "Built $SCRIPT_DIR/led-bridge.jar"

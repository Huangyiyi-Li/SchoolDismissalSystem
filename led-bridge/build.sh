#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

JAVA_HOME_VALUE=${JAVA_HOME:-}
if [ -z "$JAVA_HOME_VALUE" ]; then
    JAVA_HOME_VALUE=$(/usr/libexec/java_home 2>/dev/null || true)
fi
if [ -z "$JAVA_HOME_VALUE" ]; then
    echo "JAVA_HOME is not set and no local JDK was found." >&2
    exit 1
fi

JAVA_HOME="$JAVA_HOME_VALUE" python3 "$PROJECT_ROOT/tools/build_led_bridge.py"

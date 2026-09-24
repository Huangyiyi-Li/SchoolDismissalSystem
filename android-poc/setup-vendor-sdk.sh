#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE="${1:-$HOME/Downloads/BX_05_06_SDK_20241105/JAVA/Android/Android_Ethernet/bx.dual.android/app/libs}"
TARGET="$SCRIPT_DIR/app/libs"

if [[ ! -d "$SOURCE" ]]; then
    echo "找不到仰邦 Android SDK：$SOURCE" >&2
    exit 1
fi

mkdir -p "$TARGET"
for file in \
    bx05-0.5.0-SNAPSHOT.jar \
    bx05.message-0.5.0-SNAPSHOT.jar \
    bx06-0.6.0-SNAPSHOT.jar \
    bx06.message-0.6.0-SNAPSHOT.jar \
    log4j-1.2.14.jar \
    simple-xml-2.7.1.jar \
    uia-comm-0.3.3.jar \
    uia-utils-0.2.0.jar \
    uia-message-0.6.0.jar \
    java.awt4a-0.1-release.aar; do
    if [[ ! -f "$SOURCE/$file" ]]; then
        echo "开发包缺少 $file" >&2
        exit 1
    fi
    cp "$SOURCE/$file" "$TARGET/$file"
done
echo "已从本机仰邦开发包载入 10 个依赖文件。"

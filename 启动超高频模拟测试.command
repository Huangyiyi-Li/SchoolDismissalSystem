#!/bin/zsh
cd "$(dirname "$0")"
if [[ -x /tmp/dismissal-uhf-venv/bin/python ]]; then
    exec /tmp/dismissal-uhf-venv/bin/python tools/uhf_demo.py
elif [[ -x .venv/bin/python ]]; then
    exec .venv/bin/python tools/uhf_demo.py
else
    python3 tools/uhf_demo.py
    read '?按回车退出'
fi

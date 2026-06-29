#!/bin/bash
# macOS double-click wrapper — runs start-spad.sh (the real launcher).
exec "$(dirname "$0")/start-spad.sh"

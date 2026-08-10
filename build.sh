#!/bin/sh
# Package src/ into an importable Alfred workflow.
#
#   ./build.sh
#
# Produces dist/Claude Code Paste Cleaner.alfredworkflow — double-click to install.
# The plist is regenerated from tools/make_plist.py so a hand-edit that drifted from
# the generator can never ship silently. The icon is not regenerated (it needs a Swift
# compile); run tools/make_icon.swift by hand if you change it.

set -eu

ROOT=$(cd "$(dirname "$0")" && pwd)
NAME="Claude Code Paste Cleaner"
OUT="$ROOT/dist/$NAME.alfredworkflow"

python3 "$ROOT/tools/make_plist.py"
plutil -lint "$ROOT/src/info.plist" >/dev/null

mkdir -p "$ROOT/dist"
rm -f "$OUT"

# Zip from inside src/ so info.plist lands at the archive root; Alfred rejects
# workflows whose plist sits one directory down.
cd "$ROOT/src"
zip -q -r -X "$OUT" . -x '.*' '*/.*' '*.pyc' '__pycache__/*'

if ! unzip -l "$OUT" | grep -q ' info.plist$'; then
  echo "build failed: info.plist is not at the archive root" >&2
  exit 1
fi

echo "wrote dist/$NAME.alfredworkflow"
unzip -l "$OUT" | tail -n +4 | sed '$d' | sed '$d'

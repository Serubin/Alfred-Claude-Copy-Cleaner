#!/bin/sh
# Build a versioned, checksummed .alfredworkflow for CI snapshots and releases.
# usage: tools/package.sh <version>   (prints the asset path last)

set -eu

if [ $# -ne 1 ] || [ -z "$1" ]; then
  echo "usage: $0 <version>" >&2
  exit 2
fi

VERSION=$1
ROOT=$(cd "$(dirname "$0")/.." && pwd)
BUILT="$ROOT/dist/Claude Code Paste Cleaner.alfredworkflow"
# GitHub turns spaces in asset names into dots; name it explicitly instead.
NAME="Claude-Code-Paste-Cleaner-$VERSION.alfredworkflow"

# build.sh writes $VERSION into the tracked src/info.plist; put the committed one back.
trap 'env -u WORKFLOW_VERSION python3 "$ROOT/tools/make_plist.py" >/dev/null' EXIT
WORKFLOW_VERSION="$VERSION" "$ROOT/build.sh" >&2

# Alfred's workflow list shows the plist version, so it must match what we ship.
embedded=$(unzip -p "$BUILT" info.plist \
  | python3 -c 'import plistlib,sys; print(plistlib.loads(sys.stdin.buffer.read())["version"])')
if [ "$embedded" != "$VERSION" ]; then
  echo "package failed: built workflow reports version $embedded, expected $VERSION" >&2
  exit 1
fi

mv "$BUILT" "$ROOT/dist/$NAME"
(cd "$ROOT/dist" && shasum -a 256 "$NAME" > "$NAME.sha256")

cat "$ROOT/dist/$NAME.sha256" >&2
echo "dist/$NAME"

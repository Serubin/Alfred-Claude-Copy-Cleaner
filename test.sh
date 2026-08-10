#!/bin/sh
# Run everything: rule unit tests, packaged-workflow integration tests, and the
# differential test against the original JavaScript implementation.
#
#   ./test.sh
#
# Needs only Python 3. Re-verifying against the live reference implementation
# additionally needs node — see the README.

set -eu

ROOT=$(cd "$(dirname "$0")" && pwd)

# The tests import the cleaner from src/, which is the directory that gets packaged.
# Keep interpreter caches from being written into it.
PYTHONDONTWRITEBYTECODE=1
export PYTHONDONTWRITEBYTECODE

echo "== unit tests =="
python3 "$ROOT/tests/test_clean.py"

echo
echo "== workflow integration tests =="
python3 "$ROOT/tests/test_workflow.py"

echo
echo "== behaviour matches the original tool =="
# Golden mode by default: compares against captured reference outputs, so this needs
# nothing but Python. To re-verify against the real implementation, generate it
# locally (see the README) and run:
#   python3 tests/differential.py --mode oracle
python3 "$ROOT/tests/differential.py"

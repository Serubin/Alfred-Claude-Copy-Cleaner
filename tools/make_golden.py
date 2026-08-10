#!/usr/bin/env python3
"""Regenerate tests/golden/ from the reference implementation.

The reference implementation is third-party code and is never committed (see the
README). This captures what it produces for our own fixtures and fuzz corpus, so the
committed test suite can verify the port without redistributing anything.

Needs a local tests/reference.mjs:

  node tools/extract_reference.mjs <chunk.js|url>
  python3 tools/make_golden.py
"""

import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from differential import (  # noqa: E402
    DEFAULT_CASES,
    DEFAULT_SEED,
    FIXTURES,
    GOLDEN,
    JS_REFERENCE,
    fuzz_cases,
    read_fixture,
    run_js_batch,
)


def main():
    if not JS_REFERENCE.exists():
        print(
            f"missing {JS_REFERENCE.relative_to(ROOT)} — generate it first with:\n"
            "  node tools/extract_reference.mjs <chunk.js|url>",
            file=sys.stderr,
        )
        return 2

    GOLDEN.mkdir(exist_ok=True)
    for stale in GOLDEN.glob("*.expected"):
        stale.unlink()

    fixtures = sorted(FIXTURES.glob("*.txt"))
    outputs = run_js_batch([read_fixture(p) for p in fixtures])
    for path, expected in zip(fixtures, outputs):
        target = GOLDEN / f"{path.stem}.expected"
        with open(target, "w", encoding="utf-8", newline="") as f:
            f.write(expected)
    print(f"wrote {len(fixtures)} fixture goldens")

    # The fuzz corpus is thousands of cases; committing every expected output would
    # bloat the repo for little review value, so it is pinned by digest instead. A
    # mismatch says "run --mode oracle locally" to see the actual diff.
    cases = fuzz_cases(DEFAULT_SEED, DEFAULT_CASES)
    digest = hashlib.sha256(
        "\x00".join(run_js_batch(cases)).encode("utf-8")
    ).hexdigest()
    manifest = {
        "seed": DEFAULT_SEED,
        "cases": DEFAULT_CASES,
        "sha256": digest,
        "note": "sha256 of the reference implementation's outputs, NUL-joined. "
        "Regenerate with tools/make_golden.py.",
    }
    with open(GOLDEN / "fuzz.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    print(f"wrote fuzz manifest ({DEFAULT_CASES} cases, sha256 {digest[:12]}…)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Verify the cleaner reproduces the behaviour of the tool it was ported from.

src/clean_claude_text.py matches the plain-text behaviour of the cleaner behind
trevorfox.com's Claude Code Paste Cleaner. This makes that a checked claim rather than
an assertion: fixtures and a seeded fuzz corpus go through both, and the results must
be identical.

Two modes, because the reference implementation is third-party code that this repo
does not redistribute (see the README):

  golden (default)  Compare against tests/golden/, captured from the reference. Pure
                    Python, no node, no reference needed. This is what CI and anyone
                    cloning the repo runs.
  oracle            Compare against a locally generated tests/reference.mjs, and
                    re-verify the goldens against it so they cannot drift.

  python3 tests/differential.py                  # golden mode
  python3 tests/differential.py --mode oracle    # needs tests/reference.mjs
  python3 tests/differential.py --cases N        # different amount of fuzzing

Rules listed in LOCAL_RULES are deliberate departures from the original and are
disabled here; their behaviour is pinned in tests/test_clean.py instead.
"""

import argparse
import hashlib
import json
import pathlib
import random
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from clean_claude_text import LOCAL_RULES, clean  # noqa: E402

JS_REFERENCE = ROOT / "tests" / "reference.mjs"
FIXTURES = ROOT / "tests" / "fixtures"
GOLDEN = ROOT / "tests" / "golden"

DEFAULT_SEED = 1729
DEFAULT_CASES = 2000

# Vocabulary of Claude Code terminal artifacts. The fuzzer shuffles these into
# transcripts to hit rule interactions the curated fixtures miss — a glyph inside a
# fence, a gutter line next to wrappable prose, a box edge around a tool result.
LINE_POOL = [
    "⏺ The nightly job stalled because the advisory lock was never released",
    "  and the next runner sat waiting on the same partition all night.",
    "⏺ Read(db/seeds/accounts.rb)",
    "⏺ Bash(bundle exec rspec --seed 1234)",
    "  ⎿  Read 128 lines (ctrl+o to expand)",
    "  ⎿  Interrupted by user",
    "✻ Ruminating… (esc to interrupt · 4.1k tokens)",
    "· Simmering… (esc to interrupt)",
    "? for shortcuts",
    "❯ 1. Yes, proceed",
    "shift+tab to cycle modes",
    "╭────────────────────────────╮",
    "│ > sort the seed data       │",
    "╰────────────────────────────╯",
    "┃ Plan mode is on            ┃",
    "☐ Reproduce with a fixed seed",
    "☒ Sort the seed data",
    "◐ Running the suite",
    "▎ Worth remembering: order-dependent tests are wrong, not flaky.",
    "▎",
    "  ▎",
    "   52→  ACCOUNTS.each do |slug, attrs|",
    "   53→    Account.create!(slug: slug)",
    "  17 +    next if Account.exists?(slug: slug)",
    "  18 -    Account.create!(slug: slug)",
    '  3\trequire "active_record"',
    "```ruby",
    "ACCOUNTS.sort.each { |slug, attrs| seed(slug, attrs) }",
    "```",
    "- Sort the seed data so the assertions stop depending on hash order",
    "1. Make it deterministic",
    "  a. Sort the seed data by slug",
    "    i. Update the two account assertions",
    "> A quoted aside about the failure mode and why it matters here.",
    "## What Is Going On",
    "Short line.",
    "This line is exactly long enough to be a candidate for rejoining",
    "A line long enough to be a rejoin candidate that ends in a full stop.",
    "considering following simplified technical english",
    "continuation text that follows a long line and should be merged in",
    "He said “the ordering is wrong” and he’s right about the ‘seed’ step",
    "🚀🚀🚀🚀 emoji push this past forty utf-16 units but not code points",
    "任务失败了，因为夜间作业锁住了同一个分区",
    "  trailing spaces here   ",
    "text with\u200bzero\u200cwidth\u2060joiners",
    "non\u00a0breaking\u2009spaces\u3000inline",
    "\x1b[1m\x1b[32mbold green text\x1b[0m after the codes",
    "\x1b]8;;https://example.com\x07a hyperlink\x1b]8;;\x07 in a sentence",
    "\x1b]0;window title\x07",
    "",
    "   ",
]


def read_fixture(path):
    # newline="" is essential: the default universal-newline translation rewrites \r
    # to \n on read, which would quietly neutralise every CR-related fixture.
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def fuzz_cases(seed, count):
    """Deterministic corpus — the same seed must always yield the same cases."""
    rng = random.Random(seed)
    cases = []
    for _ in range(count):
        text = "\n".join(rng.choice(LINE_POOL) for _ in range(rng.randint(1, 14)))
        if rng.random() < 0.15:
            text += "\n"
        if rng.random() < 0.10:
            text = text.replace("\n", "\r\n")
        cases.append(text)
    return cases


def run_js_batch(cases):
    """Clean every case with the reference implementation in one node process."""
    proc = subprocess.run(
        ["node", str(JS_REFERENCE), "plain", "--batch"],
        input="\x00".join(cases).encode("utf-8"),
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"reference implementation failed: {proc.stderr.decode()}")
    results = proc.stdout.decode("utf-8").split("\x00")
    if len(results) != len(cases):
        raise RuntimeError(
            f"reference returned {len(results)} results for {len(cases)} cases "
            "— a case probably contained a NUL byte"
        )
    return results


def port(text):
    out, _stats = clean(text, disabled=LOCAL_RULES)
    return out


def visible(text):
    return text.replace("\x1b", "\\e").replace("\t", "\\t").replace("\r", "\\r")


def report(name, source, expected, actual):
    print(f"\nMISMATCH: {name}")
    print(f"--- input ---\n{visible(source)}")
    print(f"--- expected (reference) ---\n{visible(expected)}")
    print(f"--- actual (this port) ---\n{visible(actual)}")


def check_fixtures(expected_for):
    """Compare the port against `expected_for(name, source)` for every fixture."""
    failures = []
    paths = sorted(FIXTURES.glob("*.txt"))
    for path in paths:
        source = read_fixture(path)
        want = expected_for(path)
        if want is None:
            print(f"MISSING GOLDEN: {path.name} — run tools/make_golden.py")
            failures.append(path.name)
            continue
        got = port(source)
        if got != want:
            failures.append(path.name)
            if len(failures) <= 5:
                report(f"fixture {path.name}", source, want, got)
    print(f"fixtures: {len(paths) - len(failures)}/{len(paths)} identical")
    return failures


def golden_mode(seed, count):
    if not GOLDEN.exists():
        print(f"missing {GOLDEN.relative_to(ROOT)} — run tools/make_golden.py", file=sys.stderr)
        return 2

    def expected_for(path):
        target = GOLDEN / f"{path.stem}.expected"
        return read_fixture(target) if target.exists() else None

    failures = check_fixtures(expected_for)

    manifest_path = GOLDEN / "fuzz.json"
    if not manifest_path.exists():
        print("missing tests/golden/fuzz.json — run tools/make_golden.py", file=sys.stderr)
        return 2
    manifest = json.loads(manifest_path.read_text())

    if (seed, count) != (manifest["seed"], manifest["cases"]):
        print(
            f"fuzz:     skipped — manifest pins seed {manifest['seed']}/"
            f"{manifest['cases']} cases, asked for {seed}/{count}. "
            "Use --mode oracle for ad-hoc fuzzing."
        )
    else:
        cases = fuzz_cases(seed, count)
        digest = hashlib.sha256("\x00".join(port(c) for c in cases).encode("utf-8")).hexdigest()
        if digest == manifest["sha256"]:
            print(f"fuzz:     {count}/{count} identical (sha256 {digest[:12]}…)")
        else:
            print(
                f"fuzz:     DIGEST MISMATCH over {count} cases\n"
                f"          expected {manifest['sha256']}\n"
                f"          actual   {digest}\n"
                "          Run --mode oracle locally to see the failing case."
            )
            failures.append("fuzz corpus")
    return 1 if failures else 0


def oracle_mode(seed, count):
    if not JS_REFERENCE.exists():
        print(
            f"missing {JS_REFERENCE.relative_to(ROOT)} — this repo does not ship the\n"
            "reference implementation. Generate it locally:\n"
            "  node tools/extract_reference.mjs <chunk.js|url>",
            file=sys.stderr,
        )
        return 2

    paths = sorted(FIXTURES.glob("*.txt"))
    live = dict(zip(paths, run_js_batch([read_fixture(p) for p in paths])))
    failures = check_fixtures(lambda path: live[path])

    # Goldens must still agree with the real thing, or they are worthless.
    drifted = []
    for path in paths:
        target = GOLDEN / f"{path.stem}.expected"
        if not target.exists() or read_fixture(target) != live[path]:
            drifted.append(path.name)
    if drifted:
        print(f"golden drift: {', '.join(drifted)} — run tools/make_golden.py")
        failures.extend(drifted)
    else:
        print(f"goldens:  {len(paths)}/{len(paths)} match the reference")

    cases = fuzz_cases(seed, count)
    expected = run_js_batch(cases)
    fuzz_failures = 0
    for i, (source, want) in enumerate(zip(cases, expected)):
        got = port(source)
        if got != want:
            fuzz_failures += 1
            if fuzz_failures <= 5:
                report(f"random case {i} (seed {seed})", source, want, got)
    print(f"fuzz:     {count - fuzz_failures}/{count} identical")
    if fuzz_failures:
        failures.append("fuzz corpus")
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--mode", choices=("golden", "oracle"), default="golden")
    parser.add_argument("--cases", type=int, default=DEFAULT_CASES)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    print(f"mode: {args.mode}")
    result = (golden_mode if args.mode == "golden" else oracle_mode)(args.seed, args.cases)

    if result == 0:
        source = "captured reference outputs" if args.mode == "golden" else "the reference implementation"
        print(f"\nPASS: this port is byte-identical to {source}")
    elif result == 1:
        print("\nFAILED")
    return result


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Strip terminal rendering artifacts from text copied out of the Claude Code TUI.

This is a plain-text-mode port of the cleaner behind
https://trevorfox.com/tools/developer/claude-code-paste-cleaner — same rules, same
order, same regexes. tests/differential.py diffs this against the original JS
implementation (tests/reference.mjs) byte-for-byte.

Reads stdin, writes the cleaned text to stdout. Rules can be turned off either with
--disable, or by setting an environment variable per rule (cc_<rule_id>=0), which is
how the Alfred workflow's user configuration reaches this script.
"""

import argparse
import os
import re
import subprocess
import sys

# --- JavaScript semantics -------------------------------------------------------
#
# The rules below are transcribed from JS regex literals, and \s, \w, \d, `.` and $
# do not mean the same thing in the two languages. Getting this wrong produces
# artifacts that survive cleaning only on unusual input, so the differences are
# spelled out once here and every ported pattern is built from these pieces:
#
#   \s  JS has ﻿ and lacks \x1c-\x1f and \x85; Python is the reverse.
#   \w  ASCII in JS, Unicode-aware in Python.
#   \d  [0-9] in JS, Unicode-aware in Python.
#   .   excludes \r and U+2028/9 in JS; Python's excludes \n only.
#   $   end-of-string in JS; in Python it also matches before a trailing newline.
#
WS = "\t\n\x0b\f\r    -     　﻿"
WS_CHARS = frozenset(
    "\t\n\x0b\f\r       　﻿"
) | frozenset(chr(c) for c in range(0x2000, 0x200B))

S = f"[{WS}]"  # \s
NS = f"[^{WS}]"  # \S
DOT = r"[^\n\r  ]"  # .
ESC = "\x1b"


def js_len(s):
    """len() in UTF-16 code units, as JavaScript's String.length counts it."""
    return len(s) + sum(1 for ch in s if ord(ch) > 0xFFFF)


def js_trim(s):
    return s.strip("".join(WS_CHARS))


def js_trim_start(s):
    return s.lstrip("".join(WS_CHARS))


def js_trim_end(s):
    return s.rstrip("".join(WS_CHARS))


# --- Patterns -------------------------------------------------------------------

OSC8 = re.compile(
    ESC + r"\]8;;([^\x07\x1b]*)(?:\x07|" + ESC + r"\\)"
    r"((?s:.*?))" + ESC + r"\]8;;(?:\x07|" + ESC + r"\\)"
)
OSC_ANY = re.compile(ESC + r"\][^\x07\x1b]*(?:\x07|" + ESC + r"\\)")
CSI = re.compile(ESC + r"\[[0-?]*[ -/]*[@-~]")

CHROME = [
    re.compile(rf"^{S}*[·✢✳✶✻✽*]{S}+{NS}{DOT}*…"),
    re.compile(r"\(esc to interrupt", re.I),
    re.compile(r"\(ctrl\+[A-Za-z0-9_]+( again)? to (expand|edit|view|see|toggle)", re.I),
    re.compile(rf"^{S}*⎿{S}*Interrupted"),
    re.compile(rf"^{S}*\? for shortcuts"),
    re.compile(rf"^{S}*❯"),
    re.compile(rf"^{S}*[·✢✳✶✻✽]{S}*\Z"),
    re.compile(rf"^{S}*✻ Welcome to Claude Code"),
    re.compile(r"shift\+tab to cycle", re.I),
]

TOOL_CALL = re.compile(
    rf"^{S}*[⏺●]{S}+[A-Za-z][A-Za-z0-9_.:-]*\([^)]*\){S}*…?{S}*\Z"
)

BULLET_PREFIX = re.compile(rf"^({S}*)[⏺●∙]{S}+")
RESULT_PREFIX = re.compile(rf"^({S}*)⎿{S}{{0,2}}")

BOX_CHARS = "╭╮╰╯│┃─━┄┅┆┇┈┉┊┋┌┐└┘├┤┬┴┼═║╔╗╚╝╠╣╦╩╬"
BOX_ONLY = re.compile(rf"^[{WS}{BOX_CHARS}]+\Z")
BOX_ANY = re.compile(rf"[{BOX_CHARS}]")
BOX_LEFT = re.compile(rf"^({S}*)[│┃] ?")
BOX_RIGHT = re.compile(rf" ?[│┃]{S}*\Z")

GLYPH_STRIP = re.compile(rf"^({S}*)[☐☒◇◆○◐◉↑↓←→↻↯⑂⚑※▶⏸▎✽✻✶✳✢]{S}+")
GLYPH_ONLY = re.compile(rf"^{S}*[☐☒◇◆○◐◉↑↓←→↻↯⑂⚑※▶⏸]{S}*\Z")

# A blockquote bar with nothing after it: the blank line *inside* a quoted block.
# GLYPH_STRIP needs whitespace after the bar so it never matches these, and ▎ is
# absent from GLYPH_ONLY, so upstream leaves them behind as stray "▎" lines.
BARE_QUOTE_BAR = re.compile(rf"^{S}*▎{S}*\Z")

GUTTER_ARROW = re.compile(rf"^({S}*)[0-9]+→")
GUTTER_TAB = re.compile(rf"^({S}*)[0-9]+\t")
GUTTER_DIFF = re.compile(rf"^({S}*)[0-9]+{S}*([+-]){S}{{2,}}")

UNICODE_SPACE = re.compile("[   -   　]")
ZERO_WIDTH = re.compile("[​‌‍⁠﻿]")

SENTENCE_END = re.compile(r"[.!?:;…]\Z")
LIST_START = re.compile(
    rf"^([-*+•]{S}|[0-9]+[.)]{S}|[A-Za-z][.)]{S}|[ivxlcdmIVXLCDM]+[.)]{S}"
    r"|[>#|]|```|▎|⏺|●|☐|☒)"
)
FENCE = re.compile(rf"^{S}*(```|~~~)")

LEADING_SPACES = re.compile("^ *")
TRAILING_BLANKS = re.compile(r"[ \t]+\Z")

# Rules in application order. Order is load-bearing: gutter stripping must run before
# reflow (gutter lines suppress re-joining), and reflow before smart quotes.
RULES = [
    ("ansi-escapes", "Escape sequences and terminal hyperlinks"),
    ("chrome-lines", "Interface noise and hint lines"),
    ("tool-calls", "Tool invocation headers"),
    ("message-prefixes", "Reply bullets and result markers"),
    ("box-drawing", "Frames and borders"),
    ("glyphs", "Indicator symbols"),
    ("blockquote-bars", "Empty quote bars"),
    ("line-gutters", "Leading line numbers"),
    ("reflow", "Terminal hard wrapping"),
    ("unicode-whitespace", "Exotic and invisible spaces"),
    ("smart-quotes", "Curly quotes to ASCII"),
    ("trailing-blanklines", "Line-end space and blank runs"),
]
RULE_IDS = [r[0] for r in RULES]

# Rules that are ours, not the upstream tool's. The differential test disables these
# so the shared core stays verifiably byte-identical to the reference implementation.
LOCAL_RULES = frozenset({"blockquote-bars"})

# Prose shorter than this is assumed to be a deliberate line break, not a terminal
# hard wrap, so it is never re-joined.
REFLOW_MIN_LEN = 40


class Line:
    __slots__ = ("text", "gutter")

    def __init__(self, text):
        self.text = text
        self.gutter = False


def clean(text, disabled=()):
    """Return (cleaned_text, stats) where stats maps rule id -> times applied."""
    on = {rid for rid in RULE_IDS if rid not in disabled}
    stats = {}

    def hit(rule, n=1):
        stats[rule] = stats.get(rule, 0) + n

    out = text

    if "ansi-escapes" in on:
        def unlink(m):
            hit("ansi-escapes")
            return m.group(2)

        def drop(m):
            hit("ansi-escapes")
            return ""

        out = OSC8.sub(unlink, out)
        out = OSC_ANY.sub(drop, out)
        out = CSI.sub(drop, out)

    lines = [Line(t) for t in out.split("\n")]

    if "chrome-lines" in on:
        kept = []
        for line in lines:
            if js_trim(line.text) and any(p.search(line.text) for p in CHROME):
                hit("chrome-lines")
                continue
            kept.append(line)
        lines = kept

    if "tool-calls" in on:
        kept = []
        for line in lines:
            if TOOL_CALL.search(line.text):
                hit("tool-calls")
                continue
            kept.append(line)
        lines = kept

    if "message-prefixes" in on:
        for line in lines:
            # Note: the marker's own indent goes with it, matching the original.
            if BULLET_PREFIX.search(line.text):
                line.text = BULLET_PREFIX.sub("", line.text, count=1)
                hit("message-prefixes")
            elif RESULT_PREFIX.search(line.text):
                line.text = RESULT_PREFIX.sub("", line.text, count=1)
                hit("message-prefixes")

    if "box-drawing" in on:
        kept = []
        for line in lines:
            if (
                js_trim(line.text)
                and BOX_ONLY.search(line.text)
                and BOX_ANY.search(line.text)
            ):
                hit("box-drawing")
                continue
            kept.append(line)
        lines = kept
        for line in lines:
            before = line.text
            line.text = BOX_LEFT.sub(r"\1", line.text, count=1)
            line.text = BOX_RIGHT.sub("", line.text, count=1)
            if line.text != before:
                hit("box-drawing")

    if "glyphs" in on:
        kept = []
        for line in lines:
            if GLYPH_ONLY.search(line.text):
                hit("glyphs")
                continue
            kept.append(line)
        lines = kept
        for line in lines:
            if GLYPH_STRIP.search(line.text):
                line.text = GLYPH_STRIP.sub(r"\1", line.text, count=1)
                hit("glyphs")

    if "blockquote-bars" in on:
        for line in lines:
            if BARE_QUOTE_BAR.search(line.text):
                # Blanked, not deleted: this line is a paragraph break inside a quote,
                # and deleting it would let reflow run the paragraphs together.
                line.text = ""
                hit("blockquote-bars")

    if "line-gutters" in on:
        for line in lines:
            for pattern in (GUTTER_ARROW, GUTTER_TAB, GUTTER_DIFF):
                if pattern.search(line.text):
                    line.text = pattern.sub("", line.text, count=1)
                    line.gutter = True
                    hit("line-gutters")
                    break

    if "unicode-whitespace" in on:
        for line in lines:
            before = line.text
            line.text = ZERO_WIDTH.sub("", UNICODE_SPACE.sub(" ", line.text))
            if line.text != before:
                hit("unicode-whitespace")

    # Fence tracking: the delimiter lines themselves count as fenced, so a code block's
    # contents are never reflowed.
    fenced = [False] * len(lines)
    inside = False
    for i, line in enumerate(lines):
        if FENCE.search(line.text):
            fenced[i] = True
            inside = not inside
        else:
            fenced[i] = inside

    if "reflow" in on:
        result = []
        group = []
        skip = False

        def flush():
            nonlocal group, skip
            if not group:
                return
            if skip:
                result.extend(group)
            else:
                indents = [
                    len(LEADING_SPACES.match(ln.text).group(0))
                    for ln in group
                    if js_trim(ln.text)
                ]
                dedent = min(indents) if indents else 0
                if dedent > 0:
                    for ln in group:
                        ln.text = ln.text[dedent:]
                    hit("reflow")
                merged = [group[0]]
                for ln in group[1:]:
                    prev = merged[-1]
                    nxt = js_trim_start(ln.text)
                    head = js_trim_end(prev.text)
                    if (
                        js_len(head) < REFLOW_MIN_LEN
                        or SENTENCE_END.search(head)
                        or not nxt
                        or LIST_START.search(nxt)
                    ):
                        merged.append(ln)
                    else:
                        prev.text = f"{head} {nxt}"
                        hit("reflow")
                result.extend(merged)
            group = []
            skip = False

        for i, line in enumerate(lines):
            if not js_trim(line.text):
                flush()
                result.append(line)
                continue
            if line.gutter or fenced[i]:
                skip = True
            group.append(line)
        flush()
        lines = result

    if "smart-quotes" in on:
        for line in lines:
            before = line.text
            line.text = line.text.replace("“", '"').replace("”", '"')
            line.text = line.text.replace("‘", "'").replace("’", "'")
            if line.text != before:
                hit("smart-quotes")

    out = "\n".join(line.text for line in lines)

    if "trailing-blanklines" in on:
        stripped = []
        for text in out.split("\n"):
            trimmed = TRAILING_BLANKS.sub("", text, count=1)
            if trimmed != text:
                hit("trailing-blanklines")
            stripped.append(trimmed)
        out = "\n".join(stripped)

        def collapse(m):
            hit("trailing-blanklines")
            return "\n\n"

        out = re.sub(r"\n{3,}", collapse, out)
        out = re.sub(r"\A\n+", "", out)
        out = re.sub(r"\n+\Z", "", out)

    return out, stats


def disabled_from_env(env):
    """Rules switched off via cc_<rule_id> variables, as set by Alfred's workflow config."""
    off = set()
    for rule in RULE_IDS:
        value = env.get("cc_" + rule.replace("-", "_"))
        if value is not None and value.strip().lower() in ("0", "", "false", "no", "off"):
            off.add(rule)
    return off


def human_bytes(n):
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--text", help="clean this string instead of reading stdin")
    parser.add_argument(
        "--disable",
        default="",
        help="comma-separated rule ids to skip (see --list-rules)",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="put the cleaned text on the clipboard instead of writing it to stdout",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="write a one-line summary of what changed to stdout (implies --copy "
        "for the text itself); suppressed when cc_notify is off",
    )
    parser.add_argument(
        "--list-rules", action="store_true", help="print the rule ids and exit"
    )
    args = parser.parse_args(argv)

    if args.list_rules:
        for rid, label in RULES:
            print(f"{rid:22} {label}")
        return 0

    if args.text is not None:
        text = args.text
    else:
        text = sys.stdin.buffer.read().decode("utf-8", errors="replace")

    disabled = disabled_from_env(os.environ)
    disabled |= {r.strip() for r in args.disable.split(",") if r.strip()}
    unknown = disabled - set(RULE_IDS)
    if unknown:
        parser.error(f"unknown rule id(s): {', '.join(sorted(unknown))}")

    out, _stats = clean(text, disabled)

    # Refuse to overwrite the clipboard with nothing. The hotkey path cleans the
    # clipboard in place, so an empty result would silently destroy what was copied.
    empty = not out.strip()
    if (args.copy or args.stats) and not empty:
        # CC_PBCOPY exists so the tests can verify the copy path against a stub
        # instead of clobbering the real clipboard.
        pbcopy = os.environ.get("CC_PBCOPY") or "/usr/bin/pbcopy"
        subprocess.run([pbcopy], input=out.encode("utf-8"), check=True)

    if args.stats:
        # Only the summary goes to stdout, never the text: Alfred expands
        # {placeholders} in notification text and cleaned output routinely contains
        # braces (JSON, code, template literals). Printing nothing suppresses the
        # notification, since it is set to fire only on a populated query.
        if os.environ.get("cc_notify", "1").strip().lower() in ("0", "", "false", "no", "off"):
            return 0
        if empty:
            sys.stdout.write("Nothing to clean — clipboard left untouched")
            return 0
        before_lines = len(text.split("\n")) if text else 0
        after_lines = len(out.split("\n")) if out else 0
        removed = max(0, len(text.encode("utf-8")) - len(out.encode("utf-8")))
        sys.stdout.write(
            f"Cleaned {before_lines} → {after_lines} lines, {human_bytes(removed)} removed"
        )
        return 0

    if not args.copy:
        sys.stdout.buffer.write(out.encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

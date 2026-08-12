# Claude Code Paste Cleaner — Alfred workflow

Strips terminal rendering artifacts from text copied out of the Claude Code TUI, so it
can go straight into a ticket, a chat message, or a commit body.

```
⏺ Read(db/seeds/accounts.rb)                 The seed file inserts accounts in
  ⎿  Read 88 lines (ctrl+o to expand)        whatever order the hash happens to
                                       →     iterate, and the test asserts on the
✻ Ruminating… (esc to interrupt)             first row it reads back.
⏺ The seed file inserts accounts in
  whatever order the hash happens to
  iterate, and the test asserts on the
  first row it reads back.
```

It reproduces the plain-text behaviour of the cleaner behind
[trevorfox.com/tools/developer/claude-code-paste-cleaner][tool], the web tool that
worked this problem out first — same rule set, same ordering, verified against it (see
[Relationship to the original tool](#relationship-to-the-original-tool)).

[tool]: https://trevorfox.com/tools/developer/claude-code-paste-cleaner/

## Install

Download the `.alfredworkflow` from the [latest release][releases] and double-click it.

[releases]: https://github.com/Serubin/Alfred-Claude-Copy-Cleaner/releases/latest

Or build it yourself:

```sh
./build.sh
open "dist/Claude Code Paste Cleaner.alfredworkflow"
```

Either way, open the workflow in Alfred afterwards and **assign a hotkey** — exported
workflows never carry one, so the Hotkey trigger arrives unbound.

## Use

- **Hotkey** — cleans whatever is on the clipboard and puts the result back, so the
  next ⌘V pastes clean text. Nothing is auto-pasted. If the clipboard is empty, or
  cleaning would leave nothing, the clipboard is left untouched.
- **Universal Action** — select text anywhere, invoke Universal Actions, choose
  *Clean Claude Code Text*. The cleaned text goes to the clipboard.

A notification reports what changed (`Cleaned 42 → 31 lines, 1.4 KB removed`).

## What it removes

| Rule | Removes |
| --- | --- |
| `ansi-escapes` | Colour/cursor codes and OSC 8 hyperlink wrappers (the link text is kept) |
| `chrome-lines` | `(esc to interrupt)`, `+47 lines (ctrl+o to expand)`, `? for shortcuts`, spinner lines, the welcome banner |
| `prompt-lines` † | The `❯` prompt marker, **keeping what you typed**; empty prompts and `❯ 1. Yes, proceed` menu rows still go |
| `tool-calls` | `⏺ Read(file.ts)` / `⏺ Bash(npm test)` headers |
| `message-prefixes` | Leading `⏺` `●` `∙` bullets and `⎿` tool-result markers |
| `box-drawing` | `╭─╮ │ ╰─╯` frames around the prompt box, dialogs, banners |
| `glyphs` | `☐ ☒ ◇ ◆ ○ ◐ ◉ ▎ ✻` and other status indicators |
| `blockquote-bars` † | Bare `▎` bars — the blank lines inside a quoted block — become real blank lines |
| `line-gutters` | `123→` file-read gutters, `cat -n` numbering, `41 -` / `42 +` diff gutters |
| `reflow` | Terminal hard-wrapping — re-joins wrapped prose, leaving lists, quotes and fenced code alone |
| `unicode-whitespace` | Non-breaking and exotic spaces → plain spaces; zero-width characters deleted |
| `smart-quotes` | `“ ” ‘ ’` → `" '` |
| `trailing-blanklines` | Trailing spaces; runs of 3+ blank lines collapsed to one |

Markdown reconstruction (rebuilding headings, blockquotes, nested lists, code fences)
is deliberately **not** included — this workflow only strips.

† **Local deviations from upstream**, both toggleable back off.

`blockquote-bars` — the upstream `glyphs` rule only strips `▎` when text follows it,
and bare bars are not in its drop-list, so a quoted block comes out with stray `▎`
lines between paragraphs. This rule blanks them. It blanks rather than deletes, because
the bar *is* the paragraph break — deleting the line would put two paragraphs on
adjacent lines and let `reflow` run them together. Set `cc_blockquote_bars=0` for
strict upstream behaviour.

`prompt-lines` — upstream treats every `❯` line as chrome and drops it whole. That is
right for an empty prompt or a selection menu, but the prompt line is also where your
typed text lives, so copying your own prompt silently loses its first line and leaves a
paragraph beginning mid-sentence. This rule triages instead: menus and empty prompts
still go, and anything else keeps its text. The marker is replaced with padding of the
same width rather than deleted, so the wrapped continuation lines stay aligned and
`reflow` dedents the block as a whole. Set `cc_prompt_lines=0` for strict upstream
behaviour.

## Configuration

In Alfred's workflow configuration:

- **Re-join wrapped lines** — turn off to preserve the original line breaks.
- **Straighten smart quotes** — turn off to keep curly quotes.
- **Show a notification** — turn off for a silent clean.

Every rule can be toggled by environment variable (`cc_<rule_id>=0`, e.g.
`cc_reflow=0`); the three above are just the ones surfaced in the UI.

## Command line

The cleaner is a standalone stdlib-only script — no Alfred required:

```sh
pbpaste | src/clean_claude_text.py            # cleaned text to stdout
src/clean_claude_text.py --text "⏺ hello"     # clean an argument
src/clean_claude_text.py --disable reflow     # skip a rule
src/clean_claude_text.py --list-rules
```

## Development

```sh
./test.sh                                  # unit + integration + behaviour check
./build.sh                                 # repackage dist/*.alfredworkflow
python3 tools/make_plist.py                # regenerate the workflow graph
swift tools/make_icon.swift                # regenerate the icon
```

`./test.sh` needs only Python 3 and macOS. Re-verifying against the live reference
implementation additionally needs node — see
[Relationship to the original tool](#relationship-to-the-original-tool).

`src/info.plist` is generated. Edit `tools/make_plist.py` rather than the plist, or
`build.sh` will overwrite your changes on the next build.

### Cutting a release

`.github/workflows/release.yml` builds and publishes on any `v*` tag:

```sh
# 1. bump VERSION in the same commit you intend to tag
echo 1.1.0 > VERSION && ./build.sh && ./test.sh
git commit -am "Release 1.1.0"

# 2. tag and push
git tag v1.1.0 && git push origin main --tags
```

The workflow refuses to publish if the tag and `VERSION` disagree — that check exists
so a release can't ship a workflow whose Alfred-visible version says something else.
The version reaches the plist through `WORKFLOW_VERSION`, which the release job sets
from the tag; local builds fall back to `VERSION`, so ordinary builds never churn
`src/info.plist`.

`workflow_dispatch` runs the same pipeline without publishing, uploading the built
workflow as a run artifact — useful for checking the pipeline itself.

CI runs on Linux, where the integration tests stub the macOS clipboard and run the
action body under Linux zsh. That verifies logic, not the real macOS surface, so
**run `./test.sh` on your Mac before tagging** — that is the authoritative check.

## Relationship to the original tool

Credit where it is due: [trevorfox.com's Claude Code Paste Cleaner][tool] worked out
which artifacts matter and how to strip them without wrecking lists and code blocks.
This workflow exists because that tool is a web page and I wanted it on a hotkey.

**No code from that site is redistributed here.** This repository contains an
independent Python implementation. Its cleaning routine ships in a lazy-loaded JS
chunk, and `tools/extract_reference.mjs` can carve that routine out into
`tests/reference.mjs` **on your machine**, where it acts as a test oracle.
`tests/reference.mjs` is gitignored and never committed.

So that the correctness claim survives without it, `tools/make_golden.py` captures what
the oracle produces for this repo's own fixtures into `tests/golden/`, and those
captured outputs are what ship. `tests/differential.py` has two modes:

```sh
python3 tests/differential.py                # golden: pure Python, what CI runs
python3 tests/differential.py --mode oracle  # live: needs a local tests/reference.mjs
```

Oracle mode additionally re-checks the goldens against the live implementation, so they
cannot drift unnoticed. The fuzz corpus is pinned by a SHA-256 over its outputs rather
than 2000 committed files.

Rules in `LOCAL_RULES` (marked † above) are deliberate departures and are disabled for
that comparison, so the shared behaviour stays verifiable while the additions are
pinned by `tests/test_clean.py`.

### Why the port is not a transliteration

JS and Python regex semantics differ in ways that only surface on unusual input. Each
difference is handled explicitly, with a fixture that fails if the handling is removed:

| Difference | Where it bites |
| --- | --- |
| `\s` — JS includes `U+FEFF`, Python includes `U+001C-1F` and `U+0085` | Chrome/box/glyph line matching |
| `.trim()` family trims the JS whitespace set, not `str.isspace()` | Reflow blank-line grouping |
| `.length` counts UTF-16 units | The 40-character reflow threshold, on emoji |
| `\w` is ASCII in JS | Tool-call header detection |
| `\d` is `[0-9]` in JS | Line-gutter detection |
| `.` excludes `\r` in JS | Spinner lines containing a bare CR |

## License

[MIT](LICENSE), covering the code in this repository.

## Layout

```
build.sh                    package src/ into dist/*.alfredworkflow
test.sh                     run every test suite
src/clean_claude_text.py    the cleaner (stdlib only — this is all the workflow runs)
src/info.plist              generated workflow graph
tools/                      plist, icon, oracle-extraction and golden generators
tests/fixtures/             input transcripts
tests/golden/               captured reference outputs the test suite checks against
tests/                      unit, integration and behaviour tests
```

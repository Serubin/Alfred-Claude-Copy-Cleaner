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
| `dock-divider` † | Everything right of the dock's `│` divider — the whole docked panel, whatever it is showing |
| `panel-bleed` † | Diff side-panel text (`No changes this session`, `3 files changed +12 -4`, …) glued to the end of a line |
| `tool-calls` | `⏺ Read(file.ts)` / `⏺ Bash(npm test)` headers |
| `message-prefixes` | Leading `⏺` `●` `∙` bullets and `⎿` tool-result markers |
| `box-drawing` | `╭─╮ │ ╰─╯` frames around the prompt box, dialogs, banners |
| `glyphs` | `☐ ☒ ◇ ◆ ○ ◐ ◉ ▎ ✻` and other status indicators |
| `blockquote-bars` † | Bare `▎` bars — the blank lines inside a quoted block — become real blank lines |
| `line-gutters` | `123→` file-read gutters, `cat -n` numbering, `41 -` / `42 +` diff gutters |
| `reflow` | Terminal hard-wrapping — re-joins wrapped prose, leaving lists, quotes and fenced code alone |
| `wrapped-sentences` † | Wraps that land after a full stop, when the next line is plainly mid-sentence or wore a `▎` bar |
| `unicode-whitespace` | Non-breaking and exotic spaces → plain spaces; zero-width characters deleted |
| `smart-quotes` | `“ ” ‘ ’` → `" '` |
| `trailing-blanklines` | Trailing spaces; runs of 3+ blank lines collapsed to one |

Markdown reconstruction (rebuilding headings, blockquotes, nested lists, code fences)
is deliberately **not** included — this workflow only strips.

† **Local deviations from upstream**, each toggleable back off.

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
still go, and anything else keeps its text. The marker is replaced by the two columns
it occupied rather than deleted, so the wrapped continuation lines stay aligned and
`reflow` dedents the block as a whole. A kept prompt also begins a new paragraph — it
is a change of speaker, so `reflow` never joins it to the line above, which upstream
got for free by deleting the line. The one thing it costs you: a prompt you typed
starting `1. ` or `2) ` reads as a menu row and goes with them. Set `cc_prompt_lines=0`
for strict upstream behaviour.

`dock-divider` — the TUI's dock is resizable, and the grip that resizes it is drawn as a
`│` running the dock's full height, on every row including blank ones. That column is the
boundary between the conversation and whatever panel is docked, so cutting each line at it
removes the panel wholesale — file rows, `────` separators, diff hunks and all — without
needing to recognise any of it:

```
     JOIN (                               │vulnerability/vuln-feeds-manager/FEEDS.md   +19
         SELECT MIN(ID) AS ID FROM rbs    │↓ 14 more below (opt+↓ to scroll)
```

The risk of a geometric rule is deleting real text, so a column has to clear five gates
before anything is cut. It must sit **at least 40 characters** from the left margin — the
grip divides a sidebar off the conversation, so it is never near the margin, while a
two-column table's separator and a `tree` trunk are. It must carry a bar on **at least
half** the non-blank lines and on **at least three** lines outright. No **corner or tee**
(`╭ ╰ ├ └ ┬ ┼` …) may sit at that column — a frame's column is closed and a `tree`
trunk's is teed, while the grip's is open. And **fewer than half** its lines may carry a
second bar, since a frame or table repeats bars across a row where the grip is a single
rule. Together these leave `tree` output, box-drawn dialogs and `│`-delimited tables
untouched, whether or not they have an outer border.

Fenced blocks are skipped outright. A mock-up pasted inside a code fence is quoted text
however table-shaped it looks, and the fence tracking further down this pipeline is
indexed against lines this rule runs before, so it does its own pass.

Both the corner check and the bar counting read only the rows carrying the candidate bar,
not the whole paste. The TUI draws the prompt box with corners in the *conversation*
column, so a wider check would veto the common case; and a stray corner at the same
column elsewhere says nothing about whether this column is a frame. For the same reason
the cut takes whichever bar is nearest the divider rather than the line's first: a
box-drawn prompt puts its own border ahead of the grip on that row.

Matching allows two columns of slack, which absorbs a selection that starts mid-line, a
double-width glyph nudging a row, and a dock resized mid-session — scrollback keeps the
old geometry, so one paste can genuinely hold two divider columns, and each is cut
independently. Columns are counted in characters rather than display cells, so a run of
wide characters in the conversation can still push a row out of tolerance and leave it
uncut. Set `cc_dock_divider=0` to turn the rule off.

A selection taken entirely from inside the panel has no divider in it, and nothing here
fires; `panel-bleed` below covers the part of that case it can.

`panel-bleed` — the diff side panel renders to the *right* of the conversation column,
so copying a region drags the panel's text onto the end of whatever line it happened to
sit beside, behind the right-align gap:

```
• chore(vuln): Remove the CVE batch cards …/pull/35130          No changes this session
```

A line is only cut when it ends in one of the panel's known strings — the empty states
(`No changes this session`, `No uncommitted changes`, `No changes vs <branch>`,
`No commits yet`, `Diff unavailable`, `Loading diff…`, `Only … files changed`,
`Too many changed files to show diff`) or the `N files changed +12 -4` header, each
optionally followed by the panel's `✕` close button. Both a known string *and* a gap of
two or more spaces are required, so a bare `No commits yet` inside a pasted `git status`
transcript survives and prose is only at risk when it ends in one of these phrases
behind a column-width gap.

This is the fallback for captures with no divider in them — older versions of the TUI,
which drew none, and selections taken from inside the panel. Where a divider *is* present,
`dock-divider` above has already removed the panel and this rule finds nothing to do. Set
`cc_panel_bleed=0` to turn the rule off.

`wrapped-sentences` — `reflow` refuses to join across a full stop, on the reasonable
assumption that it ends a paragraph. But a terminal wrapping a long sentence can break
right after one, and then the paragraph arrives split. This rule allows the join when
the next line begins with a **lowercase letter**, which prose does not do at the start
of a sentence. Every other guard still applies: the previous line must clear the
40-character threshold, and the next must not look like a list item, quote, heading or
fence. A capitalised continuation is otherwise left alone, since it might genuinely be
a new sentence.

The one exception is a line that arrived with a `▎` bar of its own. Every wrapped line
of a quoted block carries one, so the bar says the line continues the one above it
whatever case it starts in — which is what rescues a partial copy, where the selection
began mid-line and the first line lost its bar. Quoted paragraphs stay apart because the
bare bar between them becomes a blank line. The cost is that prose sitting directly above
a quote with no blank line between them will be joined to it; the TUI puts a blank line
before a blockquote, so that shape does not arise in a real paste. Set
`cc_wrapped_sentences=0` for strict upstream behaviour.

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

`.github/workflows/release.yml` builds on any `v*` tag and attaches the workflow and
its `.sha256` to a **draft** release:

```sh
# 1. bump VERSION in the same commit you intend to tag
echo 1.1.0 > VERSION && ./build.sh && ./test.sh
git commit -am "Release 1.1.0"

# 2. tag and push
git tag v1.1.0 && git push origin main --tags

# 3. review the draft (notes are generated from merged PRs), then publish it
gh release view v1.1.0 --web
```

Re-pushing a tag whose release is still a draft replaces the draft's assets but keeps
its notes; the job refuses to touch a release that is already published.

The workflow refuses to build a release if the tag and `VERSION` disagree — that check exists
so a release can't ship a workflow whose Alfred-visible version says something else.
The version reaches the plist through `WORKFLOW_VERSION`, which the release job sets
from the tag; local builds fall back to `VERSION`, so ordinary builds never churn
`src/info.plist`.

`workflow_dispatch` runs the same pipeline without drafting a release, uploading the
built workflow as a run artifact — useful for checking the pipeline itself.

### CI

`.github/workflows/ci.yml` runs on every PR, on Linux and on macOS with Apple's
`/usr/bin/python3` (the interpreter the workflow runs under). It checks that
`src/info.plist` matches `tools/make_plist.py`, runs `./test.sh`, builds the workflow,
and fails if anything stray in `src/` would end up in the package. The snapshot and
release workflows run the same checks before they build.

`.github/workflows/snapshot.yml` runs on every push to `main` (or by hand from the
Actions tab) and packages a snapshot, versioned `<VERSION>+snapshot.<sha>` so Alfred
shows which commit it came from. It is kept for
90 days as the run's `alfredworkflow-…` artifact: a zip holding the `.alfredworkflow`
and its `.sha256`. `tools/package.sh <version>` produces the same files locally.

The integration tests stub `pbcopy`/`pbpaste`, so CI never touches a real clipboard
or Alfred itself — try the built workflow once by hand before tagging.

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

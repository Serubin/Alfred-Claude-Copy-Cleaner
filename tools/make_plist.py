#!/usr/bin/env python3
"""Regenerate src/info.plist, the Alfred workflow graph.

The plist is checked in — this exists so the graph can be reasoned about as code and
regenerated after hand-edits in Alfred's editor drift from intent.

  python3 tools/make_plist.py
"""

import pathlib
import plistlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "info.plist"

# Stable uids: regenerating must not orphan connections or reshuffle the canvas.
HOTKEY = "1B1A0F7C-9E2D-4F55-9C31-2A6D0C4E7A01"
UNIVERSAL = "2C2B1E8D-7F3E-4A66-8D42-3B7E1D5F8B02"
SCRIPT = "3D3C2F9E-6A4F-4B77-7E53-4C8F2E6A9C03"
NOTIFY = "4E4D3A0F-5B5A-4C88-6F64-5D9A3F7B0D04"

# Alfred passes the Universal Action's selected text as $1. The hotkey trigger passes
# nothing, which is the signal to clean the clipboard in place instead.
#
# The cleaner writes the clipboard itself rather than handing text back to an Alfred
# clipboard object: Alfred expands {placeholders} in object text, and cleaned Claude
# Code output routinely contains braces (JSON, code, template literals). Only the
# one-line summary comes back on stdout, which the notification is free to expand.
SCRIPT_BODY = """#!/bin/zsh --no-rcs

for candidate in /usr/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if [[ -x $candidate ]]; then
    PY=$candidate
    break
  fi
done
: ${PY:=python3}

# CC_PBPASTE/CC_PBCOPY are test seams; unset, they are the real clipboard.
if [[ -n "$1" ]]; then
  printf '%s' "$1"
else
  "${CC_PBPASTE:-/usr/bin/pbpaste}"
fi | "$PY" clean_claude_text.py --stats
"""

README = """Cleans text copied out of the Claude Code terminal UI: message bullets \
(the ⏺ and ⎿ markers), box-drawing borders, ANSI colour and hyperlink escapes, \
line-number gutters, spinner and shortcut-hint chrome, and terminal hard-wrapping.

Two ways in:

  • Hotkey — cleans whatever is on the clipboard and puts the result back, so you \
just paste. No hotkey is assigned on import; set one in the workflow editor.
  • Universal Action — select text anywhere, then "Clean Claude Code Text".

A notification reports what changed. If the result would be empty the clipboard is \
left untouched.

This is a plain-text cleaner: it strips artifacts rather than rebuilding markdown."""

objects = [
    {
        "uid": HOTKEY,
        "type": "alfred.workflow.trigger.hotkey",
        "version": 2,
        "config": {
            "action": 0,
            "argument": 0,  # pass nothing -> the script reads the clipboard
            "focusedappvariable": False,
            "focusedappvariablename": "",
            "leftcursor": False,
            "modsmode": 0,
            "relatedAppsMode": 0,
        },
    },
    {
        "uid": UNIVERSAL,
        "type": "alfred.workflow.trigger.universalaction",
        "version": 1,
        "config": {
            "acceptsfiles": False,
            "acceptsmulti": 0,
            "acceptstext": True,
            "acceptsurls": False,
            "name": "Clean Claude Code Text",
        },
    },
    {
        "uid": SCRIPT,
        "type": "alfred.workflow.action.script",
        "version": 2,
        "config": {
            "concurrently": False,
            "escaping": 0,
            "script": SCRIPT_BODY,
            "scriptargtype": 1,  # selection arrives as $1, not stdin
            "scriptfile": "",
            "type": 11,  # /bin/zsh
        },
    },
    {
        "uid": NOTIFY,
        "type": "alfred.workflow.output.notification",
        "version": 1,
        "config": {
            "lastpathcomponent": False,
            "onlyshowifquerypopulated": True,  # cc_notify=0 prints nothing -> silent
            "removeextension": False,
            "text": "{query}",
            "title": "{const:alfred_workflow_name}",
        },
    },
]


def link(destination):
    return [{"destinationuid": destination, "modifiers": 0, "modifiersubtext": "", "vitoclose": False}]


workflow = {
    "bundleid": "net.serubin.alfred.claude-code-paste-cleaner",
    "name": "Claude Code Paste Cleaner",
    "description": "Strip terminal artifacts from text copied out of Claude Code.",
    "createdby": "serubin",
    "webaddress": "",
    "version": "1.0.0",
    "category": "Tools",
    "disabled": False,
    "readme": README,
    "objects": objects,
    "connections": {
        HOTKEY: link(SCRIPT),
        UNIVERSAL: link(SCRIPT),
        SCRIPT: link(NOTIFY),
        NOTIFY: [],
    },
    "uidata": {
        HOTKEY: {"xpos": 40, "ypos": 40},
        UNIVERSAL: {"xpos": 40, "ypos": 190},
        SCRIPT: {"xpos": 300, "ypos": 110},
        NOTIFY: {"xpos": 560, "ypos": 110},
    },
    # Rule toggles reach the script as environment variables; the script maps
    # cc_<rule_id> to its rule, so these names must match the ids in RULE_IDS.
    "userconfigurationconfig": [
        {
            "type": "checkbox",
            "variable": "cc_reflow",
            "label": "Undo terminal hard wrapping",
            "description": "Merge lines the terminal wrapped back into paragraphs. "
            "Turn off to keep the original line breaks.",
            "config": {"default": True, "required": False, "text": ""},
        },
        {
            "type": "checkbox",
            "variable": "cc_smart_quotes",
            "label": "Curly quotes to ASCII",
            "description": "Convert “ ” ‘ ’ to straight ASCII quotes.",
            "config": {"default": True, "required": False, "text": ""},
        },
        {
            "type": "checkbox",
            "variable": "cc_notify",
            "label": "Show a notification",
            "description": "Report how much was removed after each clean.",
            "config": {"default": True, "required": False, "text": ""},
        },
    ],
    "variablesdontexport": [],
}


def main():
    with open(OUT, "wb") as f:
        plistlib.dump(workflow, f)
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

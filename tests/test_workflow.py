#!/usr/bin/env python3
"""Integration tests for the packaged Alfred workflow.

These run the Run Script action's real body — extracted from the built info.plist, so
what is tested is what ships — against stub clipboard binaries, exercising both entry
points without touching the real clipboard.

  python3 tests/test_workflow.py
"""

import os
import pathlib
import plistlib
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PLIST = SRC / "info.plist"

ARTIFACT_TEXT = "⏺ Read(config/settings.json)\n  ⎿  Read 42 lines (ctrl+o to expand)\n⏺ The timeout was wrong.\n"
CLEANED_TEXT = "The timeout was wrong."


def load_workflow():
    with open(PLIST, "rb") as f:
        return plistlib.load(f)


def script_body():
    for obj in load_workflow()["objects"]:
        if obj["type"] == "alfred.workflow.action.script":
            return obj["config"]["script"]
    raise AssertionError("no script action in info.plist")


class ScriptActionTests(unittest.TestCase):
    """Run the shipped script body with stubbed pbpaste/pbcopy."""

    def run_action(self, argument="", clipboard="", env=None):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = pathlib.Path(tmp)

            copied = tmpdir / "copied.txt"
            pbcopy = tmpdir / "pbcopy"
            pbcopy.write_text(f'#!/bin/sh\ncat > "{copied}"\n')
            pbcopy.chmod(pbcopy.stat().st_mode | stat.S_IEXEC)

            pbpaste = tmpdir / "pbpaste"
            clip_file = tmpdir / "clipboard.txt"
            clip_file.write_text(clipboard)
            pbpaste.write_text(f'#!/bin/sh\ncat "{clip_file}"\n')
            pbpaste.chmod(pbpaste.stat().st_mode | stat.S_IEXEC)

            script = tmpdir / "action.sh"
            script.write_text(script_body())

            environ = dict(os.environ)
            environ.update(
                {"CC_PBCOPY": str(pbcopy), "CC_PBPASTE": str(pbpaste)}, **(env or {})
            )

            proc = subprocess.run(
                ["/bin/zsh", str(script), argument],
                cwd=SRC,  # Alfred runs scripts from the workflow directory
                capture_output=True,
                env=environ,
            )
            written = copied.read_text() if copied.exists() else None
            return proc, written

    def test_universal_action_cleans_its_argument(self):
        proc, copied = self.run_action(argument=ARTIFACT_TEXT)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode())
        self.assertEqual(copied, CLEANED_TEXT)

    def test_hotkey_cleans_the_clipboard(self):
        proc, copied = self.run_action(clipboard=ARTIFACT_TEXT)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode())
        self.assertEqual(copied, CLEANED_TEXT)

    def test_summary_goes_to_stdout_for_the_notification(self):
        proc, _ = self.run_action(clipboard=ARTIFACT_TEXT)
        out = proc.stdout.decode()
        self.assertIn("Cleaned", out)
        self.assertNotIn("timeout", out)  # the text itself must never reach Alfred

    def test_empty_clipboard_is_not_clobbered(self):
        proc, copied = self.run_action(clipboard="   \n\n")
        self.assertEqual(proc.returncode, 0, proc.stderr.decode())
        self.assertIsNone(copied, "pbcopy ran on empty input")
        self.assertIn("Nothing to clean", proc.stdout.decode())

    def test_braces_in_output_survive_intact(self):
        # The reason the script copies for itself rather than handing text to an
        # Alfred clipboard object, which would expand {placeholders}.
        source = '⏺ Config is {"proxy": {"timeout": 10000}} and {var:x} stays literal.\n'
        _proc, copied = self.run_action(argument=source)
        self.assertEqual(copied, 'Config is {"proxy": {"timeout": 10000}} and {var:x} stays literal.')

    def test_rule_toggle_from_workflow_configuration(self):
        _proc, copied = self.run_action(
            argument="⏺ he said “hi”\n", env={"cc_smart_quotes": "0"}
        )
        self.assertIn("“", copied)

    def test_notification_suppressed_when_configured_off(self):
        proc, copied = self.run_action(argument=ARTIFACT_TEXT, env={"cc_notify": "0"})
        self.assertEqual(proc.stdout.decode(), "")
        self.assertEqual(copied, CLEANED_TEXT, "text should still be cleaned and copied")


class PlistTests(unittest.TestCase):
    def setUp(self):
        self.wf = load_workflow()
        self.objects = {o["uid"]: o for o in self.wf["objects"]}

    def test_plist_is_valid(self):
        subprocess.run(["plutil", "-lint", str(PLIST)], check=True, capture_output=True)

    def test_both_triggers_reach_the_script(self):
        script_uid = next(
            uid for uid, o in self.objects.items()
            if o["type"] == "alfred.workflow.action.script"
        )
        for trigger in ("alfred.workflow.trigger.hotkey", "alfred.workflow.trigger.universalaction"):
            uid = next(u for u, o in self.objects.items() if o["type"] == trigger)
            targets = [c["destinationuid"] for c in self.wf["connections"].get(uid, [])]
            self.assertIn(script_uid, targets, f"{trigger} is not wired to the script")

    def test_script_reaches_the_notification(self):
        script_uid = next(
            uid for uid, o in self.objects.items()
            if o["type"] == "alfred.workflow.action.script"
        )
        notify_uid = next(
            uid for uid, o in self.objects.items()
            if o["type"] == "alfred.workflow.output.notification"
        )
        targets = [c["destinationuid"] for c in self.wf["connections"][script_uid]]
        self.assertIn(notify_uid, targets)

    def test_hotkey_passes_no_argument(self):
        hotkey = next(
            o for o in self.wf["objects"] if o["type"] == "alfred.workflow.trigger.hotkey"
        )
        # argument 0 = none: the script reads the clipboard itself.
        self.assertEqual(hotkey["config"]["argument"], 0)

    def test_universal_action_accepts_text_only(self):
        action = next(
            o for o in self.wf["objects"]
            if o["type"] == "alfred.workflow.trigger.universalaction"
        )
        self.assertTrue(action["config"]["acceptstext"])
        self.assertFalse(action["config"]["acceptsfiles"])
        self.assertTrue(action["config"]["name"])

    def test_notification_only_fires_when_populated(self):
        notify = next(
            o for o in self.wf["objects"]
            if o["type"] == "alfred.workflow.output.notification"
        )
        self.assertTrue(notify["config"]["onlyshowifquerypopulated"])

    def test_config_variables_match_rule_ids(self):
        sys.path.insert(0, str(SRC))
        from clean_claude_text import RULE_IDS

        for entry in self.wf["userconfigurationconfig"]:
            variable = entry["variable"]
            if variable == "cc_notify":
                continue
            rule = variable[len("cc_"):].replace("_", "-")
            self.assertIn(rule, RULE_IDS, f"{variable} does not map to a real rule")


if __name__ == "__main__":
    unittest.main(verbosity=2)

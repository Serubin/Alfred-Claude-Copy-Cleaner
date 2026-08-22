#!/usr/bin/env python3
"""Per-rule unit tests for the cleaner.

The differential test proves the port matches the original implementation; these tests
pin down what each rule is *for*, so a future edit that changes behaviour fails with a
readable message rather than a byte diff.

  python3 tests/test_clean.py
"""

import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from clean_claude_text import LOCAL_RULES, RULE_IDS, clean, js_len  # noqa: E402

SCRIPT = ROOT / "src" / "clean_claude_text.py"
ESC = "\x1b"
BEL = "\x07"


class RuleTests(unittest.TestCase):
    def assert_rule(self, rule, source, expected):
        """The rule produces `expected`, and disabling it leaves the artifact alone."""
        self.assertEqual(clean(source)[0], expected, f"{rule} did not clean as expected")
        untouched, _ = clean(source, disabled={rule})
        self.assertNotEqual(
            untouched, expected, f"disabling {rule} still produced the cleaned output"
        )

    def test_ansi_escapes_removes_colour_codes(self):
        self.assert_rule(
            "ansi-escapes",
            f"{ESC}[1m{ESC}[32mgreen{ESC}[0m text",
            "green text",
        )

    def test_ansi_escapes_keeps_hyperlink_text_drops_url(self):
        source = f"see {ESC}]8;;https://example.com{BEL}the build{ESC}]8;;{BEL} here"
        self.assert_rule("ansi-escapes", source, "see the build here")

    def test_chrome_lines_drops_spinner_and_hints(self):
        source = "kept line\n✻ Ruminating… (esc to interrupt)\n? for shortcuts"
        self.assert_rule("chrome-lines", source, "kept line")

    def test_chrome_lines_drops_expand_hint(self):
        self.assert_rule(
            "chrome-lines", "text\n  … +47 lines (ctrl+o to expand)", "text"
        )

    def test_tool_calls_drops_headers(self):
        source = "⏺ Read(config/settings.json)\n⏺ real prose survives"
        self.assert_rule("tool-calls", source, "real prose survives")

    def test_message_prefixes_strips_bullets_and_results(self):
        self.assert_rule(
            "message-prefixes", "⏺ assistant text\n  ⎿  tool result", "assistant text\ntool result"
        )

    def test_box_drawing_drops_borders_and_edges(self):
        source = "╭─────────────╮\n│ prompt text │\n╰─────────────╯"
        self.assert_rule("box-drawing", source, "prompt text")

    def test_glyphs_strips_checkboxes(self):
        self.assert_rule("glyphs", "☒ done item\n☐ todo item", "done item\ntodo item")

    def test_blockquote_bars_become_blank_lines(self):
        # Local deviation from upstream, which leaves bare ▎ bars behind.
        self.assert_rule(
            "blockquote-bars", "▎ quoted text\n▎\n▎ more quoted text",
            "quoted text\n\nmore quoted text",
        )

    def test_blockquote_bars_keep_paragraphs_apart(self):
        # The bar is blanked rather than deleted: deleting it would put two
        # paragraphs on adjacent lines and let reflow run them together.
        source = (
            "▎ A quoted paragraph long enough to be a rejoin candidate here\n"
            "▎\n"
            "▎ a second paragraph that must not be merged into the first\n"
        )
        out, _ = clean(source)
        self.assertEqual(len(out.split("\n\n")), 2, out)

    def test_line_gutters_strips_file_read_numbers(self):
        # The gutter takes its own indent with it; the file's own indentation stays,
        # and gutter lines are exempt from reflow's dedent so it survives verbatim.
        source = "   52→  ACCOUNTS.each do |slug|\n   53→    seed(slug)"
        self.assert_rule("line-gutters", source, "  ACCOUNTS.each do |slug|\n    seed(slug)")

    def test_line_gutters_strips_diff_gutters(self):
        self.assert_rule("line-gutters", "  41 -    seed(slug)", "seed(slug)")

    def test_reflow_rejoins_hard_wrapped_prose(self):
        source = (
            "The seed file inserts rows in whatever order it iterates\n"
            "so the assertion depends on hash ordering"
        )
        self.assert_rule(
            "reflow",
            source,
            "The seed file inserts rows in whatever order it iterates "
            "so the assertion depends on hash ordering",
        )

    def test_wrapped_sentences_rejoin_after_a_full_stop(self):
        # Local deviation: upstream treats any full stop at a line end as a paragraph
        # boundary, so a wrap that lands there is never re-joined.
        source = (
            "When explaining anything use plain language, short sentences, and avoid "
            "dense phrasing.\n"
            "  considering following simplified technical english"
        )
        self.assert_rule(
            "wrapped-sentences",
            source,
            "When explaining anything use plain language, short sentences, and avoid "
            "dense phrasing. considering following simplified technical english",
        )

    def test_wrapped_sentences_leave_capitalised_continuations(self):
        # Might genuinely be a new sentence, so the full stop still wins.
        source = (
            "When explaining anything use plain language, short sentences, and avoid "
            "dense phrasing.\n"
            "  Considering following simplified technical english"
        )
        out, _ = clean(source)
        self.assertEqual(len(out.split("\n")), 2, out)

    def test_wrapped_sentences_respect_the_length_threshold(self):
        source = "Short line.\nconsidering this stays put"
        self.assertEqual(clean(source)[0], source)

    def test_wrapped_sentences_do_not_swallow_lists(self):
        source = (
            "The list below must not be swallowed even though this line ends in a "
            "colon:\n"
            "  - considering following simplified technical english"
        )
        out, _ = clean(source)
        self.assertEqual(len(out.split("\n")), 2, out)

    def test_reflow_leaves_short_lines_alone(self):
        source = "Short line.\nAnother short one."
        self.assertEqual(clean(source)[0], source)

    def test_reflow_does_not_swallow_list_items(self):
        source = (
            "This introduction is long enough to be a rejoin candidate\n"
            "- but a list item must stay on its own line"
        )
        self.assertEqual(clean(source)[0], source)

    def test_reflow_leaves_code_fences_intact(self):
        source = "```ts\nconst pool = createPool({\n  max: 64,\n});\n```"
        self.assertEqual(clean(source)[0], source)

    def test_unicode_whitespace_normalises(self):
        # Exotic spaces become plain spaces; zero-width characters are deleted.
        self.assert_rule(
            "unicode-whitespace",
            "non\u00a0breaking and\u200bzero\u2060width",
            "non breaking andzerowidth",
        )

    def test_smart_quotes_straightened(self):
        self.assert_rule("smart-quotes", "he said “hi” and ‘bye’", "he said \"hi\" and 'bye'")

    def test_trailing_blanklines_collapses_runs(self):
        self.assert_rule("trailing-blanklines", "a   \n\n\n\nb\n\n", "a\n\nb")


class SemanticsTests(unittest.TestCase):
    def test_js_len_counts_utf16_units(self):
        self.assertEqual(js_len("abc"), 3)
        self.assertEqual(js_len("🚀"), 2)  # astral chars are surrogate pairs in JS

    def test_reflow_threshold_uses_utf16_length(self):
        # 38 code points but 42 UTF-16 units, so this is over the 40-unit threshold
        # and must be treated as a rejoin candidate.
        head = "🚀🚀🚀🚀 the quick brown fox jumped over"
        self.assertLess(len(head), 40)
        self.assertGreaterEqual(js_len(head), 40)
        self.assertEqual(clean(f"{head}\nand kept going")[0], f"{head} and kept going")

    def test_crlf_input_is_not_mangled(self):
        out, _ = clean("⏺ hello\r\nworld\r\n")
        self.assertIn("hello", out)
        self.assertNotIn("⏺", out)

    def test_empty_and_whitespace_input(self):
        self.assertEqual(clean("")[0], "")
        self.assertEqual(clean("   \n\t\n")[0], "")


class ConfigTests(unittest.TestCase):
    def test_disable_accepts_every_rule_id(self):
        source = "⏺ anything at all"
        for rule in RULE_IDS:
            clean(source, disabled={rule})  # must not raise

    def test_local_rules_are_real_rules(self):
        for rule in LOCAL_RULES:
            self.assertIn(rule, RULE_IDS)

    def test_disabling_everything_is_identity(self):
        source = "⏺ Read(a.ts)\n  ⎿  Read 4 lines (ctrl+o to expand)\n"
        self.assertEqual(clean(source, disabled=set(RULE_IDS))[0], source)


class CliTests(unittest.TestCase):
    def run_cli(self, args, stdin="", env=None):
        environ = {"PATH": "/usr/bin:/bin"}
        environ.update(env or {})
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            input=stdin.encode("utf-8"),
            capture_output=True,
            env=environ,
        )

    def run_cli_capturing_clipboard(self, args, stdin="", env=None):
        """Run with a stub clipboard, returning (proc, what_was_copied_or_None).

        Keeps the suite off the real pbcopy — which would clobber the developer's
        clipboard and does not exist on Linux CI — while still asserting on what the
        copy path actually wrote.
        """
        with tempfile.TemporaryDirectory() as tmp:
            copied = pathlib.Path(tmp) / "copied.txt"
            stub = pathlib.Path(tmp) / "pbcopy"
            stub.write_text(f'#!/bin/sh\ncat > "{copied}"\n')
            stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
            environ = {"CC_PBCOPY": str(stub)}
            environ.update(env or {})
            proc = self.run_cli(args, stdin, environ)
            return proc, (copied.read_text() if copied.exists() else None)

    def test_stdin_to_stdout(self):
        proc = self.run_cli([], "⏺ hello world\n")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.decode(), "hello world")

    def test_text_argument(self):
        proc = self.run_cli(["--text", "⏺ hello"])
        self.assertEqual(proc.stdout.decode(), "hello")

    def test_disable_flag(self):
        proc = self.run_cli(["--disable", "message-prefixes"], "⏺ hello")
        self.assertEqual(proc.stdout.decode(), "⏺ hello")

    def test_unknown_rule_is_an_error(self):
        proc = self.run_cli(["--disable", "no-such-rule"], "x")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("unknown rule id", proc.stderr.decode())

    def test_env_var_disables_rule(self):
        proc = self.run_cli([], "he said “hi”", env={"cc_smart_quotes": "0"})
        self.assertIn("“", proc.stdout.decode())

    def test_env_var_absent_leaves_rule_on(self):
        proc = self.run_cli([], "he said “hi”")
        self.assertNotIn("“", proc.stdout.decode())

    def test_list_rules(self):
        proc = self.run_cli(["--list-rules"])
        self.assertEqual(proc.returncode, 0)
        for rule in RULE_IDS:
            self.assertIn(rule, proc.stdout.decode())

    def test_stats_reports_summary_not_text(self):
        proc, copied = self.run_cli_capturing_clipboard(
            ["--stats"], "⏺ Read(a.ts)\nsome private text\n"
        )
        out = proc.stdout.decode()
        self.assertIn("Cleaned", out)
        # Alfred expands {placeholders} in whatever comes back on stdout, so the text
        # must reach the clipboard and only the summary may reach Alfred.
        self.assertNotIn("some private text", out)
        self.assertEqual(copied, "some private text")

    def test_stats_on_empty_input_leaves_clipboard_alone(self):
        # Guards the hotkey path: cleaning an empty clipboard must not wipe it.
        proc = self.run_cli(["--stats"], "   \n\n")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Nothing to clean", proc.stdout.decode())

    def test_notify_off_silences_summary(self):
        proc = self.run_cli(["--stats"], "   \n", env={"cc_notify": "0"})
        self.assertEqual(proc.stdout.decode(), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Regression tests for gate failure paths; real-tool smoke tests are separate."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import ci


class GateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patcher = patch.object(ci, "ROOT", self.root)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        (self.root / "fixture.go").write_text(
            'package fixture\nfunc first() { dangerous() }\nfunc second() { dangerous() }\n',
            encoding="utf-8")

    def record(self, line=2):
        return ci.source_record("fixture.go", line, "rule", "finding")

    def test_context_and_duplicate_counts_fail_new_findings(self):
        first, second = self.record(2), self.record(3)
        self.assertTrue(ci.compare([first], [first]))
        self.assertFalse(ci.compare([first, second], [first]))
        self.assertFalse(ci.compare([first, first], [first]))
        self.assertFalse(ci.compare([], [first]))

    def test_findings_survive_line_moves_but_not_changed_source(self):
        original = self.record()
        path = self.root / "fixture.go"
        path.write_text("\n" + path.read_text(), encoding="utf-8")
        self.assertEqual(original, self.record(3))
        path.write_text(path.read_text().replace("dangerous()", "other()"), encoding="utf-8")
        self.assertNotEqual(original, self.record(3))

    def test_bad_analyzer_output_fails(self):
        for name in ("staticcheck", "revive", "errcheck", "gosec"):
            with self.subTest(name=name), self.assertRaises((ValueError, KeyError)):
                ci.parse_findings(name, "package could not be loaded")
        with self.assertRaises(ValueError):
            ci.parse_findings("gosec", json.dumps({"Golang errors": {"fixture": ["load failed"]},
                                                  "Stats": {"files": 1}, "Issues": []}))

    def test_tool_failure_cannot_write_baseline(self):
        for name, output in (("staticcheck", ""), ("revive", "[]"), ("errcheck", ""),
                             ("gosec", '{"Stats":{"files":1},"Issues":[]}')):
            with self.subTest(name=name), patch.object(
                    ci, "run", return_value=subprocess.CompletedProcess([], 1, output, "")):
                with self.assertRaises(ValueError):
                    ci.analyze(name, write=True)
        self.assertFalse((self.root / "scripts/ci-baselines").exists())

    def test_partial_fix_with_package_error_is_rejected(self):
        patch_text = "--- fixture.go (old)\n+++ fixture.go (new)\n@@ -1,1 +1,1 @@\n-package fixture\n+package changed\n"
        with patch.object(ci, "run", return_value=subprocess.CompletedProcess(
                [], 1, patch_text, "go: downloading example.com/module v1.0.0\npackage could not be loaded")), self.assertRaises(ValueError):
            ci.fix_check(write=True)
        self.assertFalse((self.root / "scripts/ci-baselines").exists())

    def test_only_exact_download_progress_is_accepted(self):
        notices = "go: downloading example.com/module v1.0.0\ngo: downloading go1.27.3 (linux/amd64)\n"
        self.assertEqual("", ci.tool_errors(notices))
        for error in ("go: downloading example.com/module v1.0.0: network failed",
                      "go: example.com/module: checksum mismatch",
                      "package could not be loaded", "panic: failed"):
            self.assertIn(error, ci.tool_errors(notices + error))
        patch_text = "--- fixture.go (old)\n+++ fixture.go (new)\n@@ -1,1 +1,1 @@\n-package fixture\n+package changed\n"
        with patch.object(ci, "run", return_value=subprocess.CompletedProcess(
                [], 1, patch_text, notices)):
            ci.fix_check(write=True)
        self.assertTrue((self.root / f"scripts/ci-baselines/fix-{ci.PLATFORM}.json").exists())

    def test_crash_with_findings_is_not_accepted(self):
        diagnostic = {"location": {"file": "fixture.go", "line": 2}, "code": "SA1000", "message": "invalid"}
        with patch.object(ci, "run", return_value=subprocess.CompletedProcess(
                [], 2, json.dumps(diagnostic), "")), self.assertRaises(ValueError):
            ci.analyze("staticcheck", write=True)

    def test_fix_normalizes_line_endings_and_retains_actual_changes(self):
        same = "--- fixture.go (old)\n+++ fixture.go (new)\n@@ -1,2 +1,2 @@\n-a\r\n-b\r\n+a\n+b\n"
        self.assertEqual([], ci.fix_records(same))
        changed = same.replace("+b\n", "+c\n")
        records = ci.fix_records(changed)
        self.assertEqual("-b\n+c", records[0]["source"])
        self.assertFalse(ci.compare(records, []))
        self.assertTrue(ci.compare(records, records))

    def test_weighted_coverage_and_regression_without_rounding(self):
        profile = ("mode: atomic\n"
                   "github.com/jsirianni/dzdeploy/internal/example/a.go:1.1,2.1 8950 1\n"
                   "github.com/jsirianni/dzdeploy/internal/example/a.go:3.1,4.1 1050 0\n")
        actual = ci.coverage_totals(profile)
        expected = {"internal/example": {"covered": 9000, "total": 10000, "tolerance_bps": 50}}
        ci.compare_coverage(actual, expected)  # Inclusive 0.5 pp allowance.
        actual["internal/example"]["covered"] -= 1
        with self.assertRaises(ValueError):
            ci.compare_coverage(actual, expected)
        with self.assertRaises(ValueError):
            ci.compare_coverage({}, expected)

    def test_invalid_and_duplicate_coverage_is_rejected(self):
        block = "github.com/jsirianni/dzdeploy/internal/example/a.go:1.1,2.1 1 1\n"
        for profile in ("", "mode: count\n" + block, "mode: atomic\ninvalid\n",
                        "mode: atomic\n" + block + block,
                        "mode: atomic\n../outside.go:1.1,2.1 1 1\n"):
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                ci.coverage_totals(profile)

    def test_format_preserves_crlf_and_changes_only_real_differences(self):
        path = self.root / "fixture.go"
        path.write_bytes(b"package fixture\r\n")
        def fake_imports(args, **kwargs):
            scratch = kwargs["cwd"] / "fixture.go"
            self.assertEqual(b"package fixture\n", scratch.read_bytes())
            return subprocess.CompletedProcess(args, 0, "", "")
        (self.root / "go.mod").write_text("module fixture\n", encoding="utf-8")
        (self.root / "go.sum").write_text("", encoding="utf-8")
        with patch.object(ci, "go_files", return_value=["fixture.go"]), patch.object(ci, "run", fake_imports):
            ci.format_check()
        self.assertEqual(b"package fixture\r\n", path.read_bytes())


if __name__ == "__main__":
    with contextlib.redirect_stdout(io.StringIO()) as output:
        result = unittest.main(exit=False)
    if not result.result.wasSuccessful():
        print(output.getvalue())
        raise SystemExit(1)

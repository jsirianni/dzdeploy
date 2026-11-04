import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("update_go", Path(__file__).with_name("update-go.py"))
update_go = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update_go)


class UpdateTests(unittest.TestCase):
    def test_numeric_versions_and_toolchain_move_together(self):
        source = "module example.com/test\r\n\r\ngo 1.26.0 // minimum\r\ntoolchain go1.27.3\r\n"
        updated, version = update_go.update_module(source, [
            {"version": "go1.27.9", "stable": True}, {"version": "go1.27.10", "stable": True}])
        self.assertEqual("1.27.10", version)
        self.assertIn("go 1.27.10 // minimum\r\n", updated)
        self.assertIn("toolchain go1.27.10\r\n", updated)

    def test_major_minor_and_prereleases(self):
        updated, version = update_go.update_module("go 1.27\n", [
            {"version": "go1.28.0", "stable": True}, {"version": "go1.29rc1", "stable": True}])
        self.assertEqual(("go 1.28.0\n", "1.28.0"), (updated, version))

    def test_no_effective_toolchain_downgrade(self):
        updated, version = update_go.update_module("go 1.26.0\ntoolchain go1.28.1\n",
                                                  [{"version": "go1.27.3", "stable": True}])
        self.assertEqual("1.28.1", version)
        self.assertEqual("go 1.28.1\ntoolchain go1.28.1\n", updated)

    def test_invalid_prefixes_and_toolchains_are_rejected(self):
        for toolchain in ("go1.28rc1", "default", "custom", "g1.28.0", "go1.28.0\n" + "toolchain go1.29.0"):
            with self.subTest(toolchain=toolchain), self.assertRaises(ValueError):
                update_go.update_module("go 1.27.3\n" + "toolchain " + toolchain + "\n",
                                        [{"version": "go1.28.0", "stable": True}])
        with self.assertRaises(ValueError):
            update_go.update_module("go 1.27.3\n", [{"version": "g1.28.0", "stable": True}])

    def test_invalid_modules_and_feeds_fail(self):
        for source, releases in [
            ("module fixture\n", [{"version": "go1.28.0", "stable": True}]),
            ("go 1.27.3\ngo 1.28.0\n", [{"version": "go1.28.0", "stable": True}]),
            ("go 1.27.3\n", []), ("go 1.27.3\n", [{"version": "go1.28rc1", "stable": False}]),
        ]:
            with self.subTest(source=source, releases=releases), self.assertRaises(ValueError):
                update_go.update_module(source, releases)


if __name__ == "__main__":
    unittest.main()

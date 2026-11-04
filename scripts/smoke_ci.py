#!/usr/bin/env python3
"""Prove pinned tools reject real violations; infrastructure failures never pass."""
from pathlib import Path
import tempfile
from unittest.mock import patch
import ci


def main():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        (root / "go.mod").write_text("module fixture\n\ngo 1.27.0\n", encoding="utf-8")
        fixture = root / "fixture.go"
        with patch.object(ci, "ROOT", root):
            for name, code, rule in (
                ("staticcheck", 'import "regexp"\nfunc example() { regexp.MustCompile("[") }\n', "SA1000"),
                ("revive", 'func example(value any) string { return value.(string) }\n', "unchecked-type-assertion"),
                ("revive", 'func example() int { len := 1; return len }\n', "redefines-builtin-id"),
                ("revive", 'import "fmt"\nfunc example() error { return fmt.Errorf("constant") }\n', "unnecessary-format"),
                ("errcheck", 'import "os"\nfunc example() { os.Chdir("not executed") }\n', "unchecked-error"),
                ("errcheck", 'import "os"\nfunc example() { _ = os.Chdir("not executed") }\n', "unchecked-error"),
                ("gosec", 'import "os"\nfunc example(path string) ([]byte,error) { return os.ReadFile(path) }\n', "G304"),
            ):
                fixture.write_text("package fixture\n" + code, encoding="utf-8")
                flags = {
                    "staticcheck": ["-f", "json"],
                    "revive": ["-config", str(ci.BIN.parent.parent / "revive.toml"), "-formatter", "json"],
                    "errcheck": ["-blank", "-excludeonly", "-exclude",
                                 str(ci.BIN.parent.parent / "scripts/errcheck-excludes.txt")],
                    "gosec": ["-nosec-require-rules", "-nosec-require-justification", "-fmt", "json"],
                }
                result = ci.run([ci.tool(name), *flags[name], "./..."], cwd=root)
                findings = ci.parse_findings(name, result.stdout)
                if result.returncode != 1 or not any(item["rule"] == rule for item in findings):
                    raise ValueError(f"{name} failed to detect {rule}: {result.stdout}")
                if ci.compare(findings, []):
                    raise ValueError(f"gate accepted new {rule}")
                print(f"{name} negative fixture detected {rule}")
            # Check that a narrow suppression does not hide a nearby security call.
            fixture.write_text('''package fixture
import "os"
func accepted(path string) ([]byte,error) {
    // #nosec G304 -- Synthetic path; prove suppression applies to only this call.
    return os.ReadFile(path)
}
func rejected(path string) ([]byte,error) { return os.ReadFile(path) }
''', encoding="utf-8")
            result = ci.run([ci.tool("gosec"), *flags["gosec"], "./..."], cwd=root)
            findings = ci.parse_findings("gosec", result.stdout)
            if not any(item["context"].startswith("func rejected") for item in findings):
                raise ValueError("gosec suppression hid unrelated call")
            fixture.write_text(fixture.read_text().split("func rejected")[0], encoding="utf-8")
            result = ci.run([ci.tool("gosec"), *flags["gosec"], "./..."], cwd=root)
            if result.returncode or ci.parse_findings("gosec", result.stdout):
                raise ValueError("justified, rule-specific suppression rejected")
            # Includes test-file errors and only infallible buffer exclusions.
            fixture.write_text('package fixture\nimport "bytes"\nfunc accepted() { var b bytes.Buffer; b.WriteString("ok") }\n',
                               encoding="utf-8")
            test = root / "fixture_test.go"
            test.write_text('package fixture\nimport "os"\nfunc rejected() { os.Chdir("not executed") }\n', encoding="utf-8")
            result = ci.run([ci.tool("errcheck"), *flags["errcheck"], "./..."], cwd=root)
            if result.returncode != 1 or len(ci.parse_findings("errcheck", result.stdout)) != 1:
                raise ValueError("errcheck missed test code or rejected an infallible buffer")
            test.unlink()
            result = ci.run([ci.tool("errcheck"), *flags["errcheck"], "./..."], cwd=root)
            if result.returncode:
                raise ValueError("errcheck rejected infallible buffer write")
            fixture.write_text('package fixture\nfunc example() { fmt.Println("not executed") }\n', encoding="utf-8")
            original = fixture.read_bytes()
            result = ci.run([ci.tool("goimports"), "-l", fixture], cwd=root)
            if result.returncode or "fixture.go" not in result.stdout or fixture.read_bytes() != original:
                raise ValueError("goimports failed non-mutating missing-import fixture")
            fixture.write_text('package fixture\nimport "strings"\nfunc example(s string) string {\n first := strings.Split(s,",")[0]\n return first\n}\n',
                               encoding="utf-8")
            result = ci.run(["go", "fix", "-diff", "./..."], cwd=root)
            findings = ci.fix_records(result.stdout)
            if result.returncode != 1 or not findings or "strings.Cut" not in str(findings):
                raise ValueError("go fix failed modernization fixture")
            if ci.compare(findings, []):
                raise ValueError("modernization gate accepted new rewrite")
    print("All real-tool negative and positive fixtures passed")


if __name__ == "__main__":
    main()

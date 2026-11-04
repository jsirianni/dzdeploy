#!/usr/bin/env python3
"""Portable, non-mutating quality gates. See docs/development.md."""
import argparse
from collections import Counter
import difflib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
PLATFORM = sys.platform.replace("win32", "windows")
TOOLS = json.loads((ROOT / "scripts/ci-tools.json").read_text())
BIN = ROOT / ".tools/ci-bin"


def run(args, *, cwd=ROOT, env=None):
    result = subprocess.run([str(arg) for arg in args], cwd=cwd, env=env,
                            capture_output=True, text=True, encoding="utf-8")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result


def tool(name):
    return BIN / (name + (".exe" if os.name == "nt" else ""))


def install():
    BIN.mkdir(parents=True, exist_ok=True)
    for name, module in TOOLS.items():
        result = run(["go", "install", module], env=dict(os.environ, GOBIN=str(BIN)))
        if result.returncode:
            raise ValueError(f"install {name} failed ({result.returncode})")


def relative(filename):
    path = filename.replace("\\", "/")
    prefix = str(ROOT).replace("\\", "/") + "/"
    if path.lower().startswith(prefix.lower()):
        path = path[len(prefix):]
    path = path.removeprefix("github.com/jsirianni/dzdeploy/").removeprefix("./")
    if path.startswith("/") or ".." in Path(path).parts or ":" in path:
        raise ValueError(f"finding outside the checkout: {filename}")
    return path


def source_record(filename, line, rule, message):
    filename = relative(filename)
    lines = (ROOT / filename).read_text(encoding="utf-8").splitlines()
    if line < 1 or line > len(lines):
        raise ValueError(f"invalid finding line: {filename}:{line}")
    # Function/declaration plus exact source and occurrence counts prevent an
    # identical call elsewhere from inheriting a legacy exception.
    context = ""
    for text in lines[:line]:
        if re.match(r"^(func|type|var|const)\b", text):
            context = text.strip()
    return {"file": filename, "context": context, "rule": rule,
            "source": lines[line - 1].strip(), "message": message}


def parse_findings(name, output):
    records = []
    if name == "staticcheck":
        for line in output.splitlines():
            item = json.loads(line)
            loc = item["location"]
            records.append(source_record(loc["file"], loc["line"], item["code"], item["message"]))
    elif name == "revive":
        for item in json.loads(output or "[]"):
            loc = item["Position"]["Start"]
            records.append(source_record(loc["Filename"], loc["Line"], item["RuleName"], item["Failure"]))
    elif name == "gosec":
        report = json.loads(output)
        if any(report.get("Golang errors", {}).values()) or report["Stats"]["files"] == 0:
            raise ValueError("gosec did not successfully load all packages")
        for item in report.get("Issues") or []:
            record = source_record(item["file"], int(item["line"].split("-")[0]),
                                   item["rule_id"], item["details"])
            record["severity"] = item["severity"]
            record["confidence"] = item["confidence"]
            records.append(record)
    elif name == "errcheck":
        for line in output.splitlines():
            match = re.fullmatch(r"(.+):(\d+):(\d+):\s*(.*)", line)
            if not match:
                raise ValueError(f"unrecognized errcheck output: {line}")
            records.append(source_record(match[1], int(match[2]), "unchecked-error", match[4]))
    else:
        raise ValueError(f"unknown analyzer: {name}")
    return records


def key(record):
    return json.dumps(record, sort_keys=True)


def compare(records, baseline):
    expected = Counter(key(item) for item in baseline)
    actual = Counter(key(item) for item in records)
    added = list((actual - expected).elements())
    stale = list((expected - actual).elements())
    for title, items in [("NEW (must fix)", added), ("STALE (remove from baseline)", stale)]:
        for item in sorted(items):
            print(f"{title}: {item}")
    print(f"Legacy findings: {sum((actual & expected).values())}; new: {len(added)}; stale: {len(stale)}")
    return not added and not stale


def debt_gate(name, records, write=False):
    baseline = ROOT / f"scripts/ci-baselines/{name}-{PLATFORM}.json"
    records = sorted(records, key=key)
    # Always retain full findings in logs: a baseline is debt, not a clean bill.
    for record in records:
        print(f"FINDING: {key(record)}")
    report = ROOT / f".tools/ci-reports/{name}-{PLATFORM}.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    if write:
        baseline.parent.mkdir(parents=True, exist_ok=True)
        baseline.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {len(records)} explicit findings to {baseline.relative_to(ROOT)}")
        return
    if not baseline.exists():
        raise ValueError(f"missing {baseline.relative_to(ROOT)}; establish the baseline on {PLATFORM}")
    if not compare(records, json.loads(baseline.read_text(encoding="utf-8"))):
        raise ValueError(f"{name} findings changed; fix new findings and remove resolved debt")


def analyze(name, write=False):
    flags = {
        "staticcheck": ["-f", "json", "./..."],
        "revive": ["-config", "revive.toml", "-formatter", "json", "./..."],
        "errcheck": ["-blank", "-excludeonly", "-exclude", "scripts/errcheck-excludes.txt",
                     "-ignoregenerated", "./..."],
        "gosec": ["-nosec-require-rules", "-nosec-require-justification", "-fmt", "json", "./..."],
    }
    result = run([tool(name), *flags[name]])
    if name != "gosec" and result.stderr:
        raise ValueError(f"{name} wrote unexpected diagnostics to stderr")
    records = parse_findings(name, result.stdout)
    if result.returncode not in (0, 1) or (result.returncode != 0 and not records):
        raise ValueError(f"{name} failed without valid findings ({result.returncode})")
    if result.returncode == 0 and records:
        raise ValueError(f"{name} reported findings without failing")
    debt_gate(name, records, write)


def go_files():
    result = run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", "*.go"])
    if result.returncode:
        raise ValueError("git ls-files failed")
    files = sorted(set(result.stdout.split("\0")) - {""})
    if not files:
        raise ValueError("no Go source files")
    return files


def format_check(write=False):
    files = go_files()
    # Normalize scratch copies: Windows core.autocrlf is not a style issue.
    with tempfile.TemporaryDirectory() as temp:
        scratch = Path(temp)
        for filename in files:
            dest = scratch / filename
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text((ROOT / filename).read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        for filename in ("go.mod", "go.sum"):
            (scratch / filename).write_bytes((ROOT / filename).read_bytes())
        result = run([tool("goimports"), "-w", *files], cwd=scratch)
        if result.returncode:
            raise ValueError("goimports failed")
        changed = []
        for filename in files:
            original = (ROOT / filename).read_bytes()
            before = original.decode("utf-8").replace("\r\n", "\n")
            after = (scratch / filename).read_text(encoding="utf-8")
            if before != after:
                changed.append(filename)
                if write:
                    newline = "\r\n" if b"\r\n" in original else "\n"
                    (ROOT / filename).write_bytes(after.replace("\n", newline).encode("utf-8"))
                else:
                    print("".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                                       fromfile=filename, tofile=filename)), end="")
        print(f"Go formatting/import changes: {len(changed)}")
        if changed and not write:
            raise ValueError("run python scripts/ci.py format --write")


def fix_records(patch):
    records = []
    filename = None
    old_start = 0
    old, new = [], []

    def flush():
        if filename is None:
            return
        for tag, i, j, a, b in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
            if tag == "equal":
                continue
            record = source_record(filename, max(1, old_start + i), "go-fix", "Go modernization available")
            record["source"] = "\n".join(["-" + text for text in old[i:j]] + ["+" + text for text in new[a:b]])
            records.append(record)

    for line in patch.splitlines():
        if line.startswith("--- "):
            flush()
            filename = line[4:].removesuffix(" (old)")
            old, new = [], []
        elif line.startswith("+++ "):
            continue
        elif line.startswith("@@ "):
            flush()
            match = re.match(r"@@ -(\d+)", line)
            if match is None:
                raise ValueError("invalid go fix patch header")
            old_start = int(match[1])
            old, new = [], []
        elif line.startswith("-"):
            old.append(line[1:])
        elif line.startswith("+"):
            new.append(line[1:])
        elif line.startswith(" "):
            old.append(line[1:])
            new.append(line[1:])
        elif line:
            raise ValueError(f"unrecognized go fix output: {line}")
    flush()
    return records


def fix_check(write=False):
    result = run(["go", "fix", "-diff", "./..."])
    if result.stderr:
        raise ValueError("go fix emitted package-load or tool errors")
    records = fix_records(result.stdout)
    if result.returncode not in (0, 1) or (result.returncode != 0 and not result.stdout):
        raise ValueError("go fix failed without a modernization diff")
    debt_gate("fix", records, write)


def coverage_totals(profile):
    lines = profile.splitlines()
    if not lines or lines[0] != "mode: atomic":
        raise ValueError("expected atomic coverage profile")
    totals = {}
    seen = set()
    for line in lines[1:]:
        match = re.fullmatch(r"(.+):\d+\.\d+,\d+\.\d+ (\d+) (\d+)", line)
        if match is None:
            raise ValueError(f"invalid profile block: {line}")
        block, count, hits = match[1], int(match[2]), int(match[3])
        location = line.rsplit(" ", 2)[0]
        if location in seen:
            raise ValueError("duplicate profile block")
        seen.add(location)
        package = relative(block).rsplit("/", 1)[0]
        covered, total = totals.get(package, (0, 0))
        totals[package] = (covered + (count if hits else 0), total + count)
    if not totals:
        raise ValueError("empty coverage profile")
    return {package: {"covered": c, "total": t, "tolerance_bps": 50}
            for package, (c, t) in sorted(totals.items())}


def compare_coverage(actual, expected):
    if actual.keys() != expected.keys():
        raise ValueError(f"coverage package set changed: {actual.keys() ^ expected.keys()}")
    failed = False
    for package, baseline in expected.items():
        measured = actual[package]
        if baseline["total"] <= 0 or measured["total"] <= 0:
            raise ValueError(f"missing statements: {package}")
        if not 0 <= baseline["covered"] <= baseline["total"] or not 0 <= baseline["tolerance_bps"] <= 100:
            raise ValueError(f"invalid baseline: {package}")
        rate = 100 * measured["covered"] / measured["total"]
        floor = 100 * baseline["covered"] / baseline["total"]
        print(f"{package}: {measured['covered']}/{measured['total']} = {rate:.4f}%; baseline {floor:.4f}%")
        if (measured["covered"] * baseline["total"] * 10000 <
                baseline["covered"] * measured["total"] * 10000 -
                baseline["tolerance_bps"] * measured["total"] * baseline["total"]):
            failed = True
    if failed:
        raise ValueError("coverage decreased beyond 0.5 percentage points")


def coverage(write=False):
    with tempfile.TemporaryDirectory() as temp:
        profile = Path(temp) / "coverage.out"
        result = run(["go", "test", "-count=1", "-covermode=atomic", f"-coverprofile={profile}", "./..."])
        print(result.stdout, end="")
        if result.returncode:
            raise ValueError("coverage tests failed")
        actual = coverage_totals(profile.read_text(encoding="utf-8"))
    report = ROOT / f".tools/ci-reports/coverage-{PLATFORM}.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(actual, indent=2) + "\n", encoding="utf-8")
    baseline = ROOT / f"scripts/ci-baselines/coverage-{PLATFORM}.json"
    if write:
        baseline.parent.mkdir(parents=True, exist_ok=True)
        baseline.write_bytes(report.read_bytes())
    compare_coverage(actual, json.loads(baseline.read_text(encoding="utf-8")))


def tidy_check():
    # -modfile keeps the real checkout unchanged; normalized scratch inputs
    # avoid treating Windows autocrlf as a dependency change.
    with tempfile.TemporaryDirectory() as temp:
        scratch = Path(temp)
        for filename in ("go.mod", "go.sum"):
            (scratch / filename).write_text((ROOT / filename).read_text(encoding="utf-8"),
                                           encoding="utf-8", newline="\n")
        result = run(["go", "mod", "tidy", "-modfile=" + str(scratch / "go.mod")])
        if result.returncode:
            raise ValueError("go mod tidy failed")
        for filename in ("go.mod", "go.sum"):
            before = (ROOT / filename).read_text(encoding="utf-8")
            after = (scratch / filename).read_text(encoding="utf-8")
            if before != after:
                print("".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                                  fromfile=filename, tofile=filename)), end="")
                raise ValueError("module files need go mod tidy")


def vulnerabilities():
    for flags in (["-version"], ["./..."]):
        result = run([tool("govulncheck"), *flags])
        print(result.stdout, end="")
        if result.returncode:
            raise ValueError("reachable vulnerability check failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("check", choices=["install", "format", "fix", "coverage", "all", "vulnerabilities", "tidy",
                                         "staticcheck", "revive", "errcheck", "gosec"])
    parser.add_argument("--write", action="store_true", help="explicitly establish baseline or apply formatting")
    args = parser.parse_args()
    os.chdir(ROOT)
    if args.check == "install":
        install()
    elif args.check == "all":
        failures = []
        for check in ("format", "fix", "staticcheck", "revive", "errcheck", "gosec", "coverage"):
            try:
                if check == "format":
                    format_check()
                elif check == "fix":
                    fix_check()
                elif check == "coverage":
                    coverage()
                else:
                    analyze(check)
            except (ValueError, OSError, KeyError) as error:
                print(f"{check}: {error}", file=sys.stderr)
                failures.append(check)
        if failures:
            raise ValueError(f"Failed quality gates: {failures}")
        if PLATFORM == "windows":
            vulnerabilities()
    elif args.check == "tidy":
        tidy_check()
    elif args.check == "vulnerabilities":
        vulnerabilities()
    elif args.check == "format":
        format_check(args.write)
    elif args.check == "fix":
        fix_check(args.write)
    elif args.check == "coverage":
        coverage(args.write)
    else:
        analyze(args.check, args.write)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError) as error:
        print(f"CI gate: {error}", file=sys.stderr)
        sys.exit(1)

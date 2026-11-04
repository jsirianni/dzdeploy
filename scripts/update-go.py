#!/usr/bin/env python3
"""Open a reviewed toolchain update; never select a prerelease or downgrade."""
import json
from pathlib import Path
import re
import urllib.request

URL = "https://go.dev/dl/?mode=json"
VERSION = re.compile(r"^(?:go)?(\d+)\.(\d+)\.(\d+)$")


def parts(value):
    match = VERSION.fullmatch(value)
    if match is None:
        raise ValueError(f"invalid stable Go version: {value}")
    return tuple(map(int, match.groups()))


def update_module(content, releases):
    go = list(re.finditer(r"(?m)^go[ \t]+(\d+\.\d+(?:\.\d+)?)(?=[ \t\r\n]|$)", content))
    toolchain = list(re.finditer(r"(?m)^toolchain[ \t]+(go\d+\.\d+\.\d+)(?=[ \t\r\n]|$)", content))
    all_toolchains = list(re.finditer(r"(?m)^toolchain[ \t]+([^\r\n]+)", content))
    if len(go) != 1 or len(toolchain) > 1 or len(all_toolchains) != len(toolchain):
        raise ValueError("expected one go directive and at most one stable toolchain directive")
    candidates = [item["version"] for item in releases
                  if item.get("stable") is True and item.get("version", "").startswith("go") and VERSION.fullmatch(item["version"])]
    if not candidates:
        raise ValueError("Go release feed contains no stable versions")
    current = go[0][1]
    if len(current.split(".")) == 2:
        current += ".0"
    candidates.append("go" + current)
    if toolchain:
        candidates.append(toolchain[0][1])
    selected = max(candidates, key=parts).removeprefix("go")
    substitutions = [(go[0].start(1), go[0].end(1), selected)]
    if toolchain:
        substitutions.append((toolchain[0].start(1), toolchain[0].end(1), "go" + selected))
    for start, end, value in sorted(substitutions, reverse=True):
        content = content[:start] + value + content[end:]
    return content, selected


def main():
    request = urllib.request.Request(URL, headers={"User-Agent": "dzdeploy-go-updater"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read((4 << 20) + 1)
    if len(data) > 4 << 20:
        raise ValueError("Go release feed exceeds 4 MiB")
    path = Path("go.mod")
    original = path.read_text(encoding="utf-8")
    updated, selected = update_module(original, json.loads(data))
    if updated != original:
        path.write_text(updated, encoding="utf-8")
    print(selected)


if __name__ == "__main__":
    main()

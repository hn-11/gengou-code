#!/usr/bin/env python3
"""Parse every YAML file under .github/ and say which ones do not.

A workflow that does not parse is not a failing build, it is no build:
GitHub loads nothing, every job in it dies at the first step, and the
only place that shows is the run itself. Nothing else in this
repository reads these files, so ruff and pytest both pass over a file
GitHub cannot load at all.

The shape that put this here: a shell line continuation inside a
`run: |` block, indented to the left of the block's own indentation. A
literal block scalar ends at the first line indented less than it, so
the shell text after that point was read as more YAML, and the action
failed to load in seven jobs at once.

Usage:
  python scripts/lint_workflows.py [ROOT]      # default: .github
"""

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def yaml_files(root):
    return sorted(p for p in Path(root).rglob("*")
                  if p.suffix in (".yml", ".yaml") and p.is_file())


def check(root):
    """[(path, error or None)] over every YAML file under `root`."""
    out = []
    for path in yaml_files(root):
        try:
            yaml.safe_load(path.read_text())
            out.append((path, None))
        except yaml.YAMLError as exc:
            # the mark carries the line, which is the whole value here
            out.append((path, str(exc).replace("\n", " ")))
    return out


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / ".github"
    results = check(root)
    if not results:
        print(f"no YAML under {root}")
        return 1
    bad = 0
    for path, err in results:
        rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
        if err is None:
            print(f"ok   {rel}")
        else:
            bad += 1
            print(f"FAIL {rel}: {err}")
    print(f"-- {len(results)} files, {bad} unparsable --")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

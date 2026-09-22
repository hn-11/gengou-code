"""A workflow file GitHub cannot load does not reach a push.

Nothing else in this repository reads .github/, so ruff and the rest of
the suite pass straight over a file GitHub cannot load at all -- and a
workflow that does not parse is not a failing build, it is no build:
every job in it dies at the first step, and the only place that shows
is the run itself. The shape that put this here was a shell line
continuation inside a `run: |` block, indented to the left of the
block's own indentation: a literal block scalar ends at the first line
indented less than it, so the shell text after that point was read as
more YAML and the action failed to load in seven jobs at once.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def test_this_repository_s_own_workflows_parse():
    files = sorted(p for p in (ROOT / ".github").rglob("*")
                   if p.suffix in (".yml", ".yaml") and p.is_file())
    assert files, "no YAML under .github"
    for path in files:
        yaml.safe_load(path.read_text())     # YAMLError == a dead workflow

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

import itertools
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def test_this_repository_s_own_workflows_parse():
    files = sorted(p for p in (ROOT / ".github").rglob("*")
                   if p.suffix in (".yml", ".yaml") and p.is_file())
    assert files, "no YAML under .github"
    for path in files:
        yaml.safe_load(path.read_text())     # YAMLError == a dead workflow


def _job_names(workflow):
    """Every check name a workflow's jobs report: `name:` with each
    `${{ matrix.KEY }}` expanded over the values the matrix gives KEY
    (its own list, plus any `include` entry that sets it)."""
    names = set()
    for job_id, job in workflow["jobs"].items():
        name = job.get("name", job_id)
        keys = re.findall(r"\$\{\{\s*matrix\.(\w+)\s*\}\}", name)
        if not keys:
            names.add(name)
            continue
        matrix = job["strategy"]["matrix"]
        combos = [dict(zip(keys, values)) for values in itertools.product(
            *[matrix.get(k, []) for k in keys])]
        combos += [inc for inc in matrix.get("include", [])
                   if all(k in inc for k in keys)]
        for combo in combos:
            names.add(re.sub(r"\$\{\{\s*matrix\.(\w+)\s*\}\}",
                             lambda m, c=combo: str(c[m.group(1)]), name))
    return names


def test_upstream_sync_waits_only_for_checks_ci_reports():
    # upstream-sync merges its own PR once REQUIRED_CHECKS are green on
    # it; a name ci.yml's jobs never report stays pending, and the sync
    # times out after 30 minutes on every run. Six of the eight names
    # had not existed since ci.yml merged the two families into one job
    wf = ROOT / ".github" / "workflows"
    ci = yaml.safe_load((wf / "ci.yml").read_text())
    sync = yaml.safe_load((wf / "upstream-sync.yml").read_text())
    required = json.loads(sync["env"]["REQUIRED_CHECKS"])
    reported = _job_names(ci)
    assert set(required) <= reported, sorted(set(required) - reported)
    # and the gate is all of CI, not a part of it
    assert reported <= set(required), sorted(reported - set(required))

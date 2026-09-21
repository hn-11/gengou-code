"""Unit tests for scripts/lint_workflows.py — the guard that a workflow
file GitHub cannot load does not reach a push."""

import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import lint_workflows  # noqa: E402

# the exact shape that shipped: a shell continuation inside a `run: |`
# block, indented to the LEFT of the block. The block ends there and the
# rest is read as YAML.
BROKEN = textwrap.dedent("""\
    name: x
    runs:
      steps:
        - run: |
            echo "a line that continues\\
     back at the margin"
            exit 1
    """)
GOOD = textwrap.dedent("""\
    name: x
    runs:
      steps:
        - run: |
            echo "a line that stays inside the block"
            exit 1
    """)


def test_check_flags_a_block_scalar_that_ends_early(tmp_path):
    (tmp_path / "broken.yml").write_text(BROKEN)
    (path, err), = lint_workflows.check(tmp_path)
    assert path.name == "broken.yml"
    assert err is not None


def test_check_passes_a_well_indented_block(tmp_path):
    (tmp_path / "fine.yml").write_text(GOOD)
    assert lint_workflows.check(tmp_path) == [(tmp_path / "fine.yml", None)]


def test_check_reads_yaml_and_yml_and_nothing_else(tmp_path):
    (tmp_path / "a.yml").write_text(GOOD)
    (tmp_path / "b.yaml").write_text(GOOD)
    (tmp_path / "c.txt").write_text("not: [yaml")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "d.yml").write_text(GOOD)
    assert [p.name for p, _ in lint_workflows.check(tmp_path)] == \
        ["a.yml", "b.yaml", "d.yml"]


def test_this_repository_s_own_workflows_parse():
    bad = [(p, e) for p, e in lint_workflows.check(ROOT / ".github") if e]
    assert bad == []


def test_main_returns_nonzero_for_a_broken_tree(tmp_path, capsys):
    (tmp_path / "broken.yml").write_text(BROKEN)
    sys.argv = ["lint_workflows.py", str(tmp_path)]
    assert lint_workflows.main() == 1
    assert "FAIL" in capsys.readouterr().out


def test_main_says_so_when_there_is_nothing_to_check(tmp_path, capsys):
    sys.argv = ["lint_workflows.py", str(tmp_path)]
    assert lint_workflows.main() == 1
    assert "no YAML" in capsys.readouterr().out

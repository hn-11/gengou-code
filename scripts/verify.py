#!/usr/bin/env python3
"""Run the face verifiers over the fonts named, one process each, each
output printed whole once its run ends. Exits non-zero if any run did.

Which gates a font gets is the font's own answer, not its path: a font
with an fvar is the variable Gengou, a font that draws あ is a JP face,
and anything else is a Latin-only face. The rule used to be "latin
somewhere in the path", which made dist/nerd/latin/ work by accident
and would have handed a JP face dropped in that directory the Latin
gates; and a variable font swept up by a pattern was dropped rather
than verified, so the two variable fonts had to be named again in a
step of their own.

Usage:
  python scripts/verify.py FONT [FONT ...]   # globs expanded here too
                                             # (a pattern matching
                                             # nothing is skipped, not
                                             # an error)
"""

import concurrent.futures
import glob
import os
import subprocess
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

SCRIPTS = Path(__file__).resolve().parent
HIRAGANA_A = 0x3042


def gates_for(path):
    """The verifier that holds this font's gates."""
    with TTFont(str(path), lazy=True) as tf:
        if "fvar" in tf:
            # the only variable faces this build makes are the Latin ones
            return "verify_latin_vf.py"
        return "verify_jp.py" if HIRAGANA_A in tf.getBestCmap() else "verify_latin.py"


def run(path):
    gates = gates_for(path)
    proc = subprocess.run([sys.executable, str(SCRIPTS / gates), str(path)],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                          check=False)
    return path, gates, proc.returncode, proc.stdout


def main():
    # a literal path is a named face and must be there; only a pattern is
    # allowed to sweep up nothing. A caller that names a face means that
    # face verified, and a silently dropped argument reported a missing
    # one as a full pass -- which is how the release job, then naming a
    # single Nerd Fonts face, could have checked no patched face at all.
    # An existing path is taken as itself before it is read as a pattern:
    # the variable fonts are named Gengou[wght].otf, where the brackets
    # are a character class that matches nothing
    paths, missing = [], []
    for arg in sys.argv[1:]:
        if Path(arg).exists():
            paths.append(arg)
        elif glob.has_magic(arg):
            paths.extend(sorted(glob.glob(arg)))
        else:
            missing.append(arg)
    if missing:
        sys.exit(f"no such font: {' '.join(missing)}")
    if not paths:
        sys.exit("usage: verify.py FONT [FONT ...] (nothing matched)")
    failed = []
    with concurrent.futures.ThreadPoolExecutor(os.cpu_count() or 2) as pool:
        for path, gates, rc, out in pool.map(run, paths):
            print(f"=== {gates} {path}: {'ok' if rc == 0 else f'FAILED (exit {rc})'}")
            print(out, end="" if out.endswith("\n") else "\n")
            if rc:
                failed.append(path)
    if failed:
        sys.exit(f"{len(failed)}/{len(paths)} verifications failed: {failed}")
    print(f"all {len(paths)} verifications passed")


if __name__ == "__main__":
    main()

"""Round 12, batch B: the same defects on the other drivers."""
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mutlib as M  # noqa: E402
import build  # noqa: E402
import mutants10 as X  # noqa: E402
from r12 import mutant, run_proof, lig_glyph, g, ON  # noqa: E402
from r12 import LAT_REG, JP_REG, JP_TERM, NF_REG, VF_U  # noqa: E402
from r12a import operator_ligatures  # noqa: E402


# ------------------------------------------------------------ L1b
@mutant("L1b", JP_REG, "JP: the '->' ligature rule outputs the '<-' glyph "
                       "(L1 on the driver that has the arrow checks)")
def L1b(tf, src):
    right, left = lig_glyph(src, "->"), lig_glyph(src, "<-")
    n = 0
    for lk in tf["GSUB"].table.LookupList.Lookup:
        kind, subs = build._unwrap(lk)
        if kind != 4:
            continue
        for sub in subs:
            for first, ligs in sub.ligatures.items():
                for lig in ligs:
                    if lig.LigGlyph == right:
                        lig.LigGlyph = left
                        n += 1
    print(f"    ({n} rules repointed {right} -> {left})")


L1b_proof = run_proof("a -> b", feats=ON)


# ------------------------------------------------------------ L2b
@mutant("L2b", JP_REG, "JP: a SinglePos under calt moves every ligature glyph "
                       "+90u right and 90u down (L2 on the JP driver)")
def L2b(tf, src):
    ligs = operator_ligatures(tf, src)
    X.single_pos(tf, ligs, "calt", XPlacement=90, YPlacement=-90)
    print(f"    ({len(ligs)} ligature glyphs moved)")


L2b_proof = run_proof("a != b", feats=ON)


# ------------------------------------------------------------ V1
@mutant("V1", VF_U, "VF: 'a' shifted 60u sideways at the Bold end only (a "
                    "valid CFF2 blend edit, inside check_glyph_placement's "
                    "120u centring band): the letter leans out of its cell "
                    "as the weight axis is dragged up",
        out_name="mutant[wght].otf")
def V1(tf, src):
    print("   ", X._cff2_shift(tf, g(tf, "a"), dx=60, region_peak=1.0))


def V1_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(f"{lbl} wght 700", p, "xax", variations={"wght": 700})

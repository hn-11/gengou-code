"""Round 11, batch C: the mark gates' own inputs."""
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mutlib as M  # noqa: E402
import build  # noqa: E402
import verifylib as V  # noqa: E402
from r11 import mutant, run_proof, g, ON  # noqa: E402
from r11 import LAT_REG, JP_REG, JP_TERM, NF_REG, VF_U  # noqa: E402


def _mkmk_lookups(tf):
    return [(i, subs) for i, kind, subs, _ in V._pos_lookups(tf) if kind == 6]


# ---------------------------------------------------------------- C1
@mutant("C1", LAT_REG, "GDEF MarkGlyphSetsDef + UseMarkFilteringSet on the mkmk "
                       "lookup, with the acute left out of the set: the acute "
                       "never stacks and lands on the grave "
                       "(check_mark_reachability reads MarkAttachmentType only)")
def C1(tf, src):
    cmap = tf.getBestCmap()
    acute = cmap[0x0301]
    gdef = tf["GDEF"].table
    marks = set()
    for i, subs in _mkmk_lookups(tf):
        for sub in subs:
            marks |= set(sub.Mark1Coverage.glyphs) | set(sub.Mark2Coverage.glyphs)
    keep = sorted(marks - {acute}, key=tf.getGlyphID)
    cov = ot.Coverage()
    cov.glyphs = keep
    sets = ot.MarkGlyphSetsDef()
    sets.MarkSetTableFormat = 1
    sets.MarkSetCount = 1
    sets.Coverage = [cov]
    gdef.MarkGlyphSetsDef = sets
    gdef.Version = 0x00010002
    for i, subs in _mkmk_lookups(tf):
        lk = tf["GPOS"].table.LookupList.Lookup[i]
        lk.LookupFlag |= 0x10
        lk.MarkFilteringSet = 0
    print(f"    (mark filtering set of {len(keep)} glyphs, acute {acute} left out)")


C1_proof = run_proof("x̀́", "ẍ́")


# ---------------------------------------------------------------- C2
@mutant("C2", LAT_REG, "GDEF MarkAttachClassDef: the acute moved out of the class "
                       "the mkmk lookup filters on (the same silencing, by the "
                       "route the gate does read)")
def C2(tf, src):
    cmap = tf.getBestCmap()
    gdef = tf["GDEF"].table
    gdef.MarkAttachClassDef.classDefs[cmap[0x0301]] = 2


C2_proof = run_proof("x̀́")


# ---------------------------------------------------------------- C3
@mutant("C3", LAT_REG, "mkmk Mark1 anchors lowered 150u (inside "
                       "check_anchor_placement's 250u band, and the stack gate "
                       "measures sideways only): a stacked accent floats 2.1px high")
def C3(tf, src):
    for i, subs in _mkmk_lookups(tf):
        for sub in subs:
            for rec in sub.Mark1Array.MarkRecord:
                if rec.MarkAnchor is not None:
                    rec.MarkAnchor.YCoordinate -= 150


C3_proof = run_proof("x̀́")

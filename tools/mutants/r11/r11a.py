"""Round 11, batch A: GPOS beyond marks and pairs, and the GSUB kinds
check_substitution_identity does not walk."""
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot
from fontTools.otlLib import builder as otl

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mutlib as M  # noqa: E402
from r11 import mutant, run_proof, g, register, single_pos, ON  # noqa: E402
from r11 import LAT_REG, JP_REG, JP_TERM, NF_REG, VF_U  # noqa: E402


# ---------------------------------------------------------------- A1
@mutant("A1", LAT_REG, "GPOS SinglePos YPlacement -180 on the digits, under ccmp "
                       "(a default-on feature): every digit sits 2.5px low at 14px")
def A1(tf, src):
    digits = [g(tf, c) for c in "0123456789"]
    single_pos(tf, digits, "ccmp", YPlacement=-180)


A1_proof = run_proof("x0y", "2024")


# ---------------------------------------------------------------- A2
@mutant("A2", LAT_REG, "GPOS CursivePos under 'curs' (a HarfBuzz default-on "
                       "horizontal feature): 'l' exit / 'o' entry 260 apart, so "
                       "'o' after 'l' jumps off the baseline")
def A2(tf, src):
    sub = ot.CursivePos()
    sub.Format = 1
    names = [g(tf, "l"), g(tf, "o")]
    sub.Coverage = ot.Coverage()
    sub.Coverage.glyphs = sorted(names, key=tf.getGlyphID)
    sub.EntryExitCount = 2
    sub.EntryExitRecord = []
    for n in sub.Coverage.glyphs:
        r = ot.EntryExitRecord()
        ent = ot.Anchor(); ent.Format = 1
        ent.XCoordinate, ent.YCoordinate = 100, 0
        ex = ot.Anchor(); ex.Format = 1
        ex.XCoordinate, ex.YCoordinate = 500, 260
        r.EntryAnchor, r.ExitAnchor = ent, ex
        sub.EntryExitRecord.append(r)
    lookup = ot.Lookup()
    lookup.LookupType = 3
    lookup.LookupFlag = 0
    lookup.SubTable = [sub]
    lookup.SubTableCount = 1
    register(tf, "GPOS", lookup, "curs")


A2_proof = run_proof("hello", "look")


# ---------------------------------------------------------------- A3
@mutant("A3", LAT_REG, "GSUB MultipleSubst under ccmp: 'ae' decomposes to "
                       "'a'+'e' (two cells where Unicode has one character)")
def A3(tf, src):
    b = otl.MultipleSubstBuilder(tf, None)
    b.mapping[g(tf, "æ")] = [g(tf, "a"), g(tf, "e")]
    register(tf, "GSUB", b.build(), "ccmp")


A3_proof = run_proof("xæy", "æ")


# ---------------------------------------------------------------- A4
@mutant("A4", LAT_REG, "GSUB AlternateSubst under ccmp: 'l' -> '1' "
                       "(a shaper takes alternate 0 of a default feature)")
def A4(tf, src):
    b = otl.AlternateSubstBuilder(tf, None)
    b.alternates[g(tf, "l")] = [g(tf, "1")]
    register(tf, "GSUB", b.build(), "ccmp")


A4_proof = run_proof("hello", "l1")

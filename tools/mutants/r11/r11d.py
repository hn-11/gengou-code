"""Round 11, batch D: what can hide behind check_substitution_identity's
named exceptions, and a couple of metadata probes."""
import math
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.otlLib import builder as otl

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mutlib as M  # noqa: E402
import build  # noqa: E402
from r11 import mutant, run_proof, g, register, single_pos, ON  # noqa: E402
from r11 import LAT_REG, JP_REG, JP_TERM, NF_REG, VF_U  # noqa: E402


# ---------------------------------------------------------------- D1
@mutant("D1", LAT_REG, "ccmp SingleSubst with no context: every 'i' and 'j' "
                       "becomes the dotless letter (hidden behind "
                       "check_substitution_identity's SUBSTITUTED_CHARACTERS)")
def D1(tf, src):
    cmap = tf.getBestCmap()
    b = otl.SingleSubstBuilder(tf, None)
    b.mapping[cmap[ord("i")]] = cmap[0x0131]
    b.mapping[cmap[ord("j")]] = cmap[0x0237]
    register(tf, "GSUB", b.build(), "ccmp")


D1_proof = run_proof("i j", "if join")


# ---------------------------------------------------------------- D2
@mutant("D2", JP_REG, "GPOS SinglePos YPlacement -180 on the kana, under ccmp "
                      "(the same hole as A1, on the JP face)")
def D2(tf, src):
    cmap = tf.getBestCmap()
    kana = [cmap[cp] for cp in range(0x3041, 0x3097) if cp in cmap]
    single_pos(tf, kana, "ccmp", YPlacement=-180)


D2_proof = run_proof("あ一あ")


# ---------------------------------------------------------------- D3
@mutant("D3", LAT_REG, "GPOS SinglePos XPlacement +250 on the comma, period, "
                       "semicolon and colon, under ccmp: the punctuation "
                       "leaves its own column (advance unchanged)")
def D3(tf, src):
    marks = [g(tf, c) for c in ".,;:"]
    single_pos(tf, marks, "ccmp", XPlacement=250)


D3_proof = run_proof("a, b.", "x;y:z")


# ---------------------------------------------------------------- E1
def _cov(glyphs, tf):
    from fontTools.ttLib.tables import otTables as ot
    c = ot.Coverage()
    c.glyphs = sorted(glyphs, key=tf.getGlyphID)
    return c


@mutant("E1", LAT_REG, "GPOS ChainContextPos under ccmp: 'a' before 'b' gains "
                       "300u of advance (contextual kerning; "
                       "check_pair_positioning reads PairPos lookups only)")
def E1(tf, src):
    from fontTools.ttLib.tables import otTables as ot
    from fontTools.otlLib import builder as otl
    inner = otl.SinglePosBuilder(tf, None)
    inner.mapping[g(tf, "a")] = otl.buildValue({"XAdvance": 300})
    nested = inner.build()
    gpos = tf["GPOS"].table
    gpos.LookupList.Lookup.append(nested)
    gpos.LookupList.LookupCount = len(gpos.LookupList.Lookup)
    ni = gpos.LookupList.LookupCount - 1

    sub = ot.ChainContextPos()
    sub.Format = 3
    sub.BacktrackGlyphCount = 0
    sub.BacktrackCoverage = []
    sub.InputGlyphCount = 2
    sub.InputCoverage = [_cov([g(tf, "a")], tf), _cov([g(tf, "b")], tf)]
    sub.LookAheadGlyphCount = 0
    sub.LookAheadCoverage = []
    rec = ot.PosLookupRecord()
    rec.SequenceIndex = 0
    rec.LookupListIndex = ni
    sub.PosLookupRecord = [rec]
    sub.PosCount = 1
    lookup = ot.Lookup()
    lookup.LookupType = 8
    lookup.LookupFlag = 0
    lookup.SubTable = [sub]
    lookup.SubTableCount = 1
    register(tf, "GPOS", lookup, "ccmp")


E1_proof = run_proof("abc", "a b", "table")


# ---------------------------------------------------------------- E2
@mutant("E2", LAT_REG, "every Monaspace ligature glyph raised 110u and moved 35u "
                       "right (inside check_ligature_cells' _LIG_Y 120 / "
                       "_LIG_EDGE 40 bands)")
def E2(tf, src):
    import mutants10 as X
    seen = set()
    for seq, spec in build.LIGATURES.items():
        try:
            name = X.lig_glyph(src, seq)
        except Exception:
            continue
        if name in seen:
            continue
        seen.add(name)
        M.redraw(tf, name, (1, 0, 0, 1, 35, 110))
    M.refit(tf)


E2_proof = run_proof("a -> b", "a - b", "a == b", feats=ON)

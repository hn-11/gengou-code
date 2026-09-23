"""Round 12, batch A: the four gates round 12 added or fixed --
check_ligatures_fire, check_donor_repertoire, check_run_identity and
check_family_cmap through family_reference."""
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mutlib as M  # noqa: E402
import build  # noqa: E402
from r12 import mutant, run_proof, lig_glyph, g, ON  # noqa: E402
from r12 import chain3, wrap, append_lookup, ligature_glyphs, mirror  # noqa: E402
from r12 import LAT_REG, LAT_BOLD, JP_REG, JP_TERM, NF_REG, VF_U  # noqa: E402
import mutants10 as X  # noqa: E402


def operator_ligatures(tf, src):
    """The glyphs the DECLARED operator ligatures shape to (build.LIGATURES),
    and nothing else -- not the ccmp compositions a LigatureSubst also makes."""
    cmap = tf.getBestCmap()
    out = []
    for seq in build.LIGATURES:
        if any(ord(c) not in cmap for c in seq):
            continue
        name = lig_glyph(src, seq)
        if name not in out:
            out.append(name)
    return out


# ------------------------------------------------------------ L1
@mutant("L1", LAT_REG, "the '->' ligature rule outputs the '<-' glyph: "
                       "every arrow in the source points the wrong way")
def L1(tf, src):
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
    print(f"    ({n} ligature rules repointed {right} -> {left})")


L1_proof = run_proof("a -> b", "a <- b", feats=ON)


# ------------------------------------------------------------ L2
@mutant("L2", LAT_REG, "a SinglePos under calt moves every ligature glyph "
                       "+90u right and 90u down: '!=' and '->' sit off their "
                       "cells and touch the letters beside them")
def L2(tf, src):
    ligs = operator_ligatures(tf, src)
    X.single_pos(tf, ligs, "calt", XPlacement=90, YPlacement=-90)
    print(f"    ({len(ligs)} ligature glyphs moved)")


L2_proof = run_proof("a != b", "a -> b", feats=ON)


# ------------------------------------------------------------ L3
@mutant("L3", LAT_REG, "every ligature glyph's outline scaled 0.45 about its "
                       "own centre: '!=' draws as a speck in the middle of "
                       "two empty cells")
def L3(tf, src):
    for name in operator_ligatures(tf, src):
        b = M.bounds(tf.getGlyphSet(), name)
        if b is None:
            continue
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        s = 0.45
        M.redraw(tf, name, (s, 0, 0, s, cx * (1 - s), cy * (1 - s)))
    M.refit(tf)


L3_proof = run_proof("a != b", feats=ON)


# ------------------------------------------------------------ L4 (JP)
@mutant("L4", JP_REG, "JP: every ligature glyph's outline scaled 0.45 about "
                      "its own centre (the same, on the driver whose ligature "
                      "gate round 12 rewrote)")
def L4(tf, src):
    L3(tf, src)


L4_proof = run_proof("a != b", feats=ON)


# ------------------------------------------------------------ F1
@mutant("F1", JP_REG, "the JP face drops 512 kanji (U+4E00..U+4FFF: 不 世 中 "
                      "主 ...) from its cmap: they show as tofu boxes")
def F1(tf, src):
    n = 0
    for t in tf["cmap"].tables:
        if t.isUnicode() and t.format != 14:
            for cp in list(t.cmap):
                if 0x4E00 <= cp <= 0x4FFF:
                    del t.cmap[cp]
                    n += 1
    print(f"    ({n} cmap entries deleted)")


def F1_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        tf = TTFont(str(p))
        cm = tf.getBestCmap()
        print(f"  [{lbl}] {len(cm)} codepoints; 世 mapped: {0x4E16 in cm}")
        M.report_run(lbl, p, "世界")


# ------------------------------------------------------------ F2
@mutant("F2", LAT_REG, "cmap re-pointed: é è ê ë map to the plain 'e' glyph "
                       "(round 10's known re-pointing blind spot, as a control)")
def F2(tf, src):
    plain = g(tf, "e")
    for t in tf["cmap"].tables:
        if t.isUnicode() and t.format != 14:
            for cp in (0xE9, 0xE8, 0xEA, 0xEB):
                if cp in t.cmap:
                    t.cmap[cp] = plain


F2_proof = run_proof("café")


# ------------------------------------------------------------ R1
@mutant("R1", LAT_REG, "a chain-context ccmp rule drops the dot from 'i' after "
                       "'ff': affix, office and difficult lose it "
                       "(check_run_identity shapes singles and PAIRS)")
def R1(tf, src):
    f, i, dotless = g(tf, "f"), g(tf, "i"), g(tf, 0x0131)
    from fontTools.ttLib.tables import otTables as ot
    single = ot.SingleSubst()
    single.mapping = {i: dotless}
    idx = append_lookup(tf, "GSUB", wrap(1, single))
    chain = chain3(6, [[f], [f]], [[i]], [], idx)
    X.register(tf, "GSUB", wrap(6, chain), "ccmp")


R1_proof = run_proof("affix", "office", "i")


# ------------------------------------------------------------ R2
@mutant("R2", LAT_REG, "a chain-context GPOS rule widens the space between two "
                       "letters by 120u: 'hello world' breaks the monospace "
                       "grid (check_run_identity pairs off two characters)")
def R2(tf, src):
    cmap = tf.getBestCmap()
    letters = [cmap[cp] for cp in list(range(0x41, 0x5B)) + list(range(0x61, 0x7B))]
    space = cmap[0x20]
    from fontTools.otlLib import builder as otl
    b = otl.SinglePosBuilder(tf, None)
    b.mapping[space] = otl.buildValue({"XAdvance": 120})
    idx = append_lookup(tf, "GPOS", b.build())
    chain = chain3(8, [letters], [[space]], [letters], idx)
    X.register(tf, "GPOS", wrap(8, chain), "calt")


R2_proof = run_proof("a b", "hello world", feats=ON)


# ------------------------------------------------------------ W1
@mutant("W1", NF_REG, "the Powerline separator U+E0B0 mirrored: every prompt's "
                      "arrow points backwards into the segment before it")
def W1(tf, src):
    cmap = tf.getBestCmap()
    for cp in (0xE0B0,):
        mirror(tf, cmap[cp])
    M.refit(tf)


def W1_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        tf = TTFont(str(p))
        gs = tf.getGlyphSet()
        name = tf.getBestCmap()[0xE0B0]
        import pathops
        pa = pathops.Path()
        gs[name].draw(pa.getPen())
        pa = pathops.simplify(pa)
        # where the ink sits at three heights: a triangle points one way
        print(f"  [{lbl}] U+E0B0 {name} box {tuple(round(v) for v in pa.bounds)}")
        M.report_run(lbl, p, "")


# ------------------------------------------------------------ W2
@mutant("W2", LAT_REG, "the outlines of '0' and 'O' swapped: every zero in "
                       "the source draws as a capital O and back")
def W2(tf, src):
    zero, oh = g(tf, "0"), g(tf, "O")
    td = M.cff_top(tf)
    a, b = td.CharStrings[zero], td.CharStrings[oh]
    td.CharStrings[zero], td.CharStrings[oh] = b, a
    M.refit(tf)


W2_proof = run_proof("0O")


# ------------------------------------------------------------ W3
@mutant("W3", JP_REG, "the kana し mirrored left-to-right inside its own box "
                      "(the advance and the cell are kept)")
def W3(tf, src):
    mirror(tf, g(tf, "し"))
    M.refit(tf)


W3_proof = run_proof("しし")

"""The mutants. `python mutants.py ID [ID ...]` builds each one into
<HERE>/<ID>/mutant.otf, runs the applicable verifier (log in
<ID>/verify.txt), prints the non-hint FAIL lines (none = blind spot),
and prints the ink proof. `python mutants.py list` lists them."""
import copy
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot
from fontTools.otlLib import builder as otl

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mutlib as M  # noqa: E402

DIST = M.REPO / "dist"
LAT_REG = DIST / "latin" / "Gengou-Regular.otf"
LAT_ITA = DIST / "latin" / "Gengou-RegularItalic.otf"
LAT_BOLD = DIST / "latin" / "Gengou-Bold.otf"
JP_REG = DIST / "GengouJP-Regular.otf"
JP_TERM = DIST / "GengouJPTerm-Regular.otf"
NF_REG = DIST / "nerd" / "latin" / "GengouNFM-Regular.otf"
VF_U = DIST / "latin" / "Gengou[wght].otf"
VF_I = DIST / "latin" / "Gengou-Italic[wght].otf"

MUTANTS = {}


def mutant(id_, src, doc):
    def deco(fn):
        MUTANTS[id_] = (src, doc, fn)
        return fn
    return deco


def g(tf, ch):
    return tf.getBestCmap()[ord(ch) if isinstance(ch, str) else ch]


def add_single_pos(tf, glyphs, feature, dx=0, dadv=0):
    """Append a GPOS SinglePos lookup moving `glyphs` by (dx placement,
    dadv advance) and register it under `feature` on every LangSys."""
    gpos = tf["GPOS"].table
    b = otl.SinglePosBuilder(tf, None)
    for gn in glyphs:
        b.mapping[gn] = otl.buildValue({"XPlacement": dx, "XAdvance": dadv})
    lookup = b.build()
    gpos.LookupList.Lookup.append(lookup)
    gpos.LookupList.LookupCount = len(gpos.LookupList.Lookup)
    li = gpos.LookupList.LookupCount - 1
    frs = [fr for fr in gpos.FeatureList.FeatureRecord if fr.FeatureTag == feature]
    if frs:
        for fr in frs:
            fr.Feature.LookupListIndex.append(li)
            fr.Feature.LookupCount = len(fr.Feature.LookupListIndex)
    else:
        fr = ot.FeatureRecord()
        fr.FeatureTag = feature
        fr.Feature = ot.Feature()
        fr.Feature.FeatureParams = None
        fr.Feature.LookupListIndex = [li]
        fr.Feature.LookupCount = 1
        gpos.FeatureList.FeatureRecord.append(fr)
        gpos.FeatureList.FeatureCount = len(gpos.FeatureList.FeatureRecord)
        fi = gpos.FeatureList.FeatureCount - 1
        for sr in gpos.ScriptList.ScriptRecord:
            systems = [sr.Script.DefaultLangSys] + [lr.LangSys for lr in sr.Script.LangSysRecord]
            for ls in systems:
                if ls is None:
                    continue
                ls.FeatureIndex.append(fi)
                ls.FeatureCount = len(ls.FeatureIndex)
    return li


def mark_base_subs(tf):
    import build
    out = []
    for i, lk in enumerate(tf["GPOS"].table.LookupList.Lookup):
        kind, subs = build._unwrap_pos(lk)
        if kind == 4:
            out += [(i, s) for s in subs]
    return out


def move_base_anchor(tf, base, dx, dy, top_only=True):
    """Move every base anchor of `base` in the mark-to-base subtables
    whose rule attaches by the top edge (or all, if not top_only)."""
    import anchors
    gs = tf.getGlyphSet()
    moved = []
    for i, sub in mark_base_subs(tf):
        if base not in sub.BaseCoverage.glyphs:
            continue
        rule = anchors._anchor_rule(gs, sub)
        if top_only and not (rule and rule[0]):
            continue
        rec = sub.BaseArray.BaseRecord[sub.BaseCoverage.glyphs.index(base)]
        for a in rec.BaseAnchor:
            if a is not None:
                a.XCoordinate += dx
                a.YCoordinate += dy
                moved.append((i, a.XCoordinate, a.YCoordinate))
    return moved


# ---------------------------------------------------------------- Latin

@mutant("L1", LAT_REG, "'e' advance 600 -> 1200 (hmtx + charstring width)")
def L1(tf):
    M.set_advance(tf, g(tf, "e"), 1200)
    M.refit(tf)


def L1_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, "hello")


@mutant("L2", LAT_REG, "'e' outline shifted +250u right (lsb/head/hhea refitted)")
def L2(tf):
    M.redraw(tf, g(tf, "e"), (1, 0, 0, 1, 250, 0))
    M.refit(tf)


def L2_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, "beg")


@mutant("L3", LAT_REG, "'3' outline shifted +200u up")
def L3(tf):
    M.redraw(tf, g(tf, "3"), (1, 0, 0, 1, 0, 200))
    M.refit(tf)


def L3_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, "123")


@mutant("L4", LAT_REG, "'->' ligature glyph outline shifted +300u right")
def L4(tf):
    infos, _ = M.shaper(tf.reader.file.name)("a -> b", {"calt": True, "liga": True})
    name = tf.getGlyphOrder()[infos[2].codepoint]
    M.redraw(tf, name, (1, 0, 0, 1, 300, 0))
    M.refit(tf)


def L4_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, "a -> b", {"calt": True, "liga": True})


@mutant("L5", LAT_REG, "GPOS SinglePos XAdvance +100 on 'o' under ccmp")
def L5(tf):
    add_single_pos(tf, [g(tf, "o")], "ccmp", dadv=100)


def L5_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, "foo|")


@mutant("L6", LAT_REG, "GPOS SinglePos XPlacement +250 on 'o' under ccmp")
def L6(tf):
    add_single_pos(tf, [g(tf, "o")], "ccmp", dx=250)


L6_proof = L5_proof


@mutant("L7", LAT_REG, "ccmp: delete the dotless-i chain rule (i + above mark keeps its dot)")
def L7(tf):
    gsub = tf["GSUB"].table
    i_g = g(tf, "i")
    for lk in gsub.LookupList.Lookup:
        if lk.LookupType != 6:
            continue
        keep = []
        for st in lk.SubTable:
            inp = getattr(st, "InputCoverage", None)
            if inp and i_g in inp[0].glyphs and getattr(st, "LookAheadCoverage", None):
                continue      # drop the i-before-mark rule
            keep.append(st)
        if len(keep) != len(lk.SubTable):
            lk.SubTable = keep
            lk.SubTableCount = len(keep)


def L7_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        rows = M.report_run(lbl, p, "í")
        if len(rows) == 2 and rows[0][2] and rows[1][2]:
            print("     ink shared by base and accent:", round(M.overlap_area(rows[0][1], rows[1][1])))


@mutant("L8", LAT_REG, "'o' top base anchors moved 200u DOWN (all classes, top lookups)")
def L8(tf):
    print("   moved:", move_base_anchor(tf, g(tf, "o"), 0, -200))


def L8_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        rows = M.report_run(lbl, p, "ó")
        if len(rows) == 2:
            print("     ink shared by o and acute:", round(M.overlap_area(rows[0][1], rows[1][1])))


@mutant("L9", LAT_REG, "'o' top base anchors moved 250u RIGHT")
def L9(tf):
    print("   moved:", move_base_anchor(tf, g(tf, "o"), 250, 0))


def L9_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, "ö")


@mutant("L10", LAT_ITA, "Italic: drop the raise-after-capital ccmp rule (no .cap forms at all)")
def L10(tf):
    gsub = tf["GSUB"].table
    acute = g(tf, 0x301)
    for lk in gsub.LookupList.Lookup:
        if lk.LookupType != 6:
            continue
        keep = []
        for st in lk.SubTable:
            inp = getattr(st, "InputCoverage", None)
            bt = getattr(st, "BacktrackCoverage", None)
            if inp and bt and acute in inp[0].glyphs and len(bt[0].glyphs) > 100:
                continue
            keep.append(st)
        if len(keep) != len(lk.SubTable):
            lk.SubTable = keep
            lk.SubTableCount = len(keep)


def L10_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, "É")
        M.report_run(lbl, p, "B́")


@mutant("L11", LAT_REG, "cmap: 'b' and 'd' swapped")
def L11(tf):
    for t in tf["cmap"].tables:
        if t.isUnicode() and t.format != 14:
            b, d = t.cmap.get(ord("b")), t.cmap.get(ord("d"))
            if b and d:
                t.cmap[ord("b")], t.cmap[ord("d")] = d, b


def L11_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, "bd")


@mutant("L12", LAT_REG, "'B' .cap-class base anchor moved 200u down")
def L12(tf):
    print("   moved:", move_base_anchor(tf, g(tf, "B"), 0, -200))


def L12_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        rows = M.report_run(lbl, p, "B́")
        if len(rows) == 2:
            print("     ink shared by B and accent:", round(M.overlap_area(rows[0][1], rows[1][1])))


@mutant("L13", LAT_REG, "diaeresis U+0308 outline moved 220u right, anchor left behind")
def L13(tf):
    M.redraw(tf, g(tf, 0x308), (1, 0, 0, 1, 220, 0))
    M.refit(tf)


def L13_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, "ä")


@mutant("L14", LAT_REG, "'o' top base anchors moved 150u down")
def L14(tf):
    print("   moved:", move_base_anchor(tf, g(tf, "o"), 0, -150))


L14_proof = L8_proof


@mutant("L15", LAT_REG, "'a' outline mirrored (flipped) in x inside its box")
def L15(tf):
    name = g(tf, "a")
    b = M.bounds(tf.getGlyphSet(), name)
    M.redraw(tf, name, (-1, 0, 0, 1, b[0] + b[2], 0))
    M.refit(tf)


def L15_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, "a")



@mutant("L5b", LAT_REG, "GPOS SinglePos XAdvance +100 on '0' (a glyph no mark lookup covers) under ccmp")
def L5b(tf):
    add_single_pos(tf, [g(tf, "0")], "ccmp", dadv=100)


def L5b_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, "100|")


@mutant("L12b", LAT_REG, "'B' base anchors moved 140u down (all classes)")
def L12b(tf):
    print("   moved:", move_base_anchor(tf, g(tf, "B"), 0, -140))


L12b_proof = L12_proof


@mutant("L18", LAT_REG, "mkmk: acute's Mark2 anchor moved 200u right (a second accent stacks off to the side)")
def L18(tf):
    import build
    acute = g(tf, 0x301)
    for lk in tf["GPOS"].table.LookupList.Lookup:
        kind, subs = build._unwrap_pos(lk)
        if kind != 6:
            continue
        for st in subs:
            if acute in st.Mark2Coverage.glyphs:
                rec = st.Mark2Array.Mark2Record[st.Mark2Coverage.glyphs.index(acute)]
                for a in rec.Mark2Anchor:
                    if a is not None:
                        a.XCoordinate += 200
                        print("   Mark2 anchor now", a.XCoordinate, a.YCoordinate)


def L18_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        rows = M.report_run(lbl, p, "x\u0301\u0308")
        if len(rows) == 3:
            print("     2nd mark centre - 1st mark centre:", (rows[2][2][0] + rows[2][2][2]) / 2 - (rows[1][2][0] + rows[1][2][2]) / 2,
                  "; 2nd mark xMax past the 600 cell:", rows[2][2][2] - 600)


@mutant("L19", LAT_REG, "'l' outline shifted 250u right (an ascender letter, same as L2 but on a CLEAR base)")
def L19(tf):
    M.redraw(tf, g(tf, "l"), (1, 0, 0, 1, 250, 0))
    M.refit(tf)


def L19_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, "all")


# ------------------------------------------------------------------ JP

@mutant("J1", JP_REG, "JP: 'e' advance 600 -> 1200")
def J1(tf):
    M.set_advance(tf, g(tf, "e"), 1200)
    M.refit(tf)


J1_proof = L1_proof


@mutant("J2", JP_REG, "JP: kanji 日 outline shifted +250u right")
def J2(tf):
    M.redraw(tf, g(tf, "日"), (1, 0, 0, 1, 250, 0))
    M.refit(tf)


def J2_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, "本日本")


@mutant("J3", JP_REG, "JP: 日 vertical advance 1000 -> 1500 (vhea refitted)")
def J3(tf):
    name = g(tf, "日")
    h, tsb = tf["vmtx"].metrics[name]
    tf["vmtx"].metrics[name] = (1500, tsb)
    M.refit(tf)


def J3_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, "本日本", direction="ttb")


@mutant("J3b", JP_REG, "JP: 日 vertical origin (VORG + vmtx tsb) lowered 300u")
def J3b(tf):
    name = g(tf, "日")
    vorg = tf["VORG"]
    cur = vorg.VOriginRecords.get(name, vorg.defaultVertOriginY)
    vorg.VOriginRecords[name] = cur - 300
    vorg.numVertOriginYMetrics = len(vorg.VOriginRecords)
    M.refit(tf)


J3b_proof = J3_proof


@mutant("J4", JP_REG, "JP: vert targets of （ and ） swapped")
def J4(tf):
    import build
    a, b = g(tf, "（"), g(tf, "）")
    for lk in tf["GSUB"].table.LookupList.Lookup:
        kind, subs = build._unwrap(lk)
        if kind != 1:
            continue
        for st in subs:
            if a in st.mapping and b in st.mapping:
                st.mapping[a], st.mapping[b] = st.mapping[b], st.mapping[a]
                print("   swapped in a single-subst subtable")


def J4_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, "（日）", direction="ttb")


@mutant("J5", JP_REG, "JP: fwid of 'B' re-pointed to full-width Ｃ")
def J5(tf):
    import build
    B, C = g(tf, "B"), g(tf, "C")
    fw_C = None
    tags = {}
    gsub = tf["GSUB"].table
    for fr in gsub.FeatureList.FeatureRecord:
        for li in fr.Feature.LookupListIndex:
            tags.setdefault(li, set()).add(fr.FeatureTag)
    for i, lk in enumerate(gsub.LookupList.Lookup):
        if "fwid" not in tags.get(i, ()):
            continue
        kind, subs = build._unwrap(lk)
        if kind != 1:
            continue
        for st in subs:
            if C in st.mapping:
                fw_C = st.mapping[C]
        for st in subs:
            if B in st.mapping and fw_C:
                st.mapping[B] = fw_C
                print("   fwid B ->", fw_C)


def J5_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, "BC", {"fwid": True})


@mutant("J6", JP_REG, "JP: the dakuten U+3099 outline shifted 150u UP (it is unanchored)")
def J6(tf):
    M.redraw(tf, g(tf, 0x3099), (1, 0, 0, 1, 0, 150))
    M.refit(tf)


def J6_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, "ｶ゙")


@mutant("J6b", JP_REG, "JP: the dakuten U+3099 outline shifted 200u RIGHT (into the next cell)")
def J6b(tf):
    M.redraw(tf, g(tf, 0x3099), (1, 0, 0, 1, 200, 0))
    M.refit(tf)


J6b_proof = J6_proof


@mutant("J8", JP_REG, "JP: GPOS SinglePos XAdvance +200 on う under ccmp")
def J8(tf):
    add_single_pos(tf, [g(tf, "う")], "ccmp", dadv=200)


def J8_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, "あうえ")


@mutant("J10", JP_REG, "JP: half-width ｱ outline shifted +250u right")
def J10(tf):
    M.redraw(tf, g(tf, "ｱ"), (1, 0, 0, 1, 250, 0))
    M.refit(tf)


def J10_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, "ｲｱｲ")


@mutant("J11", JP_TERM, "Term: kanji 永 left at its 1000 width (ink 0..1000 in a 1200 cell)")
def J11(tf):
    name = g(tf, "永")
    M.redraw(tf, name, (1, 0, 0, 1, -100, 0))
    M.refit(tf)


def J11_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, "日永日")


@mutant("J12", JP_REG, "JP: cmap が -> the glyph of か (precomposed voiced kana lost)")
def J12(tf):
    for t in tf["cmap"].tables:
        if t.isUnicode() and t.format != 14 and ord("か") in t.cmap:
            t.cmap[ord("が")] = t.cmap[ord("か")]


def J12_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, "かが")


@mutant("J13", JP_REG, "JP: full-width あ's own outline shifted 200u up")
def J13(tf):
    M.redraw(tf, g(tf, "あ"), (1, 0, 0, 1, 0, 200))
    M.refit(tf)


def J13_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, "いあい")



@mutant("J15", JP_TERM, "Term: ｷ dropped from the dist rule that gives the dakuten its Term shift back")
def J15(tf):
    import build
    ki = g(tf, 0xFF77)
    for i, lk in enumerate(tf["GPOS"].table.LookupList.Lookup):
        kind, subs = build._unwrap_pos(lk)
        if kind != 8:
            continue
        for st in subs:
            for cov in (getattr(st, "BacktrackCoverage", None) or []):
                if ki in cov.glyphs:
                    cov.glyphs.remove(ki)
                    print("   removed ki from backtrack of lookup", i)


def J15_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        for text in ("ｶ\u3099", "ｷ\u3099"):
            rows = M.report_run(lbl, p, text)
            if len(rows) == 2:
                print("     ink shared by kana and dakuten:", round(M.overlap_area(rows[0][1], rows[1][1])))


# ---------------------------------------------------------------- Nerd

@mutant("N1", NF_REG, "NFM: icon U+F120 advance 600 -> 1200")
def N1(tf):
    M.set_advance(tf, g(tf, 0xF120), 1200)
    M.refit(tf)


def N1_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, "a")


@mutant("N2", NF_REG, "NFM: icon U+F120 flipped vertically inside its own box")
def N2(tf):
    name = g(tf, 0xF120)
    b = M.bounds(tf.getGlyphSet(), name)
    M.redraw(tf, name, (1, 0, 0, -1, 0, b[1] + b[3]))
    M.refit(tf)


N2_proof = N1_proof


@mutant("N3", NF_REG, "NFM: Powerline U+E0B0 outline shifted 100u right (bleeds into the next cell)")
def N3(tf):
    name = g(tf, 0xE0B0)
    M.redraw(tf, name, (1, 0, 0, 1, 100, 0))
    M.refit(tf)


def N3_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, "a")


# ------------------------------------------------------------------ VF

@mutant("V1", VF_U, "VF: 'e' hmtx advance 600 -> 1200 (CFF2 has no charstring width)")
def V1(tf):
    name = g(tf, "e")
    adv, lsb = tf["hmtx"].metrics[name]
    tf["hmtx"].metrics[name] = (1200, lsb)
    hh = tf["hhea"]
    hh.advanceWidthMax = max(a for a, _ in tf["hmtx"].metrics.values())
    widths = [w for w, _ in tf["hmtx"].metrics.values() if w]
    from fontTools.misc.roundTools import otRound
    tf["OS/2"].xAvgCharWidth = otRound(sum(widths) / len(widths))


def V1_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, "hello", variations={"wght": 400})


@mutant("V2", VF_U, "VF: GPOS SinglePos XAdvance +100 on 'o' under ccmp")
def V2(tf):
    add_single_pos(tf, [g(tf, "o")], "ccmp", dadv=100)


def V2_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, "foo|", variations={"wght": 400})


def _cff2_shift_first_move(tf, name, dy_default=0, dy_region=None):
    """Shift glyph `name` in a CFF2 font by editing the first rmoveto's
    dy: `dy_default` added to the default value, and, with
    `dy_region` = (region peak normalized coord, amount), the delta of
    the region with that peak. Returns what it did."""
    td = M.cff_top(tf)
    cs = td.CharStrings[name]
    cs.decompile()
    prog = cs.program
    store = td.VarStore.otVarStore
    vsindex = 0
    for i, tok in enumerate(prog):
        if tok == "vsindex":
            vsindex = prog[i - 1]
            break
    vd = store.VarData[vsindex]
    regions = [store.VarRegionList.Region[r].VarRegionAxis[0].PeakCoord
               for r in vd.VarRegionIndex]
    k = len(regions)
    for i, tok in enumerate(prog):
        if tok in ("rmoveto", "vmoveto", "hmoveto"):
            if i >= 2 and prog[i - 1] == "blend":
                n = prog[i - 2]
                start = i - 2 - n * (k + 1)
                defaults = prog[start:start + n]
                # rmoveto: [dx dy]; vmoveto: [dy]; hmoveto: [dx]
                if tok == "rmoveto":
                    yi = 1
                elif tok == "vmoveto":
                    yi = 0
                else:
                    raise RuntimeError("first move is hmoveto; not handled")
                prog[start + yi] += dy_default
                if dy_region:
                    peak, amount = dy_region
                    r = regions.index(peak)
                    prog[start + n + yi * k + r] += amount
                return {"n": n, "regions": regions, "defaults": defaults, "tok": tok}
            else:
                # unblended move: constant across the masters
                if tok == "rmoveto":
                    prog[i - 1] += dy_default
                elif tok == "vmoveto":
                    prog[i - 1] += dy_default
                else:
                    raise RuntimeError("first move is hmoveto; not handled")
                if dy_region:
                    raise RuntimeError("first move has no blend; cannot scope to a region")
                return {"tok": tok, "regions": regions, "unblended": True}
    raise RuntimeError("no moveto")


@mutant("V3", VF_U, "VF: 'e' shifted 200u up at every master (CFF2 first-move edit)")
def V3(tf):
    print("   ", _cff2_shift_first_move(tf, g(tf, "e"), dy_default=200))
    # head/hhea are computed by the build from the union over the masters;
    # a +200 on 'e' stays inside the union of the whole glyph set


def V3_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        for w in (400, 365, 700):
            M.report_run(f"{lbl} wght {w}", p, "hello", variations={"wght": w})


@mutant("V4", VF_U, "VF: 'e' shifted 180u up ONLY at the intermediate (Monaspace-floor) master")
def V4(tf):
    td = M.cff_top(tf)
    store = td.VarStore.otVarStore
    peaks = sorted({r.VarRegionAxis[0].PeakCoord for r in store.VarRegionList.Region})
    mid = [p for p in peaks if 0 < p < 1] or [p for p in peaks if -1 < p < 0]
    print("    region peaks:", peaks, "using", mid[0])
    print("   ", _cff2_shift_first_move(tf, g(tf, "e"), dy_region=(mid[0], 180)))


V4_proof = V3_proof




# ---- overrides: proofs on sequences NFC does not compose, and the
# per-master CFF2 edit that converts an unblended first move --------------

def _pair_proof(texts, extra=None):
    def proof(orig, mut):
        for lbl, p in (("orig", orig), ("MUT", mut)):
            for text in texts:
                rows = M.report_run(lbl, p, text)
                if extra and len(rows) >= 2 and all(r[2] for r in rows[:2]):
                    extra(rows)
    return proof


def _overlap_and_gap(rows):
    print("     ink shared by base and mark:", round(M.overlap_area(rows[0][1], rows[1][1])),
          "; mark bottom minus base top:", rows[1][2][1] - rows[0][2][3])


def _dx(rows):
    print("     mark centre - base centre:", (rows[1][2][0] + rows[1][2][2]) / 2 - (rows[0][2][0] + rows[0][2][2]) / 2,
          "; mark xMax past the 600 cell:", rows[1][2][2] - 600)


L7_proof = _pair_proof(["i" + chr(0x310), "i" + chr(0x304) + chr(0x301)], _overlap_and_gap)
L8_proof = _pair_proof(["o" + chr(0x310), "o" + chr(0x313)], _overlap_and_gap)
L14_proof = L8_proof
L9_proof = _pair_proof(["o" + chr(0x310)], _dx)
L13_proof = _pair_proof(["q" + chr(0x308)], _dx)
L10_proof = _pair_proof(["B" + chr(0x301), "K" + chr(0x301)])


def _cff2_shift_first_move(tf, name, dy_default=0, dy_region=None):
    """Shift a CFF2 glyph by editing its first rmoveto's dy. With
    dy_region=(peak, amount) the shift is scoped to the region with that
    peak; an unblended move is turned into a blended one."""
    td = M.cff_top(tf)
    cs = td.CharStrings[name]
    cs.decompile()
    prog = cs.program
    store = td.VarStore.otVarStore
    vsindex = 0
    for i, tok in enumerate(prog):
        if tok == "vsindex":
            vsindex = prog[i - 1]
            break
    vd = store.VarData[vsindex]
    regions = [store.VarRegionList.Region[r].VarRegionAxis[0].PeakCoord
               for r in vd.VarRegionIndex]
    k = len(regions)
    for i, tok in enumerate(prog):
        if tok not in ("rmoveto", "vmoveto", "hmoveto"):
            continue
        if i >= 2 and prog[i - 1] == "blend":
            n = prog[i - 2]
            start = i - 2 - n * (k + 1)
            yi = 1 if tok == "rmoveto" else 0
            if tok == "hmoveto":
                raise RuntimeError("hmoveto first")
            prog[start + yi] += dy_default
            if dy_region:
                prog[start + n + yi * k + regions.index(dy_region[0])] += dy_region[1]
            return {"blended": True, "regions": regions}
        # unblended: rebuild as a blend
        if tok == "rmoveto":
            dx, dy = prog[i - 2], prog[i - 1]
            args = [dx, dy + dy_default]
            n = 2
            deltas = [[0] * k, [0] * k]
            if dy_region:
                deltas[1][regions.index(dy_region[0])] = dy_region[1]
            new = args + deltas[0] + deltas[1] + [n, "blend", "rmoveto"]
            prog[i - 2:i + 1] = new
        elif tok == "vmoveto":
            dy = prog[i - 1]
            deltas = [0] * k
            if dy_region:
                deltas[regions.index(dy_region[0])] = dy_region[1]
            prog[i - 1:i + 1] = [dy + dy_default] + deltas + [1, "blend", "vmoveto"]
        else:
            raise RuntimeError("hmoveto first")
        return {"blended": False, "converted": True, "regions": regions}
    raise RuntimeError("no moveto")


@mutant("V3b", VF_U, "VF: '3' shifted 200u up at every master")
def V3b(tf):
    print("   ", _cff2_shift_first_move(tf, g(tf, "3"), dy_default=200))


def V3b_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        for w in (400, 364.75, 700):
            M.report_run(f"{lbl} wght {w}", p, "123", variations={"wght": w})


@mutant("V4", VF_U, "VF: '3' shifted 250u up ONLY at the intermediate (Monaspace-floor) master")
def V4(tf):
    td = M.cff_top(tf)
    store = td.VarStore.otVarStore
    peaks = sorted({r.VarRegionAxis[0].PeakCoord for r in store.VarRegionList.Region})
    mid = [p for p in peaks if 0 < abs(p) < 1][0]
    print("    region peaks:", peaks, "using", mid)
    print("   ", _cff2_shift_first_move(tf, g(tf, "3"), dy_region=(mid, 250)))


def V4_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        for w in (200, 300, 364.75, 400, 700):
            M.report_run(f"{lbl} wght {w}", p, "123", variations={"wght": w})


@mutant("V4e", VF_U, "VF: 'e' shifted 150u up ONLY at the intermediate master")
def V4e(tf):
    td = M.cff_top(tf)
    store = td.VarStore.otVarStore
    peaks = sorted({r.VarRegionAxis[0].PeakCoord for r in store.VarRegionList.Region})
    mid = [p for p in peaks if 0 < abs(p) < 1][0]
    print("   ", _cff2_shift_first_move(tf, g(tf, "e"), dy_region=(mid, 150)))


def V4e_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        for w in (300, 364.75, 400):
            M.report_run(f"{lbl} wght {w}", p, "hello", variations={"wght": w})


# ------------------------------------------------------------- driver

def build_and_run(id_):
    src, doc, fn = MUTANTS[id_]
    out_dir = M.HERE / id_
    out_dir.mkdir(exist_ok=True)
    out = out_dir / ("mutant" + ("[wght].otf" if "[wght]" in src.name else ".otf"))
    print(f"=== {id_}: {doc}\n    source {src}")
    out.with_suffix(".src").write_text(str(src))
    tf = M.load(src)
    fn(tf)
    tf.save(str(out))
    fails, _ = M.run_verifier(out, out_dir / "verify.txt")
    print(f"    verifier: {M.verifier_for(out)} -> {len(fails)} non-hint FAIL(s)")
    for ln in fails:
        print("      " + ln[:300])
    if not fails:
        print("    *** BLIND SPOT: every gate passed ***")
    proof = globals().get(f"{id_}_proof")
    if proof:
        print("    ink proof:")
        proof(src, out)
    print()
    return fails


def proof_only(id_):
    src, doc, _ = MUTANTS[id_]
    out_dir = M.HERE / id_
    out = out_dir / ("mutant" + ("[wght].otf" if "[wght]" in src.name else ".otf"))
    print(f"=== {id_} (proof only): {doc}")
    globals()[f"{id_}_proof"](src, out)
    print()


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "proof":
        for id_ in args[1:]:
            proof_only(id_)
        sys.exit(0)
    if not args or args == ["list"]:
        for k, (src, doc, _) in MUTANTS.items():
            print(f"{k:5s} {src.name:28s} {doc}")
        sys.exit(0)
    summary = {}
    for id_ in args:
        try:
            summary[id_] = build_and_run(id_)
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            summary[id_] = [f"ERROR {e}"]
    print("SUMMARY")
    for k, v in summary.items():
        print(f"  {k:5s} {'CAUGHT (' + str(len(v)) + ')' if v else 'PASSED ALL GATES  <-- blind spot'}")

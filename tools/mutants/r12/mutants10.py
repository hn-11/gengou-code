"""Round 10 mutants. `python mutants10.py ID [ID ...]` builds each into
<HERE>/<ID>/mutant.otf, runs the applicable verifier (log in
<ID>/verify.txt), prints the non-hint FAIL lines (none = blind spot),
and prints the ink proof. `python mutants10.py list` lists them.
The harness (mutlib.py) is round 9's, copied."""
import io
import sys
from pathlib import Path

import uharfbuzz as hb
from fontTools.misc.roundTools import otRound
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot
from fontTools.otlLib import builder as otl

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mutlib as M  # noqa: E402
import build  # noqa: E402

DIST = M.REPO / "dist"
LAT_REG = DIST / "latin" / "Gengou-Regular.otf"
LAT_BOLD = DIST / "latin" / "Gengou-Bold.otf"
LAT_LIGHT = DIST / "latin" / "Gengou-Light.otf"
JP_REG = DIST / "GengouJP-Regular.otf"
JP_TERM = DIST / "GengouJPTerm-Regular.otf"
NF_REG = DIST / "nerd" / "latin" / "GengouNFM-Regular.otf"
VF_U = DIST / "latin" / "Gengou[wght].otf"

MUTANTS = {}
ON = {"calt": True, "liga": True}


def mutant(id_, src, doc):
    def deco(fn):
        MUTANTS[id_] = (src, doc, fn)
        return fn
    return deco


def g(tf, ch):
    return tf.getBestCmap()[ord(ch) if isinstance(ch, str) else ch]


def lig_glyph(src, seq):
    """The glyph the ligature `seq` shapes to in the face at `src`."""
    tf = TTFont(str(src))
    infos, _ = M.shaper(src)(f"a {seq} b", ON)
    return tf.getGlyphOrder()[infos[2].codepoint]


def register(tf, table, lookup, feature):
    """Append `lookup` to GSUB/GPOS `table` and register it under
    `feature` on every LangSys (adding the feature if absent)."""
    t = tf[table].table
    t.LookupList.Lookup.append(lookup)
    t.LookupList.LookupCount = len(t.LookupList.Lookup)
    li = t.LookupList.LookupCount - 1
    frs = [fr for fr in t.FeatureList.FeatureRecord if fr.FeatureTag == feature]
    if frs:
        for fr in frs:
            fr.Feature.LookupListIndex.append(li)
            fr.Feature.LookupCount = len(fr.Feature.LookupListIndex)
        return li
    fr = ot.FeatureRecord()
    fr.FeatureTag = feature
    fr.Feature = ot.Feature()
    fr.Feature.FeatureParams = None
    fr.Feature.LookupListIndex = [li]
    fr.Feature.LookupCount = 1
    t.FeatureList.FeatureRecord.append(fr)
    t.FeatureList.FeatureCount = len(t.FeatureList.FeatureRecord)
    fi = t.FeatureList.FeatureCount - 1
    for sr in t.ScriptList.ScriptRecord:
        systems = [sr.Script.DefaultLangSys] + [lr.LangSys for lr in sr.Script.LangSysRecord]
        for ls in systems:
            if ls is None:
                continue
            ls.FeatureIndex.append(fi)
            ls.FeatureCount = len(ls.FeatureIndex)
    return li


def pair_pos(tf, g1, g2, feature, **value):
    b = otl.PairPosBuilder(tf, None)
    b.addGlyphPair(None, g1, otl.buildValue(value), g2, otl.buildValue({}))
    return register(tf, "GPOS", b.build(), feature)


def single_pos(tf, glyphs, feature, **value):
    b = otl.SinglePosBuilder(tf, None)
    for gn in glyphs:
        b.mapping[gn] = otl.buildValue(value)
    return register(tf, "GPOS", b.build(), feature)


def scale_about_centre(tf, name, sx, sy=None):
    sy = sx if sy is None else sy
    b = M.bounds(tf.getGlyphSet(), name)
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    M.redraw(tf, name, (sx, 0, 0, sy, cx * (1 - sx), cy * (1 - sy)))
    M.refit(tf)


def set_gdef_class(tf, name, cls):
    tf["GDEF"].table.GlyphClassDef.classDefs[name] = cls


# ------------------------------------------------------------ ink proof

def run_proof(*texts, feats=None, variations=None, direction=None):
    def proof(orig, mut):
        for lbl, p in (("orig", orig), ("MUT", mut)):
            for text in texts:
                M.report_run(lbl, p, text, feats, variations, direction)
    return proof


def hb_extents(path, name, variations=None):
    """HarfBuzz's own glyph extents (it applies the CFF FontMatrix,
    fontTools' glyph set does not)."""
    tf = TTFont(str(path))
    gid = tf.getGlyphID(name)
    font = hb.Font(hb.Face(hb.Blob.from_file_path(str(path))))
    if variations:
        font.set_variations(variations)
    e = font.get_glyph_extents(gid)
    return (e.x_bearing, e.y_bearing + e.height, e.x_bearing + e.width, e.y_bearing)


def ft_bbox(path, ch, size=14):
    """FreeType's rendered bitmap box for `ch` at `size` px (unhinted)."""
    import freetype
    face = freetype.Face(str(path))
    face.set_char_size(size * 64)
    face.load_char(ch, freetype.FT_LOAD_NO_HINTING | freetype.FT_LOAD_RENDER)
    bm = face.glyph.bitmap
    return (face.glyph.bitmap_left, face.glyph.bitmap_top, bm.width, bm.rows,
            face.glyph.advance.x / 64)


# ============================================================== Latin

@mutant("G1", LAT_REG, "'->' ligature glyph shifted +200u right (inside the 230 lean; unencoded)")
def G1(tf, src):
    M.redraw(tf, lig_glyph(src, "->"), (1, 0, 0, 1, 200, 0))
    M.refit(tf)


G1_proof = run_proof("a -> b", "x->y", feats=ON)


@mutant("G1b", LAT_REG, "'->' ligature glyph shifted +250u UP (unencoded: no cell gate reads it)")
def G1b(tf, src):
    M.redraw(tf, lig_glyph(src, "->"), (1, 0, 0, 1, 0, 250))
    M.refit(tf)


G1b_proof = run_proof("a -> b", "a - b", feats=ON)


@mutant("G1c", LAT_REG, "'->' ligature glyph scaled 0.6 about its own centre")
def G1c(tf, src):
    scale_about_centre(tf, lig_glyph(src, "->"), 0.6)


G1c_proof = run_proof("a -> b", "a - b", feats=ON)


@mutant("G2", LAT_REG, "'->' and '<-' ligature outlines swapped (both 2 cells, both draw)")
def G2(tf, src):
    td = M.cff_top(tf)
    a, b = lig_glyph(src, "->"), lig_glyph(src, "<-")
    td.CharStrings[a], td.CharStrings[b] = td.CharStrings[b], td.CharStrings[a]
    M.refit(tf)


G2_proof = run_proof("a -> b", "a <- b", feats=ON)


@mutant("G3", LAT_REG, "GDEF: '?' (no lookup reads it) classed as a MARK -> the shaper zeroes its advance")
def G3(tf, src):
    set_gdef_class(tf, g(tf, "?"), 3)


G3_proof = run_proof("a?b", "ok?")


@mutant("G4", LAT_REG, "GPOS PairPos 'a''b' XAdvance -300 under ccmp (on by default)")
def G4(tf, src):
    pair_pos(tf, g(tf, "a"), g(tf, "b"), "ccmp", XAdvance=-300)


G4_proof = run_proof("abc", "cab")


@mutant("G5", LAT_REG, "GSUB liga: 'r''n' -> the glyph of 'm' (an undeclared ligature on by default)")
def G5(tf, src):
    b = otl.LigatureSubstBuilder(tf, None)
    b.ligatures[(g(tf, "r"), g(tf, "n"))] = g(tf, "m")
    register(tf, "GSUB", b.build(), "liga")


G5_proof = run_proof("burn", "modern", feats=ON)


@mutant("G15", LAT_REG, "GSUB ccmp (on by default): 'l' -> its cv04 serifed variant for every 'l' in running text")
def G15(tf, src):
    b = otl.SingleSubstBuilder(tf, None)
    b.mapping[g(tf, "l")] = "cid00594"
    register(tf, "GSUB", b.build(), "ccmp")


G15_proof = run_proof("hello", "ll", feats=ON)


@mutant("G7", LAT_REG, "hhea/typo ascender 984 -> 1400, descender -273 -> -600 (win metrics still cover the box)")
def G7(tf, src):
    hh, os2 = tf["hhea"], tf["OS/2"]
    hh.ascent, hh.descent = 1400, -600
    os2.sTypoAscender, os2.sTypoDescender = 1400, -600


def G7_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        tf = TTFont(str(p))
        hh, os2 = tf["hhea"], tf["OS/2"]
        line = hh.ascent - hh.descent + hh.lineGap
        print(f"  [{lbl}] hhea {hh.ascent}/{hh.descent}/{hh.lineGap} typo "
              f"{os2.sTypoAscender}/{os2.sTypoDescender}/{os2.sTypoLineGap} win "
              f"{os2.usWinAscent}/{os2.usWinDescent}: line pitch {line}u = "
              f"{M.px(line)}px at 14px (was 1257u = 17.6px)")


@mutant("G8", LAT_REG, "CFF FontDict FontMatrix 0.001 -> 0.0007 (every glyph drawn at 70%; fontTools' glyph set ignores it)")
def G8(tf, src):
    td = M.cff_top(tf)
    td.FDArray[0].FontMatrix = [0.0007, 0, 0, 0.0007, 0, 0]


def G8_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        tf = TTFont(str(p))
        for ch in "He":
            name = g(tf, ch)
            ft = M.bounds(tf.getGlyphSet(), name)
            print(f"  [{lbl}] {ch!r} fontTools box {tuple(round(v) for v in ft)}  "
                  f"HarfBuzz extents {tuple(round(v) for v in hb_extents(p, name))}  "
                  f"FreeType 14px bitmap (left, top, w, h, adv) {ft_bbox(p, ch)}")


@mutant("G9", LAT_REG, "cmap: U+00DF ß dropped from every Unicode subtable (no decomposition: renders .notdef)")
def G9(tf, src):
    for t in tf["cmap"].tables:
        if t.isUnicode() and t.format != 14:
            t.cmap.pop(0xDF, None)


def G9_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        rows = M.report_run(lbl, p, "straße")
        print("     glyph for ß:", rows[4][0], "(glyph 0 = .notdef)" if rows[4][0] == TTFont(str(p)).getGlyphOrder()[0] else "")


@mutant("G10", LAT_BOLD, "Bold: 'e' replaced by the Light face's 'e' (a Light letter in Bold text)")
def G10(tf, src):
    light = TTFont(str(LAT_LIGHT))
    lgs = light.getGlyphSet()
    name = g(tf, "e")
    td = M.cff_top(tf)
    old = td.CharStrings[name]
    old.decompile()
    private = old.private
    adv = tf["hmtx"].metrics[name][0]
    nominal, default = getattr(private, "nominalWidthX", 0), getattr(private, "defaultWidthX", 0)
    pen = T2CharStringPen(None if adv == default else adv - nominal, lgs)
    lgs[g(light, "e")].draw(pen)
    td.CharStrings[name] = pen.getCharString(private=private, globalSubrs=old.globalSubrs)
    M.refit(tf)


def G10_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        tf = TTFont(str(p))
        gs = tf.getGlyphSet()
        # stem of 'e' vs 'o': the widest horizontal run through the
        # x-height middle, as a bar thickness
        for ch in "eo":
            print(f"  [{lbl}] {ch!r} '=' -style bar thickness of the letter's "
                  f"bottom bowl: {build.bar_thickness(tf, g(tf, ch)):.1f}u; box "
                  f"{tuple(round(v) for v in M.bounds(gs, g(tf, ch)))}")


@mutant("G11", LAT_REG, "'e' outline shifted +100u right (under the 120u centre band; 1.4px at 14px)")
def G11(tf, src):
    M.redraw(tf, g(tf, "e"), (1, 0, 0, 1, 100, 0))
    M.refit(tf)


G11_proof = run_proof("hello")


@mutant("G12", LAT_REG, "'o' scaled 0.8 about its own centre (an x-height letter at 80%)")
def G12(tf, src):
    scale_about_centre(tf, g(tf, "o"), 0.8)


G12_proof = run_proof("nono", "xox")


@mutant("G13", LAT_REG, "names: Regular face carrying nameID 6 'Gengou-Bold' and nameID 4 'Gengou Bold'")
def G13(tf, src):
    name = tf["name"]
    for rec in name.names:
        if rec.nameID == 6:
            rec.string = "Gengou-Bold"
        if rec.nameID == 4:
            rec.string = "Gengou Bold"


def G13_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        n = TTFont(str(p))["name"]
        print(f"  [{lbl}] nameID 1/2/4/6/16/17: {[n.getDebugName(i) for i in (1, 2, 4, 6, 16, 17)]} "
              f"usWeightClass {TTFont(str(p))['OS/2'].usWeightClass}")


@mutant("G14", LAT_REG, "GSUB calt: one guard rule dropped (found by search: see guards.py)")
def G14(tf, src):
    import guards
    guards.drop(tf, src)


# ================================================================ Nerd

@mutant("N4", NF_REG, "NFM: Powerline U+E0B0 squeezed to start at x=50 (a 50u = 0.7px seam; 'short' allows 10% of the cell)")
def N4(tf, src):
    name = g(tf, 0xE0B0)
    b = M.bounds(tf.getGlyphSet(), name)
    # x -> 50 + (x - b0) * (b2 - 50 - b0) / (b2 - b0)
    s = (b[2] - 50 - b[0]) / (b[2] - b[0])
    M.redraw(tf, name, (s, 0, 0, 1, 50 - b[0] * s, 0))
    M.refit(tf)


N4_proof = run_proof("ab", "")


@mutant("N5", NF_REG, "NFM: icon U+F120 scaled 1.5x about its centre")
def N5(tf, src):
    scale_about_centre(tf, g(tf, 0xF120), 1.5)


N5_proof = run_proof("ab")


@mutant("N6", NF_REG, "NFM: icon U+F120 moved 100u down")
def N6(tf, src):
    M.redraw(tf, g(tf, 0xF120), (1, 0, 0, 1, 0, -100))
    M.refit(tf)


N6_proof = N5_proof


# ================================================================== JP

@mutant("J20", JP_REG, "JP: GPOS vkrn PairPos あ→て YAdvance -300 (vertical kerning is on by default in a ttb run)")
def J20(tf, src):
    # the pair as a vertical run shapes it: 'vert' swaps あ and て for
    # their vertical forms before any positioning
    infos, _ = M.shaper(src)("あて", direction="ttb")
    order = tf.getGlyphOrder()
    a, b = order[infos[0].codepoint], order[infos[1].codepoint]
    print("    vertical forms", a, b)
    pair_pos(tf, a, b, "vkrn", YAdvance=-300)


J20_proof = run_proof("あて", "あいて", feats={"vkrn": True}, direction="ttb")


@mutant("J21", JP_REG, "JP: GPOS SinglePos XPlacement +300 on 日 under 'vert' (a vertical run draws it off the column)")
def J21(tf, src):
    single_pos(tf, [g(tf, "日")], "vert", XPlacement=300)


J21_proof = run_proof("日本", direction="ttb")


@mutant("J22", JP_REG, "JP: vert targets of 「 and 」 swapped (vertical text opens with the closing bracket)")
def J22(tf, src):
    a, b = g(tf, "「"), g(tf, "」")
    n = 0
    for lk in tf["GSUB"].table.LookupList.Lookup:
        kind, subs = build._unwrap(lk)
        if kind != 1:
            continue
        for st in subs:
            if a in st.mapping and b in st.mapping:
                st.mapping[a], st.mapping[b] = st.mapping[b], st.mapping[a]
                n += 1
    print("    swapped in", n, "single-subst subtables")


J22_proof = run_proof("「あ」", direction="ttb")


@mutant("J22b", JP_REG, "JP: a vert rule added: 日 -> the glyph of 月 (vertical text shows the wrong kanji)")
def J22b(tf, src):
    a, b = g(tf, "日"), g(tf, "月")
    gsub = tf["GSUB"].table
    tags = {}
    for fr in gsub.FeatureList.FeatureRecord:
        for li in fr.Feature.LookupListIndex:
            tags.setdefault(li, set()).add(fr.FeatureTag)
    for i, lk in enumerate(gsub.LookupList.Lookup):
        if not {"vert", "vrt2"} <= tags.get(i, set()):
            continue
        kind, subs = build._unwrap(lk)
        if kind == 1:
            subs[0].mapping[a] = b
            print("    added to lookup", i, sorted(tags[i]))
            return
    raise RuntimeError("no vert+vrt2 single lookup")


J22b_proof = run_proof("日本", "月日", direction="ttb")


@mutant("J23", JP_REG, "JP: one Ideographic Variation Sequence re-pointed at 日's glyph")
def J23(tf, src):
    ivs = [t for t in tf["cmap"].tables if t.format == 14][0]
    for sel, seq in ivs.uvsDict.items():
        for k, (cp, gn) in enumerate(seq):
            if gn is not None and 0x4E00 <= cp <= 0x9FFF and cp != 0x65E5:
                print(f"    U+{cp:04X} U+{sel:04X}: {gn} -> {g(tf, 0x65E5)}")
                seq[k] = (cp, g(tf, 0x65E5))
                J23.seq = chr(cp) + chr(sel)
                return


def J23_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, J23.seq)
        M.report_run(lbl, p, J23.seq[0])


@mutant("J24", JP_REG, "JP: あ scaled 0.75 about its own centre")
def J24(tf, src):
    scale_about_centre(tf, g(tf, "あ"), 0.75)


J24_proof = run_proof("いあい")


@mutant("J26", JP_REG, "JP: half-width ｱ scaled 0.7 about its own centre")
def J26(tf, src):
    scale_about_centre(tf, g(tf, "ｱ"), 0.7)


J26_proof = run_proof("ｲｱｲ")


@mutant("J27", JP_REG, "JP: GDEF: ※ (full width, no lookup reads it) classed as a MARK -> zero advance")
def J27(tf, src):
    set_gdef_class(tf, g(tf, "※"), 3)


J27_proof = run_proof("※注", "a※b")


@mutant("J28", JP_REG, "JP: GPOS PairPos あ→て XAdvance -300 under ccmp")
def J28(tf, src):
    pair_pos(tf, g(tf, "あ"), g(tf, "て"), "ccmp", XAdvance=-300)


J28_proof = run_proof("あて", "あいて")


@mutant("J28b", JP_REG, "JP: GPOS PairPos い→う XAdvance -300 under ccmp (a pair the grid probe does not name)")
def J28b(tf, src):
    pair_pos(tf, g(tf, "い"), g(tf, "う"), "ccmp", XAdvance=-300)


J28b_proof = run_proof("いう", "あいうえ")


@mutant("J29", JP_REG, "JP: the Latin FontDict's FontMatrix 0.001 -> 0.0007 (every Latin letter at 70%; the kanji untouched)")
def J29(tf, src):
    td = M.cff_top(tf)
    fd = td.FDSelect[tf.getGlyphID(g(tf, "H"))]
    td.FDArray[fd].FontMatrix = [0.0007, 0, 0, 0.0007, 0, 0]


G8_proof_jp = G8_proof
J29_proof = G8_proof


@mutant("J30", JP_TERM, "Term: same as G7 -- hhea/typo 1400/-600 (verify.py pins LINE_METRICS: expected CAUGHT)")
def J30(tf, src):
    G7(tf, src)


J30_proof = G7_proof


# ================================================================== VF

def _blend_ctx(tf, name):
    """(charstring, commands, regions) for a CFF2 glyph: programToCommands
    represents a blended argument group as ONE list [defaults..., deltas
    per default..., n]; _unpack/_pack turn that into [(default,
    [deltas])] per argument and back."""
    from fontTools.cffLib.specializer import programToCommands
    td = M.cff_top(tf)
    cs = td.CharStrings[name]
    cs.decompile()
    store = td.VarStore.otVarStore
    vsindex = 0
    for i, tok in enumerate(cs.program):
        if tok == "vsindex":
            vsindex = cs.program[i - 1]
            break
    vd = store.VarData[vsindex]
    regions = [store.VarRegionList.Region[r].VarRegionAxis[0].PeakCoord
               for r in vd.VarRegionIndex]
    cmds = programToCommands(cs.program, getNumRegions=lambda vs: store.VarData[vs or 0].VarRegionCount)
    return cs, cmds, regions


def _unpack(args, k):
    out = []
    for a in args:
        if isinstance(a, list):
            n = a[-1]
            defaults, deltas = a[:n], a[n:-1]
            for j, d in enumerate(defaults):
                out.append((d, list(deltas[j * k:(j + 1) * k])))
        else:
            out.append((a, [0] * k))
    return out


def _pack(pairs):
    if all(not any(ds) for _, ds in pairs):
        return [d for d, _ in pairs]
    lst = [d for d, _ in pairs]
    for _, ds in pairs:
        lst += ds
    return [lst + [len(pairs)]]


def _set_program(cs, cmds):
    from fontTools.cffLib.specializer import commandsToProgram
    cs.program = commandsToProgram(cmds)
    cs.bytecode = None


def _cff2_shift(tf, name, dx=0, dy=0, region_peak=None):
    """Shift a CFF2 glyph by (dx, dy) -- everywhere, or only on the
    region peaking at `region_peak` -- by editing its first moveto."""
    cs, cmds, regions = _blend_ctx(tf, name)
    k = len(regions)
    for j, (op, args) in enumerate(cmds):
        if op not in ("rmoveto", "hmoveto", "vmoveto"):
            continue
        pairs = _unpack(args, k)
        if op == "hmoveto":
            pairs = [pairs[0], (0, [0] * k)]
        elif op == "vmoveto":
            pairs = [(0, [0] * k), pairs[0]]
        for idx, d in ((0, dx), (1, dy)):
            default, deltas = pairs[idx]
            if region_peak is None:
                pairs[idx] = (default + d, deltas)
            else:
                deltas[regions.index(region_peak)] += d
                pairs[idx] = (default, deltas)
        cmds[j] = ("rmoveto", _pack(pairs))
        _set_program(cs, cmds)
        return {"first move": cmds[j], "regions": regions}
    raise RuntimeError("no moveto")


def _cff2_scale_default(tf, name, s):
    """Scale a CFF2 glyph's DEFAULT outline by `s` about its default
    centre, leaving the deltas as they are (what a botched default
    master would do)."""
    cs, cmds, regions = _blend_ctx(tf, name)
    k = len(regions)
    b = M.bounds(tf.getGlyphSet(), name)
    ox, oy = (b[0] + b[2]) / 2 * (1 - s), (b[1] + b[3]) / 2 * (1 - s)
    first = True
    out = []
    for op, args in cmds:
        if op in ("vsindex", "endchar"):
            out.append((op, args))
            continue
        pairs = [(d * s, ds) for d, ds in _unpack(args, k)]
        if first and op in ("rmoveto", "hmoveto", "vmoveto"):
            if op == "hmoveto":
                pairs = [pairs[0], (0, [0] * k)]
            elif op == "vmoveto":
                pairs = [(0, [0] * k), pairs[0]]
            pairs = [(pairs[0][0] + ox, pairs[0][1]), (pairs[1][0] + oy, pairs[1][1])]
            op = "rmoveto"
            first = False
        out.append((op, _pack(pairs)))
    _set_program(cs, out)


@mutant("V10", VF_U, "VF: '->' ligature shifted 200u UP at the intermediate (Monaspace-floor) master only")
def V10(tf, src):
    td = M.cff_top(tf)
    store = td.VarStore.otVarStore
    peaks = sorted({r.VarRegionAxis[0].PeakCoord for r in store.VarRegionList.Region})
    mid = [p for p in peaks if 0 < abs(p) < 1][0]
    print("    region peaks", peaks, "using", mid)
    print("   ", _cff2_shift(tf, lig_glyph(src, "->"), dy=200, region_peak=mid))


def V10_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        for w in (400, 364.75, 300, 200):
            M.report_run(f"{lbl} wght {w}", p, "a -> b", ON, variations={"wght": w})


@mutant("V11", VF_U, "VF: hhea/typo 1400/-600 (same as G7, on the variable font)")
def V11(tf, src):
    G7(tf, src)


V11_proof = G7_proof


@mutant("V12", VF_U, "VF: 'o' default outline scaled 0.8 about its centre (deltas untouched)")
def V12(tf, src):
    name = g(tf, "o")
    _cff2_scale_default(tf, name, 0.8)
    # the derived metadata a build would refit: the default lsb
    b = M.bounds(tf.getGlyphSet(), name)
    adv, _ = tf["hmtx"].metrics[name]
    tf["hmtx"].metrics[name] = (adv, otRound(b[0]))


def V12_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        for w in (400, 300, 700):
            M.report_run(f"{lbl} wght {w}", p, "xox", variations={"wght": w})


# ------------------------------------------------------------- driver

def build_and_run(id_):
    src, doc, fn = MUTANTS[id_]
    out_dir = M.HERE / id_
    out_dir.mkdir(exist_ok=True)
    out = out_dir / ("mutant" + ("[wght].otf" if "[wght]" in src.name else ".otf"))
    print(f"=== {id_}: {doc}\n    source {src}")
    out.with_suffix(".src").write_text(str(src))
    tf = M.load(src)
    fn(tf, src)
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

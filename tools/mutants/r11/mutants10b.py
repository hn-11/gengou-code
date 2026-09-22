"""Round 10, second batch: mutants beyond mutants10.py (which is
imported so its helpers and registry are reused).  Usage as before:
`python mutants10b.py ID [ID ...]`, `list`, `proof ID`.  A mutant may
name its output file (`out_name`) and ask for a sibling copied beside
it (`beside=(path, name)`) so verify.py's Term-vs-JP gate finds it, and
may unset env vars for the verifier run (`unset=(...)`)."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from fontTools.misc.roundTools import otRound
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont
from fontTools.otlLib import builder as otl

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mutlib as M  # noqa: E402
import mutants10 as X  # noqa: E402
import build  # noqa: E402

MUTANTS = X.MUTANTS
EXTRA = {}
ON = X.ON
g, lig_glyph, register, pair_pos, single_pos = X.g, X.lig_glyph, X.register, X.pair_pos, X.single_pos
scale_about_centre, set_gdef_class, run_proof = X.scale_about_centre, X.set_gdef_class, X.run_proof
LAT_REG, LAT_BOLD, JP_REG, JP_TERM, NF_REG, VF_U = X.LAT_REG, X.LAT_BOLD, X.JP_REG, X.JP_TERM, X.NF_REG, X.VF_U


def mutant(id_, src, doc, **kw):
    def deco(fn):
        MUTANTS[id_] = (src, doc, fn)
        EXTRA[id_] = kw
        return fn
    return deco


# ---------------------------------------------------------- helpers

def contours(gs, name):
    """[[(op, args)...]] -- the glyph's contours, subrs decomposed."""
    rec = RecordingPen()
    gs[name].draw(rec)
    out, cur = [], []
    for op, args in rec.value:
        if op == "moveTo" and cur:
            out.append(cur)
            cur = []
        cur.append((op, args))
    if cur:
        out.append(cur)
    return out


def contour_box(c):
    pts = [p for op, args in c for p in args if op != "closePath"]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def rewrite(tf, name, keep, extra=None):
    """Replace `name`'s charstring with the contours `keep` (from
    contours()) plus `extra` (a callable drawing on a pen), keeping the
    advance; hints dropped as any redrawn glyph's are."""
    td = M.cff_top(tf)
    old = td.CharStrings[name]
    old.decompile()
    adv = tf["hmtx"].metrics[name][0]
    private = old.private
    nominal = getattr(private, "nominalWidthX", 0)
    default = getattr(private, "defaultWidthX", 0)
    pen = T2CharStringPen(None if adv == default else adv - nominal, tf.getGlyphSet())
    for c in keep:
        for op, args in c:
            getattr(pen, op)(*args)
    if extra:
        extra(pen)
    td.CharStrings[name] = pen.getCharString(private=private, globalSubrs=old.globalSubrs)


def drop_smallest_contours(tf, name, n):
    cs = contours(tf.getGlyphSet(), name)
    cs.sort(key=lambda c: (lambda b: (b[2] - b[0]) * (b[3] - b[1]))(contour_box(c)))
    dropped = [tuple(round(v) for v in contour_box(c)) for c in cs[:n]]
    rewrite(tf, name, cs[n:])
    M.refit(tf)
    return dropped


def ft_render_box(path, ch, size=14):
    return X.ft_bbox(path, ch, size)


# ============================================================== Latin

@mutant("G20", LAT_REG, "'->' ligature advance 1200 -> 600 (hmtx + charstring)")
def G20(tf, src):
    M.set_advance(tf, lig_glyph(src, "->"), 600)
    M.refit(tf)


G20_proof = run_proof("a -> b", feats=ON)


@mutant("G22", LAT_REG, "cmap: U+00E9 é -> the glyph of 'e' (the precomposed accent lost)")
def G22(tf, src):
    for t in tf["cmap"].tables:
        if t.isUnicode() and t.format != 14 and 0xE9 in t.cmap:
            t.cmap[0xE9] = g(tf, "e")


G22_proof = run_proof("café", "café")


@mutant("G23", LAT_REG, "head.unitsPerEm 1000 -> 2000 (every glyph renders at half size)")
def G23(tf, src):
    tf["head"].unitsPerEm = 2000


def G23_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        print(f"  [{lbl}] upm {TTFont(str(p))['head'].unitsPerEm}; FreeType 14px 'H' (left, top, w, h, adv) {ft_render_box(p, 'H')}")


@mutant("G24", LAT_REG, "CFF: '->' ligature charstring width omitted (takes defaultWidthX 600; hmtx stays 1200)")
def G24(tf, src):
    name = lig_glyph(src, "->")
    td = M.cff_top(tf)
    old = td.CharStrings[name]
    old.decompile()
    pen = T2CharStringPen(None, tf.getGlyphSet())   # None: width omitted
    tf.getGlyphSet()[name].draw(pen)
    td.CharStrings[name] = pen.getCharString(private=old.private, globalSubrs=old.globalSubrs)


def G24_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        tf = TTFont(str(p))
        name = lig_glyph(orig, "->")
        td = M.cff_top(tf)
        cs = td.CharStrings[name]
        cs.decompile()
        w = cs.width if hasattr(cs, "width") else None
        print(f"  [{lbl}] {name} hmtx {tf['hmtx'][name]} CFF width {w}")


@mutant("G25", LAT_REG, ".notdef emptied (an unmapped character renders as nothing, not a box)")
def G25(tf, src):
    rewrite(tf, tf.getGlyphOrder()[0], [])
    M.refit(tf)


def G25_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        tf = TTFont(str(p))
        print(f"  [{lbl}] .notdef box {M.bounds(tf.getGlyphSet(), tf.getGlyphOrder()[0])} advance {tf['hmtx'][tf.getGlyphOrder()[0]]}")
        M.report_run(lbl, p, "aกb")     # Thai ko kai: not in the face


@mutant("G26", LAT_REG, "space given ink: a 100u square at the cell's centre (a dot in every word gap)")
def G26(tf, src):
    def square(pen):
        pen.moveTo((250, 200)); pen.lineTo((350, 200)); pen.lineTo((350, 300)); pen.lineTo((250, 300)); pen.closePath()
    rewrite(tf, g(tf, " "), [], extra=square)
    M.refit(tf)


G26_proof = run_proof("a b")


@mutant("G27", LAT_REG, "'i' loses its dot (the top contour dropped; bounds shrink, no gate reads a lowercase height)")
def G27(tf, src):
    name = g(tf, "i")
    cs = contours(tf.getGlyphSet(), name)
    keep = [c for c in cs if contour_box(c)[1] < 400]
    print("    contours", [tuple(round(v) for v in contour_box(c)) for c in cs], "-> kept", len(keep))
    rewrite(tf, name, keep)
    M.refit(tf)


G27_proof = run_proof("ii", "ıı")


@mutant("G28", LAT_REG, "'o' inner contour dropped (a solid disc; bounds and centre unchanged)")
def G28(tf, src):
    print("    dropped", drop_smallest_contours(tf, g(tf, "o"), 1))


def area_proof(*chars):
    def proof(orig, mut):
        import pathops
        for lbl, p in (("orig", orig), ("MUT", mut)):
            tf = TTFont(str(p))
            gs = tf.getGlyphSet()
            for ch in chars:
                path = pathops.Path()
                gs[g(tf, ch)].draw(path.getPen())
                print(f"  [{lbl}] {ch!r} box {tuple(round(v) for v in M.bounds(gs, g(tf, ch)))} ink area {abs(path.area):.0f}u² contours {len(contours(gs, g(tf, ch)))}")
    return proof


G28_proof = area_proof("o", "e")


@mutant("G28b", LAT_REG, "'B' both counters dropped (a solid B)")
def G28b(tf, src):
    print("    dropped", drop_smallest_contours(tf, g(tf, "B"), 2))


G28b_proof = area_proof("B", "D")


@mutant("G29", LAT_REG, "OS/2 usWeightClass 400 -> 700 on the Regular face (names untouched)")
def G29(tf, src):
    tf["OS/2"].usWeightClass = 700


G29_proof = X.G13_proof


@mutant("G30", LAT_REG, "OS/2 fsSelection BOLD bit set (and REGULAR cleared) on the Regular face")
def G30(tf, src):
    os2 = tf["OS/2"]
    os2.fsSelection = (os2.fsSelection | 0x20) & ~0x40


def G30_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        print(f"  [{lbl}] fsSelection {TTFont(str(p))['OS/2'].fsSelection:#06x} macStyle {TTFont(str(p))['head'].macStyle:#06x}")


@mutant("G31", LAT_REG, "GPOS PairPos 'a''b' XAdvance -300 under 'kern' (the feature the Latin gate names)")
def G31(tf, src):
    pair_pos(tf, g(tf, "a"), g(tf, "b"), "kern", XAdvance=-300)


G31_proof = X.G4_proof


@mutant("G32", LAT_REG, "GSUB liga: '<=' ligature rule dropped (the sequence stays plain)")
def G32(tf, src):
    a, b = g(tf, "<"), g(tf, "=")
    n = 0
    for lk in tf["GSUB"].table.LookupList.Lookup:
        kind, subs = build._unwrap(lk)
        if kind != 4:
            continue
        for st in subs:
            for first, ligs in st.ligatures.items():
                before = len(ligs)
                ligs[:] = [l for l in ligs if not (first == a and l.Component == [b])]
                n += before - len(ligs)
    print("    removed", n, "ligature entries")


G32_proof = run_proof("a <= b", feats=ON)


@mutant("G33", LAT_REG, "hhea/typo lineGap 0 -> 400 (line pitch 1257 -> 1657; ascender/descender untouched)")
def G33(tf, src):
    tf["hhea"].lineGap = 400
    tf["OS/2"].sTypoLineGap = 400


G33_proof = X.G7_proof


# ================================================================ Nerd

def squeeze_y(tf, name, y0, y1):
    b = M.bounds(tf.getGlyphSet(), name)
    s = (y1 - y0) / (b[3] - b[1])
    M.redraw(tf, name, (1, 0, 0, s, 0, y0 - b[1] * s))
    M.refit(tf)


@mutant("N8", NF_REG, "NFM: Powerline U+E0B0 squeezed to y -272..983 (a 1u seam above and below the line box)")
def N8(tf, src):
    squeeze_y(tf, g(tf, 0xE0B0), -272, 983)


def N8_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        tf = TTFont(str(p))
        hh = tf["hhea"]
        print(f"  [{lbl}] U+E0B0 box {tuple(round(v) for v in M.bounds(tf.getGlyphSet(), g(tf, 0xE0B0)))} line box {hh.descent}..{hh.ascent}")


@mutant("N9", NF_REG, "NFM: Powerline U+E0B0 squeezed to y -220..930 (a 53u = 0.7px seam; run WITHOUT NF_SYMBOLS)",
        unset=("NF_SYMBOLS",))
def N9(tf, src):
    squeeze_y(tf, g(tf, 0xE0B0), -220, 930)


N9_proof = N8_proof


@mutant("N9b", NF_REG, "NFM: same as N9, run WITH NF_SYMBOLS (the donor at hand)")
def N9b(tf, src):
    squeeze_y(tf, g(tf, 0xE0B0), -220, 930)


N9b_proof = N8_proof


@mutant("N10", NF_REG, "NFM: icon U+F120 scaled 0.5 about its centre, run WITHOUT NF_SYMBOLS", unset=("NF_SYMBOLS",))
def N10(tf, src):
    scale_about_centre(tf, g(tf, 0xF120), 0.5)


N10_proof = X.N5_proof


# ================================================================== JP

@mutant("J40", JP_TERM, "Term: ※ and ！ left at the JP face's x (not re-centred in the 1200 cell); sibling beside it",
        out_name="GengouJPTerm-Regular.otf", beside=(JP_REG, "GengouJP-Regular.otf"))
def J40(tf, src):
    for ch in "※！":
        M.redraw(tf, g(tf, ch), (1, 0, 0, 1, -100, 0))
    M.refit(tf)


J40_proof = run_proof("※！日")


@mutant("J40b", JP_TERM, "Term: あ left at the JP face's x (control: the sibling gate must catch this)",
        out_name="GengouJPTerm-Regular.otf", beside=(JP_REG, "GengouJP-Regular.otf"))
def J40b(tf, src):
    M.redraw(tf, g(tf, "あ"), (1, 0, 0, 1, -100, 0))
    M.refit(tf)


J40b_proof = run_proof("いあい")


@mutant("J41", JP_REG, "JP: FDSelect of 'e' -> the Ideographs FontDict (its local subr call now reads a kanji subr)")
def J41(tf, src):
    td = M.cff_top(tf)
    td.FDSelect[tf.getGlyphID(g(tf, "e"))] = 12


G_area = area_proof


def J41_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        tf = TTFont(str(p))
        try:
            print(f"  [{lbl}] 'e' box {M.bounds(tf.getGlyphSet(), g(tf, 'e'))}")
        except Exception as e:  # noqa: BLE001
            print(f"  [{lbl}] 'e' draw error: {e!r}")


@mutant("J41b", JP_REG, "JP: FDSelect of '→' (no subr calls) -> the Ideographs FontDict, width re-encoded (only the Private dict differs)")
def J41b(tf, src):
    td = M.cff_top(tf)
    name = g(tf, "→")
    gid = tf.getGlyphID(name)
    old = td.CharStrings[name]
    old.decompile()
    td.FDSelect[gid] = 12
    private = td.FDArray[12].Private
    adv = tf["hmtx"][name][0]
    pen = T2CharStringPen(adv - private.nominalWidthX, tf.getGlyphSet())
    tf.getGlyphSet()[name].draw(pen)
    td.CharStrings[name] = pen.getCharString(private=private, globalSubrs=old.globalSubrs)


def J41b_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        tf = TTFont(str(p))
        td = M.cff_top(tf)
        fd = td.FDSelect[tf.getGlyphID(g(tf, "→"))]
        pr = td.FDArray[fd].Private
        print(f"  [{lbl}] '→' FD {fd} BlueValues {list(getattr(pr, 'BlueValues', []))} StdHW {getattr(pr, 'StdHW', None)} box {M.bounds(tf.getGlyphSet(), g(tf, '→'))}")


@mutant("J42", JP_REG, "JP: VORG.defaultVertOriginY 880 -> 780 (the 217 explicit records stay; vmtx tsb refitted)")
def J42(tf, src):
    tf["VORG"].defaultVertOriginY = 780
    M.refit(tf)


J42_proof = run_proof("日※日", direction="ttb")


@mutant("J43", JP_REG, "JP: the vert rule for っ dropped (the small kana sits bottom-left in vertical text)")
def J43(tf, src):
    a = g(tf, "っ")
    n = 0
    for lk in tf["GSUB"].table.LookupList.Lookup:
        kind, subs = build._unwrap(lk)
        if kind != 1:
            continue
        for st in subs:
            if a in st.mapping:
                del st.mapping[a]
                n += 1
    print("    removed from", n, "single-subst subtables")


J43_proof = run_proof("あっ", direction="ttb")


@mutant("J45", JP_REG, "JP: 日's inner contours dropped (a solid block; bounds unchanged)")
def J45(tf, src):
    name = g(tf, "日")
    cs = contours(tf.getGlyphSet(), name)
    print("    contours", len(cs), [tuple(round(v) for v in contour_box(c)) for c in cs])
    # keep only the largest contour
    print("    dropped", drop_smallest_contours(tf, name, len(cs) - 1))


J45_proof = area_proof("日", "目")


@mutant("J46", JP_REG, "JP: GPOS PairPos ｶ→ｷ XAdvance -200 under ccmp (half-width kana pair)")
def J46(tf, src):
    pair_pos(tf, g(tf, "ｶ"), g(tf, "ｷ"), "ccmp", XAdvance=-200)


J46_proof = run_proof("ｶｷ", "ｶﾞｷ")


@mutant("J47", JP_REG, "JP: cmap: U+30A2 ア -> the glyph of あ (katakana drawn as hiragana)")
def J47(tf, src):
    for t in tf["cmap"].tables:
        if t.isUnicode() and t.format != 14 and 0x30A2 in t.cmap:
            t.cmap[0x30A2] = g(tf, "あ")


J47_proof = run_proof("アあ")


@mutant("J48", JP_REG, "JP: the half-width dakuten ﾞ U+FF9E outline shifted 250u left (into the kana before it; a spacing glyph)")
def J48(tf, src):
    M.redraw(tf, g(tf, 0xFF9E), (1, 0, 0, 1, -250, 0))
    M.refit(tf)


J48_proof = run_proof("ｶﾞｷ")


# ================================================================== VF

@mutant("V13", VF_U, "VF: 'e' shifted 200u UP at the Bold (peak 1.0) region only (valid CFF2 blend edit)")
def V13(tf, src):
    print("   ", X._cff2_shift(tf, g(tf, "e"), dy=200, region_peak=1.0))


def V13_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        for w in (400, 550, 700):
            M.report_run(f"{lbl} wght {w}", p, "he", variations={"wght": w})


@mutant("V14", VF_U, "VF: fvar named instance 'Bold' at wght 650")
def V14(tf, src):
    for i in tf["fvar"].instances:
        if tf["name"].getDebugName(i.subfamilyNameID) == "Bold":
            i.coordinates["wght"] = 650


def V14_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        tf = TTFont(str(p))
        print(f"  [{lbl}] instances {[(tf['name'].getDebugName(i.subfamilyNameID), i.coordinates) for i in tf['fvar'].instances]}")


@mutant("V15", VF_U, "VF: STAT 'Bold' AxisValue 700 -> 650")
def V15(tf, src):
    for av in tf["STAT"].table.AxisValueArray.AxisValue:
        if av.Format == 1 and av.Value == 700:
            av.Value = 650


def V15_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        tf = TTFont(str(p))
        print(f"  [{lbl}] STAT {[(getattr(av, 'Value', None), tf['name'].getDebugName(av.ValueNameID)) for av in tf['STAT'].table.AxisValueArray.AxisValue]}")


@mutant("V16", VF_U, "VF: avar: the 0.333 (Medium) segment mapped to 0.15 instead of 0.259 (Medium renders lighter)")
def V16(tf, src):
    seg = tf["avar"].segments["wght"]
    for k in list(seg):
        if 0.33 < k < 0.34:
            seg[k] = 0.15
    print("    avar", seg)


def V16_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        tf = TTFont(str(p))
        for w in (400, 500, 600):
            print(f"  [{lbl}] wght {w}: '=' bar {build.bar_thickness(tf.getGlyphSet(location={'wght': w}), g(tf, '=')):.1f}u  'l' box {tuple(round(v) for v in M.bounds(tf.getGlyphSet(location={'wght': w}), g(tf, 'l')))}")


# ------------------------------------------------------------- driver

def run_verifier(path, log, unset=()):
    script = M.REPO / "scripts" / M.verifier_for(path)
    un = " ".join(f"unset {v};" for v in unset)
    cmd = f'source {M.ENV} && {un} cd {M.REPO} && python "{script}" "{path}"'
    p = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
    out = p.stdout + p.stderr
    Path(log).write_text(out)
    fails = [ln for ln in out.splitlines()
             if ln.startswith("FAIL") and ln.strip() != "FAILED" and "carries hints" not in ln
             and "carry hints" not in ln]
    if "Traceback" in out:
        fails.append("ERROR: verifier crashed (Traceback in log)")
    return fails, out


def build_and_run(id_):
    src, doc, fn = MUTANTS[id_]
    kw = EXTRA.get(id_, {})
    out_dir = M.HERE / id_
    out_dir.mkdir(exist_ok=True)
    out = out_dir / kw.get("out_name", "mutant" + ("[wght].otf" if "[wght]" in src.name else ".otf"))
    print(f"=== {id_}: {doc}\n    source {src}")
    out.with_suffix(".src").write_text(str(src))
    if "beside" in kw:
        bp, bn = kw["beside"]
        shutil.copy(bp, out_dir / bn)
    tf = M.load(src)
    fn(tf, src)
    tf.save(str(out))
    fails, log = run_verifier(out, out_dir / "verify.txt", kw.get("unset", ()))
    print(f"    verifier: {M.verifier_for(out)} -> {len(fails)} non-hint FAIL(s); "
          f"{sum(1 for l in log.splitlines() if l.startswith('ok'))} ok lines")
    for ln in fails:
        print("      " + ln[:300])
    if not fails:
        print("    *** BLIND SPOT: every gate passed ***")
    proof = globals().get(f"{id_}_proof") or getattr(X, f"{id_}_proof", None)
    if proof:
        print("    ink proof:")
        proof(src, out)
    print()
    return fails


# ---------------------------------------------------------- batch 3

@mutant("G37", LAT_REG, "GSUB 'zero': '0' -> the glyph of 'O' (the slashed-zero variant points at the wrong glyph)")
def G37(tf, src):
    z, o = g(tf, "0"), g(tf, "O")
    gsub = tf["GSUB"].table
    lis = {li for fr in gsub.FeatureList.FeatureRecord if fr.FeatureTag == "zero"
           for li in fr.Feature.LookupListIndex}
    n = 0
    for li in lis:
        kind, subs = build._unwrap(gsub.LookupList.Lookup[li])
        for st in subs:
            if kind == 1 and z in st.mapping:
                st.mapping[z] = o
                n += 1
    print("    re-pointed in", n, "subtables")


G37_proof = run_proof("0O", feats={"zero": True})


@mutant("J51", JP_REG, "JP: GSUB 'hwid': full-width ａ U+FF41 -> the half-width target of ｂ (hwid points at the wrong letter; no encoded form to hold it to)")
def J51(tf, src):
    a, b = g(tf, "ａ"), g(tf, "ｂ")
    gsub = tf["GSUB"].table
    lis = {li for fr in gsub.FeatureList.FeatureRecord if fr.FeatureTag == "hwid"
           for li in fr.Feature.LookupListIndex}
    n = 0
    for li in lis:
        kind, subs = build._unwrap(gsub.LookupList.Lookup[li])
        for st in subs:
            if kind == 1 and a in st.mapping and b in st.mapping:
                print("    was", st.mapping[a], "->", st.mapping[b])
                st.mapping[a] = st.mapping[b]
                n += 1
    print("    re-pointed in", n, "subtables")


J51_proof = run_proof("ａｂ", feats={"hwid": True})


@mutant("J52", JP_REG, "JP: full-width Ａ U+FF21 scaled 0.6 about its centre (a full-width form no size gate reads)")
def J52(tf, src):
    scale_about_centre(tf, g(tf, "Ａ"), 0.6)


J52_proof = run_proof("ＡＢ")


def _cff2_scale_all(tf, name, s):
    """Scale a CFF2 glyph by `s` about its default-location centre at
    EVERY master: defaults and deltas alike (a uniform scaling of the
    whole blend -- a valid edit, unlike scaling the default alone)."""
    cs, cmds, regions = X._blend_ctx(tf, name)
    k = len(regions)
    b = M.bounds(tf.getGlyphSet(), name)
    ox, oy = (b[0] + b[2]) / 2 * (1 - s), (b[1] + b[3]) / 2 * (1 - s)
    first, out = True, []
    for op, args in cmds:
        if op in ("vsindex", "endchar"):
            out.append((op, args))
            continue
        pairs = [(d * s, [x * s for x in ds]) for d, ds in X._unpack(args, k)]
        if first and op in ("rmoveto", "hmoveto", "vmoveto"):
            if op == "hmoveto":
                pairs = [pairs[0], (0, [0] * k)]
            elif op == "vmoveto":
                pairs = [(0, [0] * k), pairs[0]]
            pairs = [(pairs[0][0] + ox, pairs[0][1]), (pairs[1][0] + oy, pairs[1][1])]
            op, first = "rmoveto", False
        out.append((op, X._pack(pairs)))
    X._set_program(cs, out)
    bb = M.bounds(tf.getGlyphSet(), name)
    adv, _ = tf["hmtx"].metrics[name]
    tf["hmtx"].metrics[name] = (adv, otRound(bb[0]))


@mutant("V17", VF_U, "VF: '#' (no anchors, not a letter or digit) shifted 200u UP at the Bold (peak 1.0) region only")
def V17(tf, src):
    print("   ", X._cff2_shift(tf, g(tf, "#"), dy=200, region_peak=1.0))


def V17_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        for w in (400, 550, 700):
            M.report_run(f"{lbl} wght {w}", p, "a#b", variations={"wght": w})


@mutant("V18", VF_U, "VF: '%' scaled 0.6 about its centre at every master (defaults and deltas; a valid uniform scaling)")
def V18(tf, src):
    _cff2_scale_all(tf, g(tf, "%"), 0.6)


def V18_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        for w in (300, 400, 700):
            M.report_run(f"{lbl} wght {w}", p, "a%b", variations={"wght": w})



if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args == ["list"]:
        for k, (src, doc, _) in MUTANTS.items():
            print(f"{k:5s} {src.name:28s} {doc}")
        sys.exit(0)
    if args[0] == "proof":
        for id_ in args[1:]:
            src, doc, _ = MUTANTS[id_]
            kw = EXTRA.get(id_, {})
            out = M.HERE / id_ / kw.get("out_name", "mutant" + ("[wght].otf" if "[wght]" in src.name else ".otf"))
            print(f"=== {id_} (proof only): {doc}")
            (globals().get(f"{id_}_proof") or getattr(X, f"{id_}_proof"))(src, out)
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

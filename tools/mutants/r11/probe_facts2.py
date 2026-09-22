import sys, statistics, unicodedata
sys.path.insert(0, "/home/user/shoyu-code-pro-jp/scripts")
from fontTools.ttLib import TTFont
import build, verifylib
SP = "/tmp/claude-0/-home-user-shoyu-code-pro-jp/608d7d10-1a9e-5fcb-89e6-ebb09688cd94/scratchpad"
tf = TTFont("dist/latin/Gengou-Regular.otf")
cmap = tf.getBestCmap(); rev = {g: c for c, g in cmap.items()}
gs = tf.getGlyphSet()
gpos = tf["GPOS"].table
def vr(v):
    return {k: getattr(v, k) for k in ("XPlacement", "YPlacement", "XAdvance", "YAdvance") if hasattr(v, k)}
for i in (0, 1, 4, 5):
    kind, subs = build._unwrap_pos(gpos.LookupList.Lookup[i])
    for s in subs:
        vals = [s.Value] if s.Format == 1 else s.Value
        print(f"Latin GPOS {i}: cov {s.Coverage.glyphs[:6]}... vals {[vr(v) for v in vals[:3]]}")
# mark base lookups: class counts, and the capitals' class-1 anchors
for i, kind, subs, tags in verifylib._pos_lookups(tf):
    if kind == 4:
        for s in subs:
            marks = [(rev.get(g), g) for g in s.MarkCoverage.glyphs]
            print(f"  lookup {i}: classes {s.ClassCount} marks {len(marks)} bases {len(s.BaseCoverage.glyphs)} rule {verifylib.anchors._anchor_rule(gs, s)} first marks {[(hex(c) if c else g) for c, g in marks[:5]]}")
            if s.ClassCount == 2:
                for gn, rec in list(zip(s.BaseCoverage.glyphs, s.BaseArray.BaseRecord))[:0]:
                    pass
                rows = []
                for gn, rec in zip(s.BaseCoverage.glyphs, s.BaseArray.BaseRecord):
                    cp = rev.get(gn)
                    if cp and unicodedata.category(chr(cp)) == "Lu" and rec.BaseAnchor[1] is not None:
                        b = build._bounds(gs, gn)
                        rows.append((chr(cp), rec.BaseAnchor[0].YCoordinate if rec.BaseAnchor[0] else None, rec.BaseAnchor[1].YCoordinate, round(b[3])))
                print("    capitals (ch, class0 y, class1 y, top):", rows[:8], "n=", len(rows))
                caps = [g for g in s.MarkCoverage.glyphs if g not in rev]
                for g in caps[:3]:
                    rec = s.MarkArray.MarkRecord[s.MarkCoverage.glyphs.index(g)]
                    print("    cap mark", g, "class", rec.Class, "anchor", rec.MarkAnchor.XCoordinate, rec.MarkAnchor.YCoordinate, "box", tuple(round(v) for v in build._bounds(gs, g)))
    if kind == 6:
        for s in subs:
            print(f"  mkmk lookup {i}: mark1 {len(s.Mark1Coverage.glyphs)} mark2 {len(s.Mark2Coverage.glyphs)} classes {s.ClassCount}")
            for g in s.Mark1Coverage.glyphs:
                if rev.get(g) in (0x300, 0x301, 0x308):
                    rec = s.Mark1Array.MarkRecord[s.Mark1Coverage.glyphs.index(g)]
                    b = build._bounds(gs, g)
                    m2 = s.Mark2Array.Mark2Record[s.Mark2Coverage.glyphs.index(g)].Mark2Anchor if g in s.Mark2Coverage.glyphs else None
                    print(f"    U+{rev[g]:04X} {g} mark1 anchor ({rec.MarkAnchor.XCoordinate},{rec.MarkAnchor.YCoordinate}) class {rec.Class} box {tuple(round(v) for v in b)} mark2 anchors {[(a.XCoordinate, a.YCoordinate) if a else None for a in (m2 or [])]}")
gdef = tf["GDEF"].table
mac = gdef.MarkAttachClassDef.classDefs
import collections
print("MarkAttachClassDef classes:", collections.Counter(mac.values()))
print("mkmk flag class:", gpos.LookupList.Lookup[13].LookupFlag >> 8)
# SemiBold names
n = TTFont("dist/latin/Gengou-SemiBold.otf")["name"]
print("SemiBold names", {i: n.getDebugName(i) for i in (1, 2, 4, 6, 16, 17, 21, 22)})
n = TTFont("dist/latin/Gengou-RegularItalic.otf")
print("RegularItalic names", {i: n["name"].getDebugName(i) for i in (1, 2, 4, 6, 16, 17)}, "angle", n["post"].italicAngle, "caret", n["hhea"].caretSlopeRise, n["hhea"].caretSlopeRun)
# hinted face
h = TTFont(SP + "/hinted/Gengou-LightItalic.otf")
td = h["CFF "].cff[h["CFF "].cff.fontNames[0]]
hc = h.getBestCmap()
print("hinted LightItalic: H has hints:", verifylib.glyph_has_hint(td.CharStrings[hc[ord("H")]]), "version", h["name"].getDebugName(5))
# VORG centring rule in JP
jp = TTFont("dist/GengouJP-Regular.otf")
vorg = jp["VORG"]; jgs = jp.getGlyphSet(); jcmap = jp.getBestCmap()
devs = []
for g, o in vorg.VOriginRecords.items():
    b = build._bounds(jgs, g)
    if b:
        devs.append(round((o - 500) - (b[1] + b[3]) / 2, 1))
print("VORG records: origin-500 minus ink centre: min/max", min(devs), max(devs), "n", len(devs))
order = jp.getGlyphOrder()
shape = verifylib.make_shaper("dist/GengouJP-Regular.otf")
for ch in "ー「、。ぁっ":
    infos, pos = shape(ch, {}, script="Hani", language="ja", direction="ttb")
    g = order[infos[0].codepoint]
    print(f"  {ch} ttb -> {g} vorg rec {vorg.VOriginRecords.get(g)} box {tuple(round(v) for v in build._bounds(jgs, g))} vmtx {jp['vmtx'][g]} pos {(pos[0].x_offset, pos[0].y_offset, pos[0].y_advance)}")

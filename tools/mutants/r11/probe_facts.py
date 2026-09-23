import sys
sys.path.insert(0, "/home/user/shoyu-code-pro-jp/scripts")
from fontTools.ttLib import TTFont
import build
for path in ("dist/latin/Gengou-Regular.otf", "dist/GengouJP-Regular.otf", "dist/GengouJPTerm-Regular.otf"):
    tf = TTFont(path)
    print("=====", path)
    gpos = tf["GPOS"].table
    tags = {}
    for fr in gpos.FeatureList.FeatureRecord:
        for li in fr.Feature.LookupListIndex:
            tags.setdefault(li, set()).add(fr.FeatureTag)
    for i, lk in enumerate(gpos.LookupList.Lookup):
        kind, subs = build._unwrap_pos(lk)
        extra = ""
        if kind == 1:
            extra = " ".join(f"{len(s.Coverage.glyphs)}glyphs fmt{s.Format} val={s.Value if s.Format==1 else [v.__dict__ for v in s.Value[:2]]}" for s in subs[:2])
        if kind in (7, 8):
            extra = "ctx"
        print(f"  GPOS lookup {i}: type {kind} flag {lk.LookupFlag:#06x} subs {len(subs)} feats {sorted(tags.get(i, []))} {extra[:150]}")
    gsub = tf["GSUB"].table
    tags = {}
    for fr in gsub.FeatureList.FeatureRecord:
        for li in fr.Feature.LookupListIndex:
            tags.setdefault(li, set()).add(fr.FeatureTag)
    kinds = {}
    for i, lk in enumerate(gsub.LookupList.Lookup):
        kind, subs = build._unwrap(lk)
        kinds.setdefault((kind, tuple(sorted(tags.get(i, [])))), []).append(i)
    for k, v in sorted(kinds.items()):
        print(f"  GSUB type {k[0]} feats {k[1]}: lookups {v[:8]}{'...' if len(v) > 8 else ''} ({len(v)})")
    name = tf["name"]
    print("  names:", {i: name.getDebugName(i) for i in (1, 2, 4, 6, 16, 17)})
    hh, os2, post = tf["hhea"], tf["OS/2"], tf["post"]
    print(f"  italicAngle {post.italicAngle} caret {hh.caretSlopeRise}/{hh.caretSlopeRun} off {hh.caretOffset} win {os2.usWinAscent}/{os2.usWinDescent} fsSel {os2.fsSelection:#x} mac {tf['head'].macStyle:#x}")
    cff = tf["CFF "].cff
    td = cff[cff.fontNames[0]]
    fds = getattr(td, "FDArray", None)
    if fds:
        cmap = tf.getBestCmap()
        for i, fd in enumerate(fds):
            p = fd.Private
            n = sum(1 for g in range(len(tf.getGlyphOrder())) if td.FDSelect[g] == i)
            print(f"  FD {i} {getattr(fd,'FontName','?')}: nominal {getattr(p,'nominalWidthX',0)} default {getattr(p,'defaultWidthX',0)} blues {getattr(p,'BlueValues',None)} StdHW {getattr(p,'StdHW',None)} glyphs {n}")
        for ch in "eHあ日":
            if ord(ch) in cmap:
                print(f"    {ch!r} -> FD {td.FDSelect[tf.getGlyphID(cmap[ord(ch)])]}")
    if "VORG" in tf:
        vorg = tf["VORG"]
        recs = vorg.VOriginRecords
        print(f"  VORG default {vorg.defaultVertOriginY} records {len(recs)}")
        rev = {g: cp for cp, g in tf.getBestCmap().items()}
        gs = tf.getGlyphSet()
        import collections
        hist = collections.Counter(recs.values())
        print("   values:", hist.most_common(12))
        shown = 0
        for g, v in list(recs.items()):
            b = build._bounds(gs, g)
            if shown < 12:
                print(f"    {g} cp={hex(rev[g]) if g in rev else None} origin {v} box {tuple(round(x) for x in b) if b else None} adv {tf['hmtx'][g][0]} vmtx {tf['vmtx'][g]}")
                shown += 1
        vh = tf["vhea"]
        print(f"  vhea asc/desc/gap {vh.ascent}/{vh.descent}/{vh.lineGap}")

#!/usr/bin/env python3
"""Regression test for the variable Gengou (dist/latin/Gengou[wght].otf
/ Gengou-Italic[wght].otf): fvar/STAT/name shape, and that every named
instance shapes ligatures the same way the static faces do and lands on
the same '=' bar / 'A' bounds as the matching static face (when that face
is built), and — with SCP_VF_U / SCP_VF_I set — that the font reproduces
Source Code Pro exactly at and between the named weights.

Usage: python scripts/verify_latin_vf.py [FONT]
  FONT defaults to dist/latin/Gengou[wght].otf.
"""

import io
import os
import sys
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.varLib.models import piecewiseLinearMap

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build  # noqa: E402
import build_latin_vf  # noqa: E402
from verifylib import (  # noqa: E402
    Checker,
    check_coverage_order,
    check_features_work,
    check_gdef_marks,
    check_gdi_family_name,
    check_grid,
    check_heights,
    check_latin_repertoire,
    check_mark_class_closure,
    check_marks,
    check_monospace_metadata,
    check_name_ids,
    check_one_cell,
    check_private,
    check_style_bits,
    check_tables,
    check_version_stamp,
    check_zones,
    ink_spill,
    make_shaper,
    static_faces,
    vf_region_peaks,
)

FONT = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    ROOT / "dist" / "latin" / "Gengou[wght].otf")

# (text, expected glyph count) shaped with calt+liga on: a plain ligature
# ("a -> b"), a context guard holding ("->>" alone: no trailing/leading
# context to trigger the guard's OWN longer match, so plain '-' '>' '>'),
# and a 4-cell true ligature ("<!--", added in 3.3).
LIG_CASES = [("a -> b", 5), ("->>", 3), ("<!--", 1)]
WEIGHTS = [w for w, _ in build.FACES]


def bounds(gs, cmap, ch):
    """Bounds of `ch` drawn from the glyph set `gs` (a font's, or a VF's
    at a location)."""
    pen = BoundsPen(gs)
    gs[cmap[ord(ch)]].draw(pen)
    return pen.bounds


def close(a, b, tol):
    return a is not None and b is not None and all(abs(x - y) <= tol for x, y in zip(a, b))


def scp_reference(italic):
    """(SCP VF, to_scp) — the SCP VF this file was assembled from (env
    SCP_VF_U / SCP_VF_I) and the user wght -> SCP wght pairing
    build_latin_vf builds its axis map from; (None, None) when the env
    is not set."""
    path = os.environ.get("SCP_VF_I" if italic else "SCP_VF_U")
    if not (path and Path(path).exists()):
        return None, None
    scp = TTFont(path)
    weight_pos = build_latin_vf.weight_positions()
    design, breaks = build_latin_vf.scp_design_axis(scp)
    axis = next(a for a in scp["fvar"].axes if a.axisTag == "wght")
    _, _, _, _, to_scp = build_latin_vf.user_axis(weight_pos, design, breaks,
                                                   axis.minValue)
    return scp, to_scp


def master_locations(tf, axis):
    """The user wght of every master in the file, read back from the
    CFF2 VarStore's region peaks through avar and fvar.

    The file has FOUR masters, not three: 200, the Monaspace floor
    (build_latin_vf.mona_floor_wght — 364.75 upright, 381.15 italic,
    at no named instance), 400 and 700. A piecewise-linear blend can
    only turn at a master, so a master is exactly where a corruption
    hides: a build that moved the 61 Monaspace ligatures 600u right at
    the floor master ONLY put '->' 535 units past its own advance
    there, and 219 past it at the Light instance, while the three
    locations this used to probe measured clean."""
    tag = "CFF2" if "CFF2" in tf else "CFF "
    store = getattr(tf[tag].cff[tf[tag].cff.fontNames[0]], "VarStore", None)
    store = getattr(store, "otVarStore", None)
    peaks = {0.0}
    for region in (store.VarRegionList.Region if store else []):
        for i, a in enumerate(region.VarRegionAxis):
            if tf["fvar"].axes[i].axisTag == "wght":
                peaks.add(a.PeakCoord)
    # avar maps normalized -> normalized; invert it, then denormalize
    segments = (tf["avar"].segments.get("wght") if "avar" in tf else None) or {}
    back = {v: k for k, v in segments.items()}
    out = set()
    for peak in peaks:
        n = piecewiseLinearMap(peak, back) if back else peak
        out.add(axis.defaultValue + n * ((axis.defaultValue - axis.minValue)
                                         if n < 0 else
                                         (axis.maxValue - axis.defaultValue)))
    return sorted(out)


def main():
    tf = TTFont(str(FONT))
    check = Checker()

    name = tf["name"]
    axis = (next((a for a in tf["fvar"].axes if a.axisTag == "wght"), None)
            if "fvar" in tf else None)
    if not check(axis is not None, "fvar present with a wght axis"):
        print("FAILED (not a variable font; nothing else to check)")
        sys.exit(1)
    hi = build.WEIGHT_CLASS["Bold"]
    check((axis.minValue, axis.maxValue) == (200, hi),
          f"wght axis range {axis.minValue:.0f}-{axis.maxValue:.0f} (want 200-{hi})")
    check(axis.defaultValue == build.WEIGHT_CLASS["Regular"],
          f"wght axis default {axis.defaultValue:.0f} (want 400 = Regular)")
    check(tf["OS/2"].usWeightClass == axis.defaultValue,
          f"OS/2 usWeightClass {tf['OS/2'].usWeightClass} == fvar default")
    check("avar" in tf and "wght" in tf["avar"].segments,
          "avar maps the usWeightClass axis onto SCP's bar-matched wghts")
    instances = tf["fvar"].instances
    styles = [name.getDebugName(i.subfamilyNameID) for i in instances]
    check(len(instances) == len(WEIGHTS), f"{len(instances)} named instances (want {len(WEIGHTS)}): {styles}")
    # ... and they are NAMED: only the count was asserted, so a VF whose
    # menu read "Weight 300" passed — and then failed to find the
    # matching static face below, which was a silent skip too
    want_styles = [("Italic" if w == "Regular" else w + " Italic")
                   if "Italic" in (name.getDebugName(2) or "") else w
                   for w in WEIGHTS]
    check(styles == want_styles,
          f"named instances are the family's styles ({styles}, want {want_styles})")
    want_coords = [float(build.WEIGHT_CLASS[w]) for w in WEIGHTS]
    got_coords = [i.coordinates.get("wght") for i in instances]
    check(got_coords == want_coords,
          f"named instances at usWeightClass wghts {got_coords} (want {want_coords})")

    # the default instance must carry nameID 6 itself
    # (build_latin_vf.name_default_instance_by_font, for
    # opentype/varfont/valid_default_instance_nameids): nothing read it
    default_inst = [i for i in instances
                    if i.coordinates.get("wght") == axis.defaultValue]
    check(len(default_inst) == 1
          and getattr(default_inst[0], "postscriptNameID", None) == 6,
          f"the default instance's PostScript name is nameID 6 "
          f"({[getattr(i, 'postscriptNameID', None) for i in default_inst]})")

    check("STAT" in tf, "STAT present")
    if "STAT" in tf:
        stat = tf["STAT"].table
        wght_axis = next((i for i, a in enumerate(stat.DesignAxisRecord.Axis)
                          if a.AxisTag == "wght"), None)
        ital_axis = next((i for i, a in enumerate(stat.DesignAxisRecord.Axis)
                          if a.AxisTag == "ital"), None)
        check(wght_axis is not None and ital_axis is not None,
              "STAT declares wght and ital design axes")
        wght_values = [av for av in stat.AxisValueArray.AxisValue
                       if getattr(av, "AxisIndex", None) == wght_axis]
        ital_values = [av for av in stat.AxisValueArray.AxisValue
                       if getattr(av, "AxisIndex", None) == ital_axis]
        check(len(wght_values) == len(WEIGHTS), f"STAT has {len(wght_values)} wght values (want {len(WEIGHTS)})")
        stat_vals = sorted(av.Value for av in wght_values)
        check(stat_vals == sorted(want_coords),
              f"STAT wght values {stat_vals} == the static faces' usWeightClass values")
        check(len(ital_values) == 1, f"STAT has {len(ital_values)} ital value (want 1)")
        elidable = [av for av in wght_values if av.Flags & 0x2]
        check(len(elidable) == 1
              and name.getDebugName(elidable[0].ValueNameID) == "Regular",
              "Regular is the elidable wght value")
        # and it is THIS file's slope: only the count was read, so the
        # upright font declaring itself italic passed
        want_ital = 1 if "Italic" in (name.getDebugName(2) or "") else 0
        got_ital = [(av.Value, name.getDebugName(av.ValueNameID))
                    for av in ital_values]
        check(got_ital == [(want_ital, "Italic" if want_ital else "Regular")],
              f"STAT ital value is this file's slope ({got_ital})")
        if not want_ital and ital_values:
            av = ital_values[0]
            check(av.Flags & 0x2 and getattr(av, "LinkedValue", None) == 1,
                  f"STAT upright ital value is elidable and links to Italic "
                  f"(Flags={av.Flags:#04x}, "
                  f"LinkedValue={getattr(av, 'LinkedValue', None)})")

    fam, sub = name.getDebugName(1), name.getDebugName(2)
    ps6, ps25 = name.getDebugName(6), name.getDebugName(25)
    is_italic = sub == "Italic"
    check(fam == "Gengou", f"nameID1 family {fam!r}")
    check(sub in ("Regular", "Italic"), f"nameID2 subfamily {sub!r}")
    check(ps6 == f"Gengou-{'Italic' if is_italic else 'Roman'}",
          f"nameID6 PostScript name {ps6!r}")
    check(ps25 == "Gengou", f"nameID25 variations PS prefix {ps25!r}")
    check(name.getDebugName(16) is None and name.getDebugName(17) is None,
          "no nameID 16/17 (fvar+STAT already describe the family)")
    n0 = name.getDebugName(0) or ""
    check("Source Code Pro:" in n0 and "Monaspace:" in n0,
          "nameID 0 credits Source Code Pro and Monaspace")

    # (the win metrics: GDI clips to these. Deleting
    # build_latin.fit_win_metrics from the VF build left 984/273 against
    # a 1060/-454 box — 76u of ascender and 181u of descender cut off —
    # and every check here still passed)
    check_monospace_metadata(tf, check)
    hhea = tf["hhea"]
    # head / hhea extents must hold every instance, not just the default
    # one a CFF2 glyph set draws (build_latin_vf.py unions the masters):
    # the union of the whole glyph set at both axis ends and the default.
    # Every location below is read off the VF's own glyph set
    # (getGlyphSet(location=): fontTools blends the outlines on the fly,
    # unrounded — the instancer's per-operand rounding drifts an outline
    # by up to 1u along a path, see build_latin_vf.py); nothing is
    # instanced, and HarfBuzz shapes the VF itself at each location
    union = rsb = None
    metrics = tf["hmtx"].metrics     # no HVAR: advances are the same everywhere

    # the three things verify_latin.py checks on a static face and this
    # never did: the repertoire, the grid, and the feature surface. The
    # two variable fonts are the whole of Gengou.zip, and this is their
    # only gate — a VF that lost every codepoint above U+024F, or every
    # stylistic set, passed here while the same loss on a static face
    # failed three checks
    vf_cmap = tf.getBestCmap()
    check_latin_repertoire(check, vf_cmap)
    # the tables verify_latin.py has gated since round 43 and this file
    # never read: a VF with embedding restricted, the vendor id blanked,
    # the range bits or the char-index range zeroed, or both format-4
    # cmap subtables deleted, passed here — and these two files ARE
    # Gengou.zip. head's box is checked below instead, against every
    # instance: a VF's box is the union over its masters, not one
    # location's ink
    check_tables(tf, check, None, None, vf_cmap, codepages=True)
    for tbl in ("vhea", "vmtx", "VORG", "DSIG"):
        check(tbl not in tf, f"no {tbl} table")
    vf_gpos = {fr.FeatureTag for fr in tf["GPOS"].table.FeatureList.FeatureRecord} \
        if "GPOS" in tf else set()
    check("mark" in vf_gpos and "kern" not in vf_gpos,
          f"GPOS keeps SCP's mark positioning, no kern ({sorted(vf_gpos)})")
    check_gdef_marks(tf, check, vf_cmap)
    check_coverage_order(tf, check)
    check_mark_class_closure(tf, check)
    check_private(tf, check)
    letters = {g for cp, g in vf_cmap.items()
               if 0x30 <= cp <= 0x39 or 0x41 <= cp <= 0x5A or 0x61 <= cp <= 0x7A}
    # ... and they DRAW: the count is a cmap count, so a VF with 1,626
    # of its 1,632 glyphs emptied passed this file, which is the only
    # gate the two variable fonts have
    default_gs = tf.getGlyphSet(location={"wght": axis.defaultValue})
    drawn = set()
    for g in tf.getGlyphOrder():
        pen = BoundsPen(default_gs)
        default_gs[g].draw(pen)
        if pen.bounds is not None:
            drawn.add(g)
    inked = sum(1 for g in vf_cmap.values() if g in drawn)
    check(inked >= 700, f"{inked} mapped glyphs draw at the default weight")
    ligs = []
    shape_default = make_shaper(FONT, {"wght": axis.defaultValue})
    check_heights(tf, check, default_gs, vf_cmap)
    check_zones(tf, check, vf_cmap)
    # The mark gates run on an INSTANCE at every location: the default,
    # both axis extremes and every named instance. A variable font's
    # anchors are merged from the masters into variable anchors, so a
    # value wrong only away from the default is exactly what this file
    # is here to see, and reading the VF's own tables shows only the
    # default value -- instantiating resolves every delta into a plain
    # font the same four checks the statics get can read. The Light
    # Italic instance is where the statics' own weight extreme first
    # showed a leaning ascender; it is the one a default-only gate
    # misses, and it is a named instance here.
    # the default, the two ends, every named instance -- and every
    # master, read off the variation stores: a delta scoped to the
    # region that peaks at the wght-365 master is zero at all of the
    # former (verifylib.vf_region_peaks)
    locations = sorted({axis.defaultValue, axis.minValue, axis.maxValue}
                       | {i.coordinates["wght"] for i in tf["fvar"].instances
                          if "wght" in i.coordinates}
                       | set(vf_region_peaks(tf)))
    peaks = vf_region_peaks(tf)
    check(any(axis.minValue < p < axis.maxValue for p in peaks),
          f"an intermediate master is probed ({[round(p, 2) for p in peaks]})")
    for loc in locations:
        inst = instantiateVariableFont(TTFont(FONT), {"wght": loc}, inplace=False)
        buf = io.BytesIO()
        inst.save(buf)
        inst = TTFont(io.BytesIO(buf.getvalue()))
        shape_at, gs_at = make_shaper(buf.getvalue()), inst.getGlyphSet()
        check_marks(inst, check, shape_at, gs_at, f" at wght {round(loc, 2):g}")
    check_features_work(shape_default, check, vf_cmap)
    # the nameIDs verify_latin.py requires of the statics; 13 and 14 are
    # the licence and its URL, and dropping all seven passed this file
    check_name_ids(tf, check, (3, 4, 8, 9, 11, 13, 14))
    for seq in build.LIGATURES:
        infos, _p = shape_default(f"a {seq} b", {"calt": True, "liga": True})
        ligs += [tf.getGlyphOrder()[i.codepoint] for i in infos[2:len(infos) - 2]
                 if tf.getGlyphOrder()[i.codepoint] not in drawn]
    check(not ligs, f"every ligature draws ({len(build.LIGATURES)} probes; "
                    f"blank: {ligs[:5]})")
    check_version_stamp(tf, check)
    check_style_bits(tf, check, tf["name"].getDebugName(2) or "",
                     "Italic" in (tf["name"].getDebugName(17)
                                  or tf["name"].getDebugName(2) or ""))
    check_gdi_family_name(tf, check)
    check_grid(check, metrics, build.CELL)
    # on the grid is not the same as the RIGHT number of cells: only the
    # glyph count of three ligature cases was read here, so widening
    # '==' from two cells to three shaped 'a == b' at 4,200 units and
    # passed (verify_latin.py has had this for every one of the 61 since
    # v3, and the one-cell checks beside it)
    wrong = {}
    for seq, spec in build.LIGATURES.items():
        infos, positions = shape_default(f"a {seq} b", {"calt": True, "liga": True})
        adv = sum(p.x_advance for p in positions[2:len(infos) - 2])
        if adv != spec["cells"] * build.CELL:
            wrong[seq] = adv
    check(not wrong, f"every ligature is the cells it declares "
                     f"({len(build.LIGATURES)} probes; off: {wrong})")
    check_one_cell(tf, check, vf_cmap, metrics, build.CELL)
    check(hhea.advanceWidthMax == max(adv for adv, _ in metrics.values()),
          f"hhea advanceWidthMax is the widest advance "
          f"({hhea.advanceWidthMax} vs {max(adv for adv, _ in metrics.values())})")
    tags = {fr.FeatureTag for fr in tf["GSUB"].table.FeatureList.FeatureRecord}
    missing = [t for t in ("calt", "liga", "ss01", "ss08", "cv99",
                           "zero", "cv01", "ss11") if t not in tags]
    check(not missing, f"GSUB carries the feature surface the statics do "
                       f"(missing: {missing})")
    # WHERE the ink lands, at every location and not only the default
    # one: verify_latin.py has held the statics to this since v3, and
    # the only ink test here was "it draws at all", at the default.
    # A master translated a cell sideways is point-compatible, so
    # varLib merges it happily, head/hhea are computed from the same
    # corrupted masters and hold it, and the SCP exactness check probes
    # SCP's own glyphs — a build that moved every Monaspace ligature
    # 600u right above Regular passed this file and the whole suite,
    # rendering `!=` into the next column at Bold. The bound is
    # verifylib.ink_spill's, one location at a time
    spill, centres, default_boxes = {}, {}, {}
    probes = sorted({axis.minValue, axis.defaultValue, axis.maxValue}
                    | set(master_locations(tf, axis))
                    | {i.coordinates["wght"] for i in instances
                       if "wght" in i.coordinates})
    check(len(probes) >= len(WEIGHTS) + 2,
          f"every master and every named instance is probed "
          f"({[round(w, 2) for w in probes]})")
    for w in probes:
        gs = tf.getGlyphSet(location={"wght": w})
        offs = []
        for g in tf.getGlyphOrder():
            pen = BoundsPen(gs)
            gs[g].draw(pen)
            if pen.bounds is None:
                continue
            if w == axis.defaultValue:
                default_boxes[g] = pen.bounds
            union = pen.bounds if union is None else tuple(
                f(a, b) for f, a, b in zip((min, min, max, max), union, pen.bounds))
            right = metrics[g][0] - pen.bounds[2]
            rsb = right if rsb is None else min(rsb, right)
            adv = metrics[g][0]
            for hit in ink_spill({g: pen.bounds}, lambda _: adv, vf_cmap, build.CELL):
                spill.setdefault(round(w), []).append(hit)
            if g in letters:
                offs.append((pen.bounds[0] + pen.bounds[2]) / 2 - adv / 2)
        centres[round(w)] = sum(offs) / len(offs) if offs else None
    check(not spill, f"every glyph's ink is inside its advance at every "
                     f"location, give or take the lean "
                     f"({ {k: (len(v), v[:2]) for k, v in spill.items()} })")
    off_centre = {w: round(m, 1) for w, m in centres.items()
                  if m is None or abs(m) > 25}
    bearings = [(g, round(metrics[g][1]), round(box[0]))
                for g, box in default_boxes.items()
                if abs(metrics[g][1] - box[0]) >= 2]
    check(not bearings, f"hmtx bearings are the outlines' xMin at the "
                        f"default location ({len(bearings)} off, e.g. "
                        f"{bearings[:3]})")
    check(not off_centre, f"the letters sit centred in the cell at every "
                          f"location (mean ink-centre offsets "
                          f"{ {w: None if m is None else round(m, 1) for w, m in centres.items()} }; "
                          f"bound 25u, off: {off_centre})")
    # the box is the integer union over the MASTERS; an instance can sit a
    # hair past it (16.16 deltas, the merge's 0.01 rounding tolerance —
    # 0.002u measured); 0.05u leaves headroom for that and still catches
    # a floor/ceil taken the wrong way (a whole unit)
    eps = 0.05
    head = tf["head"]
    box = (head.xMin, head.yMin, head.xMax, head.yMax)
    if not check(union is not None, "the instances draw some outline"):
        union = (0, 0, 0, 0)
    outline = tuple(round(v, 3) for v in union)
    check(box[0] - eps <= outline[0] and box[1] - eps <= outline[1]
          and box[2] + eps >= outline[2] and box[3] + eps >= outline[3],
          f"head bbox {box} holds every instance's outlines {outline}")
    check(hhea.xMaxExtent + eps >= outline[2],
          f"hhea.xMaxExtent {hhea.xMaxExtent} >= the widest instance outline {outline[2]}")
    check(hhea.minLeftSideBearing - eps <= outline[0],
          f"hhea.minLeftSideBearing {hhea.minLeftSideBearing} <= leftmost outline {outline[0]}")
    check(rsb is not None and hhea.minRightSideBearing - eps <= rsb,
          f"hhea.minRightSideBearing {hhea.minRightSideBearing} <= smallest right side "
          f"bearing {None if rsb is None else round(rsb, 3)}")

    # every named instance: shape the ligature cases, same as the static
    # faces (verify_latin.py / verify.py CASES) -- HarfBuzz on the VF at
    # that location: the actual varLib.build-merged GSUB, per weight
    on = {"calt": True, "liga": True}
    scp, to_scp = scp_reference(is_italic)
    vf_bytes = FONT.read_bytes()
    cmap = tf.getBestCmap()
    equals = cmap[ord("=")]
    # Monaspace's own wght floor, as this VF carries it: the '=' bar at the
    # axis minimum. A static face whose bar is thinner than that could only
    # have got there by erosion (build_latin.py, static faces only — a VF
    # master can't erode, see build_latin_vf.py), so its bar is not
    # comparable; its SCP-side glyphs still are.
    floor_bar = build.bar_thickness(tf.getGlyphSet(location={"wght": axis.minValue}), equals)
    any_static = bool(static_faces(ROOT / "dist" / "latin", "Gengou"))
    for inst_desc in instances:
        style = name.getDebugName(inst_desc.subfamilyNameID) or "?"
        loc = dict(inst_desc.coordinates)
        for text, want in LIG_CASES:
            got = len(make_shaper(vf_bytes, loc)(text, on)[0])
            check(got == want, f"[{style}, wght={loc.get('wght', '?'):.0f}] "
                               f"{text!r}: {got} glyphs (want {want})")
        # the matching static face (build_latin.py): same '=' bar (this is
        # the bar-matching every weight is placed by) and the same 'A'
        # (an SCP-only glyph — no Monaspace/erosion involved); the
        # position check — the exact-outline check against SCP is below
        weight = style.replace(" Italic", "").replace("Italic", "Regular")
        static_name = f"Gengou-{weight}{'Italic' if is_italic else ''}.otf"
        static_path = ROOT / "dist" / "latin" / static_name
        if static_path.exists():
            ref = TTFont(str(static_path))
            gs = tf.getGlyphSet(location=loc)
            bar_i = build.bar_thickness(gs, equals)
            bar_r = build.bar_thickness(ref, ref.getBestCmap()[ord("=")])
            if bar_r < floor_bar:
                check(abs(bar_i - floor_bar) <= 1,
                      f"[{style}] static {static_name} '=' bar {bar_r:.1f} is eroded "
                      f"below Monaspace's floor {floor_bar:.1f}; instanced bar "
                      f"{bar_i:.1f} sits at the floor (want within 1u of it)")
            else:
                # 1.5u: '=' is Monaspace's, bar-matched at the static's
                # exact wght but interpolated between masters here, and
                # Monaspace's bar is not linear in SCP's design coordinate
                check(abs(bar_i - bar_r) <= 1.5,
                      f"[{style}] instanced '=' bar {bar_i:.1f} vs static "
                      f"{static_name} {bar_r:.1f} (delta {bar_i - bar_r:+.1f}, want <=1.5u)")
            # 1u: the static face is the VF's blend rounded point by
            # point (build_latin.round_outlines) — half a unit, plus a
            # curve extreme moving with its rounded control points
            bi, br = bounds(gs, cmap, "A"), bounds(ref.getGlyphSet(), ref.getBestCmap(), "A")
            check(close(bi, br, 1), f"[{style}] instanced 'A' bounds {bi} vs static "
                                    f"{static_name} 'A' bounds {br} (want within 1u)")
        else:
            # a silent skip in the release package job, where all ten
            # statics ARE there, means the only per-weight comparison
            # this file has was lost, not that it did not apply
            check(not any_static,
                  f"bar/bounds compare: {static_name} is missing while the "
                  f"rest of the family is built")
    # exactness against SCP itself, at the named weights AND between them:
    # our blend at user U must equal SCP's blend at the SCP wght our avar
    # maps U to (see build_latin_vf.scp_design_axis / user_axis), to 1u
    # (16.16 fixed precision)
    if scp is not None:
        scp_cmap = scp.getBestCmap()
        for u in (250, 300, 325, 350, 375, 400, 450, 500, 550, 600, 650, 700):
            s = to_scp(u)
            gs = tf.getGlyphSet(location={"wght": u})
            ref = scp.getGlyphSet(location={"wght": s})
            for ch in "AlHm¾":     # SCP-only glyphs ('=' is Monaspace's)
                bi, br = bounds(gs, cmap, ch), bounds(ref, scp_cmap, ch)
                check(close(bi, br, 1), f"[wght {u} = SCP {s:.1f}] {ch!r} bounds {bi} vs "
                                        f"SCP {br} (want within 1u)")
    else:
        print("  (skip SCP exactness check: set SCP_VF_U / SCP_VF_I)")

    print("FAILED" if check.failed else "all checks passed")
    sys.exit(check.exit_code())


if __name__ == "__main__":
    main()

"""The variable-font side of the Latin build: instancing Source Code Pro
and Monaspace at a matched stroke weight (VFSource), the erosion that
takes Monaspace below its axis floor, and the grafts drawn from those
instances (add_glyphs, replace_from_mona). scripts/build_latin.py and
scripts/build_latin_vf.py use it; the JP build in scripts/build.py never
instances a variable font, and reads only the finished Latin faces."""

import contextlib
import functools
import math
from pathlib import Path

import pathops
from build import (  # noqa: E402
    CELL,
    MONA_CELL,
    alloc_glyph_name,
    append_context,
    append_glyph,
    bar_thickness,
    charstring_lsb,
    draw_clean,
    glyph_bounds,
    note_redrawn,
    pen_width,
)
from fontTools.misc.roundTools import noRound, otRound
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from fontTools.varLib.instancer import instantiateVariableFont


@contextlib.contextmanager
def unrounded_cff2_instancing():
    """fontTools' instancer rounds every instanced CFF2 charstring operand
    to an integer. Charstring operands are RELATIVE (rmoveto/rlineto/
    rrcurveto deltas), so those roundings accumulate along a path: an
    instance of 'A' at a fractional wght lands 3u left of where HarfBuzz
    renders the VF there, 'm' up to 10u off, and two instances drift
    differently. With rounding off the outlines keep the VF's exact blend
    (fixed 16.16 operands, a CFF2 charstring's native precision): the
    variable Gengou's masters are built that way and interpolate SCP
    exactly (build_latin_vf.py), and the static faces round the blend
    afterwards, point by point (build_latin.round_outlines)."""
    orig = instancer.instantiateCFF2
    instancer.instantiateCFF2 = functools.partial(orig, round=noRound)
    try:
        yield
    finally:
        instancer.instantiateCFF2 = orig


class VFSource:
    """Variable-font instances matched to a target '=' bar thickness.

    Used for both Monaspace (wght/wdth/slnt) and Source Code Pro (wght only)
    — the axes dict template decides which. Matching is a binary search on
    wght so the operator/Latin stroke weight equals the reference face's.
    """

    def __init__(self, vf_path, scale, axes):
        self.vf_path = vf_path
        self.scale = scale        # em scale applied when the glyphs are used
        self.axes = axes          # template; wght filled by the search
        self._cache = {}
        self._vf = None
        self._ranges = None

    def _source(self):
        """The VF, loaded once: the search probes it (getGlyphSet at a
        location) and reads its axis ranges; it is never instanced in
        place."""
        if self._vf is None:
            vf = TTFont(self.vf_path)
            self._vf = vf
            self._ranges = {a.axisTag: (a.minValue, a.maxValue)
                            for a in vf["fvar"].axes}
            self._equals = vf.getBestCmap()[ord("=")]
        return self._vf

    def axis_range(self, tag, default):
        self._source()
        return self._ranges.get(tag, default)

    def _instance(self, axes):
        """A static instance at `axes`: a fresh load of the file (faster
        than deep-copying a decompiled VF) instanced in place."""
        inst = TTFont(self.vf_path)
        instantiateVariableFont(inst, axes, inplace=True)
        return inst

    def _probe_bar(self, axes):
        """The '=' bar at `axes`, in the donor's units, read off the VF's
        own glyph set at that location (fontTools blends the outline on
        the fly): no instancing, so the nine-step search costs
        milliseconds instead of nine instancings. Unrounded — the
        instancer rounds its outlines, so the instance built at the
        converged wght can measure up to ~1u off this probe."""
        return bar_thickness(self._source().getGlyphSet(location=axes), self._equals)

    def _axes_for(self, slant):
        """The axis template with `slant` on the slnt axis, clamped to
        what the font offers (Monaspace's floor is -11; SCP Italic is
        -12 — mona_transform() shears the remainder in)."""
        axes = dict(self.axes)
        if slant is not None and "slnt" in axes:
            smin, smax = self.axis_range("slnt", (-11.0, 0.0))
            clamped = max(smin, min(smax, slant))
            if abs(clamped - slant) > 1e-6:
                print(f"  slnt {slant:.2f} clamped to {clamped:.2f} "
                      f"(axis {smin}..{smax})")
            axes["slnt"] = clamped
        return axes

    def matched_wght(self, target_units, slant=None):
        """The wght matched() converges on for `target_units`, as a plain
        number (build_latin_vf.py places fvar instances and masters by it,
        so they sit exactly where the static faces are) — the search
        alone, no instance built. Nine halvings of the axis: ~1.4 wght on
        SCP's 700-wide axis, well under 1u of bar."""
        return self._converge(target_units / self.scale, self._axes_for(slant))

    def _converge(self, pre_scale_target, axes):
        """Nine halvings of the wght axis on the '=' bar (in the donor's
        units), probing the VF's glyph set at each step."""
        lo, hi = self.axis_range("wght", (200.0, 800.0))
        lo, hi = float(lo), float(hi)
        for _ in range(9):
            mid = (lo + hi) / 2
            if self._probe_bar(dict(axes, wght=mid)) < pre_scale_target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    def floor_bar(self, slant=None):
        """The '=' bar, in the consumer's units, at the wght axis floor:
        the thinnest this donor can go without erosion."""
        lo, _ = self.axis_range("wght", (200.0, 800.0))
        return self._probe_bar(dict(self._axes_for(slant), wght=float(lo))) * self.scale

    def at(self, wght, slant=None):
        """The instance at an exact `wght` (no bar search): what the Latin
        faces are — Source Code Pro's own named instances. Cached like
        matched()'s; `residual_slant` as there."""
        axes = self._axes_for(slant)
        key = ("at", float(wght), axes.get("slnt"))
        if key not in self._cache:
            inst = self._instance(dict(axes, wght=float(wght)))
            inst.wght = float(wght)
            inst.residual_slant = (slant - axes["slnt"]
                                   if slant is not None and "slnt" in axes else 0.0)
            self._cache[key] = inst
        return self._cache[key]

    def matched(self, target_units, slant=None, master=False):
        """The instance whose '=' bar measures `target_units` (in our
        units), sheared to `slant`. master=True asks for a variable
        font's master: an outline that must stay point-compatible with
        the same glyph at the other masters, so it takes neither of
        the two pathops passes -- no erosion below the axis floor
        (below) and no overlap removal in draw_clean (keeps_overlaps)
        -- since a boolean op on a fixed outline is not an
        interpolatable deformation."""
        key = (round(target_units), slant if slant is None else round(slant), master)
        if key in self._cache:
            return self._cache[key]
        pre_scale_target = target_units / self.scale
        axes = self._axes_for(slant)
        wght = self._converge(pre_scale_target, axes)
        inst = self._instance(dict(axes, wght=wght))
        inst.wght = wght
        inst.master = master
        # slant the axis could not deliver (SCP Italic is -12, Monaspace's
        # slnt floor is -11); mona_transform() shears the remainder in
        inst.residual_slant = (slant - axes["slnt"]
                               if slant is not None and "slnt" in axes else 0.0)
        t = bar_thickness(inst, inst.getBestCmap()[ord("=")])
        # the axis floor may stop short of a thin target (Monaspace's
        # wght 200 is 53u at our scale; SCP Light measures 37u). Record
        # the surplus per side, in this font's units, and mona_glyphset()
        # erodes the outlines by it — see erode_path(). A VF master can't
        # take that path (erosion is a pathops boolean op on a fixed
        # outline, not an interpolatable deformation — see docs/
        # gengou-plan.md 段階2): a master clamps at the floor (the
        # binary search already can't go past the axis bounds) and only
        # reports the shortfall, leaving `erode` unset so mona_glyphset()
        # hands back the outline as instanced.
        shortfall = t - pre_scale_target
        if not master:
            inst.erode = max(0.0, shortfall / 2)
            if abs(shortfall) > 1.0 and not inst.erode:
                print(f"  WARNING: wght search off by {shortfall:+.1f}u "
                      f"(target {pre_scale_target:.1f}, wght={wght:.1f}) in "
                      f"{Path(self.vf_path).name}")
            elif inst.erode > 0.5:
                print(f"  wght floor {wght:.0f} leaves {2 * inst.erode:.1f}u surplus "
                      f"(donor units) in {Path(self.vf_path).name}; eroding "
                      f"{inst.erode:.1f}u/side")
        elif shortfall > 1.0:
            print(f"  wght floor {wght:.0f} leaves {shortfall:.1f}u short of "
                  f"target {pre_scale_target:.1f} (donor units) in "
                  f"{Path(self.vf_path).name}; no erosion (VF master), "
                  f"clamped at the floor")
        self._cache[key] = inst   # only the converged instance is kept
        return inst


def glyph_vcenter(font, gname, scale=1.0):
    pen = BoundsPen(font.getGlyphSet())
    font.getGlyphSet()[gname].draw(pen)
    return (pen.bounds[1] + pen.bounds[3]) / 2 * scale


def erode_path(path, d):
    """Shrink a filled outline by `d` on every side: subtract a stroke of
    width 2d run along the outline itself. Straight bars, arrowheads and
    slashes keep their shape; only dots lose proportionally more."""
    inner = pathops.Path(path)
    inner.simplify()
    band = pathops.Path(inner)
    band.stroke(2 * d, pathops.LineCap.BUTT_CAP, pathops.LineJoin.MITER_JOIN, 4)
    return pathops.op(inner, band, pathops.PathOp.DIFFERENCE)


class _ErodedGlyph:
    def __init__(self, gs, gname, d):
        self._gs, self._gname, self._d = gs, gname, d

    def draw(self, pen):
        path = pathops.Path()
        self._gs[self._gname].draw(path.getPen())
        erode_path(path, self._d).draw(pen)


class _ErodedGlyphSet:
    """Glyph set view that hands out eroded outlines (see erode_path)."""
    def __init__(self, gs, d):
        self._gs, self._d = gs, d

    def __getitem__(self, gname):
        return _ErodedGlyph(self._gs, gname, self._d)

    def __contains__(self, gname):
        return gname in self._gs


def mona_glyphset(mona):
    """The glyph set every Monaspace import draws from: eroded when the
    weight search hit the axis floor (matched() sets `erode`)."""
    gs = mona.getGlyphSet()
    d = getattr(mona, "erode", 0.0)
    return _ErodedGlyphSet(gs, d) if d > 0.5 else gs


def keeps_overlaps(donor):
    """Whether outlines drawn from `donor` skip draw_clean's overlap
    removal: a variable font's master does (VFSource.matched(master=
    True)), for the reason given there."""
    return getattr(donor, "master", False)


def mona_transform(mona, dx, dy, k):
    """Affine for a Monaspace outline landing in our em: scale to the cell,
    shear in whatever slant the slnt axis clamped away, then offset."""
    shear = math.tan(math.radians(-getattr(mona, "residual_slant", 0.0)))
    return (k, 0, k * shear, k, dx, dy)


def mona_baseline_shift(font, mona, k):
    """Baseline correction: align the two fonts' '=' vertical centers."""
    cmap = font.getBestCmap()
    return round(glyph_vcenter(font, cmap[ord("=")])
                 - glyph_vcenter(mona, mona.getBestCmap()[ord("=")], k))


def replace_from_mona(font, mona, chars, dy, k):
    """Swap the outlines of `chars` for Monaspace's, keeping name, advance
    and cmap. Same instance, scale (`k`), shear and baseline as the
    ligatures. Characters missing on either side are skipped."""
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    cmap = font.getBestCmap()
    mona_cmap = mona.getBestCmap()
    mona_gs = mona_glyphset(mona)
    replaced = []
    for ch in chars:
        name = cmap.get(ord(ch))
        src = mona_cmap.get(ord(ch))
        if name is None or src is None:
            print(f"  skip standalone {ch!r}: missing in target or donor")
            continue
        gid = font.getGlyphID(name)
        private = td.FDArray[td.FDSelect[gid]].Private
        adv = font["hmtx"].metrics[name][0]
        pen = T2CharStringPen(pen_width(private, adv), font.getGlyphSet())
        draw_clean([(mona_gs, src, mona_transform(mona, 0, dy, k))], pen,
                   simplify=not keeps_overlaps(mona))
        cs = pen.getCharString(private=private)
        td.CharStrings.charStringsIndex[td.CharStrings.charStrings[name]] = cs
        font["hmtx"].metrics[name] = (adv, charstring_lsb(cs))
        note_redrawn(font, [name])
        replaced.append(ch)
    return replaced


def add_glyphs(font, mona, alts, ligatures, dy, cell=CELL):
    """Append the imported ligature glyphs at `cell` per input character;
    return {seq: glyph name}. Alternate (.alt) designs are appended too
    and recorded in `alts`."""
    k = cell / MONA_CELL
    td, cmap, fd_index, private, vdon = append_context(font)
    mona_gs = mona_glyphset(mona)
    mona_names = set(mona.getGlyphOrder())

    added = {}
    n_alt = 0
    for seq, spec in ligatures.items():
        if any(g not in mona_names for g in spec["glyphs"]):
            print(f"  skip {seq!r}: donor glyph missing")
            continue
        if any(ord(c) not in cmap for c in seq):
            print(f"  skip {seq!r}: component not in target cmap")
            continue
        cells = spec["cells"]
        width = cell * cells
        if len(spec["glyphs"]) == 1:
            # a single spanning glyph is drawn in its final cell; shift right
            offsets = [(cells - 1) * cell]
        else:
            # composed sequences: one part per cell, unless "at" says which
            # cell each part sits in ('&&=' is ampersand.init in cell 0 and
            # the 2-cell ampersand_equal, drawn in its final cell, at 2)
            offsets = [c * cell for c in spec.get("at", range(len(spec["glyphs"])))]
        pen = T2CharStringPen(pen_width(private, width), font.getGlyphSet())
        # composed sequences (':=' etc.) overlap by construction — the same
        # pathops pass the .alt path uses removes the seams
        draw_clean([(mona_gs, gname, mona_transform(mona, dx, dy, k))
                    for gname, dx in zip(spec["glyphs"], offsets)], pen,
                   simplify=not keeps_overlaps(mona))
        name = alloc_glyph_name(font)
        append_glyph(font, td, name, pen.getCharString(private=private),
                     fd_index, width, None, vdon)
        added[seq] = name

        # alternate design, if Monaspace ships one (cv99 toggles to it);
        # composed sequences take each component's .alt where it exists
        alt_glyphs = [g + ".alt" if g + ".alt" in mona_names else g
                      for g in spec["glyphs"]]
        if any(g.endswith(".alt") for g in alt_glyphs):
            pen = T2CharStringPen(pen_width(private, width), font.getGlyphSet())
            draw_clean([(mona_gs, gname, mona_transform(mona, dx, dy, k))
                        for gname, dx in zip(alt_glyphs, offsets)], pen,
                       simplify=not keeps_overlaps(mona))
            alt_name = alloc_glyph_name(font)
            append_glyph(font, td, alt_name, pen.getCharString(private=private),
                         fd_index, width, None, vdon)
            alts[name] = alt_name
            n_alt += 1

    print(f"  cv99 alternates: {n_alt}")
    if n_alt == 0:
        print("  WARNING: no .alt designs found — Monaspace may have renamed "
              "its alternate glyphs; cv99 will be empty")
    return added


def sync_lsb(font):
    """hmtx left side bearings from the outlines (otRound(xMin), like
    charstring_lsb; a blank glyph keeps its own). A CFF font's lsb is nothing
    fontTools maintains: an instanced VF keeps the default master's
    hmtx while its outlines move, so build_latin.static_base's faces
    carried SCP's wght-200 bearings at every weight. Returns the number
    of glyphs whose lsb changed."""
    bounds = glyph_bounds(font)
    metrics = font["hmtx"].metrics
    changed = 0
    for name, (adv, lsb) in list(metrics.items()):
        if name not in bounds:
            continue
        want = otRound(bounds[name][0])
        if want != lsb:
            metrics[name] = (adv, want)
            changed += 1
    return changed


# VFSource / _vf_source are build_latin.py's and build_latin_vf.py's
# (build.py's own JP faces never instance a VF): one loaded VF and its
# instances per process, keyed by path and axes
_VF_CACHE = {}


def _vf_source(path, scale, axes):
    key = (str(path), scale, tuple(sorted(axes.items())))
    if key not in _VF_CACHE:
        _VF_CACHE[key] = VFSource(path, scale, axes)
    return _VF_CACHE[key]

"""The mark anchors the Latin layer adds to its donors' GPOS: the base
anchors fitted to each lookup's own rule for the letters it leaves out
(anchor_loose_letters), the marks a lookup leaves out (anchor_loose_marks),
the second donor's anchors and decompositions carried over
(import_donor_base_anchors, import_donor_decompositions), the italic's
stacked-accent lift copied from the upright (mirror_stack_lift), and the
GDEF mark classes (classify_unicode_marks). scripts/build_latin.py and
scripts/build_latin_vf.py run these on the Latin faces; the JP build takes
the finished GPOS from them, and scripts/verifylib.py reads the same rules
back."""

import statistics
import unicodedata

from build import (  # noqa: E402
    _bounds,
    _ccmp_lookups,
    _insert_lookups_first,
    _subst_pairs,
    _unwrap,
    _unwrap_pos,
)
from fontTools.misc.roundTools import otRound
from fontTools.ttLib.tables import otTables


def _mark_base_lookups(font, tag="mark"):
    """[(lookup index, [MarkBasePos subtables])] under `tag`, Extension
    unwrapped, in LookupList order."""
    if "GPOS" not in font:
        return []
    table = font["GPOS"].table
    want = set()
    for fr in table.FeatureList.FeatureRecord:
        if fr.FeatureTag == tag:
            want |= set(fr.Feature.LookupListIndex)
    out = []
    for i in sorted(want):
        kind, subs = _unwrap_pos(table.LookupList.Lookup[i])
        if kind == 4:
            out.append((i, subs))
    return out


def _mark_codepoints(font, subtables):
    """The codepoints of the marks a lookup's subtables cover."""
    rev = {gn: cp for cp, gn in font.getBestCmap().items()}
    out = set()
    for sub in subtables:
        out |= {rev[g] for g in sub.MarkCoverage.glyphs if g in rev}
    return out


def pair_mark_lookups(base, donor):
    """Match the face's mark lookups to a donor's, by the marks they
    attach rather than by position.

    Both fonts here are Adobe's, built from the same feature source, so
    each lookup carries one class and the two fonts' lookups line up one
    for one — but "line up" has to be established, not assumed, because
    the anchors of one class written into another would put every accent
    of that class in the wrong place. Pairing on the mark codepoints
    they cover says it in the fonts' own terms. Returns {our lookup
    index: donor lookup index}, or {} when the match is not a bijection.
    """
    ours = _mark_base_lookups(base)
    theirs = _mark_base_lookups(donor)
    if not ours or not theirs:
        return {}
    donor_marks = {j: _mark_codepoints(donor, subs) for j, subs in theirs}
    pairs = {}
    for i, subs in ours:
        mine = _mark_codepoints(base, subs)
        ranked = sorted(((len(mine & cps), j) for j, cps in donor_marks.items()),
                        reverse=True)
        if ranked[0][0] == 0:          # nothing of ours is in theirs
            continue
        if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
            return {}                      # a tie is not a match, it is a guess
        pairs[i] = ranked[0][1]
    # one of theirs answering to two of ours is not a pairing either
    return pairs if len(pairs) == len(set(pairs.values())) else {}


def _plain_anchor(anchor, sx, dx):
    """A donor anchor as plain coordinates, moved with the outline.

    Format 2 names a point on the donor's contour and Format 3 hangs a
    device table off it; neither survives redrawing the glyph, so both
    come across as Format 1. The x is scaled and shifted exactly as
    cell_fit moved the ink it sits on; the y is untouched, as the
    outline's is."""
    if anchor is None:
        return None
    out = otTables.Anchor()
    out.Format = 1
    out.XCoordinate = otRound(anchor.XCoordinate * sx + dx)
    out.YCoordinate = anchor.YCoordinate
    return out


def _anchor_rule(gs, sub, floor=16, spread=24, wander=120):
    """The rule a mark lookup's own base anchors follow, fitted from
    them: (use_top, dx, dy) -- whether the anchor sits off the ink's top
    edge or its bottom, and the median offset from the ink's centre and
    from that edge. None when the lookup carries too few bases to fit,
    when neither edge explains its anchors, or when the x does not
    follow the ink's centre closely enough to be worth predicting.

    Medians, not means, and the edge is chosen by which residual is the
    tighter of the two: a top-mark lookup's anchors track the ink's top
    (Source Code Pro's sit 20 units above it, to within 4) and a
    below-mark lookup's track its bottom (-14, to within 6), while the
    other edge varies with the letter's height and spreads by 60+.

    Held out against the anchors the donors did draw, the rule puts y
    within 4-6 units of theirs at the median and 10-22 at the 90th
    centile; x within 11-15 at the median, with a tail to about 200 on
    a letter whose designer moved the anchor off centre deliberately.
    That is the accuracy this buys. What it replaces is not a smaller
    error but a whole cell: 600 units, into the next character. (The
    letters that ARE such a letter with something added to it take its
    x outright rather than the fit -- see anchor_loose_letters.)

    On the donors as pinned, `floor` is the only gate that turns
    anything away: the chosen edge's spread never exceeds 6 against a
    limit of 24, and the x never 98 against 120. The three lookups it
    rejects carry one to four bases each. The one admitted fit worth
    distrusting is the ogonek's, whose x is bimodal in the donor -- A's
    anchor is 204 right of centre, I's is on it -- so the median lands
    at neither; every letter it places goes about 100 off. Still a
    sixth of the error it replaces, and the letters built on a covered
    one bypass it.
    """
    tops, bots, xs = [], [], []
    for gn, rec in zip(sub.BaseCoverage.glyphs, sub.BaseArray.BaseRecord):
        anchor = rec.BaseAnchor[0] if rec.BaseAnchor else None
        box = _bounds(gs, gn)
        if anchor is None or not box:
            continue
        tops.append(anchor.YCoordinate - box[3])
        bots.append(anchor.YCoordinate - box[1])
        xs.append(anchor.XCoordinate - (box[0] + box[2]) / 2)
    if len(xs) < floor:
        return None

    def mad(values):
        mid = statistics.median(values)
        return statistics.median(abs(v - mid) for v in values)

    use_top = mad(tops) <= mad(bots)
    edge = tops if use_top else bots
    dx = statistics.median(xs)
    if mad(edge) > spread or statistics.median(abs(x - dx) for x in xs) > wander:
        return None
    return use_top, otRound(dx), otRound(statistics.median(edge))


def _canonical_bases(cmap):
    """{glyph: the glyph of the letter it is built on}, following
    canonical decompositions to the end of the chain -- U+1EB6 A with
    breve and dot below to U+1EA0 to plain A.

    Compatibility decompositions are not followed: a superscript w is
    not a w with something added to it, it is a different letter drawn
    somewhere else, and its marks belong where they fall.
    """
    out = {}
    for cp, gn in cmap.items():
        cur = cp
        for _ in range(8):                 # a chain, not a cycle
            spec = unicodedata.decomposition(chr(cur))
            if not spec or spec.startswith("<"):
                break
            cur = int(spec.split()[0], 16)
        if cur != cp and cur in cmap:
            out[gn] = cmap[cur]
    return out


def fit_anchor_rules(font, tag="mark"):
    """{(lookup index, subtable index): _anchor_rule} over the mark
    lookups of `font`, for anchor_loose_letters to be handed.

    Separate from applying it because a variable font's masters have to
    agree: the rule is fitted once, on the default master, and applied
    to every one. Fitted per master it could admit a lookup at one
    weight and reject it at another, and a BaseCoverage that differs
    between masters is one varLib cannot merge.
    """
    gs = font.getGlyphSet()
    out = {}
    for i, subs in _mark_base_lookups(font, tag):
        for j, sub in enumerate(subs):
            if sub.ClassCount != 1:
                continue
            rule = _anchor_rule(gs, sub)
            if rule is not None:
                out[(i, j)] = rule
    return out


def anchor_loose_letters(font, tag="mark", rules=None):
    """Give a letter no mark lookup covers a base anchor of its own,
    fitted from the letters that lookup does cover. Returns the count.

    A combining mark in these donors is drawn as a spacing glyph --
    Source Code Pro's acute has an advance of a cell and its ink sits
    inside it -- and the shaper zeroes that advance for a mark. So a
    mark the lookup cannot place does not land somewhere approximate:
    it lands one whole cell to the right, on top of the next character.
    Source Code Pro anchors 64 of the 234 letters in Greek and Cyrillic
    and Source Sans 82, neither a superset of the other, so about 160
    letters per face put the accent in the following cell -- in the
    upright and the italic alike. The JP faces never showed it, because
    the graft redraws the marks a cell to the left and an unplaced one
    then lands right by accident.

    The fitted rule is the donor's own (see _anchor_rule), so a letter
    that gets an anchor here gets the one its neighbours already have,
    and a lookup whose anchors do not follow a rule is left alone.
    `rules` supplies those fits from elsewhere (fit_anchor_rules), which
    is how a variable font's masters are kept in step.
    """
    if rules is None:
        rules = fit_anchor_rules(font, tag)
    gs = font.getGlyphSet()
    cmap = font.getBestCmap()
    letters = {gn for cp, gn in cmap.items()
               if unicodedata.category(chr(cp)).startswith("L")}
    # and what GSUB turns a letter into: the shaper substitutes before
    # it positions, so the Serbian locl б takes the accent, not б
    letters |= _letter_variants(font, letters)
    bases = _canonical_bases(cmap)
    gid = font.getGlyphID
    added = 0
    for i, subs in _mark_base_lookups(font, tag):
        for j, sub in enumerate(subs):
            if sub.ClassCount != 1:
                continue      # one class here; more would need the class too
            rule = rules.get((i, j))
            if rule is None:
                continue
            use_top, dx, dy = rule
            rows = list(zip(sub.BaseCoverage.glyphs, sub.BaseArray.BaseRecord))
            have = set(sub.BaseCoverage.glyphs)
            # a letter the donor DID anchor, whose x this one should take
            # rather than the rule's: the two are the same drawing with
            # something added, so an anchor the designer moved off centre
            # on one belongs off centre on the other. Only the x -- the y
            # comes off this letter's own ink, which is what puts a mark
            # above the accent the letter already carries
            donor_x = {g: r.BaseAnchor[0].XCoordinate
                       for g, r in rows if r.BaseAnchor and r.BaseAnchor[0]}
            for name in sorted(letters - have, key=gid):
                box = _bounds(gs, name)
                if not box:
                    continue
                anchor = otTables.Anchor()
                anchor.Format = 1
                inherited = donor_x.get(bases.get(name))
                anchor.XCoordinate = (inherited if inherited is not None
                                      else otRound((box[0] + box[2]) / 2) + dx)
                anchor.YCoordinate = otRound(box[3] if use_top else box[1]) + dy
                rec = otTables.BaseRecord()
                rec.BaseAnchor = [anchor]
                rows.append((name, rec))
                added += 1
            rows.sort(key=lambda pair: gid(pair[0]))
            sub.BaseCoverage.glyphs = [g for g, _ in rows]
            sub.BaseArray.BaseRecord = [r for _, r in rows]
            sub.BaseArray.BaseCount = len(rows)
    return added


# the combining double diacritics (U+035C-0362) tie two characters: the
# donor draws them centred on the join, a cell wide, and leaves them out
# of every mark lookup, so unattached they straddle the two cells as
# meant. Not a mark to place on one base
DOUBLE_SPAN = frozenset(range(0x035C, 0x0363))


# the GSUB features whose output is still the letter, drawn another
# way, and so still takes the letter's accent: a language form, a
# stylistic or character variant, a case form. Not a width form (fwid,
# hwid), a vertical form, a superscript or a fraction figure -- those
# are other glyphs drawn elsewhere, and their marks fall where they fall
VARIANT_FEATURES = frozenset({"locl", "salt", "case"}
                             | {f"cv{i:02d}" for i in range(1, 100)}
                             | {f"ss{i:02d}" for i in range(1, 21)})


def _letter_variants(font, letters, features=VARIANT_FEATURES):
    """The glyphs a GSUB single or alternate substitution under one of
    `features` (None: any feature) turns a letter into -- a locl form
    (the Serbian б), a cvNN or ssNN variant -- followed two steps. A
    mark on a letter the shaper has already swapped attaches to the
    substitute, so the substitute needs the letter's anchors as much
    as the letter does."""
    out = set()
    if "GSUB" not in font:
        return out
    gsub = font["GSUB"].table
    want = set()
    for fr in gsub.FeatureList.FeatureRecord:
        if features is None or fr.FeatureTag in features:
            want |= set(fr.Feature.LookupListIndex)
    pairs = []
    for i in sorted(want):
        kind, subs = _unwrap(gsub.LookupList.Lookup[i])
        if kind in (1, 3):
            pairs.extend(_subst_pairs(kind, subs, "?"))
    known = set(letters)
    for _ in range(2):
        out |= {dst for src, dst in pairs if src in known and dst not in known}
        known |= out
    return out


def anchor_loose_marks(font, floor=16, band=300, near=80):
    """Give a combining mark no lookup covers the mark anchor its
    neighbours share, in the lookup whose marks sit where it does.
    Returns the count.

    The other half of anchor_loose_letters: a base anchor places a mark
    only if the mark has an anchor of its own in the same lookup, and
    Source Code Pro Italic leaves the candrabindu (U+0310) out of its
    above-mark lookup where the upright has it, so on every italic face
    a candrabindu landed a cell right of its letter, on the next
    character. Within a lookup the donor gives every mark drawn at one
    height the same anchor -- (300, 500) for the above-marks, (300,
    680) for their .cap forms drawn higher for a capital, (300, -20)
    below, the italics' shifted by the slant -- so the median over the
    covered marks whose ink sits within `near` of this one's is the
    anchor to give it. The lookup is chosen the same way: the one,
    among those covering `floor` marks or more, whose marks' ink centre
    lies nearest, and within `band` -- an overlay has no such home and
    is left alone. A mark is every GDEF mark in the combining blocks
    and every glyph GSUB makes of one (the .cap form ccmp swaps in
    after a capital, which the donor leaves out with it). Mark-to-base
    only: which marks may stack on which is the donor's to say. The
    double diacritics are not marks to place (DOUBLE_SPAN), and a mark
    drawn with no ink has nothing to place.
    """
    cmap = font.getBestCmap()
    classes = font["GDEF"].table.GlyphClassDef.classDefs if "GDEF" in font else {}
    gs = font.getGlyphSet()
    gid = font.getGlyphID
    subs = [sub for _, parts in _mark_base_lookups(font) for sub in parts]
    covered = set()
    for sub in subs:
        covered |= set(sub.MarkCoverage.glyphs)
    marks = {g for cp, g in cmap.items() if classes.get(g) == 3 and cp not in DOUBLE_SPAN}
    marks |= {g for g in _letter_variants(font, marks, features=None) if classes.get(g) == 3}
    loose = [g for g in sorted(marks, key=gid) if g not in covered and _bounds(gs, g)]
    # each big one-class subtable: where its marks' ink sits, and each
    # mark's own anchor and ink centre
    homes = []
    for sub in subs:
        cov, array, records = sub.MarkCoverage, sub.MarkArray, sub.MarkArray.MarkRecord
        if sub.ClassCount != 1 or len(records) < floor:
            continue
        rows = [((b[1] + b[3]) / 2, r.MarkAnchor) for g, r in zip(cov.glyphs, records)
                for b in [_bounds(gs, g)] if b]
        if not rows:
            continue
        centre = statistics.median(c for c, _ in rows)
        homes.append((centre, rows, sub))
    added = 0
    for g in loose:
        box = _bounds(gs, g)
        mid = (box[1] + box[3]) / 2
        close = [h for h in homes if abs(h[0] - mid) <= band]
        if not close:
            continue
        _, rows, sub = min(close, key=lambda h: abs(h[0] - mid))
        alike = [a for c, a in rows if abs(c - mid) <= near] or [a for _, a in rows]
        x = otRound(statistics.median(a.XCoordinate for a in alike))
        y = otRound(statistics.median(a.YCoordinate for a in alike))
        anchor = otTables.Anchor()
        anchor.Format = 1
        anchor.XCoordinate, anchor.YCoordinate = x, y
        rec = otTables.MarkRecord()
        rec.Class, rec.MarkAnchor = 0, anchor
        # read the subtable afresh for each insertion: the coverage and
        # the records are replaced together below, and a list kept from
        # before the first insertion would pair every mark after it
        # with its neighbour's anchor (the italic's caron took the .cap
        # anchor that way, and drew through b's ascender)
        cov, array = sub.MarkCoverage, sub.MarkArray
        pairs = list(zip(cov.glyphs, array.MarkRecord))
        pairs.append((g, rec))
        pairs.sort(key=lambda p: gid(p[0]))
        cov.glyphs = [n for n, _ in pairs]
        array.MarkRecord = [r for _, r in pairs]
        array.MarkCount = len(pairs)
        added += 1
    return added


def _mkmk_anchors(font):
    """One {codepoint: (Mark1 anchor y, [Mark2 anchor])} per mark-to-mark
    subtable, for the encoded marks in both of its coverages."""
    out = []
    if "GPOS" not in font:
        return out
    rev = {g: cp for cp, g in font.getBestCmap().items()}
    table = font["GPOS"].table
    want = set()
    for fr in table.FeatureList.FeatureRecord:
        if fr.FeatureTag == "mkmk":
            want |= set(fr.Feature.LookupListIndex)
    for i in sorted(want):
        kind, subs = _unwrap_pos(table.LookupList.Lookup[i])
        if kind != 6:
            continue
        for sub in subs:
            ones = dict(zip(sub.Mark1Coverage.glyphs, sub.Mark1Array.MarkRecord))
            rows = {}
            for g, rec in zip(sub.Mark2Coverage.glyphs, sub.Mark2Array.Mark2Record):
                if g in ones and g in rev:
                    rows[rev[g]] = (ones[g].MarkAnchor.YCoordinate, rec.Mark2Anchor)
            if rows:
                out.append(rows)
    return out


def mirror_stack_lift(font, model):
    """Where a mark's Mark2 anchor sits at the height its own Mark1
    anchor attaches at, so that a second mark stacks ON the first
    instead of above it, lift it by what `model` -- the upright at the
    same weight -- lifts the same mark. Returns the count.

    Source Code Pro Italic's grave, acute, breve and ring carry a Mark2
    anchor at exactly the Mark1 height at every weight, and the italic
    faces drew x̀́ as two accents on top of each other where the upright
    lifts the second by 111 units at Regular. That the upright's lift
    is the designer's, weight by weight (30 at Light, 248 at Bold, none
    at wght 200), is why it is copied rather than replaced by a rule.
    """
    theirs = _mkmk_anchors(model)
    lifted = 0
    for ours in _mkmk_anchors(font):
        # the model's subtable that covers the same marks: the two
        # donors are one family, but their lookups need not be numbered
        # alike
        shared, rows = max(((len(ours.keys() & t.keys()), t) for t in theirs),
                           key=lambda pair: pair[0], default=(0, None))
        if not shared:
            continue
        for cp, (y1, anchors) in ours.items():
            if cp not in rows:
                continue
            model_y1, model_anchors = rows[cp]
            for anchor, model_anchor in zip(anchors, model_anchors):
                if anchor is None or model_anchor is None:
                    continue
                if anchor.YCoordinate == y1 and model_anchor.YCoordinate != model_y1:
                    anchor.YCoordinate = y1 + (model_anchor.YCoordinate - model_y1)
                    lifted += 1
    return lifted


def import_donor_base_anchors(base, donor, glyph_map, placements):
    """Give letters taken from a second donor that donor's own base
    anchors, inside the face's own mark lookups. Returns how many
    (glyph, lookup) anchors were added.

    The face positions accents with its first donor's lookups: a mark
    array over that donor's marks, a base array over its bases. A letter
    appended from somewhere else is a stranger to both, so an accent
    over it falls wherever the outline happens to land — which is what
    Greek and Cyrillic did in the italic faces, where every accent sat
    at offset 0.

    Only the BASE side comes across. A mark's own anchor is a point on
    the mark, and the marks in the run are the face's own, so theirs is
    the one that must be used; the base's anchor is a point on the base,
    and that is the donor's to give. Mixing the two is not a compromise,
    it is how mark attachment is defined.

    `glyph_map` is {donor glyph: [our names]} -- a list, because a donor
    glyph can be the drawing for several codepoints.
    """
    pairs = pair_mark_lookups(base, donor)
    if not pairs:
        return 0
    ours = dict(_mark_base_lookups(base))
    theirs = dict(_mark_base_lookups(donor))
    gid = base.getGlyphID
    added = 0
    for our_i, their_i in pairs.items():
        our_subs, their_subs = ours[our_i], theirs[their_i]
        if len(our_subs) != 1 or len(their_subs) != 1:
            continue          # one subtable each here; anything else is theirs
        ours_sub, theirs_sub = our_subs[0], their_subs[0]
        if ours_sub.ClassCount != theirs_sub.ClassCount:
            continue          # the classes would not line up
        have = set(ours_sub.BaseCoverage.glyphs)
        rows = list(zip(ours_sub.BaseCoverage.glyphs,
                        ours_sub.BaseArray.BaseRecord))
        for name, rec in zip(theirs_sub.BaseCoverage.glyphs,
                             theirs_sub.BaseArray.BaseRecord):
            # one donor glyph can stand for more than one codepoint --
            # Source Sans draws U+03C6 and U+03D5 with a single 'phi' --
            # and each of ours wants its own copy of the anchor
            for ours_name in glyph_map.get(name, ()):
                if ours_name in have:
                    continue
                sx, dx = placements.get(ours_name, (1.0, 0))
                moved = otTables.BaseRecord()
                moved.BaseAnchor = [_plain_anchor(a, sx, dx)
                                    for a in rec.BaseAnchor]
                if not any(moved.BaseAnchor):
                    continue
                rows.append((ours_name, moved))
                have.add(ours_name)
                added += 1
        rows.sort(key=lambda pair: gid(pair[0]))
        ours_sub.BaseCoverage.glyphs = [g for g, _ in rows]
        ours_sub.BaseArray.BaseRecord = [r for _, r in rows]
        ours_sub.BaseArray.BaseCount = len(rows)
    return added


def _our_names(glyphs, glyph_map, donor_cmap, our_cmap):
    """Our names for a donor coverage: the glyphs we took from it, plus
    any the donor and we both encode at the same codepoint. A donor
    glyph that is neither (a contextual variant like 'uni0301.g', say)
    drops out."""
    out = []
    for g in glyphs:
        ours = glyph_map.get(g)
        if ours:
            out.extend(ours)
            continue
        cp = donor_cmap.get(g)
        if cp is not None and cp in our_cmap:
            out.append(our_cmap[cp])
    return out


def _coverage(glyphs, gid):
    cov = otTables.Coverage()
    cov.glyphs = sorted(set(glyphs), key=gid)
    return cov


def _chain_context_conditions(gsub, order, callees):
    """[(backtrack, input, lookahead)] over the format-3 chain contexts
    in `order` that call one of `callees` at the first input position --
    each a list of donor glyph-name lists, in the subtable's own order
    (backtrack runs outwards from the input, as the format stores it)."""
    out = []
    for i in order:
        kind, subs = _unwrap(gsub.LookupList.Lookup[i])
        if kind != 6:
            continue
        for st in subs:
            if getattr(st, "Format", None) != 3:
                continue
            recs = getattr(st, "SubstLookupRecord", None) or ()
            if not any(r.LookupListIndex in callees and r.SequenceIndex == 0
                       for r in recs):
                continue
            if len(st.InputCoverage or ()) != 1:
                continue      # one input glyph is all this copies
            out.append(([c.glyphs for c in st.BacktrackCoverage or ()],
                        st.InputCoverage[0].glyphs,
                        [c.glyphs for c in st.LookAheadCoverage or ()]))
    return out


def import_donor_decompositions(base, donor, glyph_map):
    """Carry across the donor's 'ccmp' rules that take one of the
    imported letters apart, under the donor's own condition. Returns the
    number of rules copied.

    Some letters are positioned by decomposition rather than by an
    anchor: both Adobe donors take Cyrillic ï (U+0457) to a dotless i
    and a diaeresis, so the acute that follows stacks on the diaeresis
    instead of landing on top of it. import_donor_base_anchors has
    nothing to give those -- there is no base anchor to copy, because
    the letter is never a base.

    The condition comes across with the rule. The donor does not name
    the decomposition in its feature; it names chain contexts that call
    it, and the context is the whole point: ï comes apart BEFORE a
    combining acute, and is one drawn letter everywhere else. Copied
    without it, every Ukrainian ï in ordinary text was replaced by the
    Latin dotless i -- a different letterform, 23% wider in the ink --
    plus a floating diaeresis, and the drawn ï we had just imported was
    never reached. So a rule no copied context can reach is dropped
    rather than made unconditional.

    Only one-to-many rules, and only where every output is a glyph this
    face already has at the same codepoint: the face's own ccmp then
    carries on from there (it already composes the diaeresis and the
    acute into one mark; what it lacked was the letter coming apart).
    Nothing is grafted, so a rule whose outputs are unencoded in the
    donor is left behind rather than guessed at.

    Both new lookups go to the front of the LookupList, because a shaper
    runs a stage's lookups in that order and this has to happen before
    the marks are composed. The feature names the chain context only:
    naming the substitution itself is what would strip the condition."""
    if "GSUB" not in donor or "GSUB" not in base:
        return 0
    ours = base["GSUB"].table
    records = [fr for fr in ours.FeatureList.FeatureRecord
               if fr.FeatureTag == "ccmp"]
    if not records:
        return 0
    theirs = donor["GSUB"].table
    donor_cmap = {gn: cp for cp, gn in donor.getBestCmap().items()}
    our_cmap = base.getBestCmap()
    order, _ = _ccmp_lookups(theirs)
    callees = {i for i in order
               if _unwrap(theirs.LookupList.Lookup[i])[0] == 2}   # MultipleSubst
    mapping = {}
    for i in sorted(callees):
        _, subs = _unwrap(theirs.LookupList.Lookup[i])
        for sub in subs:
            for src, seq in getattr(sub, "mapping", {}).items():
                out = []
                for g in seq:
                    cp = donor_cmap.get(g)
                    if cp is None or cp not in our_cmap:
                        out = None
                        break
                    out.append(our_cmap[cp])
                if not out:
                    continue
                for ours_src in glyph_map.get(src, ()):
                    mapping.setdefault(ours_src, out)
    if not mapping:
        return 0
    gid = base.getGlyphID
    contexts = []
    for back, inputs, look in _chain_context_conditions(theirs, order, callees):
        got = [g for g in _our_names(inputs, glyph_map, donor_cmap, our_cmap)
               if g in mapping]
        sides = [_our_names(c, glyph_map, donor_cmap, our_cmap)
                 for c in back + look]
        # a context we cannot reproduce in full is not narrowed, it is
        # dropped: a missing lookahead would widen it to "anywhere"
        if not got or not all(sides):
            continue
        contexts.append((got, [_our_names(c, glyph_map, donor_cmap, our_cmap)
                               for c in back],
                         [_our_names(c, glyph_map, donor_cmap, our_cmap)
                          for c in look]))
    reached = {g for got, _, _ in contexts for g in got}
    mapping = {k: v for k, v in mapping.items() if k in reached}
    if not mapping:
        return 0
    st = otTables.MultipleSubst()
    st.Format = 1
    st.mapping = mapping
    multi = otTables.Lookup()
    multi.LookupType, multi.LookupFlag, multi.SubTable = 2, 0, [st]
    multi.SubTableCount = 1

    chain = otTables.Lookup()
    chain.LookupType, chain.LookupFlag = 6, 0
    chain.SubTable = []
    for got, back, look in contexts:
        sub = otTables.ChainContextSubst()
        sub.Format = 3
        sub.BacktrackCoverage = [_coverage(c, gid) for c in back]
        sub.BacktrackGlyphCount = len(sub.BacktrackCoverage)
        sub.InputCoverage = [_coverage([g for g in got if g in mapping], gid)]
        sub.InputGlyphCount = 1
        sub.LookAheadCoverage = [_coverage(c, gid) for c in look]
        sub.LookAheadGlyphCount = len(sub.LookAheadCoverage)
        rec = otTables.SubstLookupRecord()
        # index 1: the MultipleSubst below, once both sit at the front
        rec.SequenceIndex, rec.LookupListIndex = 0, 1
        sub.SubstLookupRecord = [rec]
        sub.SubstCount = 1
        chain.SubTable.append(sub)
    chain.SubTableCount = len(chain.SubTable)
    _insert_lookups_first(ours, [chain, multi])
    for fr in records:
        # the chain only: the feature naming the substitution directly
        # is exactly what would run it with its context thrown away
        fr.Feature.LookupListIndex = sorted(set(fr.Feature.LookupListIndex) | {0})
        fr.Feature.LookupCount = len(fr.Feature.LookupListIndex)
    return len(mapping)


def classify_unicode_marks(font):
    """GDEF class 3 (Mark) for every cmap'd glyph whose Unicode category
    is Mn, and for everything a feature substitutes for one of those.
    Existing classes are kept.

    Source Code Pro leaves two of its own combining marks (U+035F,
    U+0361, the double-width ones) unclassified — and, in the ITALIC
    donor only, the `.cap` design its ccmp swaps U+0310 for after a
    capital. A substituted glyph takes its class from GDEF alone once a
    font has a GlyphClassDef (HarfBuzz has no Unicode-category
    fallback), so that one became a BASE: the mark-to-base search for
    the next mark stopped on it and gave up, and 23 of the 53 combining
    marks lost their attachment after U+0310 in all five italic Latin
    faces and the italic variable font — `E` + U+0310 + U+0301 put both
    accents on the character after them. Reachable only through a
    feature, so the cmap sweep above could not see it."""
    if "GDEF" not in font or font["GDEF"].table.GlyphClassDef is None:
        return []
    defs = font["GDEF"].table.GlyphClassDef.classDefs
    fixed = []
    for cp, g in font.getBestCmap().items():
        if unicodedata.category(chr(cp)) == "Mn" and defs.get(g) != 3:
            defs[g] = 3
            fixed.append(g)
    # the closure: a variant of a variant of a mark is a mark too, and
    # so is a ligature of marks — Source Code Pro's ccmp stacks
    # U+0308+U+0301 and 29 other pairs into one glyph, 21 of which no
    # codepoint reaches, so neither the cmap sweep above nor the edges
    # below could see them. A ligature is read only when EVERY component
    # is a mark: Ą is A plus an ogonek, and calling that a mark zeroes
    # its advance
    edges = []
    for lookup in (font["GSUB"].table.LookupList.Lookup
                   if "GSUB" in font else []):
        kind, subtables = _unwrap(lookup)
        for sub in subtables:
            if kind == 1:
                edges += [([src], [dst])
                          for src, dst in (getattr(sub, "mapping", None) or {}).items()]
            elif kind == 2:
                edges += [([src], list(dsts))
                          for src, dsts in (getattr(sub, "mapping", None) or {}).items()]
            elif kind == 3:
                edges += [([src], list(dsts)) for src, dsts in
                          (getattr(sub, "alternates", None) or {}).items()]
            elif kind == 4:
                for first, ligs in (getattr(sub, "ligatures", None) or {}).items():
                    edges += [([first, *lig.Component], [lig.LigGlyph])
                              for lig in ligs]
    changed = True
    while changed:
        changed = False
        for srcs, dsts in edges:
            if any(defs.get(src) != 3 for src in srcs):
                continue
            for dst in dsts:
                if defs.get(dst) != 3:
                    defs[dst] = 3
                    fixed.append(dst)
                    changed = True
    return fixed

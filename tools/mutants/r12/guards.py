"""Search for a calt guard whose loss no CASES probe sees: drop each
chain-context rule of the combined calt lookup in turn, shape every
operator run of length 3-4 (plus the CASES), and report the rules whose
loss changes some run while every CASES probe still shapes as expected.
`python guards.py` prints the search; mutants10.G14 calls drop()."""
import io
import itertools
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mutlib as M  # noqa: E402
import build  # noqa: E402
from verify import CASES  # noqa: E402
from verifylib import make_shaper  # noqa: E402

OPS = "<>=!|-~+:./&#?%*;"
ON = {"calt": True, "liga": True}


def chain_rules(tf):
    """[(lookup index, subtable, rule list attr, rule index)] over every
    ChainContextSubst rule of the calt lookups (format 1 and 3)."""
    gsub = tf["GSUB"].table
    tags = {}
    for fr in gsub.FeatureList.FeatureRecord:
        for li in fr.Feature.LookupListIndex:
            tags.setdefault(li, set()).add(fr.FeatureTag)
    out = []
    for i, lk in enumerate(gsub.LookupList.Lookup):
        if "calt" not in tags.get(i, ()):
            continue
        kind, subs = build._unwrap(lk)
        if kind != 6:
            continue
        for si, st in enumerate(subs):
            if st.Format == 3:
                out.append((i, si, st, None, None))
            elif st.Format == 1:
                for ri, rs in enumerate(st.ChainSubRuleSet):
                    for rj, rule in enumerate(rs.ChainSubRule):
                        out.append((i, si, st, ri, rj))
    return out


def describe(tf, rule):
    i, si, st, ri, rj = rule
    if st.Format == 3:
        cov = lambda cs: ["/".join(c.glyphs[:3]) for c in cs]
        return (f"lookup {i} sub {si} fmt3 back {cov(st.BacktrackCoverage)} in {cov(st.InputCoverage)} "
                f"ahead {cov(st.LookAheadCoverage)} subst {[(r.SequenceIndex, r.LookupListIndex) for r in st.SubstLookupRecord]}")
    r = st.ChainSubRuleSet[ri].ChainSubRule[rj]
    first = st.Coverage.glyphs[ri]
    return (f"lookup {i} sub {si} fmt1 back {r.Backtrack} in {[first] + r.Input} ahead {r.LookAhead} "
            f"subst {[(s.SequenceIndex, s.LookupListIndex) for s in r.SubstLookupRecord]}")


def remove(tf, rule):
    i, si, st, ri, rj = rule
    lk = tf["GSUB"].table.LookupList.Lookup[i]
    kind, subs = build._unwrap(lk)
    if st.Format == 3:
        # drop the subtable itself
        holder = lk.SubTable
        if lk.LookupType == 7:
            ext = [e for e in lk.SubTable if e.ExtSubTable is st]
            lk.SubTable = [e for e in lk.SubTable if e.ExtSubTable is not st]
        else:
            lk.SubTable = [s for s in lk.SubTable if s is not st]
        lk.SubTableCount = len(lk.SubTable)
    else:
        rs = st.ChainSubRuleSet[ri]
        del rs.ChainSubRule[rj]
        rs.ChainSubRuleCount = len(rs.ChainSubRule)


def glyph_names(tf, shape, text):
    order = tf.getGlyphOrder()
    infos, _ = shape(text, ON)
    return tuple(order[i.codepoint] for i in infos)


def corpus():
    runs = set()
    for n in (2, 3, 4):
        for t in itertools.product(OPS, repeat=n):
            runs.add("a " + "".join(t) + " b")
    return sorted(runs)


def search(src):
    tf = TTFont(str(src))
    rules = chain_rules(tf)
    print(len(rules), "calt chain rules/subtables")
    base_shape = make_shaper(src)
    texts = corpus()
    base = {t: glyph_names(tf, base_shape, t) for t in texts}
    base_cases = {t: len(base_shape(t, ON)[0]) for t, _ in CASES if all(ord(c) < 0x3000 for c in t)}
    hits = []
    for idx in range(len(rules)):
        mt = TTFont(str(src))
        rule = chain_rules(mt)[idx]
        desc = describe(mt, rule)
        remove(mt, rule)
        buf = io.BytesIO()
        mt.save(buf)
        shape = make_shaper(buf.getvalue())
        cases_ok = all(len(shape(t, ON)[0]) == want for t, want in CASES if all(ord(c) < 0x3000 for c in t))
        changed = [t for t in texts if glyph_names(mt, shape, t) != base[t]]
        if changed:
            print(f"rule {idx}: {desc}\n    CASES {'pass' if cases_ok else 'FAIL'}; "
                  f"{len(changed)} runs change, e.g. {changed[:4]}")
            if cases_ok:
                hits.append((idx, changed))
    return hits


def drop(tf, src):
    """The mutant: drop the first rule the search found (cached)."""
    cache = Path(__file__).with_name("guards.hit")
    if cache.exists():
        idx = int(cache.read_text().split()[0])
    else:
        hits = search(src)
        if not hits:
            raise RuntimeError("no guard whose loss escapes CASES")
        idx = hits[0][0]
        cache.write_text(f"{idx} {hits[0][1][:6]}")
    rule = chain_rules(tf)[idx]
    print("    dropping", describe(tf, rule))
    remove(tf, rule)
    drop.changed = cache.read_text()


if __name__ == "__main__":
    hits = search(Path(sys.argv[1]) if len(sys.argv) > 1 else M.REPO / "dist" / "latin" / "Gengou-Regular.otf")
    print("HITS (CASES still pass):")
    for idx, changed in hits:
        print(idx, len(changed), changed[:8])

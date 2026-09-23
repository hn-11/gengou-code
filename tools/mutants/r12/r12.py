"""Round 12 mutants. `python r12.py ID [ID ...]`, `python r12.py list`.
Harness is round 9/10's mutlib.py, copied into this directory."""
import shutil
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mutlib as M  # noqa: E402
import mutants10 as X  # noqa: E402
import build  # noqa: E402

HERE = Path(__file__).resolve().parent
DIST = M.REPO / "dist"
LAT_REG = DIST / "latin" / "Gengou-Regular.otf"
LAT_BOLD = DIST / "latin" / "Gengou-Bold.otf"
JP_REG = DIST / "GengouJP-Regular.otf"
JP_TERM = DIST / "GengouJPTerm-Regular.otf"
NF_REG = DIST / "nerd" / "latin" / "GengouNFM-Regular.otf"
VF_U = DIST / "latin" / "Gengou[wght].otf"

MUTANTS, EXTRA = {}, {}
ON = {"calt": True, "liga": True}
g, register, single_pos = X.g, X.register, X.single_pos
run_proof, lig_glyph = X.run_proof, X.lig_glyph


def mutant(id_, src, doc, **kw):
    def deco(fn):
        MUTANTS[id_] = (src, doc, fn)
        EXTRA[id_] = kw
        return fn
    return deco


def cov(glyphs):
    c = ot.Coverage()
    c.glyphs = list(glyphs)
    return c


def wrap(kind, sub):
    lk = ot.Lookup()
    lk.LookupType = kind
    lk.LookupFlag = 0
    lk.SubTable = [sub]
    lk.SubTableCount = 1
    return lk


def append_lookup(tf, table, lookup):
    """Append a lookup with no feature of its own; return its index."""
    t = tf[table].table
    t.LookupList.Lookup.append(lookup)
    t.LookupList.LookupCount = len(t.LookupList.Lookup)
    return t.LookupList.LookupCount - 1


def chain3(kind, back, inp, ahead, called):
    """A format-3 chain context (GSUB type 6 / GPOS type 8) that calls
    `called` on input position 0. `back` is nearest-first."""
    sub = ot.ChainContextSubst() if kind == 6 else ot.ChainContextPos()
    sub.Format = 3
    sub.BacktrackGlyphCount = len(back)
    sub.BacktrackCoverage = [cov(b) for b in back]
    sub.InputGlyphCount = len(inp)
    sub.InputCoverage = [cov(i) for i in inp]
    sub.LookAheadGlyphCount = len(ahead)
    sub.LookAheadCoverage = [cov(a) for a in ahead]
    rec = ot.SubstLookupRecord() if kind == 6 else ot.PosLookupRecord()
    rec.SequenceIndex = 0
    rec.LookupListIndex = called
    if kind == 6:
        sub.SubstCount = 1
        sub.SubstLookupRecord = [rec]
    else:
        sub.PosCount = 1
        sub.PosLookupRecord = [rec]
    return sub


def ligature_glyphs(tf):
    """Every glyph a LigatureSubst in this face produces."""
    out = set()
    for lk in tf["GSUB"].table.LookupList.Lookup:
        kind, subs = build._unwrap(lk)
        if kind != 4:
            continue
        for sub in subs:
            for first, ligs in sub.ligatures.items():
                for lig in ligs:
                    out.add(lig.LigGlyph)
    return sorted(out, key=tf.getGlyphID)


def mirror(tf, name):
    b = M.bounds(tf.getGlyphSet(), name)
    M.redraw(tf, name, (-1, 0, 0, 1, b[0] + b[2], 0))


def build_mutant(id_):
    src, doc, fn = MUTANTS[id_]
    kw = EXTRA.get(id_, {})
    out_dir = HERE / id_
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / kw.get("out_name", "mutant.otf")
    tf = M.load(src)
    fn(tf, src)
    tf.save(str(out))
    (out.with_suffix(".src")).write_text(str(src))
    for beside_src, beside_name in kw.get("beside", []):
        shutil.copy(beside_src, out_dir / beside_name)
    print(f"=== {id_}: {doc}")
    print(f"    src {src}")
    fails, _ = M.run_verifier(out, out_dir / "verify.txt")
    if fails:
        print(f"    CAUGHT ({len(fails)}):")
        for f in fails[:8]:
            print("      " + f)
    else:
        print("    *** NOT CAUGHT (all gates pass apart from hints) ***")
    proof = None
    for mod in list(sys.modules.values()):
        if getattr(mod, "__name__", "").startswith("r12"):
            proof = getattr(mod, f"{id_}_proof", None) or proof
    if proof:
        proof(src, out)
    return out, fails


MUTANT_MODULES = ["r12a", "r12b"]


def main():
    for m in MUTANT_MODULES:
        try:
            __import__(m)
        except ModuleNotFoundError:
            pass
    args = sys.argv[1:]
    if not args or args[0] == "list":
        for k, (src, doc, _) in MUTANTS.items():
            print(f"{k:8s} {Path(src).name:28s} {doc}")
    else:
        for a in args:
            build_mutant(a)


if __name__ == "__main__":
    main()

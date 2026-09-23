"""Round 11 mutants. `python r11.py ID [ID ...]`, `python r11.py list`.
Harness is round 9/10's mutlib.py, copied into this directory."""
import shutil
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot
from fontTools.otlLib import builder as otl

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mutlib as M  # noqa: E402
import mutants10 as X  # noqa: E402
import build  # noqa: E402

HERE = Path(__file__).resolve().parent
DIST = M.REPO / "dist"
LAT_REG = DIST / "latin" / "Gengou-Regular.otf"
JP_REG = DIST / "GengouJP-Regular.otf"
JP_TERM = DIST / "GengouJPTerm-Regular.otf"
NF_REG = DIST / "nerd" / "latin" / "GengouNFM-Regular.otf"
VF_U = DIST / "latin" / "Gengou[wght].otf"

MUTANTS, EXTRA = {}, {}
ON = {"calt": True, "liga": True}
g, register, single_pos = X.g, X.register, X.single_pos
run_proof = X.run_proof


def mutant(id_, src, doc, **kw):
    def deco(fn):
        MUTANTS[id_] = (src, doc, fn)
        EXTRA[id_] = kw
        return fn
    return deco


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
        if getattr(mod, "__name__", "").startswith("r11"):
            proof = getattr(mod, f"{id_}_proof", None) or proof
    if proof:
        proof(src, out)
    return out, fails


MUTANT_MODULES = ["r11a", "r11b", "r11c", "r11d"]


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

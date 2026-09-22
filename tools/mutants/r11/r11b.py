"""Round 11, batch B: VORG records, the Nerd face's family reference,
the calt guard chain, and the mark gates' own inputs."""
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mutlib as M  # noqa: E402
import build  # noqa: E402
from r11 import mutant, run_proof, g, ON  # noqa: E402
from r11 import LAT_REG, JP_REG, JP_TERM, NF_REG, VF_U  # noqa: E402

TTB = dict(direction="ttb")


# ---------------------------------------------------------------- B1
@mutant("B1", JP_REG, "VORG: the vertical origin of あ and 一 dropped 880 -> 620 "
                      "(vmtx tsb refitted): in a vertical line they sit 3.6px high")
def B1(tf, src):
    cmap = tf.getBestCmap()
    v = tf["VORG"]
    for ch in "あ一ん":
        v.VOriginRecords[cmap[ord(ch)]] = 620
    v.numVertOriginYMetrics = len(v.VOriginRecords)
    M.refit(tf)


def B1_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, "あいあ", direction="ttb")


# ---------------------------------------------------------------- B2
@mutant("B2", NF_REG, "the Nerd face drops 40 IPA Extensions characters "
                      "(U+0250..U+0277, the block bit stays set): "
                      "check_family_cmap's reference is "
                      "Gengou-Regular.otf, which never sits beside an NFM face")
def B2(tf, src):
    for t in tf["cmap"].tables:
        if t.isUnicode() and t.format != 14:
            for cp in list(t.cmap):
                if 0x0250 <= cp <= 0x0277:
                    del t.cmap[cp]


def B2_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        tf = TTFont(str(p))
        cm = tf.getBestCmap()
        print(f"  [{lbl}] {len(cm)} codepoints; U+0259 schwa in cmap: {0x0259 in cm}")
        M.report_run(lbl, p, "əɐɥ")


# ---------------------------------------------------------------- B3
@mutant("B3", LAT_REG, "calt guard chain: the 'ignore' rules that keep '::' plain "
                       "before another ':' deleted, so 'a ::: b' ligates")
def B3(tf, src):
    cmap = tf.getBestCmap()
    colon = cmap[ord(":")]
    gsub = tf["GSUB"].table
    removed = 0
    for lookup in gsub.LookupList.Lookup:
        kind, subs = build._unwrap(lookup)
        if kind != 6:
            continue
        for sub in subs:
            for rs in (getattr(sub, "ChainSubRuleSet", None) or []):
                keep = []
                for rule in rs.ChainSubRule:
                    lk = getattr(rule, "SubstLookupRecord", None) or []
                    inp = list(getattr(rule, "Input", []) or [])
                    look = list(getattr(rule, "LookAhead", []) or [])
                    back = list(getattr(rule, "Backtrack", []) or [])
                    if (not lk and inp == [colon] and look == [colon]
                            and not back):
                        removed += 1
                        continue
                    keep.append(rule)
                rs.ChainSubRule = keep
                rs.ChainSubRuleCount = len(keep)
    print(f"    (deleted {removed} guard rules)")


B3_proof = run_proof("a ::: b", "a :: b", feats=ON)


# ---------------------------------------------------------------- B4
@mutant("B4", LAT_REG, "mkmk: the Mark1 anchor of every above-accent lowered 200u "
                       "(inside check_anchor_placement's band): a second accent "
                       "stacks 2.8px too high")
def B4(tf, src):
    for i, kind, subs, _ in [(i, k, s, t) for i, k, s, t in _pos(tf)]:
        if kind != 6:
            continue
        for sub in subs:
            for rec in sub.Mark1Array.MarkRecord:
                if rec.MarkAnchor is not None:
                    rec.MarkAnchor.YCoordinate -= 200


def _pos(tf):
    import verifylib
    return verifylib._pos_lookups(tf)


B4_proof = run_proof("x̀́", "ḗ")


# ---------------------------------------------------------------- B1b
@mutant("B1b", JP_REG, "VORG: a vertical origin of 620 (default 880) given to "
                       "the symbols ○ ■ 〇 ￥ (vmtx tsb refitted): in a vertical "
                       "line they float 3.6px above their column")
def B1b(tf, src):
    cmap = tf.getBestCmap()
    v = tf["VORG"]
    for ch in "○■〇￥":
        v.VOriginRecords[cmap[ord(ch)]] = 620
    v.numVertOriginYMetrics = len(v.VOriginRecords)
    M.refit(tf)


def B1b_proof(orig, mut):
    for lbl, p in (("orig", orig), ("MUT", mut)):
        M.report_run(lbl, p, "あ■あ", direction="ttb")

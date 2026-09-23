import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import r11
for m in ("r11a", "r11b", "r11c", "r11d"):
    try:
        __import__(m)
    except ModuleNotFoundError:
        pass
args = sys.argv[1:]
if not args or args[0] == "list":
    for k, (src, doc, _) in r11.MUTANTS.items():
        print(f"{k:8s} {Path(src).name:28s} {doc}")
else:
    for a in args:
        r11.build_mutant(a)

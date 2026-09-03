"""Parse the Reddit race logs into structured races.

Log format: races separated by '.', six comma-separated horses per race
(track 1..6). A token is the horse number plus optional flags:
  x = he bet on it, w = it won  (e.g. '4xw' / '1w' / '19x' / '3')
"""
import pathlib
import re
import sys

TOKEN_RE = re.compile(r"^(\d{1,2})([xw]{0,2})$")


def _clean(token):
    """Normalise the handful of typos in the transcript."""
    t = token.strip().lower()
    t = re.sub(r"^w(\d+)$", r"\1w", t)        # 'w29'   -> '29w'
    t = re.sub(r"^(\d+)xw(\d+)$", r"\1xw", t) # '1xw2'  -> '1xw' (stray digit)
    t = re.sub(r"^(\d+)w(\d+)$", r"\1w", t)   # '7w3'   -> '7w'
    return t


def parse_log(text):
    """Return (races, problems). A race is a list of 6 dicts, index 0 = track 1."""
    races, problems = [], []
    for chunk in text.split("."):
        chunk = chunk.strip()
        if not chunk:
            continue
        horses = []
        bad = False
        for tok in chunk.split(","):
            m = TOKEN_RE.match(_clean(tok))
            if not m:
                problems.append(f"bad token {tok!r} in race {chunk!r}")
                bad = True
                break
            flags = m.group(2)
            horses.append({"horse": int(m.group(1)),
                           "bet": "x" in flags,
                           "win": "w" in flags})
        if bad:
            continue
        if len(horses) != 6:
            problems.append(f"{len(horses)} horses in race {chunk!r}")
            continue
        if sum(h["win"] for h in horses) != 1:
            problems.append(f"{sum(h['win'] for h in horses)} winners in {chunk!r}")
            continue
        races.append(horses)
    return races, problems


def find(name):
    """Locate a post file whether it sits beside the script or in post-info/."""
    here = pathlib.Path(__file__).parent
    for cand in (here / name, here / "post-info" / name):
        if cand.exists():
            return cand
    hits = list(here.rglob(name))
    if not hits:
        raise FileNotFoundError(f"{name} not found under {here}")
    return hits[0]


def load(path):
    text = find(path).read_text(encoding="utf-8")
    # the log is the longest line in the file
    line = max(text.splitlines(), key=lambda l: l.count("."))
    return parse_log(line)


if __name__ == "__main__":
    for path in sys.argv[1:] or ["SecondPost.md", "FirstPostComment.md"]:
        races, problems = load(path)
        print(f"{path}: {len(races)} valid races, {len(problems)} rejected")
        for p in problems:
            print("   ", p)

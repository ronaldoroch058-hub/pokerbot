import json
import os
import random

from .cards import shorthand, all_classes, class_combos
from .evaluator import evaluate

DATA = os.path.join(os.path.dirname(__file__), "data")
PREFLOP_FILE = os.path.join(DATA, "preflop.json")

_preflop = None


def preflop_table():
    """{class: {"eq": [vs1..vs7], "pct": percentile 0..1}} - built by `python -m pokerbot tables`."""
    global _preflop
    if _preflop is None:
        try:
            with open(PREFLOP_FILE) as f:
                _preflop = json.load(f)
        except FileNotFoundError:
            raise SystemExit("data/preflop.json missing, run: python3 -m pokerbot tables")
    return _preflop


def preflop_equity(hole, n_opp):
    row = preflop_table()[shorthand(hole)]
    return row["eq"][min(n_opp, 7) - 1]


def preflop_pct(hole):
    """0 = 32o, 1 = AA. Weighted by combos, so it's a real percentile of the 1326 hands."""
    return preflop_table()[shorthand(hole)]["pct"]


def monte_carlo(hole, board, n_opp, iters=300, rng=random, top=1.0, dead=()):
    """Equity of `hole` against n_opp random hands (or hands from the top `top` fraction).

    Ranged hands use rejection sampling against the preflop percentile. It's
    crude - a real range would be narrowed street by street - but it's what
    lets a bot say "he raised twice, he's not holding 72o".
    """
    used = set(hole) | set(board) | set(dead)
    deck = [c for c in range(52) if c not in used]
    need = 5 - len(board)
    cut = 1.0 - top
    pct = preflop_table() if top < 1.0 else None
    hole = list(hole)
    board = list(board)
    sample = rng.sample
    won = 0.0
    done = 0

    for _ in range(iters):
        if pct is None:
            draw = sample(deck, need + 2 * n_opp)
            opp = [draw[need + 2 * k: need + 2 * k + 2] for k in range(n_opp)]
        else:
            opp, draw = _ranged_draw(deck, need, n_opp, cut, pct, rng)
            if opp is None:
                continue
        full = board + draw[:need]
        mine = evaluate(hole + full)
        best = 0
        ties = 0
        for h in opp:
            v = evaluate(h + full)
            if v > best:
                best, ties = v, 1
            elif v == best:
                ties += 1
        if mine > best:
            won += 1
        elif mine == best:
            won += 1 / (ties + 1)
        done += 1

    return won / done if done else 0.5, done


def _ranged_draw(deck, need, n_opp, cut, pct, rng):
    taken = set()
    opp = []
    for _ in range(n_opp):
        for _try in range(60):
            a, b = rng.sample(deck, 2)
            if a in taken or b in taken:
                continue
            if pct[shorthand((a, b))]["pct"] >= cut:
                taken.update((a, b))
                opp.append([a, b])
                break
        else:
            return None, None  # board makes the range nearly impossible, skip this sample
    rest = [c for c in deck if c not in taken]
    return opp, rng.sample(rest, need)


def build_preflop_table(iters=4000, workers=None):
    """Equity of every starting hand class vs 1..7 random hands. Slow-ish, run once."""
    from concurrent.futures import ProcessPoolExecutor

    classes = all_classes()
    jobs = [(k, n, iters) for k in classes for n in range(1, 8)]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(_table_job, jobs, chunksize=8))

    table = {k: {"eq": [0.0] * 7} for k in classes}
    for (k, n, _), eq in zip(jobs, results):
        table[k]["eq"][n - 1] = round(eq, 4)

    # percentile by heads-up equity, counting combos
    order = sorted(classes, key=lambda k: table[k]["eq"][0])
    below = 0
    for k in order:
        c = class_combos(k)
        table[k]["pct"] = round((below + c / 2) / 1326, 4)
        below += c

    os.makedirs(DATA, exist_ok=True)
    with open(PREFLOP_FILE, "w") as f:
        json.dump(table, f, separators=(",", ":"))
    global _preflop
    _preflop = table
    return table


def _table_job(job):
    from .cards import example_hand
    key, n, iters = job
    rng = random.Random(f"{key}-{n}")
    eq, _ = monte_carlo(example_hand(key), [], n, iters, rng)
    return eq

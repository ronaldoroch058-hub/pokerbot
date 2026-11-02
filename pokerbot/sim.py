"""Background workers: 6-max ring hands as fast as they're allowed, shipped
back to the server as (per-seat stats, book line).

Also the duplicate heads-up match behind `python3 -m pokerbot match`:
the same deck is played twice with the bots swapping seats, so a bot that got
dealt aces once has to face them the next time. Cuts the luck out of a
head-to-head a lot faster than playing more hands.
"""

import random
import time

from .book import line
from .bots import BOTS, make
from .engine import Hand
from .stats import summarize


def worker(out, stop, seed, rate):
    rng = random.Random(seed)
    bots = {name: make(name) for name in BOTS}
    lineup = [name for name in BOTS for _ in range(2)]
    k = 0
    gap = 1.0 / rate if rate else 0.0
    next_t = time.monotonic()

    while not stop.is_set():
        if k % 6 == 0:
            rng.shuffle(lineup)  # new seating every orbit
        rec = Hand([bots[n] for n in lineup], button=k % 6, rng=rng).play()
        out.put((summarize(rec), line(rec)))
        k += 1

        if gap:
            next_t += gap
            delay = next_t - time.monotonic()
            if delay > 0:
                stop.wait(delay)
            else:
                next_t = time.monotonic()  # fell behind, don't try to catch up in a burst


def duplicate_match(a, b, deals=500, seed=1):
    """a vs b, returns (bb/100 for a, 95% ci)."""
    rng = random.Random(seed)
    ba, bb_ = make(a), make(b)
    xs = []
    for _ in range(deals):
        deck = list(range(52))
        rng.shuffle(deck)
        r1 = Hand([ba, bb_], button=0, deck=deck, rng=rng).play()
        r2 = Hand([bb_, ba], button=0, deck=deck, rng=rng).play()
        xs.append((r1["net"][0] + r2["net"][1]) / 100)
    n = len(xs)
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / max(n - 1, 1)
    return mean * 50, 98 * (var / n) ** 0.5

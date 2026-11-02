"""5-7 card hand evaluator.

Returns an int where bigger is better: category in the top bits
(value >> 20), then up to five 4-bit ranks for tie breaks.

Pure python, so it's built around two 8192-entry tables indexed by a 13-bit
rank mask. About 1.5us per 7-card hand on my machine, which is enough for a
few hundred Monte Carlo rollouts per decision.
"""

HIGH_CARD, PAIR, TWO_PAIR, TRIPS, STRAIGHT, FLUSH, FULL_HOUSE, QUADS, STRAIGHT_FLUSH = range(9)

CATEGORY_NAMES = [
    "HIGH CARD", "PAIR", "TWO PAIR", "THREE OF A KIND", "STRAIGHT",
    "FLUSH", "FULL HOUSE", "FOUR OF A KIND", "STRAIGHT FLUSH",
]

WHEEL = 0x100F  # A-2-3-4-5


def _straight_high(mask):
    for hi in range(12, 3, -1):
        if (mask >> (hi - 4)) & 0x1F == 0x1F:
            return hi
    if mask & WHEEL == WHEEL:
        return 3
    return -1


def _top_bits(mask, n):
    out = []
    r = 12
    while r >= 0 and len(out) < n:
        if mask >> r & 1:
            out.append(r)
        r -= 1
    return out


def _pack(*ranks):
    v = 0
    for r in ranks:
        v = v << 4 | r
    return v << 4 * (5 - len(ranks))


STRAIGHT_HIGH = [_straight_high(m) for m in range(8192)]
# five highest ranks of a mask, already packed into 20 bits
TOP5 = [_pack(*_top_bits(m, 5)) for m in range(8192)]


def evaluate(cs):
    counts = [0] * 13
    sm = [0, 0, 0, 0]
    for c in cs:
        r = c >> 2
        counts[r] += 1
        sm[c & 3] |= 1 << r

    for m in sm:
        if m.bit_count() >= 5:
            hi = STRAIGHT_HIGH[m]
            if hi >= 0:
                return STRAIGHT_FLUSH << 20 | hi << 16
            flush = FLUSH << 20 | TOP5[m]
            break
    else:
        flush = 0

    mask = sm[0] | sm[1] | sm[2] | sm[3]
    quad = trip = trip2 = pair = pair2 = -1
    for r in range(12, -1, -1):
        n = counts[r]
        if n < 2:
            continue
        if n == 4:
            quad = r
        elif n == 3:
            if trip < 0:
                trip = r
            elif trip2 < 0:
                trip2 = r
        elif pair < 0:
            pair = r
        elif pair2 < 0:
            pair2 = r

    if quad >= 0:
        kick = TOP5[mask & ~(1 << quad)] >> 16
        return QUADS << 20 | _pack(quad, kick)
    if trip >= 0 and (trip2 >= 0 or pair >= 0):
        return FULL_HOUSE << 20 | _pack(trip, max(trip2, pair))
    if flush:
        return flush
    hi = STRAIGHT_HIGH[mask]
    if hi >= 0:
        return STRAIGHT << 20 | hi << 16
    if trip >= 0:
        rest = TOP5[mask & ~(1 << trip)] >> 12
        return TRIPS << 20 | trip << 16 | rest << 8
    if pair2 >= 0:
        kick = TOP5[mask & ~(1 << pair) & ~(1 << pair2)] >> 16
        return TWO_PAIR << 20 | _pack(pair, pair2, kick)
    if pair >= 0:
        rest = TOP5[mask & ~(1 << pair)] >> 8
        return PAIR << 20 | pair << 16 | rest << 4
    return TOP5[mask]


def describe(value):
    cat = value >> 20
    if cat == STRAIGHT_FLUSH and (value >> 16 & 0xF) == 12:
        return "ROYAL FLUSH"
    return CATEGORY_NAMES[cat]

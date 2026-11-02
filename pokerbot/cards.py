# Card ints are rank << 2 | suit.
# rank 0 = deuce .. 12 = ace, suit 0..3 = c d h s.

RANKS = "23456789TJQKA"
SUITS = "cdhs"
GLYPH = {"c": "♣", "d": "♦", "h": "♥", "s": "♠"}

DECK = tuple(range(52))


def rank(c):
    return c >> 2


def suit(c):
    return c & 3


def card(text):
    # "As", "td", "10h" all work
    text = text.strip()
    r, s = text[:-1].upper(), text[-1].lower()
    if r == "10":
        r = "T"
    if r not in RANKS or len(r) != 1 or s not in SUITS:
        raise ValueError(f"bad card {text!r}")
    return RANKS.index(r) << 2 | SUITS.index(s)


def cards(text):
    return [card(t) for t in text.replace(",", " ").split()]


def name(c):
    return RANKS[c >> 2] + SUITS[c & 3]


def names(cs):
    return [name(c) for c in cs]


def pretty(cs):
    return " ".join(RANKS[c >> 2].replace("T", "10") + GLYPH[SUITS[c & 3]] for c in cs)


def shorthand(hole):
    """AKs / AKo / 77 - the 169-class key used by the preflop table."""
    a, b = sorted(hole, key=rank, reverse=True)
    ra, rb = RANKS[rank(a)], RANKS[rank(b)]
    if ra == rb:
        return ra + rb
    return ra + rb + ("s" if suit(a) == suit(b) else "o")


def all_classes():
    out = []
    for i in range(12, -1, -1):
        for j in range(i, -1, -1):
            if i == j:
                out.append(RANKS[i] * 2)
            else:
                out.append(RANKS[i] + RANKS[j] + "s")
                out.append(RANKS[i] + RANKS[j] + "o")
    return out


def class_combos(key):
    if len(key) == 2:
        return 6
    return 4 if key[2] == "s" else 12


def example_hand(key):
    """Any concrete hole cards for a class key, for building tables."""
    hi, lo = RANKS.index(key[0]), RANKS.index(key[1])
    if hi == lo:
        return [hi << 2 | 0, lo << 2 | 1]
    if key[2] == "s":
        return [hi << 2 | 0, lo << 2 | 0]
    return [hi << 2 | 0, lo << 2 | 1]

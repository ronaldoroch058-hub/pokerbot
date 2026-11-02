from ..engine import Decision


def dec(x):
    """.62 style, the way the frontend prints probabilities."""
    s = f"{x:.2f}"
    return s[1:] if s.startswith("0") else s


def chips(x):
    return f"{int(round(x)):,}"


def round_to(x, step):
    return int(round(x / step) * step)


class Bot:
    name = "?"
    blurb = ""

    def act(self, v):
        raise NotImplementedError

    # sizing helpers every bot ends up wanting

    def bet_to(self, v, frac):
        """Bet/raise `frac` of the pot (after calling), rounded to the small blind."""
        size = frac * (v.pot + v.to_call)
        to = v.cur_bet + max(size, v.min_raise_to - v.cur_bet)
        to = round_to(to, v.sb)
        return max(v.min_raise_to, min(to, v.max_raise_to))

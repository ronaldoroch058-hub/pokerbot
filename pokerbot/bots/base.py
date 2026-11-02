from ..engine import Decision


def dec(x):
    """.62 style, the way the frontend prints probabilities."""
    s = f"{x:.2f}"
    return s[1:] if s.startswith("0") else s


def chips(x):
    return f"{int(round(x)):,}"


class Bot:
    name = "?"

    def act(self, v):
        raise NotImplementedError

    def bet_to(self, v, frac):
        """Bet/raise `frac` of the pot (after calling), rounded to the small blind."""
        to = v.cur_bet + frac * (v.pot + v.to_call)
        to = int(round(to / v.sb) * v.sb)
        return max(v.min_raise_to, min(to, v.max_raise_to))

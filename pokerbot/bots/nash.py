"""NASH - plays the textbook game-theory ratios instead of reading anyone.

  * bets are polarised: strong hands for value, the weakest hands as bluffs,
    in the ratio that leaves a caller indifferent (bluffs/value = s / (1+s)
    for a bet of s times the pot)
  * facing a bet it defends to minimum defence frequency, 1 / (1+s)
  * bet size is geometric: the size that gets the stacks in by the river

It never adjusts to the opponent, which is the point. It's also the cheapest
bot here by far - 160 rollouts and some arithmetic.
"""

from ..equity import monte_carlo, preflop_pct
from ..outs import drawing_outs
from .base import Bot, Decision, dec

# share of hands to open, by how many players are left behind (blinds included)
OPEN = {0: 1.0, 1: 0.80, 2: 0.45, 3: 0.30, 4: 0.22, 5: 0.17, 6: 0.15, 7: 0.13}
# rough width of a raiser's range after 1, 2, 3+ raises
RAISER = [1.0, 0.25, 0.09, 0.04]
VALUE_CUT = [None, 0.70, 0.73, 0.76]


class Nash(Bot):
    name = "NASH"
    blurb = "Polarised bets at the indifference ratio, defends to MDF, geometric sizing."

    def act(self, v):
        think = []
        jitter = (v.rng.random() - 0.5) * 0.06  # mixes at the borders instead of a hard cut
        if v.street == 0:
            return self.preflop(v, think, jitter)
        return self.postflop(v, think, jitter)

    # -- preflop ---------------------------------------------------------------

    def preflop(self, v, think, jit):
        pct = preflop_pct(v.hole)
        think.append(f"> PCT {dec(pct)}")
        bb = v.bb

        if v.raises <= 1:
            if v.to_call == 0:  # big blind, limped to us
                if pct + jit > 0.85 and v.can_raise:
                    think.append("> RAISE LIMPERS, TOP 15%")
                    return Decision("raise", to=bb * (3 + v.callers_pre), think=think)
                think.append("> CHECK OPTION")
                return Decision("check", think=think)
            width = OPEN[min(v.behind, 7)]
            if v.position == "SB":
                width = 0.45  # only the BB behind, but out of position all hand
            think.append(f"> OPEN TOP {int(width * 100)}% ({v.behind} BEHIND)")
            if pct + jit >= 1 - width:
                return Decision("raise", to=bb * 5 // 2 + bb * v.callers_pre, think=think)
            return Decision("fold", think=think)

        # facing a raise
        raiser = RAISER[min(v.raises - 1, 3)]
        bet = v.to_call
        before = v.pot - bet
        mdf = before / (before + bet)
        width = raiser * mdf * (0.8 if v.callers_pre else 1.0)
        value = width / 3
        bluff = value * 0.5
        think.append(f"> VS TOP {int(raiser * 100)}%, MDF {dec(mdf)}")
        think.append(f"> CONTINUE TOP {width * 100:.0f}%, 3B TOP {value * 100:.1f}%")

        if pct + jit >= 1 - value and v.can_raise:
            return self.raise_or_shove(v, v.cur_bet * 3, think)
        if pct + jit >= 1 - width:
            think.append("> CALL")
            return Decision("call", think=think)
        # bluff 3-bets from just under the calling range (suited wheel aces and friends)
        if 1 - width - bluff <= pct + jit < 1 - width and v.can_raise and v.raises == 2:
            think.append("> BLUFF RAISE, BLOCKERS")
            return self.raise_or_shove(v, v.cur_bet * 3, think)
        think.append("> FOLD")
        return Decision("fold", think=think)

    def raise_or_shove(self, v, to, think):
        if to > 0.4 * v.effective:
            think.append("> COMMITTED, ALL-IN")
            return Decision("raise", to=v.max_raise_to, think=think)
        think.append("> RAISE")
        return Decision("raise", to=to, think=think)

    # -- flop, turn, river -----------------------------------------------------

    def postflop(self, v, think, jit):
        n = max(1, v.opp)
        eq, _ = monte_carlo(v.hole, v.board, min(n, 3), 160, v.rng)
        think.append(f"> EQ {dec(eq)} VS {min(n, 3)}")
        multi = 0.04 * (n - 1)
        streets_left = 4 - v.street

        if v.to_call == 0:
            behind = max(0, v.effective - v.my_bet)
            spr = behind / max(v.pot, 1)
            frac = ((1 + 2 * spr) ** (1 / streets_left) - 1) / 2
            frac = max(0.33, min(1.0, frac))
            cut = VALUE_CUT[v.street] + multi
            value_w = 1 - cut
            bluff_w = value_w * frac / (1 + frac)
            think.append(f"> SIZE {dec(frac)}P GEOMETRIC, SPR {spr:.1f}")
            think.append(f"> VALUE ≥{dec(cut)} BLUFF <{dec(bluff_w)}")
            if not v.can_raise:
                return Decision("check", think=think)
            if eq + jit >= cut:
                think.append("> BET VALUE")
                return Decision("raise", to=self.bet_to(v, frac), think=think)
            if n <= 2:
                outs = drawing_outs(v.hole, v.board) if v.street < 3 else 0
                if outs >= 8 and v.rng.random() < 0.6:
                    think.append(f"> SEMI-BLUFF, {outs} OUTS")
                    return Decision("raise", to=self.bet_to(v, frac), think=think)
                if eq < bluff_w:
                    think.append("> BET BLUFF")
                    return Decision("raise", to=self.bet_to(v, frac), think=think)
            think.append("> CHECK")
            return Decision("check", think=think)

        bet = v.to_call
        before = max(1, v.pot - bet)
        s = bet / before
        mdf = 1 / (1 + s)
        # several defenders share the job: if together they must defend mdf, each
        # one only needs 1 - (1-mdf)^(1/k). Deeper in a raise war, defend less.
        mdf_me = (1 - (1 - mdf) ** (1 / max(1, n))) * (0.75 ** max(0, v.raises - 1))
        # MDF is about our own range, not all 1326 hands. Whatever got us this far
        # rarely has less than ~35% equity vs a random hand, so rescale from there.
        floor = 0.35 / n
        need = floor + (1 - floor) * (1 - mdf_me)
        think.append(f"> FACING {dec(s)}P, MDF {dec(mdf)}")
        think.append(f"> DEFEND TOP {mdf_me * 100:.0f}%, EQ ≥{dec(need)}")

        if eq + jit >= 0.88 + 0.03 * v.raises and v.can_raise:
            think.append("> RAISE VALUE")
            to = self.bet_to(v, 1.0)
            if to > 0.5 * v.effective:
                to = v.max_raise_to
            return Decision("raise", to=to, think=think)
        if eq + jit >= need or eq >= v.pot_odds + 0.25:
            think.append("> CALL")
            return Decision("call", think=think)
        think.append("> FOLD")
        return Decision("fold", think=think)

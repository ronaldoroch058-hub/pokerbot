import itertools
import random
import unittest

from pokerbot.bots import BOTS, make
from pokerbot.bots import cfr7
from pokerbot.cards import cards, card
from pokerbot.curve import limit
from pokerbot.engine import Decision, Hand
from pokerbot.evaluator import evaluate, describe
from pokerbot.outs import drawing_outs


class Shove:
    name = "SHOVE"

    def act(self, v):
        return Decision("raise", to=v.max_raise_to) if v.can_raise else Decision("call")


class Calls:
    name = "CALLS"

    def act(self, v):
        return Decision("call")


def deck_for(holes, board, button=0):
    """Stack a deck so seat i gets holes[i] and the board comes out as given."""
    n = len(holes)
    order = [(button + 1 + k) % n for k in range(n)]
    seq = [card(holes[i][r]) for r in range(2) for i in order]
    b = cards(board)
    spare = [c for c in range(52) if c not in set(seq) | set(b)]
    seq += [spare[0], *b[:3], spare[1], b[3], spare[2], b[4]]  # burn, flop, burn, turn, burn, river
    return spare[3:] + seq[::-1]  # the dealer pops from the end


class Evaluator(unittest.TestCase):
    def test_category_counts(self):
        counts = [0] * 9
        for h in itertools.combinations(range(52), 5):
            counts[evaluate(h) >> 20] += 1
        self.assertEqual(counts, [1302540, 1098240, 123552, 54912, 10200, 5108, 3744, 624, 40])

    def test_ordering(self):
        def v(s):
            return evaluate(cards(s))
        self.assertGreater(v("As Ad Kc Kd 2h 3c 4d"), v("As Ad Qc Qd Jh 3c 4d"))
        self.assertGreater(v("2c 3d 4h 5s 6c Kd Kh"), v("Ac 2d 3h 4s 5c Kd Kh"))   # six-high beats the wheel
        self.assertEqual(v("Ah Kh 2c 3d 7s 8s 9d"), v("Ad Kd 2c 3d 7s 8s 9d"))
        self.assertEqual(describe(v("Ts Js Qs Ks As 2d 2c")), "ROYAL FLUSH")

    def test_outs(self):
        # nut flush draw + gutshot to the wheel on the flop
        self.assertEqual(drawing_outs(cards("Ah 5h"), cards("Kh 3h 4c")), 12)
        self.assertEqual(drawing_outs(cards("Ah Kh"), cards("Ac Ad Ks")), 0)  # already full


class Engine(unittest.TestCase):
    def test_chips_are_conserved(self):
        rng = random.Random(3)
        names = [n for n in BOTS for _ in range(2)]
        bots = {n: make(n) for n in BOTS}
        for k in range(150):
            rng.shuffle(names)
            stacks = [rng.choice([600, 2500, 10000]) for _ in names]
            rec = Hand([bots[n] for n in names], button=k % 6, stacks=stacks, rng=rng).play()
            self.assertEqual(sum(rec["net"]), 0)
            for i, s in enumerate(rec["seats"]):
                self.assertGreaterEqual(s["stack"] + rec["net"][i], 0)

    def test_side_pot(self):
        # short stack has the best hand, but can only win what it covered
        rec = Hand([Shove(), Shove(), Calls()], button=0, stacks=[1000, 5000, 5000],
                   deck=deck_for([["Ac", "Ad"], ["Kc", "Kd"], ["Qc", "Qd"]], "2s 7h 9d 3c 4s")).play()
        seats = {s["cards"][0][0]: i for i, s in enumerate(rec["seats"])}
        net = rec["net"]
        self.assertEqual(net[seats["A"]], 2000)    # main pot: 1000 from each
        self.assertEqual(net[seats["K"]], 3000)    # side pot: 4000 from QQ, minus its own 1000 into main
        self.assertEqual(net[seats["Q"]], -5000)

    def test_heads_up_blinds(self):
        rec = Hand([Calls(), Calls()], button=1).play()
        posts = [(st["ev"]["seat"], st["ev"]["what"]) for st in rec["steps"] if st["ev"]["k"] == "post"]
        self.assertEqual(posts, [(1, "SB"), (0, "BB")])  # button posts the small blind


class Strategy(unittest.TestCase):
    def test_limit_curve_hits_its_anchors(self):
        self.assertAlmostEqual(limit(0.5, 0.5, 200, 10000, 3), 200, places=3)
        self.assertAlmostEqual(limit(1.0, 0.5, 200, 10000, 3), 10000, places=3)
        self.assertEqual(limit(0.49, 0.5, 200, 10000, 3), 0)

    def test_cfr_converges(self):
        s = cfr7.Solver(cfr7.NOISE[3])
        s.train(300)
        early = cfr7.exploitability(s.average(), cfr7.NOISE[3])
        s.train(900)
        late = cfr7.exploitability(s.average(), cfr7.NOISE[3])
        self.assertLess(late, early)
        self.assertLess(late, 0.002)

    def test_river_strategy_is_polarised(self):
        pol = cfr7.policy()["streets"][3]["policy"][""]["strategy"]
        bet = [row[1] + row[2] for row in pol]
        self.assertGreater(bet[6], 0.5)   # best bucket bets
        self.assertGreater(bet[0], bet[3])  # worst bucket bluffs more than the middle


if __name__ == "__main__":
    unittest.main()

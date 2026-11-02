"""CFR-7 - counterfactual regret minimisation on a small abstraction.

Full no-limit hold'em is far too big to solve, so each street is solved on
its own as a toy game:

  * every hand is squashed into one of 7 strength buckets (hence the name)
  * bets are half pot or pot, raises are pot, at most 3 bets per street
  * no future streets: whoever is best at the end of the street wins, with
    some noise on the earlier streets because cards are still to come

That toy game is small enough to solve with CFR+ over bucket vectors in a
couple of seconds. At the table we figure out which bucket we're in and where
we are in the toy betting tree, then sample from the solved average strategy.
It's an approximation stacked on an approximation, but it mixes its actions
and balances bluffs on its own, which none of the hand-tuned bots do.
"""

import functools
import json
import math
import os

from ..equity import DATA, monte_carlo, preflop_pct
from .base import Bot, Decision, dec

B = 7
BET_SIZES = {"h": 0.5, "p": 1.0}
MAX_BETS = 3
# how much the result is still up in the air on each street; 0 = river showdown
NOISE = [0.32, 0.22, 0.12, 0.02]
CACHE = os.path.join(DATA, "cfr7.json")
ITERS = 1500


# ---------------------------------------------------------------- the toy game

class Node:
    __slots__ = ("path", "player", "actions", "kids", "kind", "c", "folder")

    def __init__(self, path, player, c):
        self.path = path
        self.player = player
        self.c = c                 # chips each player put in this street, pot = 1 at the start
        self.actions = []
        self.kids = []
        self.kind = "decision"
        self.folder = None


def build(path="", player=0, c=(0.0, 0.0), bets=0, checks=0):
    n = Node(path, player, c)
    to_call = abs(c[0] - c[1])
    pot = 1 + c[0] + c[1]
    other = 1 - player

    def add(a, child):
        n.actions.append(a)
        n.kids.append(child)

    if to_call == 0:
        if checks == 1:
            add("x", leaf(path + "x", c))
        else:
            add("x", build(path + "x", other, c, bets, checks + 1))
        if bets < MAX_BETS:
            for a, frac in BET_SIZES.items():
                cc = list(c)
                cc[player] += frac * pot
                add(a, build(path + a, other, tuple(cc), bets + 1, checks))
    else:
        f = leaf(path + "f", c)
        f.kind, f.folder = "fold", player
        add("f", f)
        cc = list(c)
        cc[player] += to_call
        add("c", leaf(path + "c", tuple(cc)))
        if bets < MAX_BETS:
            cc = list(c)
            cc[player] += to_call + (pot + to_call)
            add("r", build(path + "r", other, tuple(cc), bets + 1, checks))
    return n


def leaf(path, c):
    n = Node(path, -1, c)
    n.kind = "showdown"
    return n


def win_matrix(noise):
    mid = [(i + 0.5) / B for i in range(B)]
    if noise <= 0.025:
        return [[1.0 if i > j else 0.5 if i == j else 0.0 for j in range(B)] for i in range(B)]
    return [[0.5 + 0.5 * math.tanh((mid[i] - mid[j]) / noise) for j in range(B)] for i in range(B)]


def all_nodes(root):
    out = []
    stack = [root]
    while stack:
        n = stack.pop()
        if n.kind == "decision":
            out.append(n)
            stack.extend(n.kids)
    return out


def terminal_values(n, reach_opp, me, W):
    """Leaf value for `me`, one entry per own bucket, weighted by the opponent's reach."""
    c = n.c
    pot = 1 + c[0] + c[1]
    if n.kind == "fold":
        u = (pot - c[me]) if n.folder != me else -c[me]
        return [u * sum(reach_opp)] * B
    out = []
    for i in range(B):
        acc = 0.0
        for j in range(B):
            if reach_opp[j]:
                w = W[i][j] if me == 0 else 1.0 - W[j][i]
                acc += reach_opp[j] * (w * pot - c[me])
        out.append(acc)
    return out


class Solver:
    """CFR+ with alternating updates, values carried as per-bucket vectors."""

    def __init__(self, noise):
        self.root = build()
        self.W = win_matrix(noise)
        self.nodes = all_nodes(self.root)
        self.regret = {n.path: [[0.0] * len(n.actions) for _ in range(B)] for n in self.nodes}
        self.avg = {n.path: [[0.0] * len(n.actions) for _ in range(B)] for n in self.nodes}

    def current(self, n):
        out = []
        for row in self.regret[n.path]:
            s = sum(row)
            out.append([r / s for r in row] if s > 0 else [1.0 / len(row)] * len(row))
        return out

    def walk(self, n, me, reach_me, reach_opp, t):
        if n.kind != "decision":
            return terminal_values(n, reach_opp, me, self.W)
        strat = self.current(n)
        k = len(n.actions)
        if n.player == me:
            vals = []
            for a in range(k):
                r = [reach_me[i] * strat[i][a] for i in range(B)]
                vals.append(self.walk(n.kids[a], me, r, reach_opp, t))
            node_v = [sum(strat[i][a] * vals[a][i] for a in range(k)) for i in range(B)]
            reg = self.regret[n.path]
            for i in range(B):
                for a in range(k):
                    reg[i][a] = max(0.0, reg[i][a] + vals[a][i] - node_v[i])
            return node_v
        # opponent node: their strategy just splits their reach
        avg = self.avg[n.path]
        node_v = [0.0] * B
        for a in range(k):
            r = [reach_opp[j] * strat[j][a] for j in range(B)]
            v = self.walk(n.kids[a], me, reach_me, r, t)
            for i in range(B):
                node_v[i] += v[i]
        # linear averaging (CFR+): later iterations count more
        for j in range(B):
            for a in range(k):
                avg[j][a] += t * reach_opp[j] * strat[j][a]
        return node_v

    def train(self, iters):
        uniform = [1.0 / B] * B
        for t in range(1, iters + 1):
            for me in (0, 1):
                self.walk(self.root, me, uniform, uniform, t)

    def average(self):
        out = {}
        for n in self.nodes:
            rows = []
            for row in self.avg[n.path]:
                s = sum(row)
                rows.append([round(x / s, 4) if s else round(1 / len(row), 4) for x in row])
            out[n.path] = {"actions": n.actions, "player": n.player, "strategy": rows}
        return out


def exploitability(policy, noise):
    """How much a best response wins against the solved strategy, in pots, averaged over seats."""
    root = build()
    W = win_matrix(noise)

    def br(n, me, reach_opp):
        if n.kind != "decision":
            return terminal_values(n, reach_opp, me, W)
        if n.player == me:
            vals = [br(kid, me, reach_opp) for kid in n.kids]
            return [max(v[i] for v in vals) for i in range(B)]
        strat = policy[n.path]["strategy"]
        out = [0.0] * B
        for a, kid in enumerate(n.kids):
            v = br(kid, me, [reach_opp[j] * strat[j][a] for j in range(B)])
            out = [x + y for x, y in zip(out, v)]
        return out

    uniform = [1.0 / B] * B
    # game value is 0.5 pot per seat by symmetry over seats
    v0 = sum(br(root, 0, uniform)) / B
    v1 = sum(br(root, 1, uniform)) / B
    return (v0 + v1) / 2 - 0.5


def solve_all(iters=ITERS, verbose=False):
    out = {"buckets": B, "iters": iters, "streets": []}
    for street, noise in enumerate(NOISE):
        s = Solver(noise)
        s.train(iters)
        pol = s.average()
        ex = exploitability(pol, noise)
        if verbose:
            print(f"  street {street}: {len(s.nodes)} decision nodes, exploitability {ex * 1000:.1f} mpot")
        out["streets"].append({"noise": noise, "exploitability": round(ex, 5), "policy": pol})
    os.makedirs(DATA, exist_ok=True)
    with open(CACHE, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    return out


@functools.cache
def policy():
    try:
        with open(CACHE) as f:
            return json.load(f)
    except FileNotFoundError:
        return solve_all()


# ---------------------------------------------------------------- at the table

TOP_BY_AGGR = [1.0, 0.45, 0.22, 0.12]
WORD = {"x": "CHECK", "h": "BET ½", "p": "BET POT", "f": "FOLD", "c": "CALL", "r": "RAISE"}


def translate(frac, rng):
    """Map a real bet (as a fraction of pot) onto half pot or pot.

    Pseudo-harmonic mapping (Ganzfried & Sandholm), so an opponent can't pick
    a size between ours that we systematically misread.
    """
    a, b = BET_SIZES["h"], BET_SIZES["p"]
    if frac <= a:
        return "h"
    if frac >= b:
        return "p"
    p_a = ((b - frac) * (1 + a)) / ((b - a) * (1 + frac))
    return "h" if rng.random() < p_a else "p"


class CFR7(Bot):
    name = "CFR-7"

    def __init__(self):
        self.pol = policy()

    def strength(self, v, think):
        n = max(1, v.opp)
        if v.street == 0:
            pct = preflop_pct(v.hole)
            s = pct ** n
            think.append(f"> PCT {dec(pct)}^{n} = {dec(s)}")
            return s
        top = TOP_BY_AGGR[min(v.opp_aggr, 3)]
        eq, _ = monte_carlo(v.hole, v.board, min(n, 3), 300, v.rng, top=top)
        think.append(f"> EQ {dec(eq)} VS TOP {int(top * 100)}%")
        return eq

    def locate(self, v):
        """Where we are in the toy tree, from this street's real betting."""
        if v.street == 0:
            # treat the big blind as a pot-sized bet; BB's option after limps is "checked to"
            if v.to_call == 0:
                return "x"
            return "p" + "r" * sum(1 for _, a, _ in v.street_log if a == "raise")

        last = {}
        for seat, _, to in v.street_log:
            last[seat] = to
        pot0 = max(1, v.pot - sum(last.values()))

        # multiway gets squeezed into heads-up: first check counts, extra checks
        # and flat calls don't (a call ends the street in the toy game)
        path = ""
        for _, a, to in v.street_log:
            if a == "check" and not path:
                path = "x"
            elif a == "raise":
                if path in ("", "x"):
                    path += translate(to / pot0, v.rng)
                else:
                    path += "r"
        return path

    def act(self, v):
        think = []
        s = self.strength(v, think)
        bucket = min(B - 1, int(s * B))
        street = self.pol["streets"][v.street]["policy"]

        path = self.locate(v)
        # trim from the end until the path exists (multiway lines the toy game never saw)
        while path and path not in street:
            path = path[:-1]
        node = street.get(path)
        if node is None or (v.to_call > 0) != ("f" in node["actions"]):
            node = street["p"] if v.to_call > 0 else street[""]
            path = "p" if v.to_call > 0 else ""

        acts = node["actions"]
        sigma = node["strategy"][bucket]
        think.append(f"> BUCKET {bucket + 1}/7 NODE /{path or '-'}")
        think.append("> MIX " + " ".join(f"{a.upper()}{dec(p)}" for a, p in zip(acts, sigma)))

        pick = v.rng.choices(acts, weights=sigma)[0]
        think.append(f"> PICK {WORD[pick]}")

        if pick in ("x", "c"):
            return Decision("check" if v.to_call == 0 else "call", think=think)
        if pick == "f":
            return Decision("fold", think=think)
        if not v.can_raise:
            return Decision("call" if v.to_call else "check", think=think)
        if pick == "r":
            return Decision("raise", to=self.bet_to(v, 1.0), think=think)
        frac = BET_SIZES[pick]
        if v.street == 0:
            # pot fractions are silly preflop; open 2.5bb (+1 per limper), 3x a raise
            if v.cur_bet <= v.bb:
                to = v.bb * 5 // 2 + v.bb * v.callers_pre
            else:
                to = v.cur_bet * 3
            return Decision("raise", to=to, think=think)
        return Decision("raise", to=self.bet_to(v, frac), think=think)

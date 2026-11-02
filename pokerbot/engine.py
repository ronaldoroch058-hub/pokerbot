"""No-limit hold'em dealer.

Plays one hand at a time and writes down everything that happened as a list
of steps, each with a snapshot of the table, so the frontend can scrub back
and forth without re-running anything.
"""

import random
import time
from dataclasses import dataclass, field

from .cards import names, pretty
from .evaluator import evaluate, describe

STREETS = ["PREFLOP", "FLOP", "TURN", "RIVER"]

POSITIONS = {
    2: ["BTN", "BB"],
    3: ["BTN", "SB", "BB"],
    4: ["BTN", "SB", "BB", "CO"],
    5: ["BTN", "SB", "BB", "UTG", "CO"],
    6: ["BTN", "SB", "BB", "UTG", "MP", "CO"],
    7: ["BTN", "SB", "BB", "UTG", "MP", "HJ", "CO"],
    8: ["BTN", "SB", "BB", "UTG", "UTG1", "MP", "HJ", "CO"],
}


@dataclass
class Decision:
    action: str            # fold / check / call / raise
    to: int = 0            # for raise: total bet this street, not the increment
    think: list = field(default_factory=list)


@dataclass
class View:
    """What a bot is allowed to know when it's its turn."""
    seat: int
    position: str
    hole: list
    board: list
    street: int
    pot: int               # everything in the middle, current bets included
    to_call: int
    cur_bet: int
    my_bet: int
    stack: int
    min_raise_to: int
    max_raise_to: int
    can_raise: bool
    sb: int
    bb: int
    live: int              # players still in the hand, me included
    behind: int            # live players still to act after me this street
    raises: int            # bets + raises this street (the big blind counts as one)
    effective: int         # chips I can actually lose to the biggest live opponent
    opp_aggr: int          # most bets/raises made by any live opponent this hand
    street_log: list       # [(seat, action, to)] this street
    my_street_actions: list
    aggressor: int         # seat that made the last bet/raise this hand, -1 if none
    aggressor_street: int
    callers_pre: int       # preflop flat calls so far (limps or cold calls)
    rng: random.Random

    @property
    def opp(self):
        return self.live - 1

    @property
    def pot_odds(self):
        return self.to_call / (self.pot + self.to_call) if self.to_call else 0.0


class Seat:
    def __init__(self, bot, label, stack):
        self.bot = bot
        self.label = label
        self.start = stack
        self.stack = stack
        self.cards = []
        self.bet = 0
        self.total = 0
        self.folded = False
        self.acted_id = -1
        self.raises = 0

    @property
    def live(self):
        return not self.folded

    @property
    def active(self):
        return not self.folded and self.stack > 0


class Hand:
    def __init__(self, bots, button=0, stacks=10000, sb=50, bb=100, rng=None, hand_no=1, deck=None, labels=None):
        n = len(bots)
        if isinstance(stacks, int):
            stacks = [stacks] * n
        labels = labels or [f"S{i + 1}" for i in range(n)]
        self.seats = [Seat(b, labels[i], stacks[i]) for i, b in enumerate(bots)]
        self.n = n
        self.button = button
        self.sb, self.bb = sb, bb
        self.rng = rng or random.Random()
        self.hand_no = hand_no
        if deck is None:
            deck = list(range(52))
            self.rng.shuffle(deck)
        self.deck = list(deck)
        self.board = []
        self.street = 0
        self.turn = -1
        self.steps = []
        self.log = []          # (street, seat, action, to)
        self.last_aggr = None  # (street, seat)
        self.full_raise_id = 0
        self.timings = [[] for _ in range(n)]
        pos = POSITIONS[n]
        self.positions = [pos[(i - button) % n] for i in range(n)]

    # -- bookkeeping -------------------------------------------------------

    def pot(self):
        return sum(s.total for s in self.seats)

    def snap(self):
        return {
            "street": self.street,
            "board": names(self.board),
            "pot": self.pot(),
            "stacks": [s.stack for s in self.seats],
            "bets": [s.bet for s in self.seats],
            "folded": [s.folded for s in self.seats],
            "turn": self.turn,
        }

    def step(self, ev):
        self.steps.append({"ev": ev, "s": self.snap()})

    def pay(self, s, amount):
        amount = min(amount, s.stack)
        s.stack -= amount
        s.bet += amount
        s.total += amount
        return amount

    def next_seat(self, i):
        return (i + 1) % self.n

    def order_from(self, first):
        return [(first + k) % self.n for k in range(self.n)]

    def seat_info(self):
        return [{"label": s.label, "bot": s.bot.name, "pos": self.positions[i], "stack": s.start}
                for i, s in enumerate(self.seats)]

    # -- the hand ------------------------------------------------------------

    def play(self):
        n = self.n
        if n == 2:
            sb_i, bb_i = self.button, self.next_seat(self.button)
        else:
            sb_i = self.next_seat(self.button)
            bb_i = self.next_seat(sb_i)

        self.step({"k": "start", "hand": self.hand_no, "button": self.button, "seats": self.seat_info()})
        self.post(sb_i, self.sb, "SB")
        self.post(bb_i, self.bb, "BB")

        first = self.next_seat(self.button)
        for _ in range(2):
            for i in self.order_from(first):
                self.seats[i].cards.append(self.deck.pop())
        self.step({"k": "deal", "cards": [names(s.cards) for s in self.seats]})

        self.betting(self.next_seat(bb_i), preflop=True)

        for street, count in ((1, 3), (2, 1), (3, 1)):
            if sum(s.live for s in self.seats) < 2:
                break
            self.street = street
            for s in self.seats:
                s.bet = 0
            self.deck.pop()  # burn
            new = [self.deck.pop() for _ in range(count)]
            self.board += new
            self.turn = -1
            self.step({"k": "street", "name": STREETS[street], "cards": names(new)})
            if sum(s.active for s in self.seats) >= 2:
                self.betting(self.next_seat(self.button), preflop=False)

        return self.finish()

    def post(self, i, amount, what):
        s = self.seats[i]
        paid = self.pay(s, amount)
        self.step({"k": "post", "seat": i, "amt": paid, "what": what})

    def betting(self, first, preflop):
        seats = self.seats
        cur = max(s.bet for s in seats)
        min_inc = self.bb
        raises = 1 if preflop else 0
        self.full_raise_id += 1
        for s in seats:
            s.acted_id = -1
        queue = [i for i in self.order_from(first) if seats[i].active]

        while queue:
            if sum(s.live for s in seats) < 2:
                return
            i = queue.pop(0)
            s = seats[i]
            if not s.active:
                continue
            to_call = cur - s.bet
            others = any(o.active for o in seats if o is not s)
            if to_call == 0 and not others:
                continue

            can_raise = others and s.acted_id != self.full_raise_id and s.stack > to_call
            max_to = s.bet + s.stack
            min_to = min(cur + min_inc, max_to)

            self.turn = i
            view = self.view(i, cur, to_call, min_to, max_to, can_raise, raises, queue)
            t0 = time.perf_counter()
            try:
                d = s.bot.act(view)
            except Exception as e:  # a crashing bot folds, same as a timeout at a real table
                d = Decision("fold", think=[f"> ERROR {type(e).__name__}: {e}"[:60]])
            ms = (time.perf_counter() - t0) * 1000
            self.timings[i].append(ms)

            action, to = self.legalize(d, to_call, can_raise, min_to, max_to)
            s.acted_id = self.full_raise_id
            ev = {"k": "act", "seat": i, "a": action, "think": d.think, "ms": round(ms, 1)}

            if action == "fold":
                s.folded = True
                ev["text"] = "FOLD"
            elif action == "check":
                ev["text"] = "CHECK"
            elif action == "call":
                paid = self.pay(s, to_call)
                ev["amt"] = paid
                ev["text"] = ("CALL " if s.stack else "ALL-IN ") + f"{paid:,}"
            else:
                was_bet = cur == 0
                self.pay(s, to - s.bet)
                inc = s.bet - cur
                if inc >= min_inc:
                    min_inc = inc
                    self.full_raise_id += 1
                    s.acted_id = self.full_raise_id
                cur = s.bet
                raises += 1
                s.raises += 1
                self.last_aggr = (self.street, i)
                queue = [j for j in self.order_from(self.next_seat(i)) if j != i and seats[j].active]
                ev["to"] = s.bet
                word = "ALL-IN " if not s.stack else ("BET " if was_bet else "RAISE TO ")
                ev["text"] = f"{word}{s.bet:,}"

            self.log.append((self.street, i, action, s.bet))
            self.step(ev)
        self.turn = -1

    def legalize(self, d, to_call, can_raise, min_to, max_to):
        a = d.action
        if a == "raise" and not can_raise:
            a = "call"
        if a == "fold" and to_call == 0:
            a = "check"
        if a == "call" and to_call == 0:
            a = "check"
        if a == "check" and to_call > 0:
            a = "fold"
        if a == "raise":
            to = max(min_to, min(int(d.to), max_to))
            return a, to
        return a, 0

    def view(self, i, cur, to_call, min_to, max_to, can_raise, raises, queue):
        s = self.seats[i]
        live_opps = [o for o in self.seats if o.live and o is not s]
        biggest = max((o.stack + o.bet for o in live_opps), default=0)
        street_log = [(seat, a, to) for st, seat, a, to in self.log if st == self.street]
        aggr_street, aggr = self.last_aggr or (-1, -1)
        return View(
            seat=i,
            position=self.positions[i],
            hole=list(s.cards),
            board=list(self.board),
            street=self.street,
            pot=self.pot(),
            to_call=min(to_call, s.stack),
            cur_bet=cur,
            my_bet=s.bet,
            stack=s.stack,
            min_raise_to=min_to,
            max_raise_to=max_to,
            can_raise=can_raise,
            sb=self.sb,
            bb=self.bb,
            live=len(live_opps) + 1,
            behind=sum(1 for j in queue if self.seats[j].active),
            raises=raises,
            effective=min(s.stack + s.bet, biggest),
            opp_aggr=max((o.raises for o in live_opps), default=0),
            street_log=street_log,
            my_street_actions=[a for seat, a, _ in street_log if seat == i],
            aggressor=aggr,
            aggressor_street=aggr_street,
            callers_pre=sum(1 for st, _, a, _ in self.log if st == 0 and a == "call"),
            rng=self.rng,
        )

    def finish(self):
        seats = self.seats
        contenders = [i for i, s in enumerate(seats) if s.live]
        values = {}
        showdown = len(contenders) > 1
        self.turn = -1

        if showdown:
            while len(self.board) < 5:  # everyone all-in before the river
                self.deck.pop()
                self.board.append(self.deck.pop())
            for i in contenders:
                values[i] = evaluate(seats[i].cards + self.board)
                self.step({"k": "show", "seat": i, "cards": names(seats[i].cards), "desc": describe(values[i])})

        won = [0] * self.n
        if not showdown:
            won[contenders[0]] = self.pot()
        else:
            levels = sorted({s.total for s in seats if s.total > 0})
            prev = 0
            for lv in levels:
                part = sum(min(s.total, lv) - min(s.total, prev) for s in seats)
                prev = lv
                elig = [i for i in contenders if seats[i].total >= lv]
                if not elig:
                    elig = contenders  # dead money from a folded overbet
                best = max(values[i] for i in elig)
                winners = [i for i in elig if values[i] == best]
                share, odd = divmod(part, len(winners))
                for k, i in enumerate(sorted(winners, key=lambda j: (j - self.button - 1) % self.n)):
                    won[i] += share + (1 if k < odd else 0)

        for i, amt in enumerate(won):
            if amt:
                seats[i].stack += amt
        for i, amt in enumerate(won):
            if amt:
                desc = describe(values[i]) if showdown else "UNCONTESTED"
                self.step({"k": "win", "seat": i, "amt": amt, "desc": desc})

        net = [s.stack - s.start for s in seats]
        return {
            "hand": self.hand_no,
            "button": self.button,
            "blinds": [self.sb, self.bb],
            "seats": [dict(info, cards=names(s.cards)) for info, s in zip(self.seat_info(), seats)],
            "board": names(self.board),
            "steps": self.steps,
            "net": net,
            "showdown": showdown,
            "contenders": contenders,
            "log": self.log,
            "ms": [round(sum(t) / len(t), 2) if t else 0 for t in self.timings],
        }


def hand_text(rec):
    """PokerStars-ish plain text history. Handy for eyeballing a weird hand."""
    from .cards import card
    lines = [f"Hand #{rec['hand']:06d}  NLHE {rec['blinds'][0]}/{rec['blinds'][1]}"]
    for i, s in enumerate(rec["seats"]):
        lines.append(f"Seat {i + 1}: {s['bot']} ({s['pos']}) {s['stack']:,}  [{pretty([card(c) for c in s['cards']])}]")
    for st in rec["steps"]:
        ev = st["ev"]
        k = ev["k"]
        who = rec["seats"][ev["seat"]]["bot"] if "seat" in ev else ""
        if k == "post":
            lines.append(f"{who}: posts {ev['what']} {ev['amt']:,}")
        elif k == "street":
            lines.append(f"*** {ev['name']} *** [{pretty([card(c) for c in st['s']['board']])}]")
        elif k == "act":
            lines.append(f"{who}: {ev['text'].lower()}")
        elif k == "show":
            lines.append(f"{who}: shows [{pretty([card(c) for c in ev['cards']])}] ({ev['desc'].lower()})")
        elif k == "win":
            lines.append(f"{who} collected {ev['amt']:,} ({ev['desc'].lower()})")
    return "\n".join(lines)

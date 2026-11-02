import math

from .bots import BOTS


def summarize(rec):
    """Per-seat numbers from one ring hand, small enough to ship between processes."""
    n = len(rec["seats"])
    out = []
    for i in range(n):
        acts = [(st, a) for st, seat, a, _ in rec["log"] if seat == i]
        pre = [a for st, a in acts if st == 0]
        post = [a for st, a in acts if st > 0]
        saw_flop = any(st > 0 for st, _ in acts) or (rec["board"] and i in rec["contenders"])
        sd = rec["showdown"] and i in rec["contenders"]
        out.append({
            "bot": rec["seats"][i]["bot"],
            "net": rec["net"][i],
            "vpip": any(a in ("call", "raise") for a in pre),
            "pfr": "raise" in pre,
            "agg": post.count("raise"),
            "calls": post.count("call"),
            "flop": bool(saw_flop),
            "sd": sd,
            "wsd": sd and rec["net"][i] > 0,
            "ms": rec["ms"][i],
        })
    return out


class Stats:
    def __init__(self, bb=100):
        self.bb = bb
        self.hands = 0
        self.bots = {name: dict(n=0, net=0, sq=0.0, vpip=0, pfr=0, agg=0, calls=0, flop=0, sd=0, wsd=0,
                                ms=0.0, msn=0) for name in BOTS}

    def add_ring(self, seats):
        self.hands += 1
        for s in seats:
            b = self.bots[s["bot"]]
            x = s["net"] / self.bb
            b["n"] += 1
            b["net"] += s["net"]
            b["sq"] += x * x
            for k in ("vpip", "pfr", "agg", "calls", "flop", "sd", "wsd"):
                b[k] += int(s[k])
            if s["ms"]:
                b["ms"] += s["ms"]
                b["msn"] += 1

    def snapshot(self):
        bots = {}
        for name, b in self.bots.items():
            n = max(b["n"], 1)
            mean = b["net"] / self.bb / n
            var = max(b["sq"] / n - mean * mean, 0)
            bots[name] = {
                "hands": b["n"],
                "net_bb": round(b["net"] / self.bb, 1),
                "bb100": round(mean * 100, 1),
                "ci": round(196 * math.sqrt(var / n), 1),  # 95%, in bb/100
                "vpip": round(b["vpip"] / n, 3),
                "pfr": round(b["pfr"] / n, 3),
                "af": round(b["agg"] / b["calls"], 2) if b["calls"] else None,
                "wtsd": round(b["sd"] / b["flop"], 3) if b["flop"] else None,
                "wsd": round(b["wsd"] / b["sd"], 3) if b["sd"] else None,
                "ms": round(b["ms"] / b["msn"], 2) if b["msn"] else None,
            }
        return {"hands": self.hands, "bots": bots}

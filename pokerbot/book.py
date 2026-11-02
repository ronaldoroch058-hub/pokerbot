"""Turns a hand record into one line of the opening book.

A line is the voluntary actions in order ("UTG R3", "BTN C", "FLOP", ...),
blinds left out, folds counted where they happened but not drawn, and a leaf
saying how it ended. The frontend merges lines into a tree.

Each line comes in two spellings, by position and by bot, so the page can
flip between "what does UTG do" and "what does NASH do" without the server.
"""


def token(street, a, ev, prev, bb, bet_seen, allin):
    if allin:
        return "A"
    if a == "check":
        return "X"
    if a == "call":
        return "C"
    if street == 0:
        n = int(ev["to"] / bb + 0.5)  # 2.5bb is R3, python's round() would say R2
        return "R6+" if n >= 6 else f"R{max(2, n)}"
    if bet_seen:
        return "R"  # postflop raises are rare enough that one bucket does
    added = ev["to"] - prev["bets"][ev["seat"]]
    f = added / max(1, prev["pot"])
    return "B½" if f < 0.75 else "B1" if f < 1.5 else "B2+"


def line(rec):
    bb = rec["blinds"][1]
    seats = rec["seats"]
    by_pos, by_bot, folds_at = [], [], [0]
    prev = rec["steps"][0]["s"]
    street = 0
    bet_seen = False

    for st in rec["steps"]:
        ev, s = st["ev"], st["s"]
        if ev["k"] == "street":
            street += 1
            bet_seen = False
            by_pos.append(ev["name"])
            by_bot.append(ev["name"])
            folds_at.append(0)
        elif ev["k"] == "act":
            seat, a = ev["seat"], ev["a"]
            if a == "fold":
                folds_at[-1] += 1
            else:
                allin = a in ("call", "raise") and s["stacks"][seat] == 0
                tok = token(street, a, ev, prev, bb, bet_seen, allin)
                bet_seen = bet_seen or a == "raise"
                by_pos.append(f"{seats[seat]['pos']} {tok}")
                by_bot.append(f"{seats[seat]['bot']} {tok}")
                folds_at.append(0)
        prev = s

    end = "SD" if rec["showdown"] else "END"
    by_pos.append(end)
    by_bot.append(end)
    folds_at.append(0)

    wins = [st["ev"] for st in rec["steps"] if st["ev"]["k"] == "win"]
    top = max(wins, key=lambda e: e["amt"])
    w = top["seat"]
    last = rec["steps"][-1]["s"]
    return {
        "n": rec["hand"],
        "p": by_pos,
        "b": by_bot,
        "f": folds_at,
        "pot": last["pot"],
        "sd": rec["showdown"],
        "wp": seats[w]["pos"],
        "wb": seats[w]["bot"],
        "amt": top["amt"],
        "desc": top["desc"],
        "split": len(wins) > 1,
        "board": last["board"],
        "wc": seats[w]["cards"],
    }

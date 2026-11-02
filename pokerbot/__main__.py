import argparse
import random
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pokerbot")
    sub = ap.add_subparsers(dest="cmd")

    s = sub.add_parser("serve", help="run the site (default)")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--workers", type=int, default=2, help="background sim processes")
    s.add_argument("--rate", type=float, default=40, help="ring hands/sec per worker, 0 = flat out")

    t = sub.add_parser("tables", help="rebuild data/preflop.json")
    t.add_argument("--iters", type=int, default=6000)

    sub.add_parser("solve", help="re-solve CFR-7's toy games into data/cfr7.json")

    m = sub.add_parser("match", help="duplicate heads-up match in the terminal")
    m.add_argument("a")
    m.add_argument("b")
    m.add_argument("--deals", type=int, default=500)
    m.add_argument("--seed", type=int, default=1)

    h = sub.add_parser("hand", help="play one 6-max hand and print it")
    h.add_argument("--seed", type=int)

    argv = sys.argv[1:] if argv is None else argv
    args = ap.parse_args(argv)
    if args.cmd is None:
        args = ap.parse_args(["serve", *argv])
    cmd = args.cmd

    if cmd == "serve":
        from .server import serve
        serve(args.host, args.port, args.workers, args.rate)
    elif cmd == "tables":
        from .equity import build_preflop_table
        build_preflop_table(args.iters)
        print("wrote data/preflop.json")
    elif cmd == "solve":
        from .bots.cfr7 import solve_all
        solve_all(verbose=True)
    elif cmd == "match":
        from .bots import BOTS
        from .sim import duplicate_match
        a, b = args.a.upper(), args.b.upper()
        if a not in BOTS or b not in BOTS:
            sys.exit(f"bots: {', '.join(BOTS)}")
        bb100, ci = duplicate_match(a, b, args.deals, args.seed)
        print(f"{a} vs {b}: {bb100:+.1f} bb/100 ± {ci:.1f}  ({args.deals * 2} hands, duplicate)")
    elif cmd == "hand":
        from .bots import BOTS, make
        from .engine import Hand, hand_text
        rng = random.Random(args.seed)
        names = [n for n in BOTS for _ in range(2)]
        rng.shuffle(names)
        rec = Hand([make(n) for n in names], button=0, rng=rng).play()
        print(hand_text(rec))


if __name__ == "__main__":
    main()

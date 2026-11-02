# pokerbot

Three no-limit hold'em bots playing each other, live, with a page to watch them on.

```
python3 -m pokerbot          # then open http://localhost:8000
```

No dependencies, just Python 3.10+ and a browser. The preflop table and the
CFR solution are checked in under `pokerbot/data/`, so it starts straight away.

## The bots

**MONTE** is the decision maker from [dickreuter/Poker](https://github.com/dickreuter/Poker)
without the screen scraping. Monte Carlo equity, a stack of adjustments to the
minimum equity (outs, position, pot size, getting re-raised), then two power
curves that say how much it'll call and how much it'll bet. Parameter names
match the original strategy editor so you can compare them side by side. The
lmfit curve fit is replaced with the closed form, since it's two points and two
unknowns.

**CFR-7** solves a toy version of each street with CFR+: hands squashed into 7
strength buckets, half-pot and pot bets, pot raises, max three bets. At the
table it works out its bucket and where it is in the toy betting tree, and
samples from the solved strategy. Bet sizes it never trained on are mapped with
pseudo-harmonic translation. Solving all four streets takes about two seconds;
`python3 -m pokerbot solve` redoes it.

**NASH** doesn't model anyone. It bets a polarised range with bluffs in the
ratio that makes a call break even, defends to minimum defence frequency, and
sizes bets geometrically so stacks go in by the river. Cheapest of the three by
a mile.

## The page

One exhibit: **the opening book**. Worker processes play 6-max ring hands
nonstop (two seats per bot, reseated every orbit) and every finished hand is
pushed to the page over server-sent events and merged into one tree. It keeps
the last 10,000 hands. Start at the wall and read right: each branch is one
action, the busiest line runs straight across, side lines drop off below, and
the last hand is highlighted with its board and winner. Branches can be
labelled by position or by bot. Pause, step, undo and empty only affect your
copy of the book; the bots keep playing.

## Other commands

```
python3 -m pokerbot serve --port 8000 --workers 2 --rate 40
python3 -m pokerbot match CFR-7 NASH --deals 1000    # duplicate heads-up in the terminal
python3 -m pokerbot hand --seed 7                    # one hand, printed as a hand history
python3 -m pokerbot tables                           # rebuild the preflop equity table (~30s)
python3 -m unittest discover -s tests
```

`--rate` is ring hands per second per worker; `0` runs flat out (about 130/s a core).

## Layout

```
pokerbot/
  cards.py evaluator.py     card ints are rank << 2 | suit
  equity.py outs.py curve.py
  engine.py                 the dealer: betting rounds, side pots, hand records
  bots/                     monte.py cfr7.py nash.py
  sim.py stats.py book.py   background workers, their numbers, book lines
  server.py                 http + server-sent events, stdlib only
web/                        index.html, style.css, js/
tests/
```

## Known rough edges

- CFR-7 solves each street on its own, so it doesn't plan ahead, and multiway
  pots get squeezed into its heads-up tree.
- MONTE's opponent ranges are crude (rejection sampling against the preflop
  percentile), same idea as upstream's reverse tables but simpler.
- The book and the records reset when the server restarts.
- The results are only as good as the sample. At a few thousand hands the
  intervals are still wide, so check the ± before reading much into a ranking.

## Credits

- MONTE's decision logic is ported from [dickreuter/Poker](https://github.com/dickreuter/Poker),
  which is GPL-3.0. If you publish this code, publish it under GPL-3.0 too.
- The page design and the three bot names are inspired by the
  [No Limit](https://pokerbot.sequoiacap.com/) bot tournament page. Not affiliated.

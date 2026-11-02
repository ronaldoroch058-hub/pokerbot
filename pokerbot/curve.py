"""The call/bet limit curve from dickreuter/Poker (decisionmaker/curvefitting.py).

The idea: the most you're willing to put in grows like a power curve in your
equity. It's pinned at two points - at `min_equity` you'll put in a couple of
big blinds, at 100% equity you'll put in `max_value` - and `power` bends it.
Below min_equity the limit is 0, which means fold.

The original fits y = a * (x + b) ** p through those two points with lmfit.
Two points, two unknowns, so there's a closed form and no scipy needed.
"""


def fit(min_equity, floor, max_value, power, x1=1.0):
    x0 = min(min_equity, x1 - 1e-6)
    k = (max_value / floor) ** (1.0 / power)
    b = (x1 - k * x0) / (k - 1.0)
    a = floor / (x0 + b) ** power
    return a, b


def limit(equity, min_equity, floor, max_value, power, max_equity=1.0):
    if equity < min_equity:
        return 0.0
    if equity > max_equity:
        # dickreuter zeroes this too; it only matters for the bet curve, where
        # max_equity < 1 is used for slow-playing monsters preflop
        return 0.0
    a, b = fit(min_equity, floor, max_value, power)
    return a * (equity + b) ** power

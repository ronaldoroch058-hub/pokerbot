from .evaluator import evaluate, STRAIGHT


def drawing_outs(hole, board):
    """Cards that turn a draw into a straight or better.

    The original bot pattern-matched flush draws, OESDs and gutshots one by
    one. With a fast evaluator it's simpler to just try every card. A card
    only counts if the made hand actually uses our hole cards, so a fourth
    spade on the board doesn't count for 3-high.
    """
    if not 3 <= len(board) <= 4:
        return 0
    now = evaluate(hole + board) >> 20
    if now >= STRAIGHT:
        return 0
    used = set(hole) | set(board)
    n = 0
    for c in range(52):
        if c in used:
            continue
        mine = evaluate(hole + board + [c])
        if mine >> 20 < STRAIGHT:
            continue
        if evaluate(board + [c]) >= mine:
            continue  # board plays
        n += 1
    return n

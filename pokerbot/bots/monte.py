"""MONTE - the dickreuter/Poker decision maker, minus the screen scraping.

Same pipeline as decisionmaker.py: Monte Carlo equity -> a pile of additive
adjustments to the minimum equity -> a power curve that turns equity into
"most chips I'll call" and "most chips I'll bet" -> compare against what the
table is asking. Parameter names are kept from the original strategy editor
so the two can be read side by side; values are in big blinds instead of
dollars and were tuned against the other two bots here, not on a real site.
"""

from .. import curve
from ..equity import monte_carlo, preflop_equity
from ..outs import drawing_outs
from .base import Bot, Decision, dec, chips

STREET = ["PreFlop", "Flop", "Turn", "River"]
UTG_PLUS = {"UTG": 0, "UTG1": 1, "MP": 2, "HJ": 3, "CO": 4, "BTN": 5, "SB": 6, "BB": 7}

DEFAULT = {
    "initialFunds": 100,          # call curve tops out here (bb) at 100% equity
    "initialFunds2": 100,         # same for the bet curve
    "PreFlopMinCallEquity": 0.44, "PreFlopCallPower": 2,
    "PreFlopMinBetEquity": 0.56, "PreFlopBetPower": 2, "PreFlopMaxBetEquity": 1.0,
    "FlopMinCallEquity": 0.42, "FlopCallPower": 3,
    "FlopMinBetEquity": 0.55, "FlopBetPower": 3,
    "TurnMinCallEquity": 0.45, "TurnCallPower": 3,
    "TurnMinBetEquity": 0.58, "TurnBetPower": 4,
    "RiverMinCallEquity": 0.48, "RiverCallPower": 4,
    "RiverMinBetEquity": 0.60, "RiverBetPower": 4,
    "potAdjustment": 0.08, "maxPotAdjustment": 0.08,
    "potAdjustmentPreFlop": 0.05, "maxPotAdjustmentPreFlop": 0.05,
    "secondRoundAdjustment": 0.06, "secondRoundAdjustmentPreFlop": 0.08,
    "secondRoundAdjustmentPowerIncrease": 1,
    "pre_flop_equity_reduction_by_position": 0.01,
    "pre_flop_equity_increase_if_bet": 0.07,
    "pre_flop_equity_increase_if_call": 0.02,
    "CoveredPlayersCallLikelihoodPreFlop": 0.6,
    "CoveredPlayersCallLikelihoodFlop": 0.5,
    "out_multiplier": 1.0,
    "alwaysCallEquity": 0.92,
    "always_call_low_stack_multiplier": 6,
    "FlopCheckDeceptionMinEquity": 0.90,
    "TurnCheckDeceptionMinEquity": 0.92,
    "RiverCheckDeceptionMinEquity": 1.01,  # off
    "FlopBluffMinEquity": 0.20, "FlopBluffMaxEquity": 0.32,
    "TurnBluffMinEquity": 0.18, "TurnBluffMaxEquity": 0.26,
    "RiverBluffMinEquity": 0.0, "RiverBluffMaxEquity": 0.12,
    "betPotRiverEquity": 0.85, "betPotRiverEquityMaxBBM": 40,
    "secondRiverBetPotMinEquity": 0.95,
    "BetPlusInc": 1,
    "opponent_raised_without_initiative_flop": 1,
    "opponent_raised_without_initiative_turn": 1,
    "opponent_raised_without_initiative_river": 1,
    "flop_betting_condidion_1": 1,   # sic, that's how it's spelled upstream
    "turn_betting_condidion_1": 1,
    "river_betting_condidion_1": 1,
    "minimum_bet_size": 3,           # 3 = never bet less than half pot postflop
    "increased_preflop_betting": 2,
}

NAMES = {"fold": "FOLD", "check": "CHECK", "call": "CALL", "bet1": "BET", "bet2": "BET PLUS",
         "bet3": "BET HALF POT", "bet4": "BET POT", "bluff": "BET BLUFF", "check_deception": "CHECK DECEPTION"}


class Monte(Bot):
    name = "MONTE"

    def __init__(self, strategy=None):
        self.p = dict(DEFAULT, **(strategy or {}))

    def act(self, v):
        p = self.p
        bb = v.bb
        think = []
        stage = STREET[v.street]
        second_round = bool(v.my_street_actions)
        opp_initiative = v.aggressor not in (-1, v.seat) and v.aggressor_street == v.street - 1

        # assumedPlayers: players behind only count partly, they might fold
        like = p["CoveredPlayersCallLikelihoodPreFlop"] if v.street == 0 else p["CoveredPlayersCallLikelihoodFlop"]
        already_in = v.opp - v.behind
        assumed = max(1, min(v.opp, round(already_in + v.behind * like)))

        if v.street == 0:
            eq = preflop_equity(v.hole, assumed)
            think.append(f"> TABLE EQ {dec(eq)} VS {assumed}")
        else:
            # rollouts scale with the pot, like maxRuns in the original
            n = min(800, 250 + 50 * int(v.pot / (10 * bb)))
            top = 0.35 if v.opp_aggr >= 2 else 1.0
            eq, done = monte_carlo(v.hole, v.board, assumed, n, v.rng, top=top)
            err = (eq * (1 - eq) / max(done, 1)) ** 0.5
            think.append(f"> MC N{done} EQ {dec(eq)}±{dec(err)} VS {assumed}")

        # --- minimum equity adjustments
        outs = drawing_outs(v.hole, v.board) if v.street in (1, 2) else 0
        out_adj = outs * p["out_multiplier"] * 0.01
        if outs:
            think.append(f"> OUTS {outs} → -{dec(out_adj)}")

        pre_adj = 0.0
        if v.street == 0:
            utg_plus = UTG_PLUS.get(v.position, 0)
            pre_adj = -p["pre_flop_equity_reduction_by_position"] * utg_plus
            if v.raises >= 2:
                pre_adj += p["pre_flop_equity_increase_if_bet"]
            if v.callers_pre:
                pre_adj += p["pre_flop_equity_increase_if_call"]

        second = 0.0
        power_up = 0
        if second_round:
            second = p["secondRoundAdjustmentPreFlop"] if v.street == 0 else p["secondRoundAdjustment"]
            power_up = p["secondRoundAdjustmentPowerIncrease"]

        pot_bb = v.pot / bb
        if v.street == 0:
            pot_adj = min(pot_bb / 250 * p["potAdjustmentPreFlop"], p["maxPotAdjustmentPreFlop"])
        else:
            pot_adj = min(pot_bb / 250 * p["potAdjustment"], p["maxPotAdjustment"])

        raised_wo_init = 0.0
        if v.street and v.to_call and not opp_initiative and v.aggressor != v.seat:
            raised_wo_init = 0.1 * p[f"opponent_raised_without_initiative_{stage.lower()}"]

        min_call = p[f"{stage}MinCallEquity"] + second - pot_adj - out_adj + pre_adj
        min_bet = p[f"{stage}MinBetEquity"] + second - out_adj + pre_adj + raised_wo_init
        if v.street == 0:
            min_bet -= pot_adj  # upstream only applies the pot adjustment to betting preflop
        max_bet_eq = p["PreFlopMaxBetEquity"] if v.street == 0 else 1.0

        floor = 2 * bb
        call_lim = curve.limit(eq, min_call, floor, p["initialFunds"] * bb, p[f"{stage}CallPower"] + power_up)
        bet_lim = curve.limit(eq, min_bet, floor, p["initialFunds2"] * bb, p[f"{stage}BetPower"] + power_up, max_bet_eq)

        if eq >= p["alwaysCallEquity"]:
            call_lim = float("inf")
        if v.stack * p["always_call_low_stack_multiplier"] < v.pot:
            call_lim = float("inf")
            think.append("> SHORT STACK, CALL ANY")

        think.append(f"> MIN EQ CALL {dec(max(min_call, 0))} BET {dec(max(min_bet, 0))}")
        lim = "ANY" if call_lim == float("inf") else chips(call_lim)
        think.append(f"> LIMIT CALL {lim} BET {chips(bet_lim)}")

        # --- calling()
        to_call = v.to_call
        decision = "call" if call_lim >= to_call else "fold"

        # --- betting()
        bet_cost = v.min_raise_to - v.my_bet  # what the min-raise button costs
        # upstream: not checkButton or not other_player_has_initiative or condition switched off
        cond = v.to_call > 0 or not opp_initiative or p.get(f"{stage.lower()}_betting_condidion_1", 0) == 0
        if v.can_raise:
            half = v.pot / 2
            if v.street == 0:
                if bet_lim > bet_cost:
                    decision = "bet1"
                if bet_lim >= half and p["increased_preflop_betting"] == 2:
                    decision = "bet3"
            elif cond:
                if bet_lim >= bet_cost:
                    decision = "bet1"
                if bet_lim >= bet_cost + bb * p["BetPlusInc"] and (v.street == 3 or (v.street == 2 and pot_bb > 3)):
                    decision = "bet2"
                if bet_lim >= half and bet_cost < half:
                    decision = "bet3"
                if v.street == 3 and eq >= p["betPotRiverEquity"] and pot_bb < p["betPotRiverEquityMaxBBM"]:
                    decision = "bet4"

        # --- check_deception(): slow-play monsters when checking is free
        if v.to_call == 0 and decision.startswith("bet") and v.street:
            prev_call = "call" in v.my_street_actions
            if (v.street == 1 and eq > p["FlopCheckDeceptionMinEquity"]) or \
               (v.street == 2 and prev_call and eq > p["TurnCheckDeceptionMinEquity"]) or \
               (v.street == 3 and prev_call and eq > p["RiverCheckDeceptionMinEquity"]):
                decision = "check_deception"

        if v.street == 3 and second_round and eq >= p["secondRiverBetPotMinEquity"] and v.can_raise:
            decision = "bet4"

        # --- admin(): bet size floor, and never fold when a check is free
        if v.street and decision in ("bet1", "bet2") and p["minimum_bet_size"] >= 3:
            decision = "bet3" if p["minimum_bet_size"] == 3 else "bet4"
        if v.to_call == 0 and decision in ("fold", "call"):
            decision = "check"

        # --- bluff(): heads-up, first action on the street, checked-to only
        if v.live == 2 and not second_round and decision == "check" and v.street and v.behind == 0 and v.can_raise:
            lo, hi = p[f"{stage}BluffMinEquity"], p[f"{stage}BluffMaxEquity"]
            if lo < eq < hi:
                decision = "bluff"

        think.append(f"> DECIDE {NAMES[decision]}")
        return self.to_engine(v, decision, think)

    def to_engine(self, v, decision, think):
        if decision in ("fold", "check", "call", "check_deception"):
            a = "check" if decision == "check_deception" else decision
            return Decision(a, think=think)
        if decision == "bet1":
            to = v.min_raise_to
        elif decision == "bet2":
            to = v.min_raise_to + v.bb * self.p["BetPlusInc"]
        elif decision in ("bet3", "bluff"):
            to = self.bet_to(v, 0.5)
        else:
            to = self.bet_to(v, 1.0)
        return Decision("raise", to=to, think=think)

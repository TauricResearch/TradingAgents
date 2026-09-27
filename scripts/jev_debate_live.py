"""Live check of debate convergence (fit 3) against real Jev.

Run from the repo root, with the jev extra installed and TYPESAFE_API_KEY set:

    python scripts/jev_debate_live.py [--runs 3] [--log PATH]

Jev's answers vary from run to run, so every labelled question is asked
``--runs`` times and a case passes only when every run lands on the expected
side. Record the results under "Fit 3 as built" in docs/jev-use-cases.md.

1. ``new_argument`` on hand-written NVDA turns against the round-1 openings:
   rebuttals that bring new evidence, restatements, pure rhetoric, and a turn
   that restates everything but adds one fact (the hard case). New turns should
   score at or above ``new_argument_min``, the rest below it.
2. Whole debates through the real debater nodes, ``judge_turns`` and the
   routers, with scripted LLM replies and 3 configured rounds. A round-2 that
   only repeats should stop the debate after round 2; one with new evidence
   should run all 3 rounds.
3. ``stronger_side`` on three debates: one where only the bull cites evidence,
   one where only the bear does, and one where both do. A case passes when the
   Research Manager's hint names the expected side; for the last, the soft case,
   that it names none (evenly matched, or no side at ``side_lead_min``).
4. With ``--log``, a replay of a real run log (``full_states_log_<date>.json``):
   every turn the run judged is asked again and compared with the logged score,
   and ``stronger_side`` is asked on the real bull and bear histories. This is
   the long-state check: at Deep depth the histories run past 100K characters.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock

from langgraph.graph import END, START, StateGraph

from tradingagents.agents import debate_judgments as dj
from tradingagents.agents.jev import jev_client
from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator
from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator
from tradingagents.agents.state import AgentState
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.propagation import Propagator
from tradingagents.graph.setup import DEBATE_PATH_MAP, RISK_ANALYSIS_PATH_MAP

THRESHOLD = dj.DEFAULT_POLICY.new_argument_min
LEAD_MIN = dj.DEFAULT_POLICY.side_lead_min

# ---------------------------------------------------------------------------
# Hand-written turns (bodies only; the debater nodes add the speaker label)
# ---------------------------------------------------------------------------

BULL_OPEN = """NVIDIA's growth is not slowing. Data-center revenue rose 56% year over year to $41.1 billion and is now 88% of sales, and management guided next quarter to $54.0 billion. The buyers are not going away: the four largest cloud providers are expected to spend a combined $420 billion on capital expenditure this year, and Oracle just expanded its Blackwell Ultra deployment for 2027. The chart agrees. The stock is back above its 50-day and 200-day moving averages, and MACD crossed above its signal line this week for the first time in three weeks. This is a leader re-accelerating, not a peak."""

BEAR_OPEN = """The growth is real, but it is getting more expensive to deliver. Gross margin fell to 71.2% from 75.1% a year ago, and the quarter carried a $1.1 billion inventory charge on the Blackwell Ultra ramp. At 38.2 times trailing earnings the stock prices in flawless execution. China is a live risk: Reuters reports Nvidia is designing a cut-down chip just to stay within US export rules, which caps what it can sell there. And competition is coming, with AMD saying its MI400 accelerator is on schedule for 2027. Paying a premium multiple into falling margins is how investors get hurt."""

BULL_NEW = """My opponent calls the stock expensive, but that uses trailing earnings. On forward earnings it trades at 29.5 times, below its own five-year average of 36 times. The balance sheet removes the execution risk: $56.8 billion of cash against $8.5 billion of debt, $10.0 billion returned to shareholders last quarter, and the board just added $60 billion to the buyback. A company that can do that while margins dip is not fragile."""

BULL_REPEAT = """Let me be clear about why the bull case holds. Data-center sales grew 56% to $41.1 billion, which is 88% of the business, and guidance calls for $54 billion next quarter. Hyperscalers are on track to spend $420 billion, and Oracle is adding Blackwell Ultra clusters. Technically the stock has reclaimed both its 50-day and 200-day averages and MACD just turned positive. Every piece of evidence points the same way: this is a growth leader re-accelerating."""

BULL_RHETORIC = """The bear keeps looking for reasons to stay out of the best growth story in the market. I have laid out the evidence, and it all points one way. Great companies always look expensive to people waiting for a perfect entry, and those people end up watching from the sidelines. I remain firmly bullish."""

BEAR_NEW = """Here is what the bull has not mentioned. Operating margin also slipped, to 60.8% from 62.1%, so the pressure is not only in the cost of goods. The Bollinger Bands are the narrowest since June, which usually comes before a big move, and with ATR at $4.10 a day a break below the $110 support would put the 200-day average near $106.75 in play within a week. Momentum traders who bought the MACD crossover will not wait around if that level breaks."""

BEAR_REPEAT = """None of that answers my point. Margins went from 75.1% to 71.2%, there was a $1.1 billion inventory charge, and investors are paying 38 times trailing earnings for it. Add the China export limits and AMD's MI400 arriving in 2027, and the risk-reward is poor. My view has not changed: a premium multiple on shrinking margins is a trap."""

BEAR_ONE_NEW = """I still hold that the margin decline, from 75.1% to 71.2%, and the 38.2x trailing multiple leave no room for error, and that China and AMD are real threats. One more thing, though: the 10-year Treasury yield is still 3.92% even after the Fed's cut, so anyone hoping lower rates will rescue the multiple is looking at the wrong rate."""

BULL_VAGUE = [
    """AI is the future and NVIDIA is the leader, full stop. Every company in the world needs these chips, and that is not going to change. The stock always comes back after a dip.""",
    """The bear worries too much. Great companies find a way, and this management team always delivers. Long term, this goes much higher.""",
]

BEAR_VAGUE = [
    """This whole AI trade feels like a bubble. Every cycle ends the same way, and chip stocks always crash eventually. Competition will catch up sooner or later, and customers will not keep spending like this forever.""",
    """The bull's numbers are backward-looking. Nobody knows what the next few years hold, and when sentiment turns, it turns fast. I would not want to own this when it does.""",
]

AGG_OPEN = """The trader's plan to buy is right, and a 4% position is too small. Data-center revenue grew 56% to $41.1 billion, guidance is $54.0 billion, and the stock just cleared both moving averages with a fresh MACD crossover. We should take the full position now rather than wait for a dip that may never come."""
CON_OPEN = """I would cut the size in half. Gross margin fell to 71.2% from 75.1%, the stock trades at 38.2 times trailing earnings, and a change in China export rules could remove revenue overnight. A stop below the $110 support limits the damage if the margin story gets worse."""
NEU_OPEN = """Both of you have a point. The growth is real and the trend is up, but the margin decline and the valuation are real too. Buying in two tranches, half now and half near $110, keeps us in the trade without betting everything on one entry."""

AGG_REPEAT = """My view stands. With 56% data-center growth, $54 billion guidance and the stock above both moving averages on a MACD crossover, a half-sized position leaves money on the table. Buy the full position now."""
CON_REPEAT = """And I still say the size is too big. Margins are down from 75.1% to 71.2%, 38 times trailing earnings is rich, and China could change the rules at any time. Keep it small and put the stop under $110."""
NEU_REPEAT = """As I said, each side is partly right. Two tranches, one now and one near $110, is the balanced answer between chasing the trend and ignoring it."""

AGG_NEW = """The conservative case ignores the balance sheet. With $56.8 billion in cash against $8.5 billion of debt and a fresh $60 billion buyback authorization, the company itself will be buying any dip. The forward multiple of 29.5x is below the five-year average of 36x, so we are not paying a premium on next year's earnings."""
CON_NEW = """Look at the volatility before sizing up. ATR is $4.10, about 3.5% of price, and the Bollinger Bands are the tightest since June, which often comes before a sharp move either way. At that daily range a full position could lose more than our risk budget allows in two bad sessions."""
NEU_NEW = """There is a scheduled catalyst nobody has raised: prediction markets price a 68% chance of another Fed cut in December, with CPI running at 2.7%. Timing the second tranche for after the December meeting lets the macro picture settle before we commit the full amount."""


def bull(text):
    return f"Bull Analyst: {text}"


def bear(text):
    return f"Bear Analyst: {text}"


OPENINGS = f"{bull(BULL_OPEN)}\n{bear(BEAR_OPEN)}"

# (label, expected new?, latest turn). Each is judged against the openings.
TURN_CASES = [
    ("bull rebuttal with new evidence", True, bull(BULL_NEW)),
    ("bear raises new risks", True, bear(BEAR_NEW)),
    ("bear restates, adds one fact (hard)", True, bear(BEAR_ONE_NEW)),
    ("bull restates its opening", False, bull(BULL_REPEAT)),
    ("bear rephrases its opening", False, bear(BEAR_REPEAT)),
    ("bull rhetoric only", False, bull(BULL_RHETORIC)),
]

# (label, expected top side, bull turns, bear turns)
SIDE_CASES = [
    ("only the bull cites evidence", "bull", [BULL_OPEN, BULL_NEW], BEAR_VAGUE),
    ("only the bear cites evidence", "bear", BULL_VAGUE, [BEAR_OPEN, BEAR_NEW]),
    ("both cite evidence (soft)", None, [BULL_OPEN, BULL_NEW], [BEAR_OPEN, BEAR_NEW]),
]

# (label, debate, expected turns, scripted replies per debater), 3 configured rounds.
DEBATE_CASES = [
    ("investment, round 2 repeats", "investment", 4,
     [[BULL_OPEN, BULL_REPEAT, BULL_RHETORIC], [BEAR_OPEN, BEAR_REPEAT, BEAR_REPEAT]]),
    ("investment, round 2 new", "investment", 6,
     [[BULL_OPEN, BULL_NEW, BULL_REPEAT], [BEAR_OPEN, BEAR_NEW, BEAR_REPEAT]]),
    ("risk, round 2 repeats", "risk", 6,
     [[AGG_OPEN, AGG_REPEAT, AGG_REPEAT], [CON_OPEN, CON_REPEAT, CON_REPEAT], [NEU_OPEN, NEU_REPEAT, NEU_REPEAT]]),
    ("risk, round 2 new", "risk", 9,
     [[AGG_OPEN, AGG_NEW, AGG_REPEAT], [CON_OPEN, CON_NEW, CON_REPEAT], [NEU_OPEN, NEU_NEW, NEU_REPEAT]]),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def repeat(fn, args_list, runs):
    """``fn(*args)`` ``runs`` times for each args, concurrently; results[i][run]."""
    jobs = [args for args in args_list for _ in range(runs)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        flat = list(pool.map(lambda args: fn(*args), jobs))
    return [flat[i * runs:(i + 1) * runs] for i in range(len(args_list))]


def spread(values):
    got = [v for v in values if v is not None]
    if not got:
        return "all failed"
    return f"mean {statistics.fmean(got):.2f}  [{min(got):.2f}-{max(got):.2f}]" + (
        f"  {len(values) - len(got)} failed" if len(got) < len(values) else ""
    )


def scripted_llm(replies):
    replies = list(replies)
    llm = MagicMock()
    llm.invoke.side_effect = lambda prompt: MagicMock(content=replies.pop(0))
    return llm


def initial_state():
    state = Propagator().create_initial_state("NVDA", "2026-09-22")
    state.update({
        "company_of_interest": "NVDA", "asset_type": "stock",
        "market_report": "m", "sentiment_report": "s", "news_report": "n",
        "fundamentals_report": "f", "trader_investment_plan": "Buy 4% in two tranches.",
    })
    return state


def run_debate(debate, replies):
    """The real debater nodes, ``judge_turns`` and router; 3 configured rounds."""
    logic = ConditionalLogic(max_debate_rounds=3, max_risk_discuss_rounds=3)
    graph = StateGraph(AgentState)
    if debate == "investment":
        nodes = [("Bull Researcher", create_bull_researcher), ("Bear Researcher", create_bear_researcher)]
        router, path_map, end, key = logic.should_continue_debate, DEBATE_PATH_MAP, "Research Manager", "investment_debate_state"
    else:
        nodes = [("Aggressive Analyst", create_aggressive_debator),
                 ("Conservative Analyst", create_conservative_debator),
                 ("Neutral Analyst", create_neutral_debator)]
        router, path_map, end, key = logic.should_continue_risk_analysis, RISK_ANALYSIS_PATH_MAP, "Portfolio Manager", "risk_debate_state"
    for (name, factory), texts in zip(nodes, replies, strict=True):
        graph.add_node(name, logic.judge_turns(factory(scripted_llm(texts)), debate))
        graph.add_conditional_edges(name, router, path_map)
    graph.add_node(end, lambda state: {})
    graph.add_edge(START, nodes[0][0])
    graph.add_edge(end, END)
    state = graph.compile().invoke(initial_state())[key]
    return state["count"], state["new_argument"]


TURN_START = re.compile(r"\n(?=(?:Bull|Bear|Aggressive|Conservative|Neutral) Analyst: )")


def split_turns(history):
    return [t for t in TURN_START.split(history) if t.strip()]


def fmt(p):
    return "  -  " if p is None else f"{p:.2f}"


def named_side(answer):
    """The side the Research Manager's hint names, None for none, "failed" without an answer."""
    if answer is None:
        return "failed"
    top = max(dj.SIDES, key=answer.get)
    return top if top != "even" and answer[top] >= LEAD_MIN else None


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


def check_turns(runs):
    print(f"\n== 1. new_argument on labelled turns (threshold {THRESHOLD}, {runs} runs each) ==")
    results = repeat(dj.new_argument, [(OPENINGS, text) for _, _, text in TURN_CASES], runs)
    passed = 0
    for (label, is_new, _), scores in zip(TURN_CASES, results, strict=True):
        ok = all(s is not None and (s >= THRESHOLD) == is_new for s in scores)
        passed += ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {'new   ' if is_new else 'repeat'} {label:38} "
              f"{' '.join(fmt(s) for s in scores)}   {spread(scores)}")
    return passed, len(TURN_CASES)


def check_debates(runs):
    print(f"\n== 2. whole debates through the nodes and routers (3 rounds, {runs} runs each) ==")
    passed = 0
    for label, debate, expected, replies in DEBATE_CASES:
        outcomes = [run_debate(debate, replies) for _ in range(runs)]
        ok = all(count == expected for count, _ in outcomes)
        passed += ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:30} expected {expected} turns")
        for count, scores in outcomes:
            print(f"      {count} turns   new_argument {[None if s is None else round(s, 2) for s in scores]}")
    return passed, len(DEBATE_CASES)


def check_sides(runs):
    print(f"\n== 3. stronger_side on labelled debates ({runs} runs each) ==")
    args = [
        ("\n".join(bull(t) for t in bulls), "\n".join(bear(t) for t in bears))
        for _, _, bulls, bears in SIDE_CASES
    ]
    results = repeat(dj.stronger_side, args, runs)
    passed = 0
    for (label, expected, _, _), answers in zip(SIDE_CASES, results, strict=True):
        named = [named_side(a) for a in answers]
        ok = all(side == expected for side in named)
        passed += ok
        print(f"  [{'PASS' if ok else 'FAIL'}] expect {expected or 'none':5} {label:30} hint names {named}")
        for a in answers:
            print("      " + ("failed" if a is None else "  ".join(f"{s} {a[s]:.2f}" for s in dj.SIDES)))
    return passed, len(SIDE_CASES)


def replay_log(path, runs):
    log = json.loads(Path(path).read_text(encoding="utf-8"))
    print(f"\n== 4. replay of {path} ==")
    for key, debate in (("investment_debate_state", "investment"), ("risk_debate_state", "risk")):
        state = log[key]
        turns = split_turns(state["history"])
        logged = state.get("new_argument") or []
        print(f"\n  {debate}: {len(turns)} turns (logged count {state.get('turns')}), "
              f"history {len(state['history']):,} chars, turn sizes "
              f"{min(map(len, turns)):,}-{max(map(len, turns)):,}")
        if len(turns) != state.get("turns"):
            print("    turn split does not match the logged count; skipping")
            continue
        judged = [i for i, s in enumerate(logged) if s is not None]
        jobs = [("\n".join(turns[:i]).strip(), turns[i].strip()) for i in judged]
        start = time.monotonic()
        again = repeat(dj.new_argument, jobs, 1)
        print(f"    {len(jobs)} requests in {time.monotonic() - start:.1f} s")
        for i, (prior, latest), (score,) in zip(judged, jobs, again, strict=True):
            speaker = turns[i].split(":", 1)[0]
            sent = len(dj.latest_turns(prior, dj.MAX_STATE_CHARS - len(latest)))
            print(f"    turn {i + 1:2} {speaker:22} prior {len(prior):7,} chars"
                  + (f" (sent {sent:,})" if sent < len(prior) else " " * 15)
                  + f"   logged {fmt(logged[i])}   now {fmt(score)}")
    inv = log["investment_debate_state"]
    bull_case, bear_case = inv["bull_history"], inv["bear_history"]
    sent = [len(dj.latest_turns(case, dj.MAX_STATE_CHARS // 2)) for case in (bull_case, bear_case)]
    print(f"\n  stronger_side on bull {len(bull_case):,} + bear {len(bear_case):,} chars, "
          f"sent {sent[0]:,} + {sent[1]:,} (logged {inv.get('stronger_side') or 'nothing'}):")
    start = time.monotonic()
    [answers] = repeat(dj.stronger_side, [(bull_case, bear_case)], runs)
    print(f"    {runs} requests in {time.monotonic() - start:.1f} s")
    for a in answers:
        print("    " + ("failed" if a is None else "  ".join(f"{s} {a[s]:.2f}" for s in dj.SIDES)
                        + f"   hint names {named_side(a)}"))
    decision = log.get("investment_plan", "").strip().splitlines()
    print(f"    the run's Research Manager decided: {decision[0][:100] if decision else '?'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--log", help="a full_states_log_<date>.json to replay")
    args = parser.parse_args()

    client = jev_client()
    if client is None:
        raise SystemExit("Jev is off: set TYPESAFE_API_KEY and install the jev extra.")
    with client:  # one small request, to learn which version the alias resolves to
        probe = client.system_one(
            state={"prior_turns": bull(BULL_OPEN), "latest_turn": bear(BEAR_OPEN)},
            questions=dj._questions()["turn"],
        )
    print(f"model: {client._config.default_model} ({probe.model})")

    totals = [check_turns(args.runs), check_debates(args.runs), check_sides(args.runs)]
    if args.log:
        replay_log(args.log, args.runs)
    passed, cases = map(sum, zip(*totals, strict=True))
    print(f"\n{passed}/{cases} labelled cases passed")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import sys

from .backtest import TOURNAMENTS, run_backtest
from .predict import Predictor
from .data import apifootball
from .simulate import simulate_match, save_predictions, format_result
from .grading import grade, load_actuals, format_grade
import json

DEFAULT_MODEL_PATH = "passbot_model.pkl"


def _cmd_backtest(args: argparse.Namespace) -> int:
    res = run_backtest(args.train, args.test, limit=args.limit)
    print(f"\nBacktest: train={'+'.join(args.train)}  test={args.test}\n")
    print(res.summary())
    if args.show:
        df = res.df.sort_values("target_passes", ascending=False).head(args.show)
        print(f"\n{'player':<24}{'pos':<5}{'pred':>6}{'actual':>8}")
        for _, r in df.iterrows():
            print(f"{r.player_name[:23]:<24}{r.position_group:<5}"
                  f"{r.predicted_passes:>6.0f}{r.target_passes:>8.0f}")
    return 0


def _cmd_train(args: argparse.Namespace) -> int:
    p = Predictor()
    n = p.train(args.tournaments, limit=args.limit)
    p.save(args.out)
    print(f"Trained on {n} player-matches from {'+'.join(args.tournaments)}.")
    print(f"Saved model to {args.out}")
    return 0


def _cmd_predict(args: argparse.Namespace) -> int:
    try:
        predictor = Predictor.load(args.model)
    except FileNotFoundError:
        print(f"No model at {args.model}. Run 'passbot train' first.", file=sys.stderr)
        return 1

    if args.mock:
        lineup, opponents = apifootball.mock_lineup()
        print("Using MOCK lineup: Spain vs Germany\n")
    elif args.fixture:
        lineup = apifootball.get_lineup(args.fixture)
        teams = sorted({p["team"] for p in lineup})
        opponents = {teams[0]: teams[1], teams[1]: teams[0]} if len(teams) == 2 else {}
    else:
        print("Provide --fixture <id> or --mock.", file=sys.stderr)
        return 1

    preds = predictor.predict_lineup(lineup, opponents)
    print(f"{'player':<26}{'team':<10}{'pos':<5}{'xMin':>5}{'passes':>8}")
    print("-" * 56)
    for p in preds:
        print(f"{p.player_name[:25]:<26}{p.team[:9]:<10}{p.position_group:<5}"
              f"{p.expected_minutes:>5.0f}{p.predicted_passes:>8.0f}")
    return 0


def _cmd_simulate(args: argparse.Namespace) -> int:
    result = simulate_match(args.match)
    print(format_result(result))
    if args.out:
        save_predictions(result, args.out)
        print(f"Saved predictions to {args.out} (grade them later with 'passbot grade').")
    return 0


def _cmd_grade(args: argparse.Namespace) -> int:
    result = json.loads(open(args.predictions, encoding="utf-8").read())
    actuals = load_actuals(args.actuals)
    print(format_grade(grade(result, actuals)))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="passbot",
        description="Predict how many passes each player makes in a match.")
    sub = parser.add_subparsers(dest="command", required=True)

    keys = ", ".join(TOURNAMENTS)

    b = sub.add_parser("backtest", help="train on past tournaments, score a held-out one")
    b.add_argument("--train", nargs="+", default=["wc2018"], help=f"tournaments: {keys}")
    b.add_argument("--test", default="wc2022", help=f"held-out tournament: {keys}")
    b.add_argument("--limit", type=int, default=None, help="cap matches per tournament")
    b.add_argument("--show", type=int, default=0, help="show N top predictions vs actuals")
    b.set_defaults(func=_cmd_backtest)

    t = sub.add_parser("train", help="train and persist a model for live prediction")
    t.add_argument("--tournaments", nargs="+", default=["wc2018", "wc2022"],
                   help=f"tournaments: {keys}")
    t.add_argument("--limit", type=int, default=None)
    t.add_argument("--out", default=DEFAULT_MODEL_PATH)
    t.set_defaults(func=_cmd_train)

    p = sub.add_parser("predict", help="predict passes for a lineup")
    p.add_argument("--model", default=DEFAULT_MODEL_PATH)
    p.add_argument("--fixture", type=int, help="API-Football fixture id (needs API key)")
    p.add_argument("--mock", action="store_true", help="use a built-in sample lineup")
    p.set_defaults(func=_cmd_predict)

    s = sub.add_parser("simulate", help="predict a match from a lineup spec (matches/*.yaml)")
    s.add_argument("match", help="path to a match spec YAML")
    s.add_argument("--out", help="save predictions JSON here for later grading")
    s.set_defaults(func=_cmd_simulate)

    g = sub.add_parser("grade", help="score saved predictions against actual passes")
    g.add_argument("--predictions", required=True, help="predictions JSON from 'simulate --out'")
    g.add_argument("--actuals", required=True, help="actuals as JSON {name: passes} or CSV name,passes")
    g.set_defaults(func=_cmd_grade)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from passbot.formation import FormationModel, load_rows  # noqa: E402
from passbot.models import POSITION_GROUPS  # noqa: E402
from lineups import GAMES  # noqa: E402

CSV = Path(__file__).resolve().parent / "passes.csv"


def parse_passes(path: Path) -> dict[str, dict[str, int]]:
    """Parse the sheet into {game_title: {player: passes}}."""
    games: dict[str, dict[str, int]] = {}
    cur = None
    for row in csv.reader(path.open()):
        if not row or not row[0].strip():
            continue
        name, val = row[0].strip(), (row[1].strip() if len(row) > 1 else "")
        if " vs " in name:
            cur = name
            games[cur] = {}
            continue
        if cur is None or name in ("Total",):
            continue
        try:
            games[cur][name] = int(val)
        except ValueError:
            pass  # GK rows marked "P", headers, etc.
    return games


def build_dataset():
    """Yield (game, team, player, pos, possession, actual_passes) per starter."""
    passes = parse_passes(CSV)
    rows = []
    for entry in GAMES:
        title, teams = entry[0], entry[1]
        pinned = entry[2] if len(entry) > 2 else None
        pmap = passes.get(title, {})

        # team starter pass sums for possession share
        sums = {}
        for team, xi in teams:
            sums[team] = sum(pmap.get(n, 0) for n, _ in xi)

        for i, (team, xi) in enumerate(teams):
            if pinned is not None:
                poss = pinned if i == 0 else 1 - pinned
            elif len(teams) == 2:
                other = sums[teams[1 - i][0]]
                tot = sums[team] + other
                poss = sums[team] / tot if tot else 0.5
            else:
                poss = 0.5
            for player, pos in xi:
                if player in pmap:
                    rows.append((title, team, player, pos, poss, pmap[player]))
    return rows


def main():
    rows = build_dataset()
    fm = FormationModel().fit(load_rows(["wc2018", "wc2022"]))

    print(f"Calibration set: {len(rows)} starters across "
          f"{len(set(r[0] for r in rows))} games\n")

    # Current-model bias by position group (base convex curve, no role/style).
    by_pos = defaultdict(lambda: {"pred": [], "act": []})
    abs_err = []
    for _, _, _, pos, poss, act in rows:
        pred = fm.passes_for_group(pos, poss)
        by_pos[pos]["pred"].append(pred)
        by_pos[pos]["act"].append(act)
        abs_err.append(abs(pred - act))

    print(f"{'pos':<4}{'n':>4}{'pred':>7}{'actual':>8}{'bias':>7}{'ratio':>7}")
    for g in POSITION_GROUPS:
        d = by_pos[g]
        if not d["act"]:
            continue
        p, a = np.mean(d["pred"]), np.mean(d["act"])
        print(f"{g:<4}{len(d['act']):>4}{p:>7.0f}{a:>8.0f}{a-p:>+7.0f}{a/p:>7.2f}")
    print(f"\nCurrent base-model MAE on real data: {np.mean(abs_err):.2f} passes")

    # Leave-one-GAME-out: derive per-position calibration ratios from the other
    # games, apply to the held-out game. Honest out-of-sample check.
    games = sorted(set(r[0] for r in rows))
    base_err, cal_err = [], []
    for held in games:
        train = [r for r in rows if r[0] != held]
        ratios = {}
        for g in POSITION_GROUPS:
            ps = [(fm.passes_for_group(pos, poss), act)
                  for _, _, _, pos, poss, act in train if pos == g]
            if ps:
                pred_sum = sum(p for p, _ in ps)
                act_sum = sum(a for _, a in ps)
                ratios[g] = act_sum / pred_sum if pred_sum else 1.0
        for _, _, _, pos, poss, act in rows:
            if pos != held and False:
                continue
        for _, _, _, pos, poss, act in [r for r in rows if r[0] == held]:
            base = fm.passes_for_group(pos, poss)
            base_err.append(abs(base - act))
            cal_err.append(abs(base * ratios.get(pos, 1.0) - act))
    print(f"\nLeave-one-game-out MAE:")
    print(f"  uncalibrated : {np.mean(base_err):.2f}")
    print(f"  calibrated   : {np.mean(cal_err):.2f}")

    # Final pooled calibration factors to bake into the model.
    print("\nPooled calibration factors (actual/pred):")
    print("  " + ", ".join(
        f'"{g}": {np.mean(by_pos[g]["act"])/np.mean(by_pos[g]["pred"]):.2f}'
        for g in POSITION_GROUPS if by_pos[g]["act"]))


if __name__ == "__main__":
    main()

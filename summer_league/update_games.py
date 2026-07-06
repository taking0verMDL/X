"""Update player values and totals calibration from SL box scores.

One SL game is a tiny sample, so this is a Bayesian nudge, not a rewrite:
each player's value moves a fraction of the way toward what the box score
implies, scaled by minutes played. A monster game moves a guy ~0.5-1.0
points of value; it takes several to fully re-rate him.

Inputs (append rows, then run `python -m summer_league.update_games`):

- data/boxscores_2026.csv
    date,team,player,min,pts,fgm,fga,tpm,tpa,ftm,fta,oreb,reb,ast,stl,blk,tov,pf
- data/games_2026.csv
    date,team_a,team_b,pts_a,pts_b

Player update: Hollinger Game Score per 36 minutes, mapped onto the 0-10
value scale (SL-average production ~= value 5.0), then
    new_value = old + K * (observed - old),  K = LEARN_RATE * min(1, min/28)

Game log update: reports predicted vs. actual spread/total and the
re-calibrated BASE_TOTAL to adopt in model.py once enough games are in.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .model import BASE_TOTAL, load_rosters, matchup, projected_score, rate_teams

DATA = Path(__file__).parent / "data"
ROSTERS = Path(__file__).parent / "rosters_2026.csv"
BOX = DATA / "boxscores_2026.csv"
GAMES = DATA / "games_2026.csv"

LEARN_RATE = 0.18        # value share a full-minutes game carries
FULL_GAME_MIN = 28.0     # SL minutes that count as a "full" game
GS36_ANCHOR = 10.0       # game score per 36 of an average SL rotation player
VALUE_ANCHOR = 5.0       # ...corresponds to this value
GS36_SLOPE = 0.35        # value points per game-score-per-36 point
OBS_CLAMP = (1.0, 11.0)
MIN_MINUTES = 6.0        # below this a box score says nothing


def game_score(r: dict) -> float:
    g = lambda k: float(r.get(k) or 0)
    return (g("pts") + 0.4 * g("fgm") - 0.7 * g("fga")
            - 0.4 * (g("fta") - g("ftm")) + 0.7 * g("oreb")
            + 0.3 * (g("reb") - g("oreb")) + g("stl") + 0.7 * g("ast")
            + 0.7 * g("blk") - 0.4 * g("pf") - g("tov"))


def observed_value(r: dict) -> float:
    mins = float(r["min"])
    gs36 = game_score(r) / mins * 36.0
    obs = VALUE_ANCHOR + GS36_SLOPE * (gs36 - GS36_ANCHOR)
    return min(OBS_CLAMP[1], max(OBS_CLAMP[0], obs))


def update_players() -> int:
    if not BOX.exists():
        print(f"no {BOX.name}; skipping player updates")
        return 0
    rows = list(csv.DictReader(open(ROSTERS, encoding="utf-8")))
    index = {(r["team"], r["player"]): r for r in rows}
    players = {(p.team, p.name): p for p in load_rosters(ROSTERS)}

    box_rows = list(csv.DictReader(open(BOX, encoding="utf-8")))
    n = 0
    for b in box_rows:
        if b.get("applied") == "1":       # already folded into values
            continue
        key = (b["team"], b["player"])
        if key not in index:
            print(f"  ! no roster match: {key} — fix the name and rerun")
            continue
        b["applied"] = "1"
        mins = float(b["min"] or 0)
        if mins < MIN_MINUTES:
            continue
        old = players[key].value
        k = LEARN_RATE * min(1.0, mins / FULL_GAME_MIN)
        new = old + k * (observed_value(b) - old)
        index[key]["value"] = f"{new - players[key].adj:.1f}"
        n += 1

    cols = list(rows[0].keys())
    with open(ROSTERS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    # mark applied lines so reruns are idempotent
    box_cols = [c for c in box_rows[0].keys() if c != "applied"] + ["applied"]
    with open(BOX, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=box_cols)
        w.writeheader()
        w.writerows(box_rows)
    return n


def report_games() -> None:
    if not GAMES.exists():
        print(f"no {GAMES.name}; skipping calibration report")
        return
    ratings = {r.team: r for r in rate_teams(load_rosters(ROSTERS))}
    totals, spread_err = [], []
    print("\ndate        matchup                          pred        actual")
    for g in csv.DictReader(open(GAMES, encoding="utf-8")):
        a, b = ratings.get(g["team_a"]), ratings.get(g["team_b"])
        if not (a and b):
            print(f"  ! unknown team in game row: {g}")
            continue
        pa, pb = float(g["pts_a"]), float(g["pts_b"])
        spread, _ = matchup(a, b)
        ea, eb = projected_score(a, b)
        totals.append(pa + pb)
        spread_err.append((pa - pb) - spread)
        print(f"{g['date']}  {a.team.split()[-1]:>12} v {b.team.split()[-1]:<12}"
              f"  {spread:+5.1f}/{ea + eb:5.1f}  {pa - pb:+5.0f}/{pa + pb:5.0f}")
    if totals:
        obs = sum(totals) / len(totals)
        me = sum(spread_err) / len(spread_err)
        mae = sum(abs(e) for e in spread_err) / len(spread_err)
        n = len(totals)
        # shrink toward the prior: ~8 games of prior weight
        suggested = (BASE_TOTAL * 8 + obs * n) / (8 + n)
        print(f"\n{n} games | avg total {obs:.1f} (model {BASE_TOTAL})"
              f" -> suggested BASE_TOTAL {suggested:.1f}")
        print(f"spread bias {me:+.1f}, MAE {mae:.1f}")


if __name__ == "__main__":
    n = update_players()
    print(f"updated {n} player-game lines")
    report_games()

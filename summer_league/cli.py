"""Command-line interface for the Summer League power ratings model.

Usage:
    sl-ratings rosters.csv                     # print power ratings
    sl-ratings rosters.csv --detail            # include each team's rotation
    sl-ratings rosters.csv --matchup "A,B"     # spread + win prob for A vs B
    sl-ratings rosters.csv --out ratings.csv   # also write a ratings CSV
"""

from __future__ import annotations

import argparse
import sys

from .model import (TeamRating, load_rosters, matchup, projected_score,
                    rate_teams, write_ratings_csv)


def _print_table(ratings: list[TeamRating], detail: bool) -> None:
    width = max(len(r.team) for r in ratings)
    print(f"{'#':>2}  {'TEAM':<{width}}  {'RATING':>7}  {'STRENGTH':>8}")
    for i, r in enumerate(ratings, start=1):
        print(f"{i:>2}  {r.team:<{width}}  {r.rating:>+7.2f}  {r.strength:>8.2f}")
        if detail:
            for p in r.rotation:
                pos = f" {p.pos}" if p.pos else ""
                print(f"      {p.value:5.2f}  {p.name}{pos} [{p.tier}]")
    print("\nRating = expected margin (points) vs. an average team on a neutral floor.")


def _find_team(ratings: list[TeamRating], name: str) -> TeamRating:
    needle = name.strip().lower()
    exact = [r for r in ratings if r.team.lower() == needle]
    if exact:
        return exact[0]
    partial = [r for r in ratings if needle in r.team.lower()]
    if len(partial) == 1:
        return partial[0]
    teams = ", ".join(r.team for r in ratings)
    sys.exit(f"Team {name!r} not found (or ambiguous). Teams: {teams}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="sl-ratings", description="Summer League power ratings")
    parser.add_argument("rosters", help="roster CSV file")
    parser.add_argument("--detail", action="store_true",
                        help="show each team's rotation with player values")
    parser.add_argument("--matchup", metavar="A,B",
                        help="print spread and win probability for A vs B")
    parser.add_argument("--out", metavar="FILE", help="write ratings CSV")
    args = parser.parse_args(argv)

    try:
        players = load_rosters(args.rosters)
    except (OSError, ValueError) as e:
        sys.exit(str(e))
    ratings = rate_teams(players)

    if args.matchup:
        names = args.matchup.split(",")
        if len(names) != 2:
            sys.exit("--matchup expects two team names separated by a comma")
        a = _find_team(ratings, names[0])
        b = _find_team(ratings, names[1])
        spread, p = matchup(a, b)
        pts_a, pts_b = projected_score(a, b)
        fav, dog, line = (a, b, spread) if spread >= 0 else (b, a, -spread)
        print(f"{a.team} vs {b.team}: {fav.team} -{line:.1f} | "
              f"total {pts_a + pts_b:.1f} | "
              f"proj {a.team} {pts_a:.0f}, {b.team} {pts_b:.0f} "
              f"({a.team} win prob {p:.0%})")
        return

    _print_table(ratings, args.detail)
    if args.out:
        write_ratings_csv(ratings, args.out)
        print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()

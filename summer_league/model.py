"""Player-value and team power-rating model for NBA Summer League.

The core idea: Summer League outcomes are driven far more by *pedigree and
experience* than by anything you can measure in the games themselves (tiny
samples, weird rotations). So each player gets a value in "SL impact points"
(roughly 0-10) from a pedigree tier, refined by draft slot, NBA experience,
and age. Team strength is a minutes-weighted average of the top of the
rotation, and the power rating is expressed in points relative to the
average team — so `rating_a - rating_b` is directly a point spread.

All the knobs live in module-level constants so they're easy to retune.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# --------------------------------------------------------------------------
# Tunable constants
# --------------------------------------------------------------------------

# Base player value by pedigree tier (SL impact points, ~0-10 scale).
TIER_VALUES: dict[str, float] = {
    "nba_rotation": 8.5,   # returner with real NBA rotation minutes
    "nba_fringe": 7.0,     # standard NBA contract, end of bench
    "lottery_rookie": 7.5,     # picks 1-14 in the most recent draft
    "first_round_rookie": 6.0,  # picks 15-30
    "second_round_rookie": 4.5,
    "undrafted_rookie": 3.0,
    "two_way": 5.5,        # two-way contract (usually a productive G-Leaguer)
    "gleague_vet": 4.0,    # experienced G-League / SL veteran, Exhibit 10
    "international": 3.5,  # overseas pro / draft-and-stash
    "camp": 2.0,           # roster fill
}

# If a rookie's actual draft pick is known, use a smooth curve instead of the
# coarse tier default: pick 1 ~ 8.5, pick 14 ~ 5.5, pick 30 ~ 4.6, pick 60 ~ 3.8.
PICK_CURVE_TOP = 8.5
PICK_CURVE_SLOPE = 1.15
PICK_CURVE_FLOOR = 3.0

# NBA experience bonus for returners/two-ways: games and minutes both help.
EXP_GP_WEIGHT = 0.010
EXP_MPG_WEIGHT = 0.040
EXP_BONUS_CAP = 1.5

# Age matters for non-NBA guys (a 25-year-old G-League vet beats a 21-year-old
# camp body), but the effect is small and capped.
AGE_BASELINE = 21
AGE_WEIGHT = 0.10
AGE_BONUS_CAP = 0.5
AGE_TIERS_EXEMPT = {"nba_rotation", "nba_fringe", "lottery_rookie",
                    "first_round_rookie", "second_round_rookie",
                    "undrafted_rookie"}

# Minutes-share weights for the effective SL rotation (best player first).
# SL rotations are short: your top 6-7 play almost everything.
ROTATION_WEIGHTS = [1.00, 1.00, 0.95, 0.88, 0.80, 0.70, 0.55, 0.40, 0.25, 0.15]

# Teams that show up with a thin roster (< MIN_ROTATION players) eat a small
# penalty per missing body — someone unrated has to soak up those minutes.
MIN_ROTATION = 9
THIN_ROSTER_PENALTY = 0.15

# Converts (team strength - league mean strength) into points per game.
POINTS_SCALE = 3.2

# Std dev of a single SL game margin, for win probabilities.
GAME_MARGIN_SD = 13.0

ROOKIE_TIERS = {"lottery_rookie", "first_round_rookie", "second_round_rookie",
                "undrafted_rookie"}


# --------------------------------------------------------------------------
# Data types
# --------------------------------------------------------------------------

@dataclass
class Player:
    team: str
    name: str
    tier: str
    pos: str = ""
    age: float | None = None
    draft_pick: int | None = None
    nba_gp: float | None = None
    nba_mpg: float | None = None
    adj: float = 0.0
    out: bool = False

    value: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        if self.tier not in TIER_VALUES:
            raise ValueError(
                f"{self.name!r} ({self.team}): unknown tier {self.tier!r}. "
                f"Valid tiers: {', '.join(sorted(TIER_VALUES))}"
            )
        self.value = self._compute_value()

    def _compute_value(self) -> float:
        v = TIER_VALUES[self.tier]

        # Draft-pick curve overrides the coarse rookie tier default.
        if self.draft_pick:
            pick_v = max(PICK_CURVE_FLOOR,
                         PICK_CURVE_TOP - PICK_CURVE_SLOPE * math.log(self.draft_pick))
            if self.tier in ROOKIE_TIERS:
                v = pick_v
            else:
                # Returner drafted in a previous year: pedigree is a mild bump.
                v += 0.25 * max(0.0, pick_v - v)

        # NBA experience bonus.
        gp = self.nba_gp or 0.0
        mpg = self.nba_mpg or 0.0
        if gp or mpg:
            v += min(EXP_BONUS_CAP, EXP_GP_WEIGHT * gp + EXP_MPG_WEIGHT * mpg)

        # Age bonus for the non-pedigree tiers.
        if self.age and self.tier not in AGE_TIERS_EXEMPT:
            v += min(AGE_BONUS_CAP, max(0.0, AGE_WEIGHT * (self.age - AGE_BASELINE)))

        return v + self.adj


@dataclass
class TeamRating:
    team: str
    strength: float          # weighted-average rotation player value
    rating: float = 0.0      # points vs. average SL team (set league-wide)
    players: list[Player] = field(default_factory=list)

    @property
    def rotation(self) -> list[Player]:
        active = [p for p in self.players if not p.out]
        return sorted(active, key=lambda p: p.value, reverse=True)


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------

def team_strength(players: Iterable[Player]) -> float:
    """Minutes-weighted average value of the effective rotation."""
    active = sorted((p for p in players if not p.out),
                    key=lambda p: p.value, reverse=True)
    if not active:
        return 0.0
    top = active[: len(ROTATION_WEIGHTS)]
    weights = ROTATION_WEIGHTS[: len(top)]
    strength = sum(w * p.value for w, p in zip(weights, top)) / sum(weights)
    if len(active) < MIN_ROTATION:
        strength -= THIN_ROSTER_PENALTY * (MIN_ROTATION - len(active))
    return strength


def rate_teams(players: list[Player]) -> list[TeamRating]:
    """Group players by team, compute strengths, and center ratings in points."""
    by_team: dict[str, list[Player]] = {}
    for p in players:
        by_team.setdefault(p.team, []).append(p)

    ratings = [TeamRating(team=t, strength=team_strength(ps), players=ps)
               for t, ps in by_team.items()]
    mean = sum(r.strength for r in ratings) / len(ratings)
    for r in ratings:
        r.rating = POINTS_SCALE * (r.strength - mean)
    ratings.sort(key=lambda r: r.rating, reverse=True)
    return ratings


def matchup(a: TeamRating, b: TeamRating) -> tuple[float, float]:
    """Return (spread, win probability) for team `a` vs team `b`.

    Spread is a's expected margin (positive = a favored). SL is played on a
    neutral floor, so there's no home-court term.
    """
    spread = a.rating - b.rating
    win_prob = 0.5 * (1.0 + math.erf(spread / (GAME_MARGIN_SD * math.sqrt(2.0))))
    return spread, win_prob


# --------------------------------------------------------------------------
# Roster CSV I/O
# --------------------------------------------------------------------------

CSV_COLUMNS = ["team", "player", "pos", "tier", "age", "draft_pick",
               "nba_gp", "nba_mpg", "adj", "out"]


def _num(row: dict, key: str) -> float | None:
    raw = (row.get(key) or "").strip()
    return float(raw) if raw else None


def load_rosters(path: str | Path) -> list[Player]:
    """Load players from a roster CSV (see CSV_COLUMNS / README for schema)."""
    players: list[Player] = []
    with open(path, newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            team = (row.get("team") or "").strip()
            name = (row.get("player") or "").strip()
            if not team or not name:
                continue
            try:
                pick = _num(row, "draft_pick")
                players.append(Player(
                    team=team,
                    name=name,
                    tier=(row.get("tier") or "").strip().lower(),
                    pos=(row.get("pos") or "").strip(),
                    age=_num(row, "age"),
                    draft_pick=int(pick) if pick else None,
                    nba_gp=_num(row, "nba_gp"),
                    nba_mpg=_num(row, "nba_mpg"),
                    adj=_num(row, "adj") or 0.0,
                    out=(row.get("out") or "").strip().lower()
                        in ("1", "true", "yes", "out"),
                ))
            except ValueError as e:
                raise ValueError(f"{path}, line {i}: {e}") from e
    if not players:
        raise ValueError(f"{path}: no players found")
    return players


def write_ratings_csv(ratings: list[TeamRating], path: str | Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "team", "rating", "strength", "top_players"])
        for i, r in enumerate(ratings, start=1):
            top = "; ".join(f"{p.name} ({p.value:.1f})" for p in r.rotation[:3])
            w.writerow([i, r.team, f"{r.rating:+.2f}", f"{r.strength:.2f}", top])

from __future__ import annotations

import unicodedata
from collections import defaultdict

import pandas as pd

from .models import POSITION_GROUPS, PlayerMatch


def _norm_name(name: str) -> str:
    """Normalise a player name for cross-source matching: strip accents,
    lowercase, collapse whitespace."""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(ascii_name.lower().split())

# Reasonable passes-per-90 priors by position group, used as a cold-start
# value for players we've never seen before. Tuned from World Cup averages.
_GROUP_PRIOR_P90 = {
    "GK": 28.0, "CB": 62.0, "FB": 55.0, "DM": 65.0,
    "CM": 60.0, "AM": 48.0, "W": 42.0, "ST": 32.0,
}

FEATURE_COLUMNS = [
    "player_rolling_p90",
    "player_rolling_minutes",
    "player_matches_seen",
    "group_prior_p90",
    "team_rolling_possession",
    "opp_rolling_possession",
    "is_starter",
] + [f"pos_{g}" for g in POSITION_GROUPS]


class FeatureBuilder:
    """Builds a leak-free feature table from chronologically ordered matches.

    For each player-match we emit features derived only from data available
    *before* kickoff: the player's rolling pass rate, expected minutes, and
    each team's historical possession share. The match's own passes are never
    used as an input — only as the training target.
    """

    def __init__(self) -> None:
        self._player_p90: dict[int, list[float]] = defaultdict(list)
        self._player_min: dict[int, list[float]] = defaultdict(list)
        self._team_poss: dict[str, list[float]] = defaultdict(list)
        # Name -> player_id, so live lineups (which arrive as names) can be
        # matched back to the history accumulated from StatsBomb data.
        self._name_to_id: dict[str, int] = {}

    @staticmethod
    def _mean(xs: list[float], default: float) -> float:
        return sum(xs) / len(xs) if xs else default

    def _features_for(self, r: PlayerMatch) -> dict:
        prior = _GROUP_PRIOR_P90.get(r.position_group, 55.0)
        seen = len(self._player_p90[r.player_id])
        feats = {
            "player_rolling_p90": self._mean(self._player_p90[r.player_id], prior),
            "player_rolling_minutes": self._mean(self._player_min[r.player_id], 70.0),
            "player_matches_seen": float(seen),
            "group_prior_p90": prior,
            "team_rolling_possession": self._mean(self._team_poss[r.team], 0.5),
            "opp_rolling_possession": self._mean(self._team_poss[r.opponent], 0.5),
            "is_starter": float(r.is_starter),
        }
        for g in POSITION_GROUPS:
            feats[f"pos_{g}"] = 1.0 if r.position_group == g else 0.0
        return feats

    def _observe(self, r: PlayerMatch) -> None:
        """Fold a played match into history (call AFTER extracting features)."""
        if r.minutes > 0:
            self._player_p90[r.player_id].append(r.passes_per_90)
            self._player_min[r.player_id].append(r.minutes)
            self._team_poss[r.team].append(r.team_possession_share)
            if r.player_name:
                self._name_to_id[_norm_name(r.player_name)] = r.player_id

    def live_features(self, name: str, position_group: str,
                      team: str, opponent: str, is_starter: bool) -> dict:
        """Build a feature row for an upcoming match from a lineup spec.

        Looks the player up by name in accumulated history; unknown players
        fall back to their position-group prior. This is the bridge between
        the StatsBomb-trained model and live World Cup lineups.
        """
        pid = self._name_to_id.get(_norm_name(name))
        prior = _GROUP_PRIOR_P90.get(position_group, 55.0)
        p90_hist = self._player_p90.get(pid, []) if pid is not None else []
        min_hist = self._player_min.get(pid, []) if pid is not None else []
        feats = {
            "player_rolling_p90": self._mean(p90_hist, prior),
            "player_rolling_minutes": self._mean(min_hist, 70.0),
            "player_matches_seen": float(len(p90_hist)),
            "group_prior_p90": prior,
            "team_rolling_possession": self._mean(self._team_poss.get(team, []), 0.5),
            "opp_rolling_possession": self._mean(self._team_poss.get(opponent, []), 0.5),
            "is_starter": float(is_starter),
        }
        for g in POSITION_GROUPS:
            feats[f"pos_{g}"] = 1.0 if position_group == g else 0.0
        return feats

    def build(self, rows: list[PlayerMatch], *, learn: bool = True) -> pd.DataFrame:
        """Produce a feature DataFrame. Rows are processed match-by-match in
        date order so a match's features only reflect earlier matches.

        With learn=True the builder also accumulates history, so calling
        build() on a training set then on a later set carries player/team
        form forward into the predictions.
        """
        rows = sorted(rows, key=lambda r: (r.date, r.match_id))
        # Group consecutive rows by match so all 22+ players in a match see the
        # same pre-match history, then observe the whole match at once.
        records = []
        current_match = None
        pending: list[PlayerMatch] = []

        def flush(batch: list[PlayerMatch]) -> None:
            for r in batch:
                feats = self._features_for(r)
                feats.update({
                    "match_id": r.match_id,
                    "player_id": r.player_id,
                    "player_name": r.player_name,
                    "team": r.team,
                    "position_group": r.position_group,
                    "minutes": r.minutes,
                    "target_p90": r.passes_per_90,
                    "target_passes": r.passes,
                })
                records.append(feats)
            if learn:
                for r in batch:
                    self._observe(r)

        for r in rows:
            if current_match is not None and r.match_id != current_match:
                flush(pending)
                pending = []
            current_match = r.match_id
            pending.append(r)
        flush(pending)

        return pd.DataFrame.from_records(records)

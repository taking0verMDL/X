from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from .models import PlayerMatch
from .data import statsbomb
from .backtest import TOURNAMENTS


@dataclass
class FormationModel:
    """Roster-independent pass model built on two stable signals:

    1. **Position share** — within a given formation, what fraction of the
       team's passes a position accounts for. A back-3 center-back's share is
       similar whoever fills the role, so this transfers to new squads.
    2. **Team total passes vs possession** — a team's total pass count scales
       with how much of the ball it has. We fit team_passes against possession
       share so we can turn a possession estimate into a pass budget.

    A player's predicted passes = team_total × position_share, optionally
    scaled by minutes.
    """

    # share[formation][position_name] = mean fraction of team passes
    share: dict[str, dict[str, float]] = field(default_factory=dict)
    # fallback share by position name, pooled across formations
    share_by_pos: dict[str, float] = field(default_factory=dict)
    # team_total_passes ≈ poss_intercept + poss_slope * possession_share
    poss_intercept: float = 0.0
    poss_slope: float = 1.0
    mean_match_passes: float = 1000.0

    def fit(self, rows: list[PlayerMatch]) -> "FormationModel":
        # Group starters by (formation, team, match) to compute pass shares.
        by_team_match: dict[tuple, list[PlayerMatch]] = defaultdict(list)
        for r in rows:
            if r.is_starter and r.minutes > 0 and r.formation:
                by_team_match[(r.match_id, r.team)].append(r)

        share_acc: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        pos_acc: dict[str, list[float]] = defaultdict(list)
        poss_x, poss_y, match_totals = [], [], []

        for (mid, team), players in by_team_match.items():
            team_total = players[0].team_passes
            if team_total <= 0:
                continue
            for p in players:
                frac = p.passes / team_total
                share_acc[p.formation][p.position].append(frac)
                pos_acc[p.position].append(frac)
            poss_x.append(players[0].team_possession_share)
            poss_y.append(team_total)
            match_totals.append(players[0].team_passes + players[0].opponent_passes)

        self.share = {f: {pos: float(np.mean(v)) for pos, v in d.items()}
                      for f, d in share_acc.items()}
        self.share_by_pos = {pos: float(np.mean(v)) for pos, v in pos_acc.items()}

        # Linear fit: team passes as a function of possession share.
        if len(poss_x) > 2:
            slope, intercept = np.polyfit(poss_x, poss_y, 1)
            self.poss_slope, self.poss_intercept = float(slope), float(intercept)
        self.mean_match_passes = float(np.mean(match_totals)) if match_totals else 1000.0
        return self

    def team_total_passes(self, possession_share: float) -> float:
        return max(50.0, self.poss_intercept + self.poss_slope * possession_share)

    def position_share(self, formation: str, position: str) -> float:
        f = self.share.get(formation, {})
        if position in f:
            return f[position]
        # Fall back to the pooled cross-formation share for that position.
        return self.share_by_pos.get(position, 1.0 / 11)

    def predict_lineup(self, formation: str, possession_share: float,
                       lineup: list[tuple[str, str]]) -> list[tuple[str, str, float]]:
        """Predict passes for a starting XI given as (name, position_slot).

        Each player's passes = team pass budget (from possession) × the
        player's share of the formation, with shares normalised across the XI
        so they allocate the whole budget. No individual player history is
        used — only role, formation, and the possession estimate.
        """
        total = self.team_total_passes(possession_share)
        shares = [self.position_share(formation, slot) for _, slot in lineup]
        s = sum(shares) or 1.0
        out = [(name, slot, sh / s * total) for (name, slot), sh in zip(lineup, shares)]
        return sorted(out, key=lambda x: -x[2])


def load_rows(tournament_keys: list[str], limit: int | None = None) -> list[PlayerMatch]:
    rows: list[PlayerMatch] = []
    for key in tournament_keys:
        cid, sid, name, season = TOURNAMENTS[key]
        rows.extend(statsbomb.load_tournament(cid, sid, name, season, limit=limit))
    return rows

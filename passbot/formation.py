from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from .models import PlayerMatch
from .data import statsbomb
from .backtest import TOURNAMENTS


# Role premiums multiply a player's positional pass estimate to capture the
# extremes within a position — where individual role, not the slot, decides
# volume. Calibrated from World Cup data (e.g. an isolated #9 like Almoez Ali
# made ~14 passes vs the ~22 striker line → ~0.6×; ball-playing CBs and deep
# playmakers sit well above their position line).
ROLE_PREMIUMS = {
    "": 1.00,                # ordinary occupant of the position
    "default": 1.00,
    "lead_cb": 1.05,         # build-up centre-back — only slightly above average
                             # (calibrated to WC2026: Laporte ~100 vs ~104 base,
                             # well below the pivot; the CB does NOT out-pass the
                             # regista, which the old 1.20 wrongly implied)
    "deep_playmaker": 1.18,  # very good deep mid (de Jong 73, Caicedo 60 — ~1.2x
                             # the calibrated DM base)
    "regista": 1.40,         # elite ball-dominant metronome (Rodri 126,
                             # Çalhanoğlu 105 — ~1.5x base, world's best deep
                             # passers do this every game)
    "outlet": 1.15,          # forward/winger who drops in to link play
    "target_man": 0.60,      # isolated striker in a low block — starved of touches
    "runner": 0.72,          # off-ball winger/forward who stays high and chases
}


def role_premium(role: str) -> float:
    return ROLE_PREMIUMS.get(role, 1.0)


# How the OPPONENT's press redistributes passes within a team, at fixed
# possession. Measured from WC data (controlling for possession): a deep block
# lets the build-up recycle freely (CBs +~10%) while starving the lone striker
# (-~15%); a high press does the reverse — the ball skips midfield and is
# played direct to the forwards. Multipliers are relative to a neutral
# opponent and are renormalised so the team's possession budget is preserved —
# press changes *who* touches the ball, not the team total.
# Magnitudes softened after WC2026 calibration (effects were over-stacking).
PRESS_MULT = {
    "low":  {"GK": 0.96, "CB": 1.04, "FB": 1.01, "DM": 1.02, "CM": 1.03,
             "AM": 1.00, "W": 0.98, "ST": 0.88},   # opponent sits in a deep block
    "mid":  {},                                      # neutral (all 1.0)
    "high": {"GK": 1.04, "CB": 0.95, "FB": 0.99, "DM": 0.98, "CM": 0.97,
             "AM": 1.00, "W": 1.02, "ST": 1.12},    # opponent presses high
}

# Team press ratings = mean height (x, 0-120) of a team's defensive actions in
# WC 2018/2022. Higher = presses higher up the pitch. Used to auto-pick the
# opponent's press tier when the opponent is one of these teams.
TEAM_PRESS = {
    "Germany": 61, "Spain": 60, "Canada": 58, "Ecuador": 58, "England": 57,
    "Brazil": 55, "Argentina": 55, "United States": 54, "Netherlands": 53,
    "France": 53, "Portugal": 52, "Japan": 52, "Belgium": 51, "Croatia": 51,
    "Morocco": 50, "Switzerland": 50, "Senegal": 49, "Mexico": 49, "Uruguay": 48,
    "Poland": 48, "Egypt": 47, "Sweden": 46, "Peru": 45, "Qatar": 45,
    "Costa Rica": 45, "Tunisia": 46, "Saudi Arabia": 47, "Iran": 46,
}


# How a team's OWN directness changes its pass volume by position, as a
# fractional change per +10 percentage points of long-ball share above the
# ~20% average. Measured from WC data controlling for possession: a direct
# (long-ball) side's build-up players pass far less (CB -12%/+10pp), wingers
# fall hardest, the striker barely moves, and the keeper passes *more* (he
# launches it). Patient sides are the mirror (negative long% delta -> boost).
# Magnitudes reduced ~40% after WC2026 calibration: the style effects are real
# but compound too hard with the possession curve at the extremes (a patient
# *and* high-possession side like Spain was over-boosted — its CBs hit ~100,
# not the 120+ the stacked multipliers implied).
DIRECTNESS_SENS = {
    "GK": +0.07, "CB": -0.07, "FB": -0.05, "DM": -0.06,
    "CM": -0.07, "AM": -0.08, "W": -0.12, "ST": -0.07,
}

# Team directness = long-ball share (passes > 30yd) in WC 2018/2022. Higher =
# more direct. ~0.20 is average. Used to auto-set a team's style.
TEAM_DIRECTNESS = {
    "Spain": 0.13, "Brazil": 0.14, "Argentina": 0.16, "Netherlands": 0.17,
    "Belgium": 0.17, "United States": 0.17, "Germany": 0.18, "Portugal": 0.18,
    "France": 0.19, "Japan": 0.19, "Croatia": 0.19, "England": 0.20,
    "Mexico": 0.20, "Switzerland": 0.22, "Morocco": 0.21, "Ecuador": 0.21,
    "Uruguay": 0.21, "Qatar": 0.22, "Poland": 0.22, "Senegal": 0.24,
    "Cameroon": 0.25, "Sweden": 0.26, "Tunisia": 0.23, "Iran": 0.29,
    "Saudi Arabia": 0.24, "Australia": 0.23, "Costa Rica": 0.23,
}

AVG_LONG = 0.20

# Per-position calibration to real WC2026 results (187 starters, 9 games). The
# StatsBomb-trained curves nail center-backs and keepers but carry too much
# volume for everyone else — especially strikers (~2x) and wide/attacking
# players. Multipliers = actual/predicted, validated leave-one-game-out
# (MAE 14.5 -> 11.0). Re-derive with calib/calibrate.py as more games arrive.
POS_CALIB = {
    "GK": 0.93, "CB": 1.00, "FB": 0.72, "DM": 0.80,
    "CM": 0.81, "AM": 0.69, "W": 0.68, "ST": 0.52,
}


def directness_factor(position_group: str, long_share: float) -> float:
    """Multiplier on a position's pass estimate for a team's directness."""
    sens = DIRECTNESS_SENS.get(position_group, -0.10)
    return max(0.3, 1.0 + sens * (long_share - AVG_LONG) / 0.10)


def team_directness(team: str, default: float = AVG_LONG) -> float:
    return TEAM_DIRECTNESS.get(team, default)


# Team possession-control ratings = observed share of passes in WC2026 so far.
# A prior for predicting who controls the ball in a future matchup; it sharpens
# as more games (and common opponents) accumulate. Re-derive with calib/.
TEAM_CONTROL = {
    "Spain": 0.74, "Switzerland": 0.70, "Turkey": 0.70, "Netherlands": 0.63,
    "Germany": 0.70, "Belgium": 0.54, "Haiti": 0.53, "Ecuador": 0.52,
    "Tunisia": 0.51, "Brazil": 0.50, "Morocco": 0.50, "Sweden": 0.49,
    "Ivory Coast": 0.48, "Scotland": 0.47, "Egypt": 0.46, "USA": 0.55,
    "Japan": 0.37, "Australia": 0.30, "Qatar": 0.30,
}


def predict_possession(team: str, opponent: str, default: float = 0.5) -> float:
    """Estimate a team's possession share vs an opponent from control ratings.

    Combines both teams' control tendencies: share_A = c_A / (c_A + c_B). With
    one game each this is opponent-confounded, but it's a reasonable prior and
    improves as ratings are averaged over more rounds.
    """
    ca = TEAM_CONTROL.get(team)
    cb = TEAM_CONTROL.get(opponent)
    if ca is None or cb is None:
        return default
    return ca / (ca + cb)


def press_tier(rating: float) -> str:
    """Map a numeric press rating (def-action height) to a tier."""
    if rating >= 55:
        return "high"
    if rating <= 48:
        return "low"
    return "mid"


def team_press_tier(team: str, default: str = "mid") -> str:
    """Press tier for a known team, else the default."""
    r = TEAM_PRESS.get(team)
    return press_tier(r) if r is not None else default


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
    # Per position group: passes ≈ quadratic(possession_share). The curve is
    # convex — center-backs and mids surge against a low block (a parked
    # opponent lets the dominant side recycle the ball endlessly), while
    # strikers and keepers stay nearly flat.
    pos_poss_fit: dict[str, tuple[float, float, float]] = field(default_factory=dict)

    def fit(self, rows: list[PlayerMatch]) -> "FormationModel":
        # Group starters by (formation, team, match) to compute pass shares.
        by_team_match: dict[tuple, list[PlayerMatch]] = defaultdict(list)
        for r in rows:
            if r.is_starter and r.minutes > 0 and r.formation:
                by_team_match[(r.match_id, r.team)].append(r)

        share_acc: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        pos_acc: dict[str, list[float]] = defaultdict(list)
        poss_x, poss_y, match_totals = [], [], []
        # passes-vs-possession samples per position group
        grp_xy: dict[str, tuple[list[float], list[float]]] = defaultdict(lambda: ([], []))
        for r in rows:
            if r.is_starter and r.minutes >= 80:
                gx, gy = grp_xy[r.position_group]
                gx.append(r.team_possession_share)
                gy.append(r.passes)

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

        for grp, (gx, gy) in grp_xy.items():
            if len(gx) >= 15:
                c2, c1, c0 = np.polyfit(gx, gy, 2)
                self.pos_poss_fit[grp] = (float(c2), float(c1), float(c0))
        return self

    def passes_for_group(self, position_group: str, possession_share: float) -> float:
        """Expected passes for a full-match starter of this position group at
        the given team possession — a convex per-position curve (center-backs
        and mids surge at high possession, strikers stay flat), scaled by a
        real-data calibration factor (see POS_CALIB)."""
        coeffs = self.pos_poss_fit.get(position_group, (0.0, 0.0, 40.0))
        base = max(0.0, float(np.polyval(coeffs, possession_share)))
        return base * POS_CALIB.get(position_group, 1.0)

    def team_total_passes(self, possession_share: float) -> float:
        return max(50.0, self.poss_intercept + self.poss_slope * possession_share)

    def position_share(self, formation: str, position: str) -> float:
        f = self.share.get(formation, {})
        if position in f:
            return f[position]
        # Fall back to the pooled cross-formation share for that position.
        return self.share_by_pos.get(position, 1.0 / 11)

    def predict_lineup(self, possession_share: float, lineup: list[tuple],
                       opp_press: str = "mid",
                       directness: float = AVG_LONG) -> list[tuple[str, str, float]]:
        """Predict passes for a starting XI.

        Each entry is (name, position_group) or (name, position_group, role),
        where role is a key in ROLE_PREMIUMS (e.g. "lead_cb", "target_man") or
        a raw float multiplier. The base comes from the position's convex
        possession curve; the role premium captures the within-position
        extremes — where individual role, not the slot, decides volume.

        `directness` is the team's own long-ball share (~0.20 average). A
        direct side makes fewer passes at the same possession — its build-up
        players and wingers fall most, the keeper rises. This changes the team
        TOTAL (unlike press, it is not renormalised).

        `opp_press` ("low"/"mid"/"high") is the OPPONENT's defensive style: a
        low block pools passes at the build-up players, a high press skips the
        ball to the forwards. It redistributes who touches the ball while
        preserving the (post-directness) possession budget.
        """
        base = []
        for entry in lineup:
            name, grp = entry[0], entry[1]
            role = entry[2] if len(entry) > 2 else 1.0
            premium = role if isinstance(role, (int, float)) else role_premium(role)
            val = self.passes_for_group(grp, possession_share) * premium
            val *= directness_factor(grp, directness)  # team style changes the total
            base.append((name, grp, val))

        mult = PRESS_MULT.get(opp_press, {})
        if mult:
            adjusted = [(n, g, v * mult.get(g, 1.0)) for n, g, v in base]
            # Renormalise so the team total (possession budget) is unchanged —
            # press only moves passes between players, not the team total.
            total_base = sum(v for _, _, v in base)
            total_adj = sum(v for _, _, v in adjusted) or 1.0
            scale = total_base / total_adj
            base = [(n, g, v * scale) for n, g, v in adjusted]

        return sorted(base, key=lambda x: -x[2])


def load_rows(tournament_keys: list[str], limit: int | None = None) -> list[PlayerMatch]:
    rows: list[PlayerMatch] = []
    for key in tournament_keys:
        cid, sid, name, season = TOURNAMENTS[key]
        rows.extend(statsbomb.load_tournament(cid, sid, name, season, limit=limit))
    return rows

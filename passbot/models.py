from __future__ import annotations

from dataclasses import dataclass, field


# Coarse position groups, ordered roughly from most to least pass-involved.
# StatsBomb has ~25 granular positions; we collapse them into these buckets
# because pass volume tracks the group far more than the exact slot.
POSITION_GROUPS = ["GK", "CB", "FB", "DM", "CM", "AM", "W", "ST"]


@dataclass
class PlayerMatch:
    """One player's involvement in one match — the unit of training data.

    `passes` is the target we ultimately predict. Everything else is either a
    feature or an identifier used to build features (rolling form, opponent,
    team possession share).
    """

    match_id: int
    competition: str
    season: str
    date: str

    player_id: int
    player_name: str
    team: str
    opponent: str
    position: str            # granular StatsBomb position name
    position_group: str      # one of POSITION_GROUPS
    is_starter: bool

    minutes: float
    passes: int              # passes attempted (the target)
    passes_completed: int

    # Match-level context, duplicated onto every player row for convenience.
    team_passes: int = 0     # total passes by this player's team
    opponent_passes: int = 0

    @property
    def passes_per_90(self) -> float:
        if self.minutes <= 0:
            return 0.0
        return self.passes * 90.0 / self.minutes

    @property
    def team_possession_share(self) -> float:
        """Fraction of in-match passes made by this player's team — a proxy
        for which side controlled the ball."""
        total = self.team_passes + self.opponent_passes
        if total <= 0:
            return 0.5
        return self.team_passes / total


@dataclass
class Prediction:
    player_id: int
    player_name: str
    team: str
    position_group: str
    expected_minutes: float
    predicted_passes_per_90: float

    @property
    def predicted_passes(self) -> float:
        return self.predicted_passes_per_90 * self.expected_minutes / 90.0

    # Filled in after the match is played, for forward-test grading.
    actual_passes: int | None = None

    @property
    def error(self) -> float | None:
        if self.actual_passes is None:
            return None
        return self.predicted_passes - self.actual_passes

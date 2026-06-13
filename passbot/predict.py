from __future__ import annotations

import pickle
from pathlib import Path

import pandas as pd

from .features import FeatureBuilder
from .model import PassModel
from .models import Prediction
from .data import statsbomb
from .backtest import TOURNAMENTS


class Predictor:
    """A trained model plus the history needed to feature-ise new lineups.

    Train it on past tournaments, persist it, then feed it confirmed World Cup
    lineups to get per-player pass predictions for forward-testing.
    """

    def __init__(self) -> None:
        self.model = PassModel()
        self.features = FeatureBuilder()

    def train(self, tournament_keys: list[str], limit: int | None = None) -> int:
        frames = []
        for key in tournament_keys:
            cid, sid, name, season = TOURNAMENTS[key]
            rows = statsbomb.load_tournament(cid, sid, name, season, limit=limit)
            frames.append(self.features.build(rows, learn=True))
        df = pd.concat(frames, ignore_index=True)
        self.model.fit(df)
        return len(df)

    def predict_lineup(self, lineup: list[dict], opponent_by_team: dict[str, str]) -> list[Prediction]:
        """Predict passes for a lineup.

        Each lineup entry is a dict: name, position_group, team, and optionally
        `starter` (default True) and `expected_minutes` (default: the player's
        historical average, or 70 for unknowns).
        """
        rows = []
        specs = []
        for p in lineup:
            team = p["team"]
            opp = opponent_by_team.get(team, p.get("opponent", ""))
            starter = p.get("starter", True)
            feats = self.features.live_features(
                p["name"], p["position_group"], team, opp, starter)
            rows.append(feats)
            specs.append((p, feats, opp))

        df = pd.DataFrame.from_records(rows)
        p90 = self.model.predict_p90(df)

        out: list[Prediction] = []
        for (p, feats, opp), rate in zip(specs, p90):
            exp_min = p.get("expected_minutes")
            if exp_min is None:
                exp_min = feats["player_rolling_minutes"] if p.get("starter", True) else 20.0
            out.append(Prediction(
                player_id=0,
                player_name=p["name"],
                team=p["team"],
                position_group=p["position_group"],
                expected_minutes=float(exp_min),
                predicted_passes_per_90=float(rate),
            ))
        out.sort(key=lambda x: x.predicted_passes, reverse=True)
        return out

    def save(self, path: str | Path) -> None:
        Path(path).write_bytes(pickle.dumps(self))

    @staticmethod
    def load(path: str | Path) -> "Predictor":
        return pickle.loads(Path(path).read_bytes())

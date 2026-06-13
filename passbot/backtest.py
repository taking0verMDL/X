from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .features import FeatureBuilder
from .model import PassModel
from .data import statsbomb

# (competition_id, season_id, name, season) for the tournaments we can use.
TOURNAMENTS = {
    "wc2018": (43, 3, "FIFA World Cup", "2018"),
    "wc2022": (43, 106, "FIFA World Cup", "2022"),
    "euro2024": (55, 282, "UEFA Euro", "2024"),
    "copa2024": (223, 282, "Copa America", "2024"),
}


@dataclass
class BacktestResult:
    n: int
    model_mae: float          # MAE on total passes, model + actual minutes
    model_mae_estmin: float   # MAE on total passes, model + estimated minutes
    baseline_mae: float       # MAE from naive career-average baseline
    model_corr: float
    df: pd.DataFrame

    def summary(self) -> str:
        lift = (self.baseline_mae - self.model_mae_estmin) / self.baseline_mae * 100
        return (
            f"player-matches evaluated : {self.n}\n"
            f"baseline MAE (career avg): {self.baseline_mae:5.2f} passes\n"
            f"model MAE (est. minutes) : {self.model_mae_estmin:5.2f} passes  "
            f"({lift:+.1f}% vs baseline)\n"
            f"model MAE (true minutes) : {self.model_mae:5.2f} passes  "
            f"(rate model only)\n"
            f"correlation (pred vs act): {self.model_corr:5.3f}"
        )


def run_backtest(train_keys: list[str], test_key: str,
                 limit: int | None = None) -> BacktestResult:
    """Train on one or more tournaments, evaluate on a held-out one."""
    fb = FeatureBuilder()

    train_frames = []
    for key in train_keys:
        cid, sid, name, season = TOURNAMENTS[key]
        rows = statsbomb.load_tournament(cid, sid, name, season, limit=limit)
        train_frames.append(fb.build(rows, learn=True))
    train_df = pd.concat(train_frames, ignore_index=True)

    cid, sid, name, season = TOURNAMENTS[test_key]
    test_rows = statsbomb.load_tournament(cid, sid, name, season, limit=limit)
    test_df = fb.build(test_rows, learn=True)

    model = PassModel()
    model.fit(train_df)

    played = test_df[test_df["minutes"] > 0].copy()
    actual = played["target_passes"].to_numpy()

    # Model predictions: rate × actual minutes (isolates rate quality) and
    # rate × estimated minutes (realistic — minutes aren't known pre-match).
    pred_true_min = model.predict_passes(played)
    est_minutes = played["player_rolling_minutes"].to_numpy()
    pred_est_min = model.predict_passes(played, minutes=est_minutes)

    # Baseline: assume the player repeats their rolling career pass rate over
    # their typical minutes. This is the "no model" strawman to beat.
    baseline = played["player_rolling_p90"].to_numpy() * est_minutes / 90.0

    played["predicted_passes"] = pred_est_min
    return BacktestResult(
        n=len(played),
        model_mae=float(np.mean(np.abs(pred_true_min - actual))),
        model_mae_estmin=float(np.mean(np.abs(pred_est_min - actual))),
        baseline_mae=float(np.mean(np.abs(baseline - actual))),
        model_corr=float(np.corrcoef(pred_est_min, actual)[0, 1]),
        df=played,
    )

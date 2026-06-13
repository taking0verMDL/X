from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from .features import FEATURE_COLUMNS


class PassModel:
    """Predicts a player's passes for a match.

    The model learns *passes per 90 minutes* — a rate that's stable and well
    explained by role and form — and total passes are recovered by scaling by
    expected minutes. Splitting it this way keeps minutes uncertainty (rotation,
    red cards, blowouts) out of the learnable part.
    """

    def __init__(self) -> None:
        self.regressor = HistGradientBoostingRegressor(
            max_iter=300,
            learning_rate=0.05,
            max_depth=4,
            l2_regularization=1.0,
            min_samples_leaf=20,
            random_state=0,
        )
        self.trained = False

    def fit(self, df: pd.DataFrame) -> None:
        # Only learn from players who actually took the field.
        df = df[df["minutes"] > 0]
        X = df[FEATURE_COLUMNS].to_numpy()
        y = df["target_p90"].to_numpy()
        # Weight by minutes so a 90-minute performance counts more than a
        # 5-minute cameo when fitting the rate.
        self.regressor.fit(X, y, sample_weight=df["minutes"].to_numpy())
        self.trained = True

    def predict_p90(self, df: pd.DataFrame) -> np.ndarray:
        preds = self.regressor.predict(df[FEATURE_COLUMNS].to_numpy())
        return np.clip(preds, 0.0, None)

    def predict_passes(self, df: pd.DataFrame, minutes: np.ndarray | None = None) -> np.ndarray:
        """Predicted total passes = predicted p90 × expected minutes / 90.

        If `minutes` is None the match's actual minutes column is used (handy
        for isolating the rate model during backtests).
        """
        p90 = self.predict_p90(df)
        mins = minutes if minutes is not None else df["minutes"].to_numpy()
        return p90 * mins / 90.0

    def save(self, path: str | Path) -> None:
        Path(path).write_bytes(pickle.dumps(self))

    @staticmethod
    def load(path: str | Path) -> "PassModel":
        return pickle.loads(Path(path).read_bytes())

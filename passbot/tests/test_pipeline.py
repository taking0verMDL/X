"""Offline tests for the passbot pipeline — no network required.

These exercise the feature/model logic on synthetic player-matches so the
core math (leak-free rolling features, rate -> total passes, name matching)
is verified without downloading StatsBomb data.
"""
from __future__ import annotations

import pandas as pd

from passbot.features import FeatureBuilder, _norm_name
from passbot.model import PassModel
from passbot.models import PlayerMatch, Prediction


def _pm(match_id, pid, name, team, opp, group, minutes, passes, tp, op, date):
    return PlayerMatch(
        match_id=match_id, competition="T", season="1", date=date,
        player_id=pid, player_name=name, team=team, opponent=opp,
        position=group, position_group=group, is_starter=True,
        minutes=minutes, passes=passes, passes_completed=passes,
        team_passes=tp, opponent_passes=op,
    )


def test_passes_per_90_and_possession_share():
    pm = _pm(1, 1, "A", "X", "Y", "CB", 45, 30, 100, 50, "2020-01-01")
    assert pm.passes_per_90 == 60.0           # 30 passes in 45 min -> 60/90
    assert abs(pm.team_possession_share - 100 / 150) < 1e-9


def test_features_are_leak_free():
    # Two matches for the same player; the first match must NOT see its own
    # pass count in player_rolling_p90 (cold start -> position prior).
    rows = [
        _pm(1, 1, "A", "X", "Y", "CB", 90, 90, 100, 80, "2020-01-01"),
        _pm(2, 1, "A", "X", "Z", "CB", 90, 50, 100, 80, "2020-01-02"),
    ]
    df = FeatureBuilder().build(rows).sort_values("match_id")
    first, second = df.iloc[0], df.iloc[1]
    # Match 1: no history -> falls back to the CB prior (62), not 90.
    assert first["player_matches_seen"] == 0
    assert first["player_rolling_p90"] == 62.0
    # Match 2: now sees match 1's 90 passes/90.
    assert second["player_matches_seen"] == 1
    assert second["player_rolling_p90"] == 90.0


def test_model_trains_and_predicts_total_from_rate():
    rows = []
    for i in range(60):
        # CBs pass a lot, strikers little — a signal the model should learn.
        rows.append(_pm(i, i, f"cb{i}", "X", "Y", "CB", 90, 80, 200, 100, "2020-01-01"))
        rows.append(_pm(i, 100 + i, f"st{i}", "X", "Y", "ST", 90, 20, 200, 100, "2020-01-01"))
    df = FeatureBuilder().build(rows)
    model = PassModel()
    model.fit(df)
    p90 = model.predict_p90(df)
    cb_pred = p90[df["position_group"].to_numpy() == "CB"].mean()
    st_pred = p90[df["position_group"].to_numpy() == "ST"].mean()
    assert cb_pred > st_pred
    # Total passes scale with minutes: half the minutes -> half the passes.
    half = model.predict_passes(df.head(1), minutes=pd.Series([45.0]).to_numpy())
    full = model.predict_passes(df.head(1), minutes=pd.Series([90.0]).to_numpy())
    assert abs(half[0] * 2 - full[0]) < 1e-6


def test_name_normalisation_matches_accents():
    assert _norm_name("Álvaro Morata") == _norm_name("Alvaro  Morata")


def test_prediction_total_and_error():
    p = Prediction(player_id=1, player_name="A", team="X", position_group="CB",
                   expected_minutes=90, predicted_passes_per_90=60)
    assert p.predicted_passes == 60
    p.actual_passes = 50
    assert p.error == 10

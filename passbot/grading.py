from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .features import _norm_name


def grade(result: dict, actuals: dict[str, float]) -> dict:
    """Score saved predictions against actual pass counts.

    `actuals` maps player name -> actual passes (names matched accent- and
    case-insensitively). Returns overall MAE and bias plus a per-player table,
    so we can see not just how far off we were but in which direction.
    """
    norm_actuals = {_norm_name(k): v for k, v in actuals.items()}
    rows = []
    for team in result["teams"]:
        for p in team["predictions"]:
            actual = norm_actuals.get(_norm_name(p["player"]))
            if actual is None:
                continue
            pred = p["predicted_passes"]
            rows.append({
                "player": p["player"], "team": team["name"], "pos": p["pos"],
                "predicted": pred, "actual": actual, "error": pred - actual,
            })

    if not rows:
        return {"n": 0, "rows": [], "mae": None, "bias": None, "corr": None}

    err = np.array([r["error"] for r in rows])
    pred = np.array([r["predicted"] for r in rows])
    act = np.array([r["actual"] for r in rows])
    corr = float(np.corrcoef(pred, act)[0, 1]) if len(rows) > 1 and act.std() > 0 else None
    return {
        "n": len(rows),
        "rows": sorted(rows, key=lambda r: -abs(r["error"])),
        "mae": float(np.mean(np.abs(err))),
        "bias": float(np.mean(err)),   # +ve => we over-predicted on average
        "corr": corr,
    }


def load_actuals(path: str | Path) -> dict[str, float]:
    """Load actuals from JSON ({name: passes}) or CSV (name,passes)."""
    path = Path(path)
    text = path.read_text()
    if path.suffix.lower() == ".json":
        return {k: float(v) for k, v in json.loads(text).items()}
    out: dict[str, float] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("name"):
            continue
        name, _, passes = line.rpartition(",")
        out[name.strip()] = float(passes)
    return out


def format_grade(report: dict) -> str:
    if report["n"] == 0:
        return "No matching players between predictions and actuals."
    lines = [
        f"graded {report['n']} players",
        f"MAE  : {report['mae']:.2f} passes",
        f"bias : {report['bias']:+.2f} passes  "
        f"({'over' if report['bias'] > 0 else 'under'}-predicted on average)",
    ]
    if report["corr"] is not None:
        lines.append(f"corr : {report['corr']:.3f}")
    lines.append("")
    lines.append(f"{'player':<18}{'pos':<5}{'pred':>6}{'actual':>8}{'error':>8}")
    for r in report["rows"]:
        lines.append(f"{r['player']:<18}{r['pos']:<5}{r['predicted']:>6.0f}"
                     f"{r['actual']:>8.0f}{r['error']:>+8.0f}")
    return "\n".join(lines)

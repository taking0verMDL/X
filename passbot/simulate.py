from __future__ import annotations

import json
from pathlib import Path

import yaml

from .formation import FormationModel, load_rows, team_press_tier


def simulate_match(spec_path: str | Path) -> dict:
    """Run a match spec (see matches/*.yaml) and return predictions per team.

    Returns a dict: {match, teams: [{name, possession, predictions: [
    {player, pos, predicted_passes}]}]}. Predictions are also the thing we
    later grade against actuals.

    Each team's prediction uses the OPPONENT's press tier: a team's own
    `press` field ("low"/"mid"/"high") in the spec, else looked up from the
    known team-press table, decides how it presses — and that drives the
    other team's pass distribution.
    """
    spec = yaml.safe_load(Path(spec_path).read_text())
    fm = FormationModel().fit(load_rows(spec.get("train", ["wc2018", "wc2022"])))

    teams = spec["teams"]
    # Each team's press style (how it defends), used as the opponent's
    # context for the other team.
    press = [t.get("press") or team_press_tier(t["name"]) for t in teams]

    out_teams = []
    for i, team in enumerate(teams):
        opp_press = press[1 - i] if len(teams) == 2 else "mid"
        lineup = [(p["name"], p["pos"], p.get("role", 1.0)) for p in team["lineup"]]
        preds = fm.predict_lineup(float(team["possession"]), lineup, opp_press=opp_press)
        out_teams.append({
            "name": team["name"],
            "formation": team.get("formation", ""),
            "possession": float(team["possession"]),
            "opp_press": opp_press,
            "predictions": [
                {"player": n, "pos": g, "predicted_passes": round(p, 1)}
                for n, g, p in preds
            ],
        })
    return {"match": spec.get("match", "match"), "teams": out_teams}


def save_predictions(result: dict, path: str | Path) -> None:
    Path(path).write_text(json.dumps(result, indent=2, ensure_ascii=False))


def format_result(result: dict) -> str:
    lines = [result["match"], ""]
    for team in result["teams"]:
        press = team.get("opp_press", "mid")
        lines.append(f"=== {team['name']}  {team['formation']}  "
                     f"~{team['possession']*100:.0f}% possession  "
                     f"(vs {press} press) ===")
        lines.append(f"{'player':<18}{'pos':<5}{'passes':>7}")
        for p in team["predictions"]:
            lines.append(f"{p['player']:<18}{p['pos']:<5}{p['predicted_passes']:>7.0f}")
        lines.append("")
    return "\n".join(lines)

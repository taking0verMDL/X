from __future__ import annotations

import json
from pathlib import Path

import requests

from ..models import PlayerMatch

# StatsBomb's free, open event data. No key required; please be polite about
# request volume — that's what the on-disk cache below is for.
BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "statsbomb"

# Map StatsBomb's granular positions onto our coarse groups (see models.py).
_POSITION_MAP = {
    "Goalkeeper": "GK",
    "Right Back": "FB", "Left Back": "FB",
    "Right Wing Back": "FB", "Left Wing Back": "FB",
    "Center Back": "CB", "Right Center Back": "CB", "Left Center Back": "CB",
    "Right Defensive Midfield": "DM", "Center Defensive Midfield": "DM",
    "Left Defensive Midfield": "DM",
    "Right Center Midfield": "CM", "Center Midfield": "CM",
    "Left Center Midfield": "CM",
    "Right Midfield": "CM", "Left Midfield": "CM",
    "Right Attacking Midfield": "AM", "Center Attacking Midfield": "AM",
    "Left Attacking Midfield": "AM", "Secondary Striker": "AM",
    "Right Wing": "W", "Left Wing": "W",
    "Center Forward": "ST", "Right Center Forward": "ST", "Left Center Forward": "ST",
}


def _group(position: str | None) -> str:
    if not position:
        return "CM"
    return _POSITION_MAP.get(position, "CM")


def _fetch_json(path: str) -> list | dict:
    """Fetch a StatsBomb JSON file, caching it on disk forever (the open-data
    archive is immutable for completed matches)."""
    cache_file = CACHE_DIR / path
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    resp = requests.get(f"{BASE}/{path}", timeout=60)
    resp.raise_for_status()
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(resp.text)
    return resp.json()


def list_matches(competition_id: int, season_id: int) -> list[dict]:
    return _fetch_json(f"matches/{competition_id}/{season_id}.json")


def _minutes_by_player(events: list[dict]) -> dict[int, float]:
    """Estimate minutes played for every player from the event stream.

    Starters run from kickoff to their sub-off (or full time); substitutes
    run from their entry to their own sub-off (or full time). Match length is
    taken as the last event minute so stoppage time is included.
    """
    match_end = max((e.get("minute", 0) for e in events), default=90)

    on: dict[int, float] = {}   # player_id -> minute they were on the pitch
    off: dict[int, float] = {}  # player_id -> minute they left

    for e in events:
        etype = e.get("type", {}).get("name")
        if etype == "Starting XI":
            for p in e.get("tactics", {}).get("lineup", []):
                pid = p.get("player", {}).get("id")
                if pid is not None:
                    on[pid] = 0.0
        elif etype == "Substitution":
            minute = e.get("minute", match_end)
            off_id = e.get("player", {}).get("id")
            if off_id is not None:
                off[off_id] = minute
            repl = e.get("substitution", {}).get("replacement", {})
            on_id = repl.get("id")
            if on_id is not None:
                on[on_id] = minute

    minutes: dict[int, float] = {}
    for pid, start in on.items():
        end = off.get(pid, match_end)
        minutes[pid] = max(0.0, end - start)
    return minutes


def load_match(match: dict, competition: str, season: str) -> list[PlayerMatch]:
    """Turn one match into a list of PlayerMatch rows (one per player who
    touched the ball)."""
    match_id = match["match_id"]
    date = match.get("match_date", "")
    home = match["home_team"]["home_team_name"]
    away = match["away_team"]["away_team_name"]

    events = _fetch_json(f"events/{match_id}.json")
    minutes = _minutes_by_player(events)

    # Aggregate passes and capture each player's primary position / team.
    agg: dict[int, dict] = {}
    team_passes = {home: 0, away: 0}
    starters: set[int] = set()
    formation_by_team: dict[str, str] = {}

    for e in events:
        if e.get("type", {}).get("name") == "Starting XI":
            team = e.get("team", {}).get("name", "")
            formation_by_team[team] = str(e.get("tactics", {}).get("formation", ""))
            for p in e.get("tactics", {}).get("lineup", []):
                pid = p.get("player", {}).get("id")
                if pid is not None:
                    starters.add(pid)

    for e in events:
        player = e.get("player")
        if not player:
            continue
        pid = player["id"]
        team = e.get("team", {}).get("name", "")
        row = agg.setdefault(pid, {
            "name": player.get("name", ""),
            "team": team,
            "position": e.get("position", {}).get("name"),
            "passes": 0,
            "completed": 0,
        })
        # Keep the first non-null position we see for the player.
        if row["position"] is None and e.get("position"):
            row["position"] = e["position"].get("name")

        if e.get("type", {}).get("name") == "Pass":
            row["passes"] += 1
            if team in team_passes:
                team_passes[team] += 1
            # A pass with no 'outcome' is a completed pass in StatsBomb's schema.
            if "outcome" not in e.get("pass", {}):
                row["completed"] += 1

    rows: list[PlayerMatch] = []
    for pid, r in agg.items():
        team = r["team"]
        opponent = away if team == home else home
        rows.append(PlayerMatch(
            match_id=match_id,
            competition=competition,
            season=season,
            date=date,
            player_id=pid,
            player_name=r["name"],
            team=team,
            opponent=opponent,
            position=r["position"] or "",
            position_group=_group(r["position"]),
            is_starter=pid in starters,
            minutes=minutes.get(pid, 0.0),
            passes=r["passes"],
            passes_completed=r["completed"],
            team_passes=team_passes.get(team, 0),
            opponent_passes=team_passes.get(opponent, 0),
            formation=formation_by_team.get(team, ""),
        ))
    return rows


def load_tournament(competition_id: int, season_id: int,
                    competition: str, season: str,
                    limit: int | None = None) -> list[PlayerMatch]:
    """Load every player-match row for a whole tournament."""
    matches = list_matches(competition_id, season_id)
    matches.sort(key=lambda m: m.get("match_date", ""))
    if limit:
        matches = matches[:limit]

    rows: list[PlayerMatch] = []
    for m in matches:
        rows.extend(load_match(m, competition, season))
    return rows

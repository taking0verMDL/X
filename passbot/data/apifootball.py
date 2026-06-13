from __future__ import annotations

import os

import requests

# API-Football (api-sports.io) provides fixtures, confirmed lineups, and
# post-match player stats including passes. The free tier is enough to grade a
# handful of World Cup games. Set the key in the environment:
#     export API_FOOTBALL_KEY=...
BASE = "https://v3.football.api-sports.io"
KEY_ENV = "API_FOOTBALL_KEY"


class ApiFootballError(Exception):
    pass


def _headers() -> dict:
    key = os.environ.get(KEY_ENV)
    if not key:
        raise ApiFootballError(
            f"No API key. Set ${KEY_ENV} or use --mock for a sample lineup.")
    return {"x-apisports-key": key}


def _get(path: str, params: dict) -> dict:
    resp = requests.get(f"{BASE}/{path}", headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_lineup(fixture_id: int) -> list[dict]:
    """Fetch a confirmed lineup as our internal spec. Maps API-Football
    position codes (G/D/M/F) onto coarse position groups."""
    data = _get("fixtures/lineups", {"fixture": fixture_id})
    out: list[dict] = []
    for side in data.get("response", []):
        team = side.get("team", {}).get("name", "")
        for p in side.get("startXI", []):
            player = p.get("player", {})
            out.append({
                "name": player.get("name", ""),
                "position_group": _map_pos(player.get("pos")),
                "team": team,
                "starter": True,
            })
    return out


def _map_pos(code: str | None) -> str:
    # API-Football only exposes broad codes on lineups; refine with the model's
    # position priors as needed.
    return {"G": "GK", "D": "CB", "M": "CM", "F": "ST"}.get(code or "", "CM")


def mock_lineup() -> tuple[list[dict], dict[str, str]]:
    """A realistic sample matchup for demoing predictions offline: Spain vs
    Germany, two possession-heavy sides. Names match StatsBomb history so the
    player-form lookups actually fire."""
    spain = [
        ("Unai Simón Mendibil", "GK"), ("Daniel Carvajal Ramos", "FB"),
        ("Aymeric Laporte", "CB"), ("Pau Francisco Torres", "CB"),
        ("Jordi Alba Ramos", "FB"), ("Sergio Busquets i Burgos", "DM"),
        ("Rodrigo Hernández Cascante", "CM"), ("Pedro González López", "CM"),
        ("Ferran Torres García", "W"), ("Álvaro Borja Morata Martín", "ST"),
        ("Marco Asensio Willemsen", "W"),
    ]
    germany = [
        ("Manuel Neuer", "GK"), ("Joshua Kimmich", "FB"),
        ("Antonio Rüdiger", "CB"), ("Niklas Süle", "CB"),
        ("David Raum", "FB"), ("İlkay Gündoğan", "CM"),
        ("Leon Goretzka", "CM"), ("Jamal Musiala", "AM"),
        ("Serge Gnabry", "W"), ("Kai Havertz", "ST"),
        ("Thomas Müller", "AM"),
    ]
    lineup = [{"name": n, "position_group": g, "team": "Spain", "starter": True}
              for n, g in spain]
    lineup += [{"name": n, "position_group": g, "team": "Germany", "starter": True}
               for n, g in germany]
    opponents = {"Spain": "Germany", "Germany": "Spain"}
    return lineup, opponents

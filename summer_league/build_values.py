"""Derive per-player SL values from advanced stats and write them into the
roster CSV's `value` column.

Keeps the tier system as the *baseline* (same 0-10 scale, same anchors) and
lets each player's actual production move them off it:

- NBA returners  -> 2025-26 NBA BPM (basketball-reference), weighted by
  minutes played. Anchor: a young NBA rotation player (BPM ~ -2) = 8.0.
- 2026 rookies   -> final college season BPM (barttorvik), age-adjusted
  (older college producers translate worse), blended 50/50 with the
  draft-pedigree value: scouts know things box scores don't.
- 2025 grads now in the G-League -> their final college BPM at a discount.
- No stats found (internationals, multi-year G-League vets) -> keep the
  tier/pedigree value already computed by the model.

Usage:  python -m summer_league.build_values [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from datetime import date
from pathlib import Path

from .model import Player, TIER_VALUES, load_rosters

DATA = Path(__file__).parent / "data"
ROSTERS = Path(__file__).parent / "rosters_2026.csv"

# --- conversion constants -------------------------------------------------

NBA_ANCHOR_VALUE = 8.0      # SL value of a BPM=-2 young NBA rotation player
NBA_ANCHOR_BPM = -2.0
NBA_SLOPE = 0.45            # SL points per NBA BPM point
NBA_CLAMP = (5.5, 10.5)
NBA_FULL_CONF_MP = 800      # NBA minutes for full confidence in the stat
NBA_MAX_WEIGHT = 0.75       # even at full minutes, keep 25% pedigree: BPM
                            # punishes inefficient rookies who still eat in SL

COL26_INTERCEPT, COL26_SLOPE = 3.2, 0.42   # SL value from age-adj college BPM
COL26_CLAMP = (2.0, 9.5)
COL26_BLEND = 0.5           # stat share for the current draft class
COL25_INTERCEPT, COL25_SLOPE = 3.0, 0.36   # a year removed: bigger discount
COL25_CLAMP = (2.0, 7.5)
COL25_BLEND = 0.6
COL_FULL_CONF_MIN = 450     # college minutes for full confidence
AGE_ADJ_PER_YEAR = 0.5      # BPM haircut per year older than 19.5 at draft
AGE_BASELINE = 19.5

ROOKIE_TIERS = {"lottery_rookie", "first_round_rookie",
                "second_round_rookie", "undrafted_rookie"}

# roster name -> stats-source name, for spellings the normalizer can't bridge
ALIASES = {
    "cam boozer": "cameron boozer",
}

# lookalike Cyrillic letters that appear in source data (e.g. bbref's "Dёmin")
CYRILLIC = str.maketrans("ёеа", "eea")


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name.translate(CYRILLIC))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[.'’-]", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", s)
    return re.sub(r"\s+", " ", s).strip()


def load_college(path: Path) -> dict[str, dict]:
    """Best row per normalized name (most minutes wins on duplicates)."""
    table: dict[str, dict] = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        try:
            row = {"bpm": float(r["bpm"]), "gp": float(r["gp"] or 0),
                   "mpg": float(r["mpg"] or 0), "birthdate": r["birthdate"]}
        except ValueError:
            continue
        row["min"] = row["gp"] * row["mpg"]
        k = norm(r["player"])
        if k not in table or row["min"] > table[k]["min"]:
            table[k] = row
    return table


def load_nba(path: Path) -> dict[str, dict]:
    return {norm(r["player"]): {"bpm": float(r["bpm"]), "mp": float(r["mp"])}
            for r in csv.DictReader(open(path, encoding="utf-8"))}


def draft_age(birthdate: str) -> float | None:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", birthdate or "")
    if not m:
        return None
    y, mo, d = map(int, m.groups())
    return (date(2026, 6, 24) - date(y, mo, d)).days / 365.25


def pedigree_value(p: Player) -> float:
    """The model's tier/pick/experience value, ignoring any manual override."""
    clone = Player(team=p.team, name=p.name, tier=p.tier, pos=p.pos, age=p.age,
                   draft_pick=p.draft_pick, nba_gp=p.nba_gp, nba_mpg=p.nba_mpg,
                   adj=0.0, out=p.out)
    return clone.value


def college_value(stat: dict, intercept: float, slope: float,
                  clamp: tuple[float, float], blend: float,
                  base: float) -> float:
    age = draft_age(stat["birthdate"])
    adj_bpm = stat["bpm"]
    if age is not None:
        adj_bpm -= AGE_ADJ_PER_YEAR * max(0.0, age - AGE_BASELINE)
    sl = min(clamp[1], max(clamp[0], intercept + slope * adj_bpm))
    w = blend * min(1.0, stat["min"] / COL_FULL_CONF_MIN)
    return w * sl + (1 - w) * base


def build(dry_run: bool = False) -> None:
    players = load_rosters(ROSTERS)
    nba = load_nba(DATA / "nba_2026.csv")
    col26 = load_college(DATA / "college_2026.csv")
    col25 = load_college(DATA / "college_2025.csv")

    values: dict[tuple[str, str], float] = {}
    hits = {"nba": 0, "college_2026": 0, "college_2025": 0, "none": 0}
    report = []

    for p in players:
        k = ALIASES.get(norm(p.name), norm(p.name))
        base = pedigree_value(p)
        src, val = "none", None

        if k in nba and nba[k]["mp"] >= 100:
            s = nba[k]
            sl = NBA_ANCHOR_VALUE + NBA_SLOPE * (s["bpm"] - NBA_ANCHOR_BPM)
            sl = min(NBA_CLAMP[1], max(NBA_CLAMP[0], sl))
            w = NBA_MAX_WEIGHT * min(1.0, s["mp"] / NBA_FULL_CONF_MP)
            val, src = w * sl + (1 - w) * base, "nba"
        elif p.tier in ROOKIE_TIERS and k in col26 and col26[k]["min"] >= 100:
            val = college_value(col26[k], COL26_INTERCEPT, COL26_SLOPE,
                                COL26_CLAMP, COL26_BLEND, base)
            src = "college_2026"
        elif k in col25 and col25[k]["min"] >= 100:
            val = college_value(col25[k], COL25_INTERCEPT, COL25_SLOPE,
                                COL25_CLAMP, COL25_BLEND, base)
            src = "college_2025"

        hits[src] += 1
        if val is not None:
            values[(p.team, p.name)] = round(val, 1)
            if abs(val - base) >= 1.0:
                report.append((p.team, p.name, base, val, src))

    print({k: v for k, v in hits.items()})
    print("\nBiggest moves vs pedigree (>=1.0):")
    for t, n, b, v, s in sorted(report, key=lambda r: r[3] - r[2]):
        print(f"  {v - b:+.1f}  {n} ({t}) {b:.1f} -> {v:.1f} [{s}]")

    if dry_run:
        return

    rows = list(csv.DictReader(open(ROSTERS, encoding="utf-8")))
    for r in rows:
        v = values.get((r["team"], r["player"]))
        if v is not None:
            r["value"] = v
    cols = list(rows[0].keys())
    with open(ROSTERS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {len(values)} stat-derived values to {ROSTERS}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    build(ap.parse_args().dry_run)

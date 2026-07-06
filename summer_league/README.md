# Summer League Power Ratings

A pedigree-based power ratings model for NBA Summer League. SL games are a
tiny, noisy sample, so the model rates teams from *who is on the floor* —
draft pedigree, NBA experience, contract status — rather than from game
results. Each player gets a value in "SL impact points" (~0–10); a team's
rating is a minutes-weighted average of its rotation, expressed in **points
vs. an average SL team**, so the difference between two ratings is directly
a point spread (neutral floor, no home-court term).

## Quick start

```bash
pip install -e .
sl-ratings summer_league/example_rosters.csv --detail
sl-ratings summer_league/example_rosters.csv --matchup "Team Alpha,Team Bravo"
sl-ratings rosters.csv --out ratings.csv
```

## Roster CSV schema

One row per player. Only `team`, `player`, and `tier` are required —
everything else refines the estimate.

| column | meaning |
| --- | --- |
| `team` | team name (any consistent string) |
| `player` | player name |
| `pos` | position (display only) |
| `tier` | pedigree tier — see table below (**required**) |
| `age` | age in years; small bonus for older G-League/international vets |
| `draft_pick` | overall pick number; for rookies this overrides the tier default via a smooth pick-value curve |
| `nba_gp` | career NBA games played (bonus for returners/two-ways) |
| `nba_mpg` | career NBA minutes per game |
| `adj` | manual adjustment in player-value points (e.g. `0.5` if you're high on a guy, `-1` if he's hurt-ish) |
| `out` | `1`/`yes`/`out` if the player is on the roster but not playing |
| `value` | **direct override** of the player's value — replaces the tier/pick/experience formula entirely (any `adj` still adds on top). Use when pedigree misleads, e.g. a former top-10 pick who hasn't panned out. |

### Tiers

| tier | base value | who it's for |
| --- | --- | --- |
| `nba_rotation` | 8.5 | returner with real NBA rotation minutes |
| `lottery_rookie` | 7.5 | picks 1–14 in the most recent draft |
| `nba_fringe` | 7.0 | standard NBA contract, end of bench |
| `first_round_rookie` | 6.0 | picks 15–30 |
| `two_way` | 5.5 | two-way contract |
| `second_round_rookie` | 4.5 | picks 31–60 |
| `gleague_vet` | 4.0 | experienced G-League / SL veteran, Exhibit 10 |
| `international` | 3.5 | overseas pro / draft-and-stash |
| `undrafted_rookie` | 3.0 | undrafted rookie free agent |
| `camp` | 2.0 | roster fill |

## How the team rating works

1. Each player's value = tier base, refined by draft pick (log curve: pick 1
   ≈ 8.5, pick 14 ≈ 5.5, pick 30 ≈ 4.6), NBA experience (up to +1.5), age
   (up to +0.5 for non-pedigree tiers), plus any manual `adj`.
2. Players marked `out` are dropped; the rest are sorted by value and
   weighted by a short SL rotation curve (top two guys ~full weight, fading
   to ~0.15 by the 10th man). Rosters thinner than 9 take a small penalty.
3. Team strength = the weighted average; the power rating is
   `3.2 × (strength − league mean)`, in points per game.
4. Matchup: spread = rating difference; win probability assumes a ~13-point
   standard deviation on SL game margins.
5. Totals: SL games are **40 minutes**, not 48. `BASE_TOTAL` (178) is the
   combined regulation score between two average teams — a prior, not a fit.
   Each team's rating splits 70/30 into scoring more vs. allowing less
   (`OFF_SHARE`), so better teams push the total up while the score
   difference still equals the spread. Recalibrate `BASE_TOTAL` against
   actual scores once games are played.

All constants live at the top of `summer_league/model.py` and are meant to
be retuned as results come in.

## Stats-derived values (`build_values.py`)

`python -m summer_league.build_values` replaces tier defaults with values
derived from each player's advanced stats, written into the roster CSV's
`value` column (same 0–10 scale, anchored to the tier baselines):

- **NBA returners** — 2025-26 NBA BPM (`data/nba_2026.csv`, from
  basketball-reference), minutes-weighted, capped at 75% stat / 25%
  pedigree. Anchor: BPM −2 with a full season ≈ 8.0.
- **2026 rookies** — final college season BPM (`data/college_2026.csv`,
  from barttorvik), age-adjusted (−0.5 BPM per year older than 19.5 at
  draft), blended 50/50 with draft pedigree.
- **2025 grads** now in the G-League — final college BPM at a steeper
  discount, 60/40 stat/baseline.
- **No stats found** (internationals, multi-year G-League vets) — the tier
  baseline stands.

Run with `--dry-run` to preview matches and the biggest movers without
writing. ~75% of rostered players get a stat-derived value.

## Caveats

- Ratings are only relative to the teams **in the file** — the league mean
  is computed from whatever rosters you load, so load all 30 teams for
  Vegas.
- SL rotations shift daily (shutdowns after 2–3 games, late adds). Use the
  `out` flag and re-run rather than editing rosters destructively.
- `example_rosters.csv` uses fictional players purely to demonstrate the
  schema and output.

## Updating from box scores (`update_games.py`)

Append player lines to `data/boxscores_2026.csv` and final scores to
`data/games_2026.csv`, then run `python -m summer_league.update_games`.
Each player's value takes a Bayesian nudge toward what the box score
implies (Hollinger Game Score per 36, mapped to the value scale), scaled
by minutes — a monster game moves a player ~0.5–1.0 points; it takes
several games to fully re-rate someone. The game log prints predicted vs.
actual spreads/totals and a shrunk `BASE_TOTAL` suggestion to adopt in
`model.py` as the sample grows.

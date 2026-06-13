# passbot — World Cup pass predictor

Predicts **how many passes each player will make in a match**. Trains and
backtests on past tournaments using free StatsBomb event data, then forward-tests
on live World Cup lineups.

## The idea

Total passes are mostly driven by *minutes played*, so the model doesn't predict
totals directly. It predicts a **rate** — passes per 90 minutes — and scales by
expected minutes:

```
predicted_passes = predicted_passes_per_90 × expected_minutes / 90
```

This keeps the noisy, hard-to-predict part (rotation, subs, red cards, blowouts)
out of the learnable part. The rate is well explained by **position**, **player
form**, and **team possession style** — all of which the model uses.

Every feature is **leak-free**: it's computed only from matches *before*
kickoff (rolling pass rate, expected minutes, each team's historical possession
share). A match's own outcome is never an input, only the training target.

## Data

| Source | Role | Key needed |
| --- | --- | --- |
| [StatsBomb open data](https://github.com/statsbomb/open-data) | training + backtest (event-level passes for past World Cups, Euros, Copa América) | no |
| [API-Football](https://www.api-football.com/) | live 2026 lineups + post-match grading | yes (`API_FOOTBALL_KEY`) |

StatsBomb gives us **full World Cups 2018 & 2022** with every pass logged — so
the *model* can be backtested even though the 2026 games haven't happened.

## Install

```bash
pip install -e .[passbot]
```

## Use

**Backtest** — train on 2018, score on 2022 (out-of-sample):

```bash
passbot backtest --train wc2018 --test wc2022 --show 10
```

```
baseline MAE (career avg): 16.75 passes
model MAE (est. minutes) : 15.30 passes  (+8.7% vs baseline)
model MAE (true minutes) : 10.39 passes  (rate model only)
correlation (pred vs act): 0.620
```

Available tournaments: `wc2018`, `wc2022`, `euro2024`, `copa2024`.

**Train & save** a model for live prediction:

```bash
passbot train --tournaments wc2018 wc2022 --out passbot_model.pkl
```

**Predict** a lineup. Try the built-in mock (Spain vs Germany, offline):

```bash
passbot predict --mock
```

…or a real fixture once you have an API-Football key:

```bash
export API_FOOTBALL_KEY=...
passbot predict --fixture 123456
```

## Forward-testing workflow for 2026

1. Before a match, grab the confirmed lineup (`--fixture`) and predict.
2. After the match, pull actual passes from API-Football and compare.
3. Track MAE across a handful of games — that's the real test, since we can't
   backtest the *2026* squads, only validate the modelling approach on history.

## Known limitations

- **Minutes dominate the error.** The rate model is good (MAE ~10 with true
  minutes); most remaining error is not knowing exactly how long each player
  plays. Confirmed lineups help; in-game shocks (red cards, early subs) don't.
- **Extreme possession is under-predicted.** Hyper-possession sides (Spain 2022)
  push individual counts to 150–220; the model regresses these toward the mean.
  Better team-possession features are the main lever to improve.
- **Cross-source identity matching** is name-based (accent-normalised). A player
  with no StatsBomb history falls back to a position-group prior.

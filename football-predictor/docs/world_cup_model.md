# World Cup Prediction Model

## Scope

The World Cup module is isolated under `src/world_cup`. It does not reuse or
overwrite the English club model.

The current baseline uses:

- men's full international results since 2000
- sequential national-team Elo
- exponentially weighted goals scored and conceded
- neutral-site handling and tournament importance weights
- an independent Poisson score matrix

It outputs expected goals, win/draw/loss probabilities, and the most likely
score.

## Evaluation

Each tournament holdout freezes the model before the opening match. Training
uses only completed internationals before that date, so no match from the
evaluated World Cup can update the model.

| Holdout | Train matches | Log loss | Uniform | Difference |
| --- | ---: | ---: | ---: | ---: |
| 2010 | 9,802 | 0.9748 | 1.0986 | -0.1239 |
| 2014 | 13,799 | 1.0354 | 1.0986 | -0.0632 |
| 2018 | 17,577 | 1.0252 | 1.0986 | -0.0734 |
| 2022 | 21,638 | 1.0939 | 1.0986 | -0.0047 |

The enhanced model beats uniform probabilities in all four holdouts. It is a
research candidate, not a production or betting model: the 2022 margin is too
small to establish robust out-of-sample reliability.

## Commands

```powershell
.\.venv\Scripts\python.exe scripts\run_world_cup.py --evaluate true --training-source internationals
.\.venv\Scripts\python.exe scripts\run_world_cup.py --training-source internationals --predict-date 2026-06-14
```

## Next Validation Layer

- tune parameters only on earlier tournaments and preserve later tournaments
  as untouched tests
- add calibration diagnostics and confidence intervals
- include squad availability, injuries, rest, travel, and confirmed lineups
- compare Elo-Poisson against multinomial and goal-model alternatives

Sources:

- https://github.com/martj42/international_results
- https://github.com/openfootball/worldcup

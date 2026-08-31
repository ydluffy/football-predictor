# 世界杯实时数据增强

本阶段完成四类实时数据增强入口：

1. 盘口变化增强
2. 情报结构化
3. 伤停与停赛
4. 实时阵容

这些能力已经接入 `scripts/run_world_cup_lineup_adjusted.py` 和每日流水线。它们不会替代基础 Elo/EWMA/Poisson 模型，而是在赛前为每场比赛增加更厚的数据层。

## 1. 盘口变化增强

输入文件：

```text
data/manual/sporttery_handicap_line_movement_features.csv
```

生成方式：

```powershell
.\.venv\Scripts\python.exe scripts\build_sporttery_line_movement_features.py --history data/manual/sporttery_handicap_market_history.csv --output data/manual/sporttery_handicap_line_movement_features.csv
```

预测输出字段：

- `line_movement_opening_home_handicap`
- `line_movement_latest_home_handicap`
- `line_movement_delta`
- `line_movement_direction`
- `line_movement_favorite_movement`
- `line_movement_snapshots`

说明：盘口变化依赖多次快照。只有一次抓取时无法形成变化，需要持续保存初盘、临场、收盘。

## 2. 情报结构化

模板：

```text
data/templates/world_cup_structured_intelligence.csv
```

字段：

- `match_id`
- `team`
- `category`
- `severity`
- `text`
- `source`
- `url`
- `updated_at`

支持分类：

- `injury`
- `suspension`
- `lineup`
- `tactical`
- `motivation`
- `schedule`
- `form`
- `weather`
- `other`

预测输出字段：

- `structured_intelligence_count`
- `structured_intelligence_severity`
- `structured_injury_count`
- `structured_suspension_count`
- `structured_tactical_count`
- `structured_motivation_count`
- `structured_schedule_count`

## 3. 伤停与停赛

模板：

```text
data/templates/world_cup_absences.csv
```

字段：

- `date`
- `team`
- `player`
- `player_id`
- `status`
- `impact`
- `reason`
- `source`
- `updated_at`
- `notes`

支持状态：

- `injured`
- `suspended`
- `unavailable`
- `doubtful`
- `illness`
- `rested`

预测输出字段：

- `home_absence_count`
- `away_absence_count`
- `home_absence_weighted_impact`
- `away_absence_weighted_impact`
- `home_injury_count`
- `away_injury_count`
- `home_suspension_count`
- `away_suspension_count`
- `absence_goal_shift`

说明：伤停停赛会实际影响最终进球期望。主队伤停更重会降低主队进球乘数；客队伤停更重会提高主队相对进球乘数。

## 4. 实时阵容

模板：

```text
data/templates/world_cup_realtime_lineups.csv
```

字段：

- `match_id`
- `team`
- `player`
- `player_id`
- `role`
- `position`
- `confirmed`
- `source`
- `updated_at`

角色：

- `starter`
- `substitute`
- `absent`

预测输出字段：

- `home_realtime_lineup_confirmed`
- `away_realtime_lineup_confirmed`
- `home_realtime_starters`
- `away_realtime_starters`
- `home_realtime_substitutes`
- `away_realtime_substitutes`

说明：当某队有 11 名 confirmed starter 时，系统认为该队实时首发已确认，并提高数据完整度评分。

## 运行命令

```powershell
.\.venv\Scripts\python.exe scripts\run_world_cup_lineup_adjusted.py `
  --as-of-date 2026-06-25 `
  --sporttery-markets data\manual\sporttery_handicap_markets_2026-06-26.csv `
  --line-movement data\manual\sporttery_handicap_line_movement_features.csv `
  --structured-intelligence data\templates\world_cup_structured_intelligence.csv `
  --absences data\templates\world_cup_absences.csv `
  --realtime-lineups data\templates\world_cup_realtime_lineups.csv
```

每日流水线也支持传入这些文件：

```powershell
.\.venv\Scripts\python.exe scripts\run_world_cup_daily_pipeline.py `
  --as-of-date 2026-06-25 `
  --refresh-sporttery true `
  --sporttery-date 2026-06-26 `
  --structured-intelligence data\manual\world_cup_structured_intelligence.csv `
  --absences data\manual\world_cup_absences.csv `
  --realtime-lineups data\manual\world_cup_realtime_lineups.csv
```

## 当前边界

- 盘口变化已经接入，但需要多次快照积累。
- 情报结构化已接入，后续可以把雷速/网页文本解析器接到该格式。
- 伤停停赛已会影响进球期望，但影响权重仍需赛后复盘校准。
- 实时阵容已能识别确认首发，下一步可进一步按球员强度计算首发净影响。

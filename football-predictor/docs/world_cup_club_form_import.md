# 世界杯俱乐部近期状态导入

## 当前完成

项目已新增标准化俱乐部逐场状态导入通道。它把外部整理的球员俱乐部比赛数据写入统一契约：

- `data/player_level/espn_world_cup_2026/club_appearances.csv`

导入后，以下模型层会自动使用这些数据：

- 阵容特征：近 30/90 天分钟、近 14 天负荷、进球助攻、xG+xA
- 球员强度：`club_minutes_score`、`club_attack_score`
- 首发修正：通过球员强度和阵容特征间接影响预期进球

## 输入格式

模板文件：

- `data/templates/world_cup_club_form_import.csv`

必须包含：

- `match_date`
- `club`
- `competition`
- `minutes`
- `started`
- `goals`
- `assists`
- `xg`
- `xa`

球员身份可以二选一：

- 直接填 `player_id`
- 或填 `source` + `source_player_id`，通过 `player_aliases.csv` 自动解析

## 使用命令

```powershell
.\.venv\Scripts\python.exe scripts\import_world_cup_club_form.py `
  --input data\manual\world_cup_club_form.csv `
  --as-of-date 2026-06-16 `
  --audit-output artifacts\data\world_cup_club_form_import_2026-06-16.json
```

导入后重建球员强度：

```powershell
.\.venv\Scripts\python.exe scripts\build_world_cup_player_strength.py `
  --as-of-date 2026-06-16 `
  --output data\player_level\espn_world_cup_2026\player_strengths.csv `
  --audit-output artifacts\data\world_cup_player_strength_2026-06-16.json
```

## 当前数据状态

当前没有把示例数据导入真实预测集，避免污染模型。

截至目前：

- 俱乐部归属已接入
- 俱乐部逐场状态入口已接入
- 稳定免费逐场数据源尚未确认
- 真实 `club_appearances.csv` 仍为空

## 下一步

需要选择真实数据来源并填充模板。优先级：

1. 商业或授权 API：稳定性最好。
2. 官方/联赛开放数据：覆盖可能有限。
3. FBref/公开网页整理：需要确认使用条款和稳定性。
4. 人工 CSV：适合先覆盖重点球队和关键球员。

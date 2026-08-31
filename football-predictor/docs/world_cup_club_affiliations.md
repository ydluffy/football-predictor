# 世界杯球员俱乐部归属

## 当前完成

项目已从 ESPN 公开 roster 数据中提取球员当前默认俱乐部和默认联赛。

新增产物：

- `data/player_level/espn_world_cup_2026/club_affiliations.csv`
- `data/player_level/espn_world_cup_2026/squads.csv` 中的 `club` 字段

这让阵容特征中的以下列可以开始工作：

- `same_club_starter_pairs`
- `club_concentration`

## 重要过滤规则

ESPN 的 `defaultTeam` 有时会指向国家队本身，例如 `fifa.world` 或
`fifa.friendly`。这类值不是俱乐部，已被过滤为空。

这样可以避免把“同一国家队”误判为“同一俱乐部”，从而高估球员默契。

## 2026-06-16 覆盖率

- 球员数：1,251
- 俱乐部归属行：1,246
- 有效俱乐部归属覆盖率：27.7%
- 俱乐部逐场出场数据：0

当前接入的是“球员现在归属哪个俱乐部”，不是“最近 90 天踢了多少分钟”。
因此它可以支持默契和阵容结构研究，但还不能支持近期状态、疲劳或进攻贡献。

## 使用方式

刷新实时球员数据后会自动生成俱乐部归属：

```powershell
.\.venv\Scripts\python.exe scripts\import_espn_world_cup_live.py `
  --download true `
  --as-of-date 2026-06-16
```

重新生成阵容特征：

```powershell
.\.venv\Scripts\python.exe scripts\build_world_cup_squad_features.py `
  --data-dir data\player_level\espn_world_cup_2026 `
  --fixtures data\player_level\espn_world_cup_2026\fixtures.csv `
  --output data\processed\world_cup_espn_squad_features_2026-06-16.csv `
  --audit-output artifacts\data\world_cup_espn_squad_features_2026-06-16.json
```

## 下一步

下一阶段仍然是逐场俱乐部状态：

- 最近 90 天分钟
- 最近 14 天负荷
- 进球、助攻、xG、xA
- 门将扑救和后卫防守数据

免费公开 ESPN 球员 gamelog/statistics 接口当前没有稳定返回，因此需要继续寻找
FBref、Kaggle/StatsBomb 开放数据、football-data 付费 API 或手工 CSV 导入方案。

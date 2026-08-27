# 2026 世界杯实时球员数据

## 当前接入

项目已接入 ESPN 公开接口，作为自动化辅助数据源：

- 完整赛事日历：104 场
- 48 支参赛队当前名单
- 球员 ID、姓名、出生日期和位置
- 比赛确认名单、11 人首发、替补和阵型
- 比赛结束后的国家队出场记录
- 原始请求 URL 和 UTC 抓取时间

该来源不是 FIFA 官方数据源。模型会保留来源标记和抓取时间，后续可用
FIFA、各国家队足协公告或商业数据源进行交叉核验。

## 首发使用规则

球队 roster 只表示当前名单，统一写为 `squad`，不会猜测首发。

比赛摘要中只有恰好出现 11 名首发时，才写入 `starter` 和
`substitute`。未确认、占位或提前抓取的比赛仍保持 `squad`。

## 伤停使用规则

只有来源明确报告的球员才写入：

- `injured`
- `doubtful`
- `suspended`
- `unavailable`

来源没有提到某名球员时保持 `unknown`，不能解释为 `available`。
截至 2026-06-15，本次 ESPN 免费公开接口没有返回明确伤停记录，
因此伤停覆盖率为 0%，伤停特征尚不能自动进入正式模型。

## 数据位置

- 原始缓存：`data/external/espn-world-cup`
- 统一球员数据：`data/player_level/espn_world_cup_2026`
- 接入审计：`artifacts/data/espn_world_cup_2026_import.json`
- 来源快照：`data/player_level/espn_world_cup_2026/source_snapshots.csv`

## 刷新命令

```powershell
.\.venv\Scripts\python.exe scripts\import_espn_world_cup_live.py --download true
```

固定复盘日期：

```powershell
.\.venv\Scripts\python.exe scripts\import_espn_world_cup_live.py `
  --download true `
  --as-of-date 2026-06-15
```

## 当前模型决策

名单和已确认首发可以用于赛前阵容连续性、位置结构和临场首发修正研究。
伤停和俱乐部近期表现覆盖不足，因此暂不自动晋升为正式预测特征。

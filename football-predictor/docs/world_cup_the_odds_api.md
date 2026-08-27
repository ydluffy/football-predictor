# The Odds API 赔率接入

本文档说明 The Odds API 在世界杯模型和每日竞彩流程中的定位、使用方式和限制。

## 定位

The Odds API 用来补充多博彩公司市场数据，主要覆盖：

- 胜平负 / h2h
- 让球或分差 / spreads
- 大小球 / totals
- 多博彩公司赔率快照
- 国际市场隐含概率

它不提供伤停、停赛、实时首发，所以不能替代 API-Football 或人工核验情报源。

## 导入命令

推荐通过环境变量传入 key，避免把密钥写入项目文件：

```powershell
$env:THE_ODDS_API_KEY="你的 API key"
.\.venv\Scripts\python.exe scripts\import_the_odds_api_world_cup.py `
  --sport-key soccer_fifa_world_cup `
  --regions eu,uk,us,au `
  --markets h2h,spreads,totals `
  --output-dir data\external\the_odds_api_world_cup `
  --audit-output artifacts\data\the_odds_api_world_cup_import.json
```

## 输出文件

- `data/external/the_odds_api_world_cup/odds.csv`
- `data/external/the_odds_api_world_cup/match_market_summary.csv`
- `artifacts/data/the_odds_api_world_cup_import.json`

`odds.csv` 是原始长表，每一行代表一个比赛、博彩公司、市场、结果的赔率。

`match_market_summary.csv` 是按比赛和市场聚合后的摘要，包含：

- 博彩公司数量
- 平均赔率
- 最佳赔率
- 胜平负市场隐含概率

## 和体彩数据的关系

体彩数据代表国内竞彩市场，The Odds API 代表多博彩公司国际市场。两者可以共同用于：

- 检查国内外市场是否出现明显分歧
- 计算模型概率与市场概率差
- 跟踪盘口或赔率快照变化
- 支撑大小球和多市场分析

单次抓取只是一个快照。要做盘口变化，需要后续定时运行该脚本，积累赛前 12 小时、2 小时、临场等时间点。

## 每日竞彩接入

11:05 开售确认命令默认自动读取 `config/the_odds_api_sport_keys.json`，只为中国体彩确认 `on_sale` 的赛事请求对应 sport key，并将结果写入不可变目录：

- `data/external/the_odds_api_sporttery/snapshots/<时间戳>_confirm/`
- `raw_payload.json`
- `odds.csv`
- `match_market_summary.csv`
- `sporttery_alignment.csv`
- `audit.json`

终版分析必须再次执行：

```powershell
.\.venv\Scripts\python.exe scripts\refresh_the_odds_for_sporttery.py `
  --scan-json <当天确认扫描JSON> `
  --snapshot-type final
```

映射只有在主客队规范名、开赛时间和唯一性同时通过时才标记为 `mapped`。外盘快照只提供市场特征和复核信息，不证明体彩在售，不允许直接写投注台账；请求失败、赛事未路由或映射失败时自动降级为体彩市场基线。

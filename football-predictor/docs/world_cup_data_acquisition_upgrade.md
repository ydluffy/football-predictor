# 世界杯数据获取能力升级

本文档用于说明当前数据获取方案、主要缺口、可行解决办法，以及本阶段新增的数据源注册表和采集覆盖率审计。

## 当前数据获取方式

| 数据源 | 获取方式 | 已覆盖维度 | 主要限制 |
|---|---|---|---|
| ESPN World Cup public data | 公开接口 + 本地缓存 | 赛程、球队、球员名单、已完赛出场、部分首发 | 伤停字段经常缺失，临场首发不稳定 |
| 中国体彩 SPF/RQSPF | Playwright 浏览器渲染页面 | 胜平负赔率、让球胜平负赔率、让球盘、支持率 | 无稳定公开 API，历史初盘不能回补 |
| 雷速公开页面 | HTTP 抓取，新增浏览器渲染兜底 | 比赛 ID、中文队名、情报数量、分析/情报链接 | 详情页可能限制自动访问，首页不保证覆盖所有世界杯比赛 |
| API-Football/API-SPORTS | 认证 API | 赛程、伤停、停赛、实时首发、场馆 | 需要 `API_FOOTBALL_KEY`，覆盖取决于套餐和赛事支持 |
| football-data.org | 认证 API | 世界杯赛程、赛果、48 队、球员名单、教练 | 不提供伤停/实时首发，赔率需额外 odds 包 |
| StatsBomb/历史数据 | 本地导入 | 历史训练和回测 | 不提供 2026 实时伤停、盘口、临场阵容 |
| 人工实时模板 | CSV 人工确认 | 伤停、停赛、实时首发、结构化情报 | 不是自动源，需要来源链接和人工校验 |

## 不能获取的数据主要卡在哪里

1. 伤停 / 停赛
   - 当前 ESPN 导入中 `availability_rows = 0`，说明这个公开源没有稳定给出伤停数据。
   - 解决办法：接入公开情报网页文本抽取，并保留人工确认入口；未确认前只进入低权重解释层。

2. 临场首发
   - 首发通常赛前 30-90 分钟才公布，赛前远期预测无法稳定拿到。
   - 解决办法：建立赛前 120/90/60/30 分钟轮询，双方各 11 人确认后才启用阵容修正。

3. 盘口变化
   - 中国体彩当前页面只能抓当前展示数据；过去没抓的初盘无法凭空回补。
   - 解决办法：从现在开始定时抓快照，形成自己的盘口时间序列；同时保留原始 HTML/文本/截图。

4. 多平台盘口
   - 当前主要是体彩，缺少欧赔、亚盘、大小球、交易热度。
   - 解决办法：新增数据源注册项后逐个接入，先把字段和审计标准统一。

5. 球员近期状态 / 教练战术
   - 需要俱乐部比赛级数据和文本战术情报，免费公开源覆盖不稳定。
   - 解决办法：先用可验证字段起步，例如近 5 场分钟数、是否首发、伤后复出，再逐步做战术标签。

## 本阶段新增能力

### 1. 数据源注册表

代码位置：

- `src/world_cup/data_source_audit.py`

注册表记录：

- source_id
- 展示名称
- 获取通道
- 是否自动化
- 是否需要浏览器
- 是否官方源
- 可覆盖的数据维度
- 必需字段 / 可选字段
- 已知限制
- 失败后的建议兜底方式

### 2. 采集覆盖率审计

新增脚本：

```powershell
.\.venv\Scripts\python.exe scripts\audit_world_cup_data_sources.py --as-of-date 2026-06-26
```

默认输出：

```text
artifacts/data/world_cup_data_source_coverage.json
```

审计内容：

- 每个源的行数
- 必需字段是否存在
- 必需字段非空率
- 可选字段非空率
- 行覆盖率
- 源级 issues
- 预测级维度覆盖率
- 关键缺失维度

### 3. 体彩浏览器采集增强

`scripts/refresh_lottery_gov_spf.py` 现在会额外输出 JSON 审计：

```text
artifacts/data/sporttery_lottery_gov_import_YYYY-MM-DD.json
```

其中包含：

- 浏览器抓取摘要
- 原始文本路径
- CSV 输出路径
- 历史快照输出路径
- 体彩字段覆盖率
- 解析失败/字段缺失问题

### 4. 雷速浏览器采集增强

新增浏览器抓取脚本：

```powershell
node scripts\fetch_leisu_public.mjs --output data\external\leisu_home_rendered.html
```

导入脚本新增模式：

```powershell
.\.venv\Scripts\python.exe scripts\import_leisu_public.py --method browser --download true
```

模式说明：

- `--method http`：默认 requests 抓取。
- `--method browser`：使用 Playwright 渲染后保存 HTML，再解析。
- `--method cache`：只解析已有 HTML。

### 5. 体彩赛程驱动预测

新增脚本：

```powershell
.\.venv\Scripts\python.exe scripts\build_sporttery_fixture_file.py `
  --markets data\manual\sporttery_handicap_markets_2026-06-26.csv `
  --output data\external\sporttery_world_cup_fixtures_2026-06-26.csv
```

用途：

- 直接从中国体彩已抓到的真实比赛列表生成预测赛程。
- 避免 ESPN 赛程和体彩赛程不一致时，盘口数据抓到了但无法进入预测。
- 生成的 `match_id` 使用 `sporttery_日期_编号`，保留体彩编号和 kickoff_time。

本阶段验证结果：

- 原 ESPN 赛程预测：体彩/雷速只匹配 2/15。
- 使用体彩赛程驱动预测：体彩盘口、盘口变化、雷速公开情报均匹配 6/6。

这是真正提升当前可用数据覆盖率的一步。它没有解决伤停和实时首发，但解决了“数据抓到了却进不了预测”的关键问题。

### 6. 稳定专业源：API-Football

新增脚本：

```powershell
$env:API_FOOTBALL_KEY="你的 API key"
.\.venv\Scripts\python.exe scripts\import_api_football_realtime.py `
  --league-id 1 `
  --season 2026 `
  --date 2026-06-26 `
  --output-dir data\external\api_football_world_cup
```

输出：

- `data/external/api_football_world_cup/fixtures.csv`
- `data/external/api_football_world_cup/absences.csv`
- `data/external/api_football_world_cup/realtime_lineups.csv`
- `artifacts/data/api_football_realtime_import.json`

用途：

- `absences.csv` 可直接传给预测脚本的 `--absences`。
- `realtime_lineups.csv` 可直接传给预测脚本的 `--realtime-lineups`。

没有配置 `API_FOOTBALL_KEY` 时，脚本会输出空 CSV 和 `status=skipped`，不会把缺失数据伪装成成功。

### 7. 稳定源：football-data.org

新增脚本：

```powershell
$env:FOOTBALL_DATA_TOKEN="你的 token"
.\.venv\Scripts\python.exe scripts\import_football_data_org_world_cup.py `
  --season 2026 `
  --snapshot-date 2026-06-26 `
  --output-dir data\external\football_data_org_world_cup
```

输出：

- `data/external/football_data_org_world_cup/fixtures.csv`
- `data/external/football_data_org_world_cup/teams.csv`
- `data/external/football_data_org_world_cup/coaches.csv`
- `data/external/football_data_org_world_cup/players.csv`
- `data/external/football_data_org_world_cup/player_aliases.csv`
- `data/external/football_data_org_world_cup/squads.csv`

本地验证结果：

- token 可用。
- 世界杯 `WC` 可访问。
- `matches?season=2026` 返回 104 场。
- `teams?season=2026` 返回 48 队、1249 名球员、48 名教练。

限制：

- 不提供伤停/停赛。
- 不提供实时首发。
- odds 字段需要额外开通 odds package。

因此它适合作为稳定的赛程、赛果、名单和教练源，不适合作为临场情报源。

## 当前审计结论

以 2026-06-26 的本地数据为例：

- ESPN 基础赛程源：可用。
- 中国体彩源：当前 CSV 可用，但只覆盖当前页面展示场次。
- 雷速公开源：可用但覆盖有限，详情页自动访问仍可能受限。
- 雷速情报详情页：HTTP 抓取会返回阿里云 WAF 挑战页；浏览器模式会进入滑动验证页，当前不能作为稳定自动源。
- API-Football：已完成适配器，当前本地未配置 token，所以审计显示 skipped；配置 token 后可补伤停和实时首发。
- football-data.org：已接入并验证可用，当前可稳定补赛程、赛果、球队、名单和教练。
- 预测级关键缺失：盘口变化覆盖不足、伤停/停赛为 0、实时首发为 0。

这意味着当前模型可做基础赛前方向判断，但临场高质量预测仍不能宣称数据充分。

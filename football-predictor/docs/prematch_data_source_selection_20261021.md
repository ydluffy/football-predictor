# 赛前数据源选型：xG / 旅行距离 / 阵容覆盖（2026-10-21）

本文对齐 [prematch_coverage.py](../src/data/prematch_coverage.py) 中已经冻结的 7 个字段组，
只解决其中 3 个长期 `available=false` 的组：`prematch_xg`、`travel`、`timezone`（`confirmed_lineups` 为覆盖不足）。

> 结论先行：**旅行距离/时区必须自建（没有现成数据源）；xG 没有任何"赛前预测型"产品，只能用赛后 xG 做滚动特征，
> 且不要指望单一源覆盖竞彩全量日历；阵容覆盖的实际瓶颈是"开赛前 20–40 分钟"的时效窗，不是接口本身。**
> 所有价格与联赛覆盖均标注了核实日期，采购前必须逐个实测确认。

---

## 1. 目标字段（代码已定义，选型必须落到这些列名）

| 组 | 字段 | 当前状态 |
|---|---|---|
| `prematch_xg` | `prematch_xg_home` / `prematch_xg_away` / `xg_home` / `xg_away` | 全空 |
| `travel` | `home_travel_km` / `away_travel_km` / `travel_km_diff` | 全空 |
| `timezone` | `home_timezone_shift_hours` / `away_timezone_shift_hours` | 全空 |
| `confirmed_lineups` | `lineup_confirmed` / `confirmed_starters` / `starter_count` | 已有接口，覆盖不足 |

`prematch_intelligence` 侧的 `signal_type` 需同步新增：`prematch_xg`、`travel_km`、`timezone_shift_hours`、`confirmed_starter`。
注意 `model_gate = blocked_until_timestamped_prematch_coverage_is_sufficient`——这 3 个组不补齐，模型门槛一直卡着。

## 2. 项目现状（已有能力，避免重复采购）

- **API-Football**：`fixtures/lineups`（带 `confirmed` 标记）、`injuries`、赛程/球队/场馆名称；已有 `lineup_rows_to_realtime_lineups` 与 `injury_rows_to_absences` 解析层。
- **赔率**：The Odds API（外盘）、API-Football odds、竞彩 SP、捷报 Nowscore（页面 17 家 + 本次新增的 cp 结构化接口）。
- **缺口**：xG 完全没有；旅行距离/时区完全没有；阵容只覆盖 API-Football 支持的联赛。

---

## 3. xG：先纠正一个前提

**不存在"赛前预测型 xG"的公开数据源。** xG 本质是赛后（含赛中逐分钟重算）产出指标，
工程上所谓"赛前 xG 特征"= 用 kickoff 之前**已完赛**比赛的 xG 做滚动窗口（类似 `xg_last_1..3`，见 `mock_data_generator.py` 的既有 schema）。
因此选型标准只有三条：

1. **联赛覆盖**是否覆盖竞彩日历（这是最大约束，竞彩大量是亚洲/次级联赛）。
2. **历史深度**够不够做滚动窗口与回测。
3. 每条记录是否带可对齐的 `observed_at`（否则无法进入 `blocked_until_timestamped` 门槛）。

| 源 | 性质 | 覆盖 | 价格 | 判断 |
|---|---|---|---|---|
| Understat | 免费、无官方 API（JSON 内嵌 `<script>`） | 6 个联赛（英超/西甲/德甲/意甲/法甲/俄超） | 免费 | 仅够做欧洲验证集，且属页面逆向 |
| FBref | 免费 | **2026-01-20 起高级数据（含 xG）已被彻底移除** | — | **不可再规划依赖** |
| SportMonks xG add-on | 官方 API，附加在足球套餐上 | xG Basic 覆盖其联赛范围 | Basic €15/月（年付）；Advanced 档更高（另见：Odds+Predictions ≈€15/月） | **首选试点**；基础套餐 €29 / €99 Growth / €249 Pro |
| TheStatsAPI | 官方 API，xG 含在所有套餐 | 见其覆盖表 | Starter $50/月（10 万请求）→ Growth $129 → Scale $379 | 备选；单价比 SportMonks 高 |
| FotMob / Sofascore | 非官方逆向接口（Sofascore 有 Akamai 反爬） | 广 | 免费 | 不可作为主链路（见 §6） |
| 火星数据 / 纳米数据 / 蚂蚁体育 / 飞鲸体育 | 国内商业数据商（含足球阵容/统计接口） | 亚洲联赛通常更强 | 需逐个询价 | 报价后按"亚洲赛事覆盖"评估 |

**建议**：只对欧洲主流联赛接入 xG 影子特征（可回测、可作为 ablation 对照），
亚洲赛事**明确标记为不提供**，而不是用替代指标硬填。字段名沿用 `prematch_xg_*`，并在 payload 里写清 `provider` 与 `observed_at`。

## 4. 旅行距离 / 时区：没有数据源，必须自建

已核实：API-Football 只返回 `venue`**名称/城市**，**不返回经纬度**；没有任何主流源直接提供"球队旅行距离"。

自建链路（全部确定性、无时效问题，是三个缺口里性价比最高的）：

1. **球场坐标表**：`jokecamp/FootballData` 的 `stadiums-with-GPS-coordinates.csv`，或按 `venue.name` 从 Wikidata 反查 `P625` 坐标。
2. **距离**：Haversine（主队场馆 → 客队场馆，项目当前无 haversine 实现，需新增）。
3. **时区**：`timezonefinder` + 场馆坐标反查 IANA 时区，再算 `timezone_shift_hours`。

产出落到 `home_travel_km` / `away_travel_km` / `travel_km_diff` / `home_timezone_shift_hours` / `away_timezone_shift_hours`。

**风险点**：中立场与"名义主场"（如国际赛、杯赛决赛）会失真，需要用 `venue` 是否等于主队常驻场馆来打标记，
无法确认的行置空而不是猜。

## 5. 阵容覆盖：瓶颈是时效窗，不是接口

- **API-Football `fixtures/lineups`**：首发**开赛前 20–40 分钟**才出现（个别联赛可到 75 分钟前）；**次要联赛可能始终没有**。
  → 当前总控在 T-1 天或 T-2h 拉阵容必然拿不到数据，这是 `confirmed_lineups` 覆盖率低的主因。
- **football-data.org Deep Data**：€29/月（30 请求/分钟）含 lineups，Standard €49、Pro €199；覆盖 150+ 赛事但**以欧洲为主**。
- **SportMonks Expected Lineups**（add-on）：提供**预测**阵容，可早于 20 分钟拿到；语义是预测而非确认，不能置 `lineup_confirmed=true`。
- **国内服务商**：亚洲联赛（日职/J 联赛/K 联赛/中超）阵容覆盖通常优于欧美源，需询价 + 实测确认推送时效。

**动作建议**：①先审计 API-Football 在竞彩实际联赛上的阵容可得率，再决定是否引入第二家；
②总控加 T-40min 与 T-20min 两次拉取（后一次用于覆盖确认窗口）；③`lineup_confirmed` 仅由 `confirmed=true` 置位。

## 6. 合规与风险

- **官方 API 与页面逆向必须区分**：FBref 的教训说明逆向/白拿的数据源会被供应商一刀切断且要求清除历史数据，不能进长期依赖。
- 若继续用公开页面（如捷报），保持现有做法：只读公开页面、归档 raw + `sha256`、`source_time_verified` 门禁、**不使用 App 私有接口、不绕验证码/登录**。
- 采购类源（SportMonks / TheStatsAPI / football-data.org / 国内数据商）需确认**是否允许用于博彩相关产品**，这是最常见的合同红线。
- 大陆网络可达性需实测（项目已有 `SPORTTERY_DIRECT_CONNECTION=1` / `--no-proxy-server` 的先例）。

## 7. 建议落地顺序

1. **时区 + 旅行距离（自建）**：无外部依赖、无时效问题、可直接进特征；先做坐标覆盖率审计。
2. **xG（SportMonks xG add-on 试点）**：只覆盖欧洲主流联赛，作为影子特征加 ablation 对照，不替换现有任何信号。
3. **阵容覆盖**：先做 API-Football 现有覆盖审计，再决定是否采购第二家；总控拉取时点从 T-1 改为 T-40/T-20。

## 8. 待实测确认清单

- [ ] SportMonks xG add-on 的价格档位与"xG 覆盖哪些联赛"的准确清单（含是否有历史深度限制）。
- [ ] TheStatsAPI 的 xG 联赛覆盖表与历史深度。
- [ ] football-data.org Deep Data 是否覆盖任何亚洲联赛。
- [ ] API-Football 阵容在竞彩实际联赛（日职/K 联赛/中超/北欧/南美）的可得率与最早可用时点。
- [ ] 国内数据商（火星/纳米/蚂蚁/飞鲸）报价、亚洲联赛阵容覆盖与推送时效。
- [ ] 球场坐标表在竞彩涉及联赛上的命中率（这是 §4 能否成立的前提）。
- [ ] 各源是否允许用于博彩相关用途。

## 参考

- FBref 高级数据移除（2026-01-20，Opta/Stats Perform 终止供给）：[statpair.com 对比](https://statpair.com/blog/best-xg-websites-2026-comparison)、[theixsports 报道](https://www.theixsports.com/the-ix-soccer/fbrefs-loss-advanced-stats-womens-soccer-data-accessibility/)、[xglab 说明](https://xglab.io/fbref-alternative)
- SportMonks xG add-on 与套餐：[xG Data API](https://www.sportmonks.com/football-api/xg-data/)、[Football API 套餐](https://www.sportmonks.com/football-api/)
- TheStatsAPI 定价：[Football API](https://www.thestatsapi.com/football-api)、[套餐对比](https://www.thestatsapi.com/compare/best-football-api)
- football-data.org：[定价](https://www.football-data.org/pricing)、[覆盖](https://www.football-data.org/coverage)
- API-Football 阵容时效（20–40 分钟）：[官方入门指南](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide)
- 国内数据商阵容接口示例：[火星数据足球阵容接口](https://0ubamojnmz.apifox.cn/api-253700029)、[蚂蚁体育 API 文档](https://www.kancloud.cn/esport/antscore/3195131)、[纳米数据](https://www.nami.com/zh/details/j3ry6iztqltnwe0)、[飞鲸体育数据](https://v1.feijing88.com/news/article-391.html)

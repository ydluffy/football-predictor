# 足球预测项目计划任务

项目目录：`E:\ball-match-prediction-system\football-predictor`

生产调度使用绑定当月总控对话的单一 heartbeat，直接运行于本地项目目录，不使用隔离工作树。独立 cron 仅保留为暂停的人工恢复模板，不得与总控同时启用。

## 单对话总控架构

为避免每次自动化运行都创建新的 Codex 对话，生产调度采用“每月一个总控对话 + 一个 heartbeat 自调度控制器”：

- 当月所有预扫描、开售确认、动态终版、复盘和月度回顾都回复到同一个总控对话。
- 项目文件和任务注册表是唯一长期状态；聊天记录仅作为当月控制面，不得成为唯一数据来源。
- 控制器自动化 ID 以 `artifacts/data/football_automation_controller_state.json` 的 `controller_automation_id` 为准，不得在文档或脚本中写死。每次运行结束必须从注册表计算下一次最早任务，并更新该控制器自身的下一次唤醒时间，不得创建新的 cron 对话。
- 动态终版任务只写入 `sporttery_task_registry_YYYY-MM-DD.json`，由控制器依次执行；不再为每个时间组创建独立 Codex 自动化。
- 自身重排失败时写入 `artifacts/data/football_automation_controller_state.json` 的 `pending_reschedule`，保留旧的暂停任务作为人工恢复模板，不得谎报已安排。
- 月度滚动成功前不得归档旧总控；新总控创建、控制器迁移和交接文件三项都成功后，才归档上月对话。

控制器阶段顺序为：`10:00 预扫描 → 11:05 开售确认 → 13:00 复盘 → 注册表中最早终版 → 工作日 21:00/周末 22:00 兜底 → 次日 10:00`。复盘只结算前一销售日既有方案，不得生成新的赛前投注方案；已过期任务只留档，不得补写投注方案。

当日存在 `artifacts/data/sporttery_daily_schedule_override_YYYY-MM-DD.json` 时，13:00 复盘之后的当日阶段改为按该文件及注册表 `run_at` 顺序执行，允许包含“早期基线分析”和“正式预测和投注方案”两类任务。早期基线只冻结官方赔率、可用外盘和分析基准，禁止生成或写入真实投注方案；正式阶段必须重新抓取、与对应基线比较并继续遵守官方在售、时效、硬锁、玩法覆盖、额度和重复入账闸门。用户给出的目标场次数与官方确认数不一致时，必须记录差异，只处理官方确认或后续刷新新增的在售比赛，不得补造场次。

## 项目文件衔接规则

每次计划任务开始时必须先读取：

- `docs/scheduled_tasks.md`
- `docs/model_upgrade_roadmap.md`
- `config/competitions.json`
- `config/prematch_data_sources.json`
- `config/the_odds_api_sport_keys.json`
- `config/handicap_margin_movement_v3.json`
- `data/mappings/team_aliases.json`
- `data/manual/prematch_intelligence.csv`
- `data/manual/sporttery_snapshot_index.csv`
- `data/external/outer_market_snapshots/history.csv`
- `data/manual/external_market_snapshot_history.csv`
- `data/manual/shadow_prediction_ledger_v2.csv`
- `data/manual/shadow_portfolio_ledger_v2.csv`
- `data/manual/fixed_odds_shadow_ledger.csv`
- `data/manual/betting_plan_ledger.csv`
- `artifacts/betting/betting_ledger_audit_latest.json`
- `artifacts/data/competition_coverage_audit_latest.json`
- `artifacts/data/the_odds_api_sporttery_latest.json`（存在时）
- `artifacts/data/handicap_market_movement_latest.json`（存在时）
- 最新 `artifacts/data/prematch_intelligence_coverage_*.json`
- 当天最新扫描报告
- 最新复盘报告

缺失文件或读取异常必须写入本次审计，不得凭空补造。每次运行结束都必须把结果写回 `artifacts/data/`、`artifacts/betting/` 或 `artifacts/reviews/`，供后续任务通过项目文件继续衔接。

## football-data.org 七联赛增量衔接

11:05 开售确认后运行 `scripts/import_football_data_org_europe_incremental.py`，日期范围覆盖北京时间销售日前一日至次日，用于英超、西甲、德甲、法甲、意甲、荷甲、葡超的赛程时间校验、赛果补强和积分榜/赛季阶段上下文。该数据源不能证明体彩在售、不能代替体彩赔率，也不能单独创建投注方案；接口失败必须降级并写入审计，不阻断体彩官方扫描。

13:00 复盘仍优先运行 `scripts/import_sporttery_results.py`。只有中国体彩官方赛果不可用时，才允许用 `scripts/import_football_data_org_results.py` 生成后备赛果；球队与开赛时间必须唯一映射，未完场、缺少90分钟比分、未匹配或歧义场次全部保持待核验。每月回顾可在七联赛增量命令中增加 `--include-teams` 刷新球队、教练与可用阵容基础资料；端点受套餐限制时标记 `partial`，不得用空表表示无人伤停或阵容完整。详细契约见 `docs/football_data_org_europe_incremental.md`。

## 场次与批次状态

场次只允许使用以下三种销售状态：

- `prelisted`：官网开售前预列；可用于发现候选比赛，但不得作为在售证明、不得生成投注方案、不得写台账。
- `on_sale`：11:05 后重新抓取四类玩法，比赛仍出现在官方销售窗口且赔率有效；只有该状态才能进入后续终版任务。
- `stopped`：预列或曾在售、但确认刷新时已消失、已停售或已开赛；只能观察和留档。

空批次分两种口径：10:00 空表仍属于 `prelisted` 阶段，只能表述为“开售前尚未发布”；11:05 确认仍为空时，批次才允许标记为 `no_matches`。

## 每日 10:00 开售前预扫描

- 名称：`体彩开售前预扫描`
- 时区：`Asia/Shanghai`
- 频率：每天 10:00
- RRULE：`FREQ=DAILY;BYHOUR=10;BYMINUTE=0;BYSECOND=0`

提示词：

> 在本地主目录 `E:\ball-match-prediction-system\football-predictor` 执行开售前预扫描，不使用独立工作树。先按“项目文件衔接规则”读取文件，再运行 `python scripts/run_sporttery_sales_window_scan.py scan --stage preopen --fetch`。允许读取官网预列 SPF/RQSPF、总进球、比分和半全场；所有场次状态只能是 `prelisted`。空表只能报告“开售前尚未发布”，不得报告“今日无比赛”。本阶段禁止创建后续终版任务、禁止生成投注方案、禁止写入台账。将 JSON 和中文报告写回 `artifacts/data/` 与 `artifacts/betting/`。

扫描脚本会自动将官方赔率和玩法文件归档到不可变快照仓库并更新 `sporttery_snapshot_index.csv`；自动化不得删除该归档，也不得用 latest 文件替代历史快照。

## 每日 11:05 开售确认与任务编排

- 名称：`体彩开售确认与任务编排`
- 时区：`Asia/Shanghai`
- 频率：每天 11:05
- RRULE：`FREQ=DAILY;BYHOUR=11;BYMINUTE=5;BYSECOND=0`

提示词：

> 在本地主目录 `E:\ball-match-prediction-system\football-predictor` 执行开售确认与任务编排，不使用独立工作树。先按“项目文件衔接规则”读取文件，找到当天最新 `preopen` 扫描，再运行 `python scripts/run_sporttery_sales_window_scan.py scan --stage confirm --fetch --previous-scan <当天最新preopen JSON>`。必须重新抓取 SPF/RQSPF、总进球、比分和半全场；仍确认在售的比赛标记为 `on_sale`，消失、停售或已开赛的标记为 `stopped`。只有本次仍为空时才标记 `no_matches`。确认命令默认以 `--the-odds-mode auto` 对 `on_sale` 场次按赛事路由 The Odds API，保存不可变原始响应、赔率长表、市场摘要、逐场同队同时间映射和哈希审计；外盘失败只降级并留档，不能改变体彩在售结论。读取脚本生成的任务注册表，对 `pending_schedule`、`failed`、`updated` 记录创建或更新同一本地主目录下的终版任务；成功或失败后必须用脚本 `task-status` 子命令回写同一记录。不得只报告“任务未安排”后放弃。确认扫描及外盘导入本身都不写投注台账。

开售确认及后续刷新如果取得外盘赔率，必须保留 `captured_at`、原始开赛时间和来源，不得只覆盖 latest 文件；无法证明早于开赛的快照不得进入历史研究。

The Odds API 的确认快照保存到 `data/external/the_odds_api_sporttery/snapshots/<时间戳>_confirm/`。逐场 `mapping_status` 只有在主客队规范名一致、开赛时间差不超过配置阈值且候选唯一时才是 `mapped`；`unmatched` 或 `ambiguous` 只能留档。`artifacts/data/the_odds_api_sporttery_latest.json` 只是最新审计指针，研究和复盘必须读取带时间戳的快照目录及 SHA-256，不能把 latest 当历史原件。

每次 The Odds API 或 API-Football 快照完成后必须运行 `scripts/build_unified_outer_market_history.py`。该命令把两类来源规范化到 `data/external/outer_market_snapshots/history.csv`，并把具备胜平负、主亚洲盘及2.5球大小盘的安全快照写入 `data/manual/external_market_snapshot_history.csv`。内外盘配对、盘口变化特征和影子预测只能读取这两份统一历史，禁止继续读取停更的单来源副本。脚本按 `record_id`/`snapshot_id + match_id` 去重，回灌归档不会制造重复样本。

动态终版必须在官方体彩终版刷新后，对本时间组最新扫描 JSON 再运行：

```powershell
.\.venv\Scripts\python.exe scripts\refresh_the_odds_for_sporttery.py `
  --scan-json artifacts\data\sporttery_sales_window_scan_YYYY-MM-DD_HHMM_confirm.json `
  --snapshot-type final
```

终版快照与确认快照必须分别保留。The Odds API 返回 `not_configured`、`source_failed`、`no_routed_sports`、`unmatched` 或 `partial` 时，报告要写明降级原因；不得循环消耗额度，不得用旧确认快照冒充终版，也不得因为外盘缺失提高模型权重或投注金额。The Odds API 永远不能证明中国体彩在售，不能授权台账写入。

外盘亚洲让球必须保留主队视角的精确 0.25 球盘口、主客赔率、机构、抓取时间和对应体彩 `match_id`。平半、半一、一球/球半等盘口不得提前合并成浅盘/中盘；同场同时间映射未通过时只能分别归档，不能生成内外盘差值特征。

终版分析在外盘快照归档后运行 `scripts/predict_sporttery_handicap.py`，读取 `artifacts/models/sporttery_handicap_margin_v1.joblib` 及其元数据，将输出 CSV 通过 `build_multi_play_betting_strategy.py --handicap-model-csv` 接入让球排序。`-1/-2` 模型权重固定为 25%，`+1/+2` 固定为 10%；模型不得单独触发投注或提高预算。外盘缺失、时间不安全、球队映射失败或赛事不在英超/西甲/德甲/法甲/意甲/荷甲/葡超训练域时，必须自动退回原体彩市场策略。

在上述生产流程完成后，以旁路方式运行 `scripts/predict_sporttery_handicap_shadow_v2.py --stage final --sales-day <销售日>`。v2 只能读取 `artifacts/models/sporttery_handicap_shadow_v2.joblib` 和 `deployment_mode=shadow_only` 的元数据，输出文件名必须带 `shadow_v2`，不得传入生产候选生成器、不得改变原方案、不得写 `betting_plan_ledger.csv`。

影子证据分为两层，不得再把“禁止真实入账”误解为“禁止留档”：

- 每次运行的全部比赛（包括 blocked 及原因）追加到 `data/manual/shadow_prediction_ledger_v2.csv`，形成不可变赛前预测证据；确认阶段使用 `--stage confirm`，只留预测，不产生虚拟方案。
- 只有终版 `--stage final`、独立模型概率完整且通过赔率、边际、串数和风险敞口闸门的候选，才以虚拟资金写入 `data/manual/shadow_portfolio_ledger_v2.csv`。同一模型同一比赛的 `candidate_id` 固定，重复运行不得重复累计。

纯市场概率、三串及以上、赔率超限或缺少独立模型概率时，组合层仍可输出0方案，但预测层必须保留记录。虚拟本金不是实际投注授权，两个影子台账均不得复制到 `betting_plan_ledger.csv`。

终版候选同时生成一个目标总赔率 `8.00`、允许区间 `[6.00, 10.00]`（含上下限）、最多四腿的“固定赔率观察”方案。它只能从低风险方向选择；同样落入区间时先选择腿数更少的组合，同腿数再选择最接近 `8.00` 的组合。找不到区间内组合时必须输出空方案，不得用区间外赔率凑数。该方案仅用于独立统计命中率、ROI和最大回撤，不占用稳健/价值方案预算，不得自动写入真实投注台账；至少累计50个已结算前瞻样本后再评估是否调整区间，100个样本前不得进入生产投注规则。

固定赔率观察方案只允许在终版运行后调用 `scripts/record_fixed_odds_shadow.py --plans-csv <终版方案CSV> --sales-day <销售日> --time-window <时间组> --analysis-at <北京时间ISO时间> --stage final --audit-output <固定赔率审计JSON>`，以2元虚拟注冻结到 `data/manual/fixed_odds_shadow_ledger.csv`。同一销售日和时间组使用固定唯一键，重复运行不得重复记录；每日赛果导入器自动结算该独立台账。确认阶段、预扫描阶段或区间内没有候选时不得留下注单记录。

所有首轮分析、动态终版和晚间兜底的中文报告及用户回复必须同时包含两个独立章节：`真实入账方案`与`固定赔率影子方案（不入账）`。真实方案章节显示本次新增、沿用或0入账及原因；影子章节显示选择、总赔率、2元虚拟注、预计虚拟返奖和留档状态。没有区间内影子组合时也必须保留该章节并说明未生成原因，不得因真实方案为0或影子方案不入账而省略。每日复盘回复同时显示固定赔率影子的累计样本、命中率、ROI和最大回撤。

## 用户反馈详细度契约

自动化阶段完成后的用户回复不得只给场次数和一句结论，必须在消息正文中提供可直接阅读的详细内容，不能要求用户自行打开附件才能知道结果；同时附上完整报告和 JSON 审计路径。

- 10:00 预扫描和 11:05 确认：列出当日完整比赛行程表，至少包含比赛编号、赛事、主客队、北京时间开赛时间、销售状态、让球、SPF/RQSPF 是否可用、总进球/比分/半全场覆盖情况、所属终版时间组和硬锁时间。确认相对预扫描的新增、消失或停售场次必须单独列出。
- 早期分析和终版：先给逐场预测表，至少包含主要胜平负方向、让球方向、总进球区间、参考比分、半全场倾向、关键赔率、相对上一快照的变化、风险标记、数据缺口和置信等级。不得把市场赔率方向表述成确定赛果。
- 方案展示：在数据允许时尽量生成并展示多种用途的候选，包括稳健、价值、防冷、高赔观察、总进球、比分、半全场和固定赔率影子；每个方案须列出逐腿选择与赔率、串关方式、注数/倍数、本金、组合赔率或范围、预计返奖、净收益区间、主要风险和是否入账。候选方案数量可以增加，但真实生产入账上限保持最多 1 个稳健和 1 个价值、每个不超过 100 元；其余必须明确标为观察/影子且不得写真实台账。
- 若某类方案因玩法覆盖、赔率区间、模型概率、时效或风控不足未生成，仍须保留该分类并写明原因，不能省略。
- 复盘：先列上一销售日全部比赛的 90 分钟赛果表，再对每个真实与影子方案逐腿核验，标出每腿命中/未中、导致断票的腿、返奖、净收益和 ROI；随后汇总当日、累计、按方案类型、按玩法和按时段的命中率/ROI，并列固定赔率影子的累计样本、命中率、ROI和最大回撤。最后给出错误归因和下一轮可执行改进，但不得用赛后信息回写赛前预测。
- 用户后续提供的示例方案只用于学习方案结构、分层、表达和风险展示；未经用户明确授权，不得放宽官方在售、时间硬锁、额度、防重复或真实入账上限。

若已配置 `API_FOOTBALL_KEY`，11:05确认阶段调用 `scripts/import_api_football_daily_intelligence.py --scan-json <确认扫描JSON> --date <销售日> --stage confirm`；动态终版阶段对本时间组扫描调用同一脚本并使用 `--stage final`。脚本只接受球队和开赛时间唯一匹配、且观测时尚未开赛的外部 fixture。确认阶段尝试伤停与最近7日日历；任一日历日期受套餐拒绝时不得写零负荷，并调用 `scripts/import_football_data_org_schedule_load.py` 生成账户可访问赛事范围内的七天负荷后备。终版阶段刷新伤停和确认首发。未配置凭据、接口不覆盖、匹配缺失/歧义时只记录 skipped/unmapped，不得人工猜测 fixture ID。每次审计记录每日/每分钟剩余额度；Free 套餐应优先保障终版刷新，禁止对同一场次无节制循环请求。API 自带 predictions 只能旁路比较，不得作为独立模型概率、训练标签或投注触发器。

API-Football 亚洲让球快照统一调用 `scripts/import_api_football_odds_snapshot.py --scan-json <确认扫描JSON> --date <北京时间日期>`。脚本一次取得当天赛程并与全部体彩场次按球队及开赛时间唯一匹配；需要限制单项赛事时才增加 `--league-id <赛事ID>`。Free 套餐不允许直接查询当前赛季历史参数，因此禁止改用不可用的赛季历史参数。原始 JSON 写入 `data/external/api_football_odds/raw/`，全量替代盘写入 `snapshots/`，累计历史写入 `history.csv`；同一快照另生成 `_primary.csv`，每家机构只保留赔率最均衡且价格差阈值通过的主盘口。全量替代盘可用于价格曲线研究，但生产模型默认只能读取 `eligible_for_primary_research=true` 的主盘口行。开赛后、映射歧义、开赛时间缺失、非四分之一盘口全部只归档不研究。

每次 API-Football 亚洲盘快照成功后，运行 `scripts/build_handicap_market_movement_features.py`。该脚本按同一 `match_id` 和快照时间聚合多家机构中位数，输出开盘/最新主队让球、去水概率、升退盘幅度、每小时变化速度，以及“胜赔变热但盘口不足”“升盘但水位不支持”等背离标记。只有至少两个赛前安全快照的场次才标记 `safe_for_shadow_features=true`。这些字段当前只进入 v3 影子研究，`production_probability_change_allowed=false`、`stake_increase_allowed=false`；不得直接把亚洲盘赢盘解释成体彩让胜。

每次体彩官方快照和外盘快照均归档后，必须运行 `scripts/audit_inner_outer_market_alignment.py`。同一体彩 `match_id` 只算身份配对；两边 `captured_at` 相差不超过30分钟且都早于开赛才算时间对齐。审计输出固定写入 `artifacts/data/inner_outer_market_alignment_latest.csv/json`。时间差超过阈值的记录可以保留做来源覆盖审计，但不得进入内外盘差值训练；至少300个不同比赛达到时间对齐前，v2的历史赔率闸门保持未通过。

### 开售确认后的当日任务编排

11:05 确认完成后，只根据 `on_sale` 比赛的开赛时间和停售时间，为每个有效时间组创建或更新后续终版任务：

- 常规比赛：安排在开赛前 90-60 分钟刷新官方赔率并完成终版分析、预测和投注方案判断。
- 次日凌晨比赛：安排在前一晚停售前完成；工作日不得晚于 21:00-21:45，周末不得晚于 22:00-22:45。
- 每个任务唯一键固定为 `销售日 | 时间组 | 用途`，例如 `2026-08-05|00:30-02:00|终版分析`。重复扫描只能更新同一记录和同一任务，不得重复创建。
- 后续任务必须选择本地项目主目录，不使用独立工作树；开始时遵守“项目文件衔接规则”，结束后写回审计、报告及符合闸门的台账变更。
- 没有可售比赛、已停售、已开赛或官方赔率不可用时，不创建可入账方案，只生成 no-action/观察记录。
- 每日注册表为 `artifacts/data/sporttery_task_registry_YYYY-MM-DD.json`，状态只允许 `scheduled`、`updated`、`completed`、`pending_schedule`、`failed`。
- 调度接口失败时写入 `pending_schedule` 或 `failed`；下一次 11:05、13:00 或晚间兜底任务必须运行 `python scripts/run_sporttery_sales_window_scan.py retry --sales-day YYYY-MM-DD` 并重试，成功后回写同一记录。

## 每日 13:00 昨日复盘

- 名称：`每日体彩投注复盘`
- 时区：`Asia/Shanghai`
- 频率：每天 13:00
- RRULE：`FREQ=DAILY;BYHOUR=13;BYMINUTE=0;BYSECOND=0`

提示词：

> 在本地项目 `E:\ball-match-prediction-system\football-predictor` 执行每日 13:00 复盘。只复盘前一销售日已经留档的预测和投注方案，不生成新的赛前投注方案。先读取 `data/manual/betting_plan_ledger.csv`、对应日期的扫描/投注报告、任务注册表和最新复盘报告；先运行注册表 `retry`，对前一销售日及当天仍为 `pending_schedule`、`failed`、`updated` 的未过期任务尝试补建并回写结果。优先使用 `scripts/import_sporttery_results.py` 或中国体彩官方赛果，按 90 分钟赛果核验。体彩销售日跨越次日凌晨：带 `--ledger` 结算时导入器会自动把查询结束日扩展一天，并且每张方案只允许匹配其销售日及次一自然日的赛果；不得再把销售日直接等同于比赛自然日。更新台账的结果、返奖、净收益、ROI 和复盘说明，避免重复结算；部分命中和拆票方案逐项结算。生成 `artifacts/reviews/` 下的中文复盘报告，并汇总总体、按玩法和按时段 ROI。官方赛果不可用时明确标记待核验，不得猜测入账。

体彩赛果 CSV 生成后必须额外运行 `scripts/settle_shadow_evidence_v2.py --results-csv <官方赛果CSV> --settled-at <北京时间>`。该命令只更新影子预测结果和虚拟方案返奖，输出 `artifacts/data/shadow_evidence_settlement_latest.json`，汇总已结算影子方案数、虚拟ROI及最大回撤；它不得写真实投注台账。未找到唯一官方赛果的预测保持 pending，禁止猜测结算。月度v3晋级计数只认影子方案台账中 `result=hit/miss` 的赛前冻结记录。

## 晚间终版分析硬闸门

10:00 预扫描只发现官网预列，11:05 开售确认才确定当日销售窗口；两者都不能替代停售前的终版刷新。每个时间组必须按该组最早开赛时间设置独立截止：默认终版开始为最早开赛前90分钟、硬锁为最早开赛前15分钟、销售截止不得晚于最早开赛；跨天晚场才使用工作日21:00-21:45（周末22:00-22:45）的销售日兜底窗口。用户指定更早的分析时点时，应将该时点作为 `--decision-start`，同时传入本组的 `--decision-lock` 和 `--sales-cutoff`。窗口锁定后不得新增方案。

完成官方 SPF/RQSPF 与总进球、比分、半全场刷新后，运行：

```powershell
.\.venv\Scripts\python.exe scripts\check_evening_final_analysis_gate.py `
  --official-markets data\manual\sporttery_handicap_markets_YYYY-MM-DD_HHMM.csv `
  --play-odds data\manual\sporttery_play_odds_YYYY-MM-DD_HHMM.csv `
  --matches 001,002,003 `
  --decision-start <本时间组分析开始时间> `
  --decision-lock <本时间组最早开赛前15分钟> `
  --sales-cutoff <本时间组最早开赛时间或更早官方停售时间> `
  --require-ready
```

退出码为 0 且报告中 `may_create_plan=true` 才能进入最终组合环节。该闸门本身只读，不会自动写台账。台账可另行运行 `scripts\audit_betting_ledger.py --fail-on-errors` 做一致性检查。

## 晚间终版恢复模板

以下两个旧独立任务仅作为暂停恢复模板。正常情况下由单 heartbeat 总控依据日期执行相同逻辑；只有总控故障并经人工确认后才可临时启用其中一个：

- `体彩晚间终版分析（工作日）`：`FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=21;BYMINUTE=0;BYSECOND=0`
- `体彩晚间终版分析（周末）`：`FREQ=WEEKLY;BYDAY=SA,SU;BYHOUR=22;BYMINUTE=0;BYSECOND=0`

提示词：

> 在本地项目 `E:\ball-match-prediction-system\football-predictor` 执行停售前晚间终版分析。先读取当天 11:05 开售确认、The Odds API 确认快照审计、任务注册表、`data/manual/betting_plan_ledger.csv`、`artifacts/betting/betting_ledger_audit_latest.json` 和最新复盘报告；先运行注册表 `retry` 并补建仍为 `pending_schedule`、`failed`、`updated` 的未过期任务，回写同一记录。若当天确认没有 `on_sale` 场次或没有需要在停售前处理的凌晨场，只生成 no-action 审计并结束。否则重新抓取中国体彩 SPF/RQSPF、总进球、比分和半全场，并运行 `scripts/refresh_the_odds_for_sporttery.py --scan-json <本时间组最新扫描JSON> --snapshot-type final`；两类数据均禁止复用下午快照冒充终版数据。随后运行 `scripts/check_evening_final_analysis_gate.py --require-ready`。只有闸门允许、官方仍在售、预期场次和玩法覆盖完整、所有比赛尚未开赛时，才生成最终预测及最多 1 个稳健方案和 1 个价值方案，每个方案本金不超过 100 元，并追加台账。The Odds API 失败或未匹配时退回体彩市场基线，不能单独阻断官方在售确认，也不能授权或增加投入。21:45（周末 22:45）以后不得新增方案，只能核验与留档。数据源失败、赔率过期、场次消失或闸门未通过时全部降为观察。完成对应终版任务后把注册表状态更新为 `completed`。将最终中文报告和 JSON 审计写入 `artifacts/betting/` 与 `artifacts/data/`。

> 若当次已取得安全外盘快照，先生成盘口模型预测 CSV，再用 `--handicap-model-csv` 生成投注候选；报告必须列出模型状态、融合权重、预测让胜平负概率、推荐项和降级原因。不得删除“模型不能单独触发投注”的闸门。

终版分析取得经过核验的阵容、伤停、赛前强度/xG、跨赛事负荷或旅行信息时，按 `docs/prematch_intelligence_data_layer.md` 追加到 `data/manual/prematch_intelligence.csv`，必须记录 `observed_at`、`source_url` 和许可状态。缺失时只标记不可用，不得写零冒充“无伤停”或“阵容完整”；未经许可、开赛后发布或无法确定发布时间的信息禁止入表。赛前情报不足本身不阻断市场基线分析，但禁止据此宣称额外模型优势或提高投注金额。

若 `SPORTMONKS_API_TOKEN` 已配置，终版任务可将 SportMonks 作为补充源读取赛程、阵容、阵型、伤停和赔率，但只能处理账户订阅且已与体彩场次可靠映射的联赛。它不能替代中国体彩官方在售状态或官方赔率；当前套餐不含 SportMonks predictions/xGFixture，因此自动化不得请求、推测或填充这两类字段。原始响应时间、来源比赛 ID 和映射结果必须进入审计，映射失败时忽略该补充源。

若 `SERPAPI_API_KEY` 已配置，可用 SerpApi 搜索球队官网、联赛官网和可靠媒体的赛前伤停、停赛、预计阵容、轮换、旅行与赛程背景。SerpApi 只承担“候选来源发现”，搜索结果的标题、摘要、排名和第三方预测页不能直接写入模型特征或作为投注依据。必须打开原始页面，核验主体、发布时间、适用比赛和许可状态；通过核验后再按 `manual_verified` 规则入表。每场应限制查询次数并在审计中记录当次消耗，避免免费额度被重复任务耗尽。

追加后必须运行 `scripts/validate_prematch_intelligence.py`；分析代码只能读取验证输出，不得直接读取人工原表。动态终版再运行 `scripts/build_daily_prematch_features.py --scan-json <本时间组扫描JSON> --analysis-at <终版时间>`，把伤停、确认首发和七天负荷转换为逐场特征及可用性标记。验证出现拒绝记录时写入本次审计并忽略对应记录，不得为了通过闸门修改时间戳。当前数据只允许进入中文报告和影子研究，特征审计中的 `production_probability_change_allowed` 与 `stake_increase_allowed` 必须保持 false，直至最低历史覆盖门槛通过。

## 每月模型与投注策略回顾

每月 1 日在当日 13:00 复盘完成后，由当月总控执行上一个自然月的综合回顾，并生成：

- `artifacts/reviews/sporttery_monthly_review_YYYY-MM.md`
- `artifacts/data/sporttery_monthly_review_YYYY-MM.json`
- `artifacts/data/football_automation_handoff_YYYY-MM.json`
- `artifacts/data/competition_coverage_audit_latest.json`
- `artifacts/eval/season_context_v7_candidate_decision_YYYY-MM-DD.json`（存在候选评估时）

月度回顾至少拆分以下指标：数据源成功率、任务准时率、确认在售覆盖率、弃投率、玩法/联赛/时段 ROI、命中率、赔率区间表现、最大回撤、概率校准、Brier score/log loss（存在预测概率时）、收盘线价值（存在终版与早盘快照时），并明确区分“模型判断失败”和“数据/调度执行失败”。

2026年9月起每月总控必须使用独立生产对话，名称采用“足球预测生产总控（YYYY-MM）”。2026-09首次迁移任务固定在2026-09-01的13:00复盘和2026-08月度回顾完成后执行，具体审计读取 `artifacts/data/football_controller_migration_schedule_2026-09.json`。迁移期间仍只允许一个ACTIVE heartbeat；新总控创建、交接文件读取、控制器目标线程迁移和下一次唤醒验证全部成功前，旧总控不得归档。

月度回顾同时运行 `scripts/run_asian_handicap_research.py` 或读取其最新输出，按精确盘口、联赛和赛季检查样本量、全赢/半赢/走盘/半输/全输及机械基准 ROI。只有同场同时间内外盘配对达到训练门槛后，才允许评估盘口差值候选特征。

月度回顾同时运行 `scripts/run_handicap_margin_movement_v3.py`，使用扩展赛季顺序留出比较 v3 与当前 v2。v3 必须先输出净胜球分布（主队不胜、赢1球、赢2球以上），再按体彩整数让球映射让胜/让平/让负。历史开盘—终盘数据只属于方法代理验证；生产晋级仍要求至少300场体彩时间对齐事件、300个独立已结算影子方案、竞彩赔率下ROI/风险收益和最大回撤均不退化。任一闸门失败时只继续积累影子特征，不修改生产模型或预算。

同时运行 `scripts/audit_prematch_intelligence_coverage.py`，按联赛汇总阵容、伤停、赛前强度、跨赛事赛程、旅行和时间戳覆盖。未达到 `docs/prematch_intelligence_data_layer.md` 的最低覆盖条件时，不得启用新增信息模型。

模型优化采用候选晋级制：

1. 先冻结当月生产基线，任何结果不得反向改写历史预测。
2. 生成候选参数、特征或策略，只在研究配置中评估。
3. 使用时间顺序 walk-forward/赛季留出回测，禁止随机打乱造成未来信息泄漏。
4. 至少有 50 个已结算方案、受影响分组至少 20 个样本，且校准、收益风险比和最大回撤没有实质退化，候选才可自动晋级为下一月配置。
5. 样本不足、只有 ROI 提升、或提升来自单一高赔率结果时，只输出建议，不自动修改生产配置。
6. 所有晋级必须带测试、基线对比、回滚点和中文变更说明。

回顾完成后创建下一月份的本地总控对话，读取交接 JSON，随后把唯一 heartbeat 控制器迁移到新对话。迁移失败时继续使用旧总控并在次日 10:00 重试，禁止同时启用两个控制器。

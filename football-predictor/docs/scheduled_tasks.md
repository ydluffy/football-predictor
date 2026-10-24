2026-10-18 18:38全批修复：build_multi_play_betting_strategy.py现在评估过滤后输入全批，旧--max-matches 3不再截断分析。须核对策略input_rows/match_rows与注册场次；缺赔率逐场说明，不能把截断误报缺赔率。原空回执如因范围遗漏错误产生，只允许未过硬锁且原两卡均0时使用record_formal_batch.py --correct-empty-scope --prior-strategy-audit <原策略审计>生成独立_scope_correction回执；原文件和预测保留，非空票不得改写。

2026-10-18用户授权优先规则：每批稳健/价值各100元虚拟预算，取消旧每日各一份限制。完整读取docs/formal_batch_simulation.md与config/formal_simulation_policy.json。每批正文及审计必须展示两张卡，证据不足保留空卡/投入0/原因，禁止凑票或补写历史。终版必须经scripts/record_formal_batch.py按规范batch-key入账并保存回执，禁止历史runner的每日plan_type过滤及手工追加。价值来源及独立覆盖单列，不冒称已验证正EV；复盘按批次和类型核算再汇总全日实际投入。

# 足球预测项目计划任务

2026-10-17调度事故修复：TZID规则在当前桌面运行时出现8小时偏移，文本及dateutil回读不能证明应用执行时间。每次受支持接口更新及view后，必须运行scripts/verify_controller_runtime_schedule.py，核对只读sqlite的next_run_nominal_at与目标北京时间精确一致（next_run_at允许5分钟抖动）。当前使用UTC DTSTART及UTC小时，核验失败保留pending_reschedule=true；不得直接修改数据库/toml。详见docs/controller_heartbeat_prompt.md。机器待机或应用未运行仍可能阻止实际唤醒。

2026-10-12新增独立研究必读：docs/independent_comparison_controller.md。每批终版新增run_independent_comparison.py freeze，次日复盘新增settle；模型、市场和固定融合同条件对照，原正式策略保留。仍使用唯一心跳，已有下一唤醒时间不因流程升级改变。

项目目录：`E:\ball-match-prediction-system\football-predictor`

2026-10-02新增授权的宽松模拟研究层见 `docs/october_simulation_protocol.md`。所有正式终版后在硬锁前冻结新研究方案，次日复盘结算；研究层不沿用正式概率/价格/数量筛选，但保持赛前数据和时间真实性。现有正式策略保留为基准，不因模拟方案增加而宣称模型已经晋级或真实资金可用。唯一心跳和国庆恢复时间不变。

生产调度使用绑定当月总控对话的单一 heartbeat，直接运行于本地项目目录，不使用隔离工作树。独立 cron 仅保留为暂停的人工恢复模板，不得与总控同时启用。

## 单对话总控架构

为避免每次自动化运行都创建新的 Codex 对话，生产调度采用“每月一个总控对话 + 一个 heartbeat 自调度控制器”：

- 当月所有预扫描、开售确认、动态终版、复盘和月度回顾都回复到同一个总控对话。
- 项目文件和任务注册表是唯一长期状态；聊天记录仅作为当月控制面，不得成为唯一数据来源。
- 控制器自动化 ID 以 `artifacts/data/football_automation_controller_state.json` 的 `controller_automation_id` 为准，不得在文档或脚本中写死。每次运行结束必须从注册表计算下一次最早任务，并更新该控制器自身的下一次唤醒时间，不得创建新的 cron 对话。
- 动态终版任务先写入 `sporttery_task_registry_YYYY-MM-DD.json`，再由控制器把**下一次**执行时间更新到同一个桌面端心跳并回读；注册表本身不是定时器，不再为每个时间组创建独立 Codex 自动化。
- 自身重排失败时写入 `artifacts/data/football_automation_controller_state.json` 的 `pending_reschedule`，保留旧的暂停任务作为人工恢复模板，不得谎报已安排。
- 唤醒采用事件驱动：每天从 10:00 预扫描、11:05 确认开始；11:05 根据实际在售赛程生成当天注册表，之后同一 heartbeat 每次只排到下一项 `run_at`。不得保留无任务的半小时或整点轮询；当日队列清空后排到次日 10:00。
- 月度滚动成功前不得归档旧总控；新总控创建、控制器迁移和交接文件三项都成功后，才归档上月对话。

控制器阶段顺序为：`10:00 预扫描 → 11:05 开售确认 → 13:00 复盘 → 注册表中最早终版 → 工作日 21:00/周末 22:00 兜底 → 次日 10:00`。长期运行提示词见 `docs/controller_heartbeat_prompt.md`，不得用带过期“下一任务”的单日流水替换。复盘只结算前一销售日既有方案，不得生成新的赛前投注方案；已过期任务只留档，不得补写投注方案。

当日存在 `artifacts/data/sporttery_daily_schedule_override_YYYY-MM-DD.json` 时，13:00 复盘之后的当日阶段改为按该文件及注册表 `run_at` 顺序执行，允许包含“早期基线分析”和“正式预测和投注方案”两类任务。早期基线只冻结官方赔率、可用外盘和分析基准，禁止生成或写入真实投注方案；正式阶段必须重新抓取、与对应基线比较并继续遵守官方在售、时效、硬锁、玩法覆盖、额度和重复入账闸门。用户给出的目标场次数与官方确认数不一致时，必须记录差异，只处理官方确认或后续刷新新增的在售比赛，不得补造场次。

## 项目文件衔接规则

### 外部方案影子对照（2026-09-04 登记）

正式终版及复盘阶段读取 `docs/external_structure_shadow_20260903.md`，按其中冻结、可比性和独立输出规则执行结构影子对照。仅覆盖登记后的未锁定批次，缺输入记录跳过，不补造历史前瞻记录。用户9月3日四组票登记在 `data/manual/external_shadow_2026-09-03.json`，全部为回顾性案例，不计前瞻收益或生产晋级。时间敏感的正式工作优先；影子失败只报独立状态，不影响生产，不新增自动化。

### 阶段完成后数据同步与失败补偿（2026-09-04 起）

同一个本地总控负责同步，不新增 cron 或独立总控。先完成并落盘生产工作，再执行同步；数据库展示失败不回滚预测、不阻断下一阶段，不修改正式投注台账。

- 11:05确认/迟采确认完成后：`.\.venv\Scripts\python.exe scripts/sync_if_stale.py --stage confirm --sales-day YYYY-MM-DD`。
- 每批早期分析、动态终版或晚间兜底完成后：同命令使用 `--stage analysis`，销售日为本批实际销售日。
- 13:00复盘完成后：同命令使用 `--stage review`，销售日为被复盘日，不是当前自然日。此模式不重写历史赛前预测。
- 每次更新总控状态和下一次心跳后：同命令使用 `--stage controller --sales-day <当日>`，将最新编排同步到网页。
- 每次唤醒在处理时间敏感的采集/终版任务之后，按上面阶段对本次唤醒涉及的每个销售日各跑一次同一命令；若还需覆盖不属于本批的遗留日期，再用 `run_controller_data_sync.py --retry-pending` 兜底。紧邻硬锁时优先生产任务，同步延后，不为重试新增高频唤醒。

#### 一天的数据分批采集/分批预测时的同步口径（2026-10-24 登记）

同一天常被拆成多批采集与预测，因此"要不要同步"不能靠记忆，必须由命令自判：批次收尾与唤醒收尾都只跑 `scripts/sync_if_stale.py`，它读取 `artifacts/data/controller_sync/outbox.json`，比对"该销售日的本地产物最新 mtime"与"该阶段各步骤上次验证通过的落库时间"——产物更新过或任一步骤从未成功，才委托 `run_controller_data_sync.py` 发请求；否则只打印 `up_to_date` 且不发任何请求。委托对象按销售日全量重推，本来就幂等，所以每批收尾重跑同一命令即可补齐差额，不需要新增定时任务或增量协议。本地还没有该销售日产物时判为 `no_local_artifact` 并跳过（同步也无数据可发），产物出现后自然会被判为待同步。`--force` 可跳过自判直接同步，只用于人工干预。判不准时宁可多同步一次，绝不漏同步：漏了页面上就永远缺这批数据。

### 市场信号同步（2026-10-01 登记，2026-10-21 加门禁）

`confirm` 与 `analysis` 阶段自登记起额外包含 `market` 步骤：读取 `data/processed/handicap_market_movement_latest.csv` 与 `artifacts/data/inner_outer_market_alignment_latest.csv`，**只取本次销售日当天的行**（movement 按 `match_id` 前缀、alignment 按 `sales_day`），经 `/api/automation/sync-market` 按“主客队名 + 北京时间开赛日期”匹配到当日 fixtures 后写入 `fixture_market_intel` 表；变盘明细同样只取该销售日的捷报快照。网页端 `/api/market-intel` 已改为优先读该表，本地 CSV 仅作本地开发回退。首次使用前需在 Supabase 执行一次 `supabase/migrations/add_fixture_market_intel.sql`。

movement 产物的主客队名必须是中文：远端 `fixtures` 存中文名，而 `history.csv` 里同一场比赛可能同时存在 API-Football 英文行与中文行，取错就只会在服务端静默落到 0 行。因此构建器会用 `data/mappings/team_aliases.json` 把仅含拉丁字母的队名换成该表登记的中文名，已含中文的队名保持原样；队名口径仍不一致时按上条降级处理，不得当作成功。

两个 latest 别名由独立构建器刷新，同步链路本身不重建它们，因此发送前必须做新鲜度门禁：任一产物覆盖的最新销售日早于本次销售日时，不发请求，记录 `stale_local_artifact` 与各自 `newest_day`，该步骤保持待同步。请求发出后即使上游回 `verified`，只要“收到行数 > 0 且匹配到 fixtures 的行数为 0”，必须降级为 `market_rows_unmatched` 失败，不得记成功。只有两个产物都确实没有该日数据（收到 0 行）时才允许视为无信号。

`2026-10-21` 曾因 movement latest 停更在 `2026-08-27` 而出现“HTTP 200 + 回读通过但 0 行入库”的假成功，故登记本条门禁并一次性重建产物；不得把该次重建解释为允许日常默认回填。

需要连产物一起刷新时使用 `--rebuild-market`（仅允许配合含 `market` 步骤的 `--stage`）：先依次运行 `scripts/build_handicap_market_movement_features.py` 与 `scripts/audit_inner_outer_market_alignment.py` 刷新两个 latest 别名，再进入同步；重建失败时不入队并退出码 3。日常心跳不得默认开启该开关。重建后也可用 `--stage market --sales-day <当日>` 分项补同步；该步骤不改变任何预测、台账或生产结论。

日期必须显式指定；日常不得用默认40天历史回填。新增入口只导出冻结产物，不调用在线预测引擎；缺失快照不得伪造，预测来源时间保留原文件时间。`--dry-run` 只检查计划，不发网络请求、不写队列。

历史同步兼容 daily/full 两种复盘JSON；若仅有Markdown报告，也从已结算正式/固定赔率影子台账只读导出结构化摘要和逐票记录，附原CSV哈希。不得重新结算，不把导出时间冒充复盘发生时间，CSV重复票号或结构损坏时保留失败。台账原件不修改，Supabase仅为展示副本。

同步前探活本地写入服务：`/api/status` 必须返回本项目的 `env`/`supabase` 结构（只看状态码会把同端口上别的项目判成"已就绪"，本机 3000 的 IPv4 曾被另一项目的前端占用）。已在运行就直接复用且绝不关闭；未就绪时由同步脚本自行用 `node next dev -p 3100` 拉起，默认地址 `http://127.0.0.1:3100`（`--base-url` 可改），等待就绪（默认 180 秒，`--web-timeout` 可调），仅在本次由脚本拉起时才在结束回收该实例。必须是开发模式：生产模式（`next build` / `next start`）下 `localArtifactsEnabled()` 恒为 false，`/api/automation/*` 会全部 503，读写本地产物的步骤根本无法工作。固定用 3100 而不是 3000，是因为 3000 的 IPv4 常被其它项目占用；开发模式不需要 `next build`，`ALLOW_LOCAL_ARTIFACTS=true` 由 `web/.env.development.local` 提供。若本机已有手工启动的 dev 服务，用 `--base-url` 指向它复用，避免两个实例共用 `web/.next`。启动日志写入 `artifacts/data/controller_sync/web_autostart.log`，远端/CI 场景用 `--no-web-autostart` 关闭自拉起。仍需 Supabase 配置存在；凭据从环境变量或 `web/.env.local` 读取，禁止把密码放入命令行或报告。服务不可用或自拉起超时则保留待同步状态，不能声称网页已更新；不自动开放公网端口。每次同步结束把健康度（`at` / 是否成功 / 待补偿数 / 最近失败原因）POST 到 `/api/automation/sync-health`，并入 `automation_controller_state.payload.last_sync` 供总控页只读展示；该上报失败只影响展示，不改变同步结论。

队列：`artifacts/data/controller_sync/outbox.json`；逐次审计：同目录 `run_*.json`；最新摘要：`latest.json`。每个销售日/步骤唯一，网络请求前持久化，写后独立数据库SELECT核对主键和字段；不允许仅凭HTTP成功判定。重复主键按最新证据去重。每次最多处理6个步骤，每个步骤瞬时最多2次请求，普通失败30分钟后可补偿，401/403延迟一天并提示核验配置。后续唤醒只补未完成步骤；新阶段落盘可以重新触发该日期同步。

`writer.lock` 保护单写入者；若进程异常留下锁，只能先核实不存在运行中的同步进程后人工清理，禁止盲删。队列损坏时保留原文件并报错，不能重置成空队列。退出非0时正文区分“生产已完成、数据同步待补偿”，报告待同步键及审计路径。

### 2026-09-04 起强制防漏排检查

每次结束前运行 `.\.venv\Scripts\python.exe scripts/next_controller_task.py`，合并每日10:00预扫描、11:05确认、13:00复盘、确有未完成比赛时的晚间兜底与前一日/当日/次日未完成注册任务，取最早合法时间更新唯一心跳。禁止用“明日复盘”覆盖更早的上午采集。该命令只选择任务，不会自动修改心跳；必须通过受支持的桌面端定时任务接口把同一 heartbeat 重排到唯一下一时间并回读验证，失败时记录 `pending_reschedule=true`、保留注册表 `pending_schedule`，不得宣称已安排。当日队列清空后，下一时间必须回到次日10:00预扫描，防止事件驱动链断开。

总控提示词必须长期保留完整流程，不能替换成仅某销售日某一任务。每次唤醒先检查今日是否已有确认快照；11:05后缺失时按实际时间补采并标明迟采，不伪造10:00/11:05快照，不补写过锁投注。13:00前不得把尚未到期复盘视为漏跑。

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

> 在本地主目录 `E:\ball-match-prediction-system\football-predictor` 执行开售确认与任务编排，不使用独立工作树。先按“项目文件衔接规则”读取文件，找到当天最新 `preopen` 扫描，再运行 `python scripts/run_sporttery_sales_window_scan.py scan --stage confirm --fetch --previous-scan <当天最新preopen JSON>`。必须重新抓取 SPF/RQSPF、总进球、比分和半全场；仍确认在售的比赛标记为 `on_sale`，消失、停售或已开赛的标记为 `stopped`。只有本次仍为空时才标记 `no_matches`。确认命令默认以 `--the-odds-mode auto` 对 `on_sale` 场次按赛事路由 The Odds API，保存不可变原始响应、赔率长表、市场摘要、逐场同队同时间映射和哈希审计；外盘失败只降级并留档，不能改变体彩在售结论。读取脚本生成的任务注册表，计算最早的未过硬锁任务，更新**同一个心跳**的下一次唤醒并回读；回读成功或失败后用 `task-status` 回写同一记录。不得把注册表 `pending_schedule` 当成已上线，也不得因更新接口缺失而静默放弃。确认扫描及外盘导入本身都不写投注台账。

开售确认及后续刷新如果取得外盘赔率，必须保留 `captured_at`、原始开赛时间和来源，不得只覆盖 latest 文件；无法证明早于开赛的快照不得进入历史研究。

The Odds API 的确认快照保存到 `data/external/the_odds_api_sporttery/snapshots/<时间戳>_confirm/`。逐场 `mapping_status` 只有在主客队规范名一致、开赛时间差不超过配置阈值且候选唯一时才是 `mapped`；`unmatched` 或 `ambiguous` 只能留档。`artifacts/data/the_odds_api_sporttery_latest.json` 只是最新审计指针，研究和复盘必须读取带时间戳的快照目录及 SHA-256，不能把 latest 当历史原件。

每次 The Odds API 或 API-Football 快照完成后必须运行 `scripts/build_unified_outer_market_history.py`。该命令把 The Odds API、API-Football 及已采集的捷报亚洲让球快照规范化到 `data/external/outer_market_snapshots/history.csv`，并把具备胜平负、主亚洲盘及2.5球大小盘的安全快照写入 `data/manual/external_market_snapshot_history.csv`。内外盘配对、盘口变化特征和影子预测只能读取这两份统一历史，禁止继续读取停更的单来源副本。脚本按 `record_id`/`snapshot_id + match_id` 去重，回灌归档不会制造重复样本。

当 The Odds API 返回 `quota_insufficient`、`no_routed_sports`、`not_configured`、`source_failed`、`unmatched` 或 `partial` 时，确认扫描和终版刷新会自动运行 `scripts/capture_nowscore_market.py` 的捷报后备采集，同时保留原始失败状态和 `trigger_status`，不得用后备成功掩盖主来源故障。后备取得赛前合格报价时，审计另写 `effective_status=available_via_nowscore`、`effective_source=nowscore` 和覆盖数量；总控不得只读主来源 `status` 后误报“无外盘”。采集仅覆盖仍在售、未开赛且场次号、主客队与开赛时间唯一匹配的比赛，并限制运行时长；失败写入独立审计，不阻断体彩官方扫描或正式终版。捷报原始页、六类报价与亚洲让球标准化快照保存在 `data/external/nowscore/snapshots/`，统一外盘历史构建器纳入合格亚洲让球行。当前该来源仍是外盘数据与影子研究后备，不补写生产模型专用的完整特征历史，也不授权提高投注权重或金额；模型缺完整安全快照时继续体彩市场基线。若统一历史 CSV 被 Excel 等程序占用，构建结果写入 `artifacts/data/unified_outer_market_pending/` 并标记 `deferred_file_locked`，总控不得声称已更新主历史，后续任务需重试合并。

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

### 邪修方案：市场分歧观察（2026-09-07用户新增）

从登记后的下一批未锁定分析起，每次报告及用户回复必须增加“邪修方案（独立影子研究）”，每日复盘单列该类。执行详细规则见 `docs/contrarian_market_shadow.md`。没有合格信号也保留分类并说明空方案原因。不得回填历史赛前方案。

自动化阶段完成后的用户回复不得只给场次数和一句结论，必须在消息正文中提供可直接阅读的详细内容，不能要求用户自行打开附件才能知道结果；同时附上完整报告和 JSON 审计路径。

- 10:00 预扫描和 11:05 确认：列出当日完整比赛行程表，至少包含比赛编号、赛事、主客队、北京时间开赛时间、销售状态、让球、SPF/RQSPF 是否可用、总进球/比分/半全场覆盖情况、所属终版时间组和硬锁时间。确认相对预扫描的新增、消失或停售场次必须单独列出。
- 早期分析和终版：先给逐场预测表，至少包含主要胜平负方向、让球方向、总进球区间、参考比分、半全场倾向、关键赔率、相对上一快照的变化、风险标记、数据缺口和置信等级。不得把市场赔率方向表述成确定赛果。
- 方案展示：在数据允许时尽量生成并展示多种用途的候选，包括稳健、价值、防冷、高赔观察、总进球、比分、半全场和固定赔率影子；每个方案须列出逐腿选择与赔率、串关方式、注数/倍数、本金、组合赔率或范围、预计返奖、净收益区间、主要风险和是否入账。候选方案数量可以增加，但真实生产入账上限保持最多 1 个稳健和 1 个价值、每个不超过 100 元；其余必须明确标为观察/影子且不得写真实台账。
- 若某类方案因玩法覆盖、赔率区间、模型概率、时效或风控不足未生成，仍须保留该分类并写明原因，不能省略。
- 复盘：先列上一销售日全部比赛的 90 分钟赛果表，再对每个真实与影子方案逐腿核验，标出每腿命中/未中、导致断票的腿、返奖、净收益和 ROI；随后汇总当日、累计、按方案类型、按玩法和按时段的命中率/ROI，并列固定赔率影子的累计样本、命中率、ROI和最大回撤。最后给出错误归因和下一轮可执行改进，但不得用赛后信息回写赛前预测。
- 用户后续提供的示例方案只用于学习方案结构、分层、表达和风险展示；未经用户明确授权，不得放宽官方在售、时间硬锁、额度、防重复或真实入账上限。

若已配置 `API_FOOTBALL_KEY`，11:05确认阶段调用 `scripts/import_api_football_daily_intelligence.py --scan-json <确认扫描JSON> --date <销售日> --stage confirm`；动态终版阶段对本时间组扫描调用同一脚本并使用 `--stage final`。脚本只接受球队和开赛时间唯一匹配、且观测时尚未开赛的外部 fixture。确认阶段尝试伤停与最近7日日历；任一日历日期受套餐拒绝时不得写零负荷，并调用 `scripts/import_football_data_org_schedule_load.py` 生成账户可访问赛事范围内的七天负荷后备。终版阶段刷新伤停和确认首发。未配置凭据、接口不覆盖、匹配缺失/歧义时只记录 skipped/unmapped，不得人工猜测 fixture ID。每次审计记录每日/每分钟剩余额度；Free 套餐应优先保障终版刷新，禁止对同一场次无节制循环请求。API 自带 predictions 只能旁路比较，不得作为独立模型概率、训练标签或投注触发器。

API-Football 亚洲让球快照统一调用 `scripts/import_api_football_odds_snapshot.py --scan-json <确认扫描JSON> --date <北京时间日期>`。脚本一次取得当天赛程并与全部体彩场次按球队及开赛时间唯一匹配；需要限制单项赛事时才增加 `--league-id <赛事ID>`。Free 套餐不允许直接查询当前赛季历史参数，因此禁止改用不可用的赛季历史参数。原始 JSON 写入 `data/external/api_football_odds/raw/`，全量替代盘写入 `snapshots/`，累计历史写入 `history.csv`；同一快照另生成 `_primary.csv`，每家机构只保留赔率最均衡且价格差阈值通过的主盘口。全量替代盘可用于价格曲线研究，但生产模型默认只能读取 `eligible_for_primary_research=true` 的主盘口行。开赛后、映射歧义、开赛时间缺失、非四分之一盘口全部只归档不研究。

每次 `scripts/build_unified_outer_market_history.py` 成功后，运行 `scripts/build_handicap_market_movement_features.py`。该构建器读的是统一历史而不是 API-Football 快照，因此只在 API-Football 成功后触发是不足的：完全依赖捷报后备采集的日子同样必须重建，否则 `latest` 停更会让市场信号同步静默落空。脚本按同一 `match_id` 和快照时间聚合多家机构中位数，主客队名按上文中文口径归一，输出开盘/最新主队让球、去水概率、升退盘幅度、每小时变化速度，以及“胜赔变热但盘口不足”“升盘但水位不支持”等背离标记。只有至少两个赛前安全快照的场次才标记 `safe_for_shadow_features=true`。这些字段当前只进入 v3 影子研究，`production_probability_change_allowed=false`、`stake_increase_allowed=false`；不得直接把亚洲盘赢盘解释成体彩让胜。

每次体彩官方快照和外盘快照均归档后，必须运行 `scripts/audit_inner_outer_market_alignment.py`。同一体彩 `match_id` 只算身份配对；两边 `captured_at` 相差不超过30分钟且都早于开赛才算时间对齐。审计输出固定写入 `artifacts/data/inner_outer_market_alignment_latest.csv/json`。时间差超过阈值的记录可以保留做来源覆盖审计，但不得进入内外盘差值训练；至少300个不同比赛达到时间对齐前，v2的历史赔率闸门保持未通过。

### 开售确认后的当日任务编排

11:05 确认完成后，只根据 `on_sale` 比赛的开赛时间和停售时间，为每个有效时间组写入或更新注册表记录；然后只重排单一控制器心跳：

- 常规比赛：安排在开赛前 90-60 分钟刷新官方赔率并完成终版分析、预测和投注方案判断。
- 次日凌晨比赛：安排在前一晚停售前完成；工作日不得晚于 21:00-21:45，周末不得晚于 22:00-22:45。
- 每个任务唯一键固定为 `销售日 | 时间组 | 用途`，例如 `2026-08-05|00:30-02:00|终版分析`。重复扫描只能更新同一记录和同一任务，不得重复创建。
- 后续任务必须选择本地项目主目录，不使用独立工作树；开始时遵守“项目文件衔接规则”，结束后写回审计、报告及符合闸门的台账变更。
- 没有可售比赛、已停售、已开赛或官方赔率不可用时，不创建可入账方案，只生成 no-action/观察记录。
- 每日注册表为 `artifacts/data/sporttery_task_registry_YYYY-MM-DD.json`，状态只允许 `scheduled`、`updated`、`completed`、`pending_schedule`、`failed`。
- 调度接口失败时写入 `pending_schedule` 或 `failed`，同时设置控制器 `pending_reschedule=true` 并通知用户；下一次固定唤醒必须运行 `python scripts/run_sporttery_sales_window_scan.py retry --sales-day YYYY-MM-DD` 并重试，成功且回读后才回写 `scheduled`。任务硬锁已过则只留失败审计，不补写方案。

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

终版编排强制顺序：官方终版抓取 → `check_evening_final_analysis_gate.py --require-ready` → `build_multi_play_betting_strategy.py --stake 100` → `validate_final_orchestration.py` → 硬锁前幂等写正式台账 → 再生成固定赔率、邪修和其他影子方案。影子v2是旁路研究，任何 `blocked`/`shadow_eligible=0` 都不得覆盖正式策略审计。若门禁READY但缺少正式策略审计，本阶段必须标记失败而不是completed；若正式策略审计有 `production_plan_rows>0` 却未在硬锁前写台账，也必须标记失败并通知用户。100元是每个正式稳健/价值方案的标准本金上限，不因外盘缺失或影子模型阻断而自动缩成2元；2元只用于明确标记的影子方案。

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


2026-10-19用户授权优先修复：一次唤醒连续处理全部已到期且未过硬锁的注册终版批次，替代旧“每次只执行一项”。先运行scripts/next_controller_task.py --due-batches读取本轮队列；每批重新检查当前时间、身份、官方数据新鲜度及READY，不因共享快照绕过任何门禁。相同全页采集可共享原始档案，但逐批过滤市场/扫描、逐批生成READY和规范batch-key，禁止把8场混作一个批次或重复入账。每批立即落盘进度/冻结回执；单批失败保存失败原因后继续其他独立批次，禁止无界重试；临近锁时停止新增方案。所有本轮到期批次完成或留下失败审计后，再选择唯一下一任务并通过受支持接口重排、view及运行时核验。不得每完成一批就结束当前唤醒。今晚21:00依次处理001—002、003—007、008，保持各批稳健/价值卡和模型对照独立。

每批新增总进球0—6/7+八档及净胜球−4及以下至+4及以上九档：纯球队专用及通用后备由同一比分联合分布聚合，保存完整概率、期望值、模型ID和真实预测时间；无方案也冻结评分，覆盖失败逐场说明。scripts/run_independent_comparison.py及run_universal_comparison.py已接入，新冻结包含total_probability_*、expected_total_goals、expected_goal_margin；settle输出goal_distribution_review，记录Log Loss/Brier/有序RPS及最高档命中率。报告必须逐场展示上述分布，并在13:00汇总评分及缺失/待结算原因。旧冻结缺总进球不补算或回填；研究产物不改变正式概率/金额。市场增强模型仍未获上线资格，真实样本160<300；不得把纯球队输出标成市场增强输出。


2026-10-19后续优先规则：相同run_at、hard_lock、sales_cutoff的终版时间组，合并为一个规范注册批次；保留逐场开赛时间。不同销售/决策窗口不强行合并。build_task_records/group_on_sale_fixtures已实现，11:05生成任务采用新规则；不得拆组重复计额。今日001—008已合为2026-10-19|00:30-07:00|终版分析，旧三批归档且尚未冻结，不再执行旧三批。正式仅稳健/价值各100元上限，总计200元。

每批正文新增四张分账研究卡：市场胜平负基准、独立模型胜平负、独立净胜球映射整数让球、净胜球与市场固定50%融合；build_comparison自动生成research_cards。卡片仅是现有方向对照experiments的展示，引用原每组每玩法12元理论预算，严禁再次加总入账。专用及通用后备不同覆盖集合分开报预算和成绩，模型身份明确；无覆盖或缺报价显示空卡/原因，未验证EV不称真实优势。总进球仅预测评分，未接入总进球票据结算前不新增此类投注方案。报告与settle入口必须分别展示上述family的投入返奖ROI及概率误差，不混入正式SAFE/VALUE。

每次确认后及收尾运行scripts/audit_controller_readiness.py --sales-day <销售日> --output <独立审计JSON>；若确认后已有部分批次完成，按已冻结/终态排除后再核对剩余覆盖，不能将有效完成批次误报漏赛。任务完成必须有正式两卡回执、专用及通用研究冻结或明确失败/跳过、总进球/净胜球报告；缺项保留部分完成并从已冻结产物恢复，不重复出非空票。研究子进程最多180秒，超时落审计不阻断正式任务。当天队列清空后重排次日10:00并进行view及运行时核验；不依赖每日21:00规则自然恢复。


2026-10-21欧冠跨联赛概率研究（仅新批次）：已接入scripts/run_independent_comparison.py原freeze/settle入口，新建研究挂钩scripts/ucl_research_hook.py。配置config/ucl_domestic_research.json；先读取docs/ucl_domestic_phase5_20261021.md。两个候选elo_only与elo_domestic_form独立保存胜平负、总进球八档、净胜球九档，并在官方报价完整时保存SPF/RQSPF市场及固定50%融合概率。预算为0，不新增票，不改变原正式或研究金额。必须本批READY、相同完整批次、官方采集时效、真实预测时间、模型训练截止、稳定提供商球队ID与开赛时间匹配；国内历史每队至少5场、距最新不超过120天；提供商赛程归档超过24小时须刷新，否则记录失败，禁止沿用。当前预检004/007/009/010可覆盖，005/008/011/012因对手国内历史未覆盖跳过。预检不等于冻结。原冻结已存在时不补写该新队列；新冻结独立保存artifacts/data/ucl_domestic_comparison/，子进程180秒限时，失败不阻断生产但须在报告中说明。13:00原settle自动调用该队列settle-pending，按候选分别展示Log Loss/Brier/有序RPS；同场两个候选算一次独立事件。历史开发留出已查看过，尚无前瞻结论，不声称优于市场。当前16:30及21:00批次安排不因研究改变。

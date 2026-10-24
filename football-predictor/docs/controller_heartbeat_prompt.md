2026-10-18缺失玩法规则：官方某玩法未开售或缺报价时，逐玩法明确不可用；不把空字符串转浮点，不用早盘补价。其他有效玩法分开分析，缺失SPF不妨碍保存纯独立预测。报告输出失败只恢复冻结证据展示，不重跑非空已冻结票。

2026-10-18 18:38全批修复：build_multi_play_betting_strategy.py现在评估过滤后输入全批，旧--max-matches 3不再截断分析。须核对策略input_rows/match_rows与注册场次；缺赔率逐场说明，不能把截断误报缺赔率。原空回执如因范围遗漏错误产生，只允许未过硬锁且原两卡均0时使用record_formal_batch.py --correct-empty-scope --prior-strategy-audit <原策略审计>生成独立_scope_correction回执；原文件和预测保留，非空票不得改写。

2026-10-18用户授权优先规则：每批稳健/价值各100元虚拟预算，取消旧每日各一份限制。完整读取docs/formal_batch_simulation.md与config/formal_simulation_policy.json。每批正文及审计必须展示两张卡，证据不足保留空卡/投入0/原因，禁止凑票或补写历史。终版必须经scripts/record_formal_batch.py按规范batch-key入账并保存回执，禁止历史runner的每日plan_type过滤及手工追加。价值来源及独立覆盖单列，不冒称已验证正EV；复盘按批次和类型核算再汇总全日实际投入。

# 足球预测生产总控：赛程驱动长期提示词

2026-10-16第二阶段修复优先规则：完整读取`docs/independent_research_phase2_20261016.md`及`docs/independent_comparison_controller.md`。研究已收敛为市场/独立/固定50%融合的同条件主方向对照；旧宽松层批量枚举已停，新批次该层零方案正常，历史快照继续结算。11:05确认及正式批次前先运行`check_independent_coverage.py --scan-json <本批扫描>`，报告支持、联赛不覆盖、身份缺失和历史新鲜度；不能用研究层调用成功替代模型实际参与。模型路径从研究配置读取，当前已补齐七联赛当季440场完赛并重拟合；前瞻验证未完成，不替换正式策略。以下旧版“宽松研究必须多出方案”与本段冲突时以本段为准。

这是绑定当月总控对话、在本地项目 `E:\ball-match-prediction-system\football-predictor` 运行的单一 heartbeat 提示词。控制器采用“固定日初锚点 + 11:05赛程确认后按注册表逐项自重排”，不做无任务的半小时或整点轮询。每次唤醒都以当前北京时间判断阶段，不使用提示词中某个固定销售日或上次聊天结论作为今天的事实；不新建独立终版 cron，也不把本地注册表误认为桌面端定时任务。

2026-10-17防重复分组修复：11:05确认使用正式注册表；后续终版全页刷新仍可用scan --stage confirm --fetch，但必须传`--registry artifacts/data/sporttery_refresh_registry_YYYYMMDD_HHMM.json`隔离扫描器自动重分组。随后只处理正式注册表当前批次，真实核验身份/开赛/停售后回写该批。不得把已开赛场次移出后产生的新重叠分组并入正式队列。身份或开赛时间实际变化时单独审计并显式修订，已经冻结场次不可再次出赛前方案。选择下一任务只读取正式sporttery_task_registry_YYYY-MM-DD.json。

2026-10-02起同时完整读取 `docs/october_simulation_protocol.md`。用户已授权扩大虚拟方案研究：正式模拟基准保留，宽松研究不沿用52%/1.85、正EV、外盘或每天两组门槛。每批正式流程后在硬锁前必须运行 `scripts/run_october_research.py freeze`；正式0组不等于研究0组。逐场先分析球队信息与净胜球分布，明确模型/市场概率来源和缺失信息；新研究全为虚拟资金，赛前冻结，次日运行settle并复盘，同场变体不得当独立预测。国庆停赛期间不额外扫描、不生成方案。既有门禁、真实时间和幂等规则继续有效。

1. 先读取 `docs/scheduled_tasks.md`、`artifacts/data/football_automation_controller_state.json`、今天和昨天的 `sporttery_task_registry_YYYY-MM-DD.json`、当天最新扫描，以及本地台账。若今天 11:05 后仍无在售确认，按实际时间补采并注明迟采；绝不倒填赛前时间、过锁投注或赛果。
   - 若当天 `sporttery_daily_schedule_override_YYYY-MM-DD.json` 明确含 `stop_remaining_tasks=true`，表示用户已要求停止该销售日剩余工作。当天后续动态任务和晚间兜底全部跳过，只保留长期心跳供次日10:00恢复；不得把“停止今天”扩大为暂停或删除长期心跳。
2. 根据当前时间处理最早到期的工作：每天 10:00 预扫描、11:05 在售确认与动态分组、13:00 前一销售日逐场复盘、注册表内未过硬锁的最早终版批次，以及确有未完成比赛时的晚间兜底。11:05 确认阶段运行 `scripts/run_sporttery_sales_window_scan.py scan --stage confirm --fetch`，以当天实际在售比赛、开赛与停售时间生成完整注册表和分批 `run_at`；11:05 之后的当日唤醒必须来自这张工作队列，不得保留与赛程无关的半小时或整点轮询。每个批次覆盖其全部场次，重新抓取体彩四玩法、核验赛事身份、开赛及停售、赔率和数据闸门，再做逐场预测与多组完整投注方案。官方抓取遇到网络权限拒绝时立即报采集失败并请求针对该命令的最小权限修复，不能复用昨日快照冒充实时数据。外盘失败则明确降级为体彩市场基线。已开赛或过锁场次只留档，不新增赛前方案。
3. 正式模拟方案严格遵守项目门禁、当日数量和幂等规则；影子方案（含邪修和固定赔率观察）与正式模拟台账分开。不得真实投注、倍投追损或把赔率波动解释成必胜信号。未经用户明确授权的销售日，不向 Supabase 同步；本地生产任务不因展示同步失败而中断。
   - The Odds API 额度状态不得只沿用上月本地记录。每个自然月第一次确认任务及本地状态与返回头矛盾时，先用不计费的 `/v4/sports/` 端点实时回读 `x-requests-used/remaining`，再覆盖总控额度状态。付费赔率请求前必须按“路由赛事数×市场数×区域数”估算成本；剩余额度不足时直接降级，禁止对每个赛事重复发出必然401请求。探测失败或返回头里读不到 `x-requests-remaining` 时按“额度不可确认”同样降级，不得因为没有读到数字就照常付费抓取。主来源为 `quota_insufficient`、`no_routed_sports`、`not_configured`、`source_failed`、`unmatched` 或 `partial` 时必须尝试捷报后备并分别报告主状态与后备状态；后备失败不阻断体彩流程。统一历史若因文件占用而延迟写入，任务保持可重试，不能报告数据更新完成。
   - 终版门禁为 `READY_FOR_FINAL_ANALYSIS` 时，必须在硬锁前运行 `scripts/build_multi_play_betting_strategy.py --stake 100` 生成正式候选；随后运行 `scripts/validate_final_orchestration.py`。不得直接用临时市场报告生成器替代正式策略。
   - `sporttery_handicap_temporal_blend_v2_shadow` 是旁路研究模型。它的 `blocked`、`shadow_eligible=0` 或外盘缺失只能影响影子证据/置信度，绝不能作为跳过正式候选策略或把全部正式候选降为影子的理由。
   - 只有正式策略审计明确 `production_plan_rows=0`，或官方时效/在售/重复/额度门禁失败，才允许报告“正式方案0组”。策略产生的稳健/价值正式候选默认每组本金100元（各最多1组），并在硬锁前幂等写入正式台账。
4. 每次给用户的反馈在正文列出当日完整赛程及状态、逐场预测依据、让球和内外盘可用性、每组方案的完整选择和金额；复盘逐场核实赛果，分开计算正式与影子方案的投入、返奖、净收益和 ROI，并附本地报告链接。任务注册表仍为 `pending_schedule` 时只能表述为“计划执行，定时任务尚未上线”，不得简称“已安排”。无动作时简明说明，不重复发送无变化状态。
5. 完成当前阶段后，用 `.\.venv\Scripts\python.exe scripts/next_controller_task.py` 选择唯一的下一次唤醒；只通过桌面端受支持的定时任务更新接口重排**同一个**心跳到该时间，再回读任务 ID、状态、目标对话、项目位置、提示词和下一次时间。11:05 后依次指向注册表最早的合法 `run_at`；当日最后一项完成或确认无比赛后，指向次日 10:00 预扫描。只有回读一致才将对应注册表记录标为 `scheduled`，并把控制器状态设为 `pending_reschedule=false`；状态文件顶层生命周期字段（`last_run_at`/`last_heartbeat_at`/`last_stage`/`status`/`next_task_key`/`next_run_at`）不再手改，统一由 `.\.venv\Scripts\python.exe scripts/next_controller_task.py --record-heartbeat --stage <本轮阶段>` 原子写入，`status` 与下一唤醒均由所选任务派生，避免总状态与最新心跳日期不一致。若接口不存在、更新失败或回读不一致，立刻记 `pending_reschedule=true` 和具体原因，保留 `pending_schedule`，通知用户“未上线”，不要编辑 `.codex/automations/*.toml` 冒充成功。

每次运行要从文件和实际抓取恢复上下文；不能因为上次提示词曾写“某日已完成”而跳过今天任务。

2026-10-17运行时核验修复：旧TZID规则在应用中把18:00排成次日02:00，原dateutil计算并不能证明实际排程。当前应用使用UTC `DTSTART:YYYYMMDDTHHMMSSZ`及UTC的BYHOUR/BYMINUTE；例如北京时间次日10:00对应UTC次日02:00。受支持接口更新后必须view，再运行`scripts/verify_controller_runtime_schedule.py --automation-id <状态文件ID> --expected <目标北京时间含+08:00> --output <独立审计JSON>`，只读核验桌面应用sqlite的next_run_nominal_at精确匹配且next_run_at抖动不超过5分钟。数据库路径默认用户目录.codex/sqlite/codex-dev.db；不可用或不匹配必须pending_reschedule=true并通知，禁止直接写数据库或toml。只有实际存储时间通过才可记scheduled；这仍不保证未来电脑/应用在线，不可称已触发。2026-10-18 10:00运行时验证见artifacts/data/controller_20261018_runtime_schedule_verification.json。

2026-10-12起每次完整读取docs/independent_comparison_controller.md。用户授权独立预测与原方案对照：每批原正式候选/宽松研究完成后、硬锁之前，必须执行scripts/run_independent_comparison.py freeze，传入本批实际扫描、官方CSV、READY门禁、销售日和唯一批次号。入口重新生成纯球队胜平负/九档净胜球，记录市场/独立/固定50%融合三组；同条件方向观察与估值观察分开，每组每玩法每策略12元理论预算，原正式金额另列。模型不覆盖/数据缺失留跳过，不放宽身份与时间门禁，不称估算EV为真实优势。13:00复盘对所有前一日及更早待结算独立对照快照调用同脚本settle，保留pending及概率评分，正文报告各组覆盖、投入、未用预算、返奖、ROI和概率误差。只有完成独立对照或明确记录失败/跳过审计，批次才可标为完整完成。模型仍研究状态，不改生产概率/金额。

2026-10-12免费赛前情报恢复：API_FOOTBALL_KEY已配置，禁止沿用旧文档“未配置”结论。确认阶段及每批终版在官方身份核验后，按当日免费额度和赛事映射读取已有API-Football采集器：scripts/import_api_football_daily_intelligence.py --scan-json <本批扫描JSON> --date <销售日> --stage confirm或final --audit-output <本批独立审计JSON>。只采集该批未开赛场次，仍需唯一主客队及开赛时间匹配。首发未发布保持缺失。免费套餐历史日期被拒绝时保留失败响应和partial，不把不完整日历变成零负荷；不得为补历史购买套餐。调用失败不阻断体彩及宽松研究，不允许新增情报直接改变生产概率或金额。使用新的球队别名注册表，未匹配必须输出逐场原因。

2026-10-11调度修复：提前唤醒不能仅返回等待并依赖原触发再次到来。日初锚点不超过5分钟时，本轮等待至到期执行；更早时必须显式重排同一心跳并回读。到期缺失的今日确认及昨日复盘须优先补做，禁止倒填时间。

2026-10-14重启后网络恢复：系统代理127.0.0.1:7897未监听，但体彩官网直连已验证HTTP200。运行官方浏览器采集前在本轮PowerShell设置$env:SPORTTERY_DIRECT_CONNECTION='1'；采集器仅对此项目使用--no-proxy-server，不改系统代理。


2026-10-19用户授权优先修复：一次唤醒连续处理全部已到期且未过硬锁的注册终版批次，替代旧“每次只执行一项”。先运行scripts/next_controller_task.py --due-batches读取本轮队列；每批重新检查当前时间、身份、官方数据新鲜度及READY，不因共享快照绕过任何门禁。相同全页采集可共享原始档案，但逐批过滤市场/扫描、逐批生成READY和规范batch-key，禁止把8场混作一个批次或重复入账。每批立即落盘进度/冻结回执；单批失败保存失败原因后继续其他独立批次，禁止无界重试；临近锁时停止新增方案。所有本轮到期批次完成或留下失败审计后，再选择唯一下一任务并通过受支持接口重排、view及运行时核验。不得每完成一批就结束当前唤醒。今晚21:00依次处理001—002、003—007、008，保持各批稳健/价值卡和模型对照独立。

每批新增总进球0—6/7+八档及净胜球−4及以下至+4及以上九档：纯球队专用及通用后备由同一比分联合分布聚合，保存完整概率、期望值、模型ID和真实预测时间；无方案也冻结评分，覆盖失败逐场说明。scripts/run_independent_comparison.py及run_universal_comparison.py已接入，新冻结包含total_probability_*、expected_total_goals、expected_goal_margin；settle输出goal_distribution_review，记录Log Loss/Brier/有序RPS及最高档命中率。报告必须逐场展示上述分布，并在13:00汇总评分及缺失/待结算原因。旧冻结缺总进球不补算或回填；研究产物不改变正式概率/金额。市场增强模型仍未获上线资格，真实样本160<300；不得把纯球队输出标成市场增强输出。


2026-10-19后续优先规则：相同run_at、hard_lock、sales_cutoff的终版时间组，合并为一个规范注册批次；保留逐场开赛时间。不同销售/决策窗口不强行合并。build_task_records/group_on_sale_fixtures已实现，11:05生成任务采用新规则；不得拆组重复计额。今日001—008已合为2026-10-19|00:30-07:00|终版分析，旧三批归档且尚未冻结，不再执行旧三批。正式仅稳健/价值各100元上限，总计200元。

每批正文新增四张分账研究卡：市场胜平负基准、独立模型胜平负、独立净胜球映射整数让球、净胜球与市场固定50%融合；build_comparison自动生成research_cards。卡片仅是现有方向对照experiments的展示，引用原每组每玩法12元理论预算，严禁再次加总入账。专用及通用后备不同覆盖集合分开报预算和成绩，模型身份明确；无覆盖或缺报价显示空卡/原因，未验证EV不称真实优势。总进球仅预测评分，未接入总进球票据结算前不新增此类投注方案。报告与settle入口必须分别展示上述family的投入返奖ROI及概率误差，不混入正式SAFE/VALUE。

每次确认后及收尾运行scripts/audit_controller_readiness.py --sales-day <销售日> --output <独立审计JSON>；若确认后已有部分批次完成，按已冻结/终态排除后再核对剩余覆盖，不能将有效完成批次误报漏赛。任务完成必须有正式两卡回执、专用及通用研究冻结或明确失败/跳过、总进球/净胜球报告；缺项保留部分完成并从已冻结产物恢复，不重复出非空票。研究子进程最多180秒，超时落审计不阻断正式任务。当天队列清空后重排次日10:00并进行view及运行时核验；不依赖每日21:00规则自然恢复。


2026-10-19用户授权跨玩法优化：scripts/run_independent_comparison.py及通用后备共用的build_comparison已新增cross_play_stress_v1研究卡。逐场列出普通胜平负、整数让球选项的独立/市场/50%融合概率、当前官方赔率、盈亏平衡概率、估算EV和减5个百分点压力后的估值。按预先固定规则筛选（独立概率至少35%、赔率至多5、融合估算EV至少5%、压力估值非负），每场最多一个选项，每个专用/后备研究队列最多两场；这些阈值只是待验证研究假设，不是校准置信下界或真实优势。
独立研究每队列总预算上限12元：两场入选时各3元理论单场、6元二串一；仅一场时6元单场并留6元未用；零场为空卡。沿用experiments赛前冻结及原settle逐腿赛果/退款逻辑，不再重复从卡片计额。专用与后备覆盖不同，分别核算，新增总投入最多24元；正式稳健/价值200元上限不变。二串一不宣称已知联合概率，相关性未知；不得升至三串/四串或提高倍率。报告必须展示所有比较选项、落选原因、选中玩法及单场/组合投入；复盘比较概率误差和模拟收益，不用一次盈利调参。只对新READY冻结生效，不补写历史。


2026-10-21欧冠跨联赛概率研究（仅新批次）：已接入scripts/run_independent_comparison.py原freeze/settle入口，新建研究挂钩scripts/ucl_research_hook.py。配置config/ucl_domestic_research.json；先读取docs/ucl_domestic_phase5_20261021.md。两个候选elo_only与elo_domestic_form独立保存胜平负、总进球八档、净胜球九档，并在官方报价完整时保存SPF/RQSPF市场及固定50%融合概率。预算为0，不新增票，不改变原正式或研究金额。必须本批READY、相同完整批次、官方采集时效、真实预测时间、模型训练截止、稳定提供商球队ID与开赛时间匹配；国内历史每队至少5场、距最新不超过120天；提供商赛程归档超过24小时须刷新，否则记录失败，禁止沿用。当前预检004/007/009/010可覆盖，005/008/011/012因对手国内历史未覆盖跳过。预检不等于冻结。原冻结已存在时不补写该新队列；新冻结独立保存artifacts/data/ucl_domestic_comparison/，子进程180秒限时，失败不阻断生产但须在报告中说明。13:00原settle自动调用该队列settle-pending，按候选分别展示Log Loss/Brier/有序RPS；同场两个候选算一次独立事件。历史开发留出已查看过，尚无前瞻结论，不声称优于市场。当前16:30及21:00批次安排不因研究改变。赛前冻结前若`config/ucl_domestic_research.json`的`provider_captured_at`距今超过24小时，先运行`.\.venv\Scripts\python.exe scripts/collect_ucl_phase5.py --refresh`补采当季档案并自动更新该指针，再进入freeze；拉取失败时指针不推进、照旧留失败审计，不得手改时间戳或关闭过期检查。

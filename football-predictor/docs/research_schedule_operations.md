# 资料质量调度：已实施功能与操作规程

更新：2026-09-28。此文是已落地实现的操作说明，优先于此前设计稿中的设想。

## 部署范围

已新增独立资料质量调度，桌面自动化名称“资料质量审计与人工调度”，ID 与同步信息保存于 `artifacts/research_schedule/platform.json`，绑定本设计实施对话。旧生产总控 `2026-09` 未迁移、未改期、未修改提示词。两个执行器不会共用新注册表。

新模块只允许两个任务类型：

- intelligence_validation：调用既有资料验证脚本，输入原资料，输出验证副本和审计到独立目录；有拒绝记录时失败并留证据。
- coverage_audit：调用既有资料覆盖审计脚本，输出覆盖报告到独立目录。

不自动请求外部数据，不训练或晋级模型，不生成投注方案，不优化金额，不写正式或影子投注台账。既有方案业务未接入这个新模块。此前更广泛的动态赛事编排设计没有整体上线。

## 每日执行

首次 tick 自动登记今天和明天的资料任务：北京时间11:00资料校验和覆盖审计。实际执行以 run_at 到期为条件；不是每天无条件重复执行。手工改期、暂停、取消和完成状态不会被再次生成计划覆盖。2026-09-28修复将未执行且未经人工调整的旧13:30/13:35默认任务迁移到11:00，迁移前后值记录在SQLite的plan_changes表。当天已完成任务不会重跑。

平台使用一个绑定当前对话的 heartbeat 唤醒执行器。每次执行结束读取 next_due_at，再通过 automation_update 更新本资料任务的下一次每日唤醒小时和分钟，并回读。每日重复规则只是唤醒机制，日期判断在本地执行器完成；并不表示平台已注册所有未来任务。若无下一任务，保留11:00日检用于生成新日期任务。

11:00日检检查的是本地已有资料，不证明当天官方赛事已刷新或已采集。旧生产总控的采集安排没有修改。

### 已接入的采集后检查

`scripts/import_api_football_daily_intelligence.py` 将资料写入默认数据集并保存采集审计后，会调用独立的资料质量审计。无需等待第二天或固定日检。批次标识由采集审计路径和内容哈希组成，同一批次重复回调不会重复执行，也不会偷偷执行其他已到期任务。审计针对执行时的本地资料，并非冻结该批所有输入的回放。

质量审计输出只保存在独立目录，返回状态附在导入命令的JSON结果中；失败不会撤销导入或改变模型、投注决策。默认数据集之外的自定义输出明确跳过此步骤。每个审计最多10分钟，导入命令会等待两项检查完成，超时或失败会留存状态。其他采集入口尚未接入，不能宣称全项目已经实现采集后检查。

独立调用入口是 `scripts/manage_research_schedule.py after-collection --event-id <稳定批次标识>`，使用相同Python解释器。此入口不会采集外部数据。它只领取该批两项审计，尊重该实例的暂停/取消状态，失败须人工补跑。

若 next_due_at 已过期，下一唤醒取当前北京时间后一整分钟，不设置到今天已经过去的小时。临时取消全部已登记实例不会暂停未来日期的计划生成。

如果客户端未运行、离线或平台没有触发，本地脚本不能自行唤醒电脑。恢复后 tick 可补做资料检查，started_at 记录真实时间，不回填为计划时间。单次最多领取4个任务；失败不会每次唤醒自动重跑。

## 人工命令

用户可在绑定对话中说“明天的资料校验改到18:30”“暂停明天的覆盖审计”“恢复该项”“取消今天的覆盖审计”“补跑昨天失败的资料校验”“撤销刚才的改期”。助手依据明确目标调用下面入口。目标有歧义时先消歧，不猜日期或任务。

本次支持单个任务实例，不支持自动理解任意业务名称、整类长期规则修改或正在运行任务的立即中断。需要调整多个实例时分别操作并逐项回执，不能宣称是一个原子批量操作。长期默认规则尚无人工策略命令。暂停每日实例不等于暂停未来新采集批次，两者有不同task_id，必须说明用户指令的作用范围。

从项目目录 `E:\ball-match-prediction-system\football-predictor` 使用：

```powershell
.\.venv\Scripts\python.exe scripts/manage_research_schedule.py inspect
.\.venv\Scripts\python.exe scripts/manage_research_schedule.py plan
.\.venv\Scripts\python.exe scripts/manage_research_schedule.py tick
```

人工修改采用统一参数，值取自刚读取的 inspect，不照抄旧 revision：

```text
manage_research_schedule.py reschedule --task-id <任务ID> --command-id <唯一命令ID> --revision <当前版本> --at <带+08:00的未来时间>
manage_research_schedule.py pause --task-id <任务ID> --command-id <唯一命令ID> --revision <当前版本> [--until <带时区的恢复时间>]
manage_research_schedule.py resume --task-id <任务ID> --command-id <唯一命令ID> --revision <当前版本>
manage_research_schedule.py cancel --task-id <任务ID> --command-id <唯一命令ID> --revision <当前版本>
manage_research_schedule.py run_once --task-id <失败任务ID> --command-id <唯一命令ID> --revision <当前版本>
manage_research_schedule.py revert --task-id <任务ID> --command-id <唯一命令ID> --revision <当前版本> --reference <被撤销的命令ID>
```

这些命令使用上方相同Python前缀及scripts路径。时间必须包含时区。相同 command_id 与相同参数重试返回原回执；同 ID 换参数会拒绝。补跑仅允许失败任务；已完成任务不会被重跑。撤销只允许该任务最新且尚未执行的修改。

**人工修改之后仍必须同步桌面唤醒：**

1. inspect 获取 next_due_at。
2. 读取 platform.json 中的 automation_id，并通过 automation_update 的 view 核对目标。
3. 用 automation_update 更新该自动化的每日唤醒时间，保留名称、提示词、目标对话、状态和通知配置；不能改旧生产总控。
4. 回读实际规则，成功再更新 platform.json 的同步回执；失败写 pending_platform_sync，保留旧唤醒规则，不宣称已安排。

CLI 自身不能调用桌面 MCP，输出 committed_local 只代表SQLite事务成功。直接在终端改期而不完成上述同步，可能要等原来的唤醒才能执行；这点必须明确告知用户。

## 数据与并发

状态、人工命令与执行尝试保存到 `artifacts/research_schedule/schedule.sqlite3`。使用事务、版本校验和执行租约避免并发重复领取；进程重启后状态保留。命令修改和回执同一事务写入。

运行中禁止修改该实例，避免产生无法兑现的暂停承诺。任务租约15分钟，子进程最多10分钟。租约过期标记失败，不自动重放，因为旧进程可能已写入产物；人工核查后才能补跑。

输出目录：`artifacts/research_schedule/runs/<任务ID哈希>-<尝试序号>/`。包含执行日志和审计文件；资料验证另有 validated.csv。失败尝试也留存，后续补跑使用新目录。不要删除SQLite而保留同名执行目录后重新运行，否则目录冲突会安全失败。

## 验证记录

- 调度及研究回归测试共23项通过，覆盖默认迁移、人工保护、采集批次去重、失败不自动重跑及异常回执隔离。
- 新增代码 Ruff 检查通过。
- 2026-09-28手动调用 tick，两项真实资料检查均完成；再次tick返回 executed=[]，没有重复执行。
- automation_update 更新及view成功；本地平台配置回读为ACTIVE，下一计划唤醒为2026-09-29北京时间11:00，原13:30安排已替换，没有另建重复自动化。
- 本次使用明确标记的修复验证事件手动运行两项真实检查并重复调用，均成功且没有重复执行；没有请求外部接口，因此尚未验证真实外部采集完成后的端到端回调。
- 尚未观察到本任务真实平台定时触发。真实触发、人工改期后的唤醒及客户端重启后的平台恢复仍需后续运行验证，不能把手工运行成功当作此项已通过。

出现失败时先检查 execution.log、audit.json 和 platform.json，不修改原始资料的时间戳或放宽验证规则来强行通过。

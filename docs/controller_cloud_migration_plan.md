# 总控任务云端迁移方案

登记日期：2026-10-18
适用对象：`football-predictor` 生产总控（单 heartbeat 控制器）
状态：方案待评审，未实施

---

## 0. 结论摘要

**可行。** 建议按"单机云化（方案 B）"落地。

三条核心判断：

1. **Codex 桌面端只承担两个角色**：按时唤醒、按提示词执行 CLI 命令。业务逻辑全部在 Python/Node 脚本里，长期状态全部在项目文件里（见 `docs/scheduled_tasks.md` 第 22 行"项目文件和任务注册表是唯一长期状态，聊天记录仅作为当月控制面"）。因此迁移的本质是**换闹钟 + 把自然语言提示词固化成编排脚本**，不是重写业务。
2. **脚本几乎不硬编码路径**：多数脚本用 `ROOT = Path(__file__).resolve().parents[1]` 定位项目根（例：`scripts/run_controller_data_sync.py` 第 19 行、`scripts/next_controller_task.py` 第 10 行）。硬编码的 `E:\ball-match-prediction-system\football-predictor` 只存在于**提示词文本和文档**中，不在代码里。这一点大幅降低了迁移成本。
3. **真正的障碍只有 3 个**，且都有成熟替代：调度器（绑桌面应用 sqlite）、采集器（绑本地浏览器）、同步脚本（硬编码只允许回环地址）。

---

## 1. 现状拆解

| 组件 | 当前载体 | 迁移难度 | 说明 |
|---|---|---|---|
| **唤醒调度器** | Codex 桌面端定时任务 + `~/.codex/sqlite/codex-dev.db` | 中 | 唯一"必须换掉"的外部依赖 |
| **编排大脑** | `docs/controller_heartbeat_prompt.md` 自然语言提示词 | 中 | 需要固化为可执行编排，或保留 LLM 执行 |
| **业务执行** | `scripts/*.py` + `scripts/*.mjs` | 低 | 纯 CLI，可原样搬迁 |
| **长期状态** | `artifacts/`、`data/manual/`、`data/processed/` 本地文件 | 低 | 挂持久盘即可 |
| **对外同步** | `scripts/run_controller_data_sync.py` → Web API | 低 | 改一处地址校验 |
| **展示层** | Vercel + Supabase | 无需迁移 | 已经在云上 |

每天固定阶段（`docs/scheduled_tasks.md` 第 29 行）：

```
10:00 预扫描 → 11:05 开售确认 → 13:00 昨日复盘
→ 注册表中最早终版批次 → 工作日 21:00 / 周末 22:00 兜底 → 次日 10:00
```

---

## 2. 三个真实障碍（附证据）

### 障碍 1：调度器绑死桌面应用

- `scripts/verify_controller_runtime_schedule.py` 直接以只读方式连接 `~/.codex/sqlite/codex-dev.db`，读取 `automations` 表的 `next_run_nominal_at` 来证明"任务真的排上了"。
- `docs/scheduled_tasks.md` 第 7 行明确：接口更新失败或回读不一致时须置 `pending_reschedule=true`，且"不得直接修改数据库/toml"。
- 结论：这是**外部应用的所有权边界**，云端无法复用，必须替换为自有调度。

### 障碍 2：采集器绑本地浏览器

- `scripts/run_sporttery_sales_window_scan.py` 第 81-94 行通过 subprocess 调 `node scripts/fetch_lottery_gov_spf.mjs --channel <chrome|msedge> ...`。
- `scripts/fetch_lottery_gov_spf.mjs` 通过 `.pnpm` 目录解析 playwright，并在 `SPORTTERY_DIRECT_CONNECTION=1` 时加 `--no-proxy-server`（对应本地代理 `127.0.0.1:7897`）。
- 同类脚本还有 `fetch_lottery_gov_results.mjs`、`fetch_leisu_public.mjs`、`build_world_cup_chinese_report.mjs`。
- 结论：**技术上完全可云化**（Playwright 支持 Linux 无头 Chromium，不需要图形界面），但引入两个新依赖：云端 Node 运行时、Chromium 二进制。**风险点是体彩官网对云 IP 的可达性**，必须实测。

### 障碍 3：同步脚本硬编码只允许回环地址

- `scripts/run_controller_data_sync.py` 第 210-212 行：

  ```python
  parsed = urlparse(args.base_url)
  if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
      parser.error("only a local loopback Web service is allowed")
  ```

- 另有第 241 行 `session.trust_env = False`（防止回环凭证经代理外泄）、第 242 行从 `web/.env.local` 读管理员凭证。
- 结论：这是**有意的安全设计**（禁止密码出本机）。云化时要么放开校验并强制 HTTPS + 域名白名单，要么改走 Supabase 直连。

### 次要问题

| 问题 | 证据 | 处理 |
|---|---|---|
| 时区 | `docs/scheduled_tasks.md` 第 7 行记录过一次 TZID 8 小时偏移事故 | 容器/主机统一固定 `Asia/Shanghai`，所有时间计算已用 `timezone(timedelta(hours=8))`，保持并加回归测试 |
| 凭证来源 | `football-predictor/.env`、`web/.env.local` | 云端改为 secret 注入，禁止落盘明文 |
| 单写者锁 | `artifacts/data/controller_sync/writer.lock` | 持久盘上继续有效，无需改 |
| 外部配额 | The Odds API、API-Football 按月/按量计费 | 云化不改变额度逻辑，但需确认云出口 IP 与账号策略不冲突 |

---

## 3. 目标架构

```
┌─────────────────────────── 国内轻量云主机 ───────────────────────────┐
│                                                                      │
│  controller.service (systemd, 常驻)                                  │
│    └─ orchestrator.py  ← 替代 Codex heartbeat 提示词                  │
│         1. 读注册表/锚点 → 计算下一次 run_at（复用 next_controller_task.py）│
│         2. 到点执行阶段脚本（scan / refresh / gate / strategy / sync）  │
│         3. 写 heartbeat.json（健康态，替代 sqlite 回读核验）            │
│                                                                      │
│  systemd timer (固定锚点兜底: 10:00 / 11:05 / 13:00)                  │
│                                                                      │
│  运行时: Python 3.11+ (.venv) + Node + Chromium(headless)             │
│  持久盘: /srv/ball-match/{artifacts,data}                             │
│  密钥: /etc/ball-match/env (600, 非明文入 Git)                        │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ HTTPS (Basic Auth)
                               ▼
                  Web API (Vercel)  →  Supabase  →  浏览器展示
                  或：直连 Supabase (service role)
```

关键变化对照：

| 现状 | 迁移后 |
|---|---|
| Codex 桌面定时任务 | `controller.service` 常驻编排 + systemd timer 兜底 |
| `verify_controller_runtime_schedule.py` 读 sqlite | 读自有 `heartbeat.json` + 运行日志 |
| `next_controller_task.py` 算完交给桌面接口重排 | 算完写回自有队列，orchestrator 自己等到点 |
| 本地 Chrome/Edge | 容器/主机的 headless Chromium |
| `--no-proxy-server` + 本地代理 | 云直连，移除代理逻辑 |
| 同步只允许 loopback | HTTPS 域名白名单（或直连 Supabase） |

---

## 4. 关键设计决策

### 4.1 调度层：用"常驻编排"而非"多个 timer"

两种做法：

- **方案 T（多 timer）**：为 10:00/11:05/13:00 各配 `OnCalendar`，动态终版用 `systemd-run --on-calendar`。
  - 缺点：定时器状态与注册表状态**双重真源**，动态任务重排需在 timer 和注册表之间同步，容易不一致（这正是现在用 sqlite 回读核验的原因）。
- **方案 O（常驻编排，推荐）**：一个常驻进程，内部循环"读注册表 → 算下次 → sleep 到点 → 执行 → 记录"。
  - 优点：与现有"事件驱动、单一心跳"语义完全一致；注册表仍是唯一真源；无需排程回读核验。
  - 缺点：进程崩溃会停摆 → 用 systemd `Restart=always` + `WatchdogSec` 兜底。

推荐组合：**方案 O 为主 + systemd timer 每小时一次"看门狗"**（发现 orchestrator 未运行或已过期未执行则告警/重启）。

`next_controller_task.py` 可**原样复用**（它只做纯计算、只读文件），只需把"输出给桌面接口"改为"输出给 orchestrator 内部循环"。这已经是整个迁移中最大的复用点。

### 4.2 编排大脑：确定性编排为主

提示词里存在大量需要判断的内容（阶段识别、失败降级、中文报告）。两条路线：

- **路线 A（推荐起步）：确定性编排**
  把提示词固化成 `orchestrator.py` 的阶段函数，例如：

  ```
  stage_preopen(day)   → run_sporttery_sales_window_scan.py scan --stage preopen --fetch
  stage_confirm(day)   → scan --stage confirm --fetch --previous-scan <...>
                         + build_unified_outer_market_history.py
                         + sync --stage confirm
  stage_review(day)    → import_sporttery_results.py + settle_shadow_evidence_v2.py
                         + sync --stage review
  stage_final(batch)   → refresh_the_odds_for_sporttery.py --snapshot-type final
                         + check_evening_final_analysis_gate.py --require-ready
                         + build_multi_play_betting_strategy.py --stake 100
                         + validate_final_orchestration.py + sync --stage analysis
  ```

  每条命令的退出码/审计文件作为下一步的闸门条件——这些闸门在文档里**已经是明确规则**（如 `may_create_plan=true` 才继续），可直接编码，不需要 LLM 判断。

- **路线 B（可选增强）：保留 LLM 生成报告**
  编排仍走路线 A，仅在阶段结束时调用 LLM，把审计 JSON 转成"用户反馈详细度契约"要求的中文报告（`docs/scheduled_tasks.md` 第 173-186 行）。
  - 注意：这只影响**报告文案**，不参与任何闸门判断，模型不可用时降级为模板化输出即可。

建议：**先做 A，报告先用模板；B 作为二期增强。**

### 4.3 Playwright 云化

- 服务器上安装 Chromium 及系统依赖（`npx playwright install --with-deps chromium`）。
- 把 `--channel chrome|msedge` 默认值改为 `chromium`（`fetch_lottery_gov_spf.mjs` 已支持三选一，只需换默认值/传参）。
- 移除 `SPORTTERY_DIRECT_CONNECTION` 相关代理分支（云上无本地代理；若仍需要走代理则改为环境变量配置的显式出口）。
- **必测项**：体彩官网（`lottery.gov.cn`）在目标云区域的可达性与响应稳定性。若目标区域不可达，退回**方案 C**（采集留本地、其余上云）。

### 4.4 数据同步

三选一：

| 方式 | 改法 | 取舍 |
|---|---|---|
| **A. 放开 loopback 校验**（改动最小） | 在 `run_controller_data_sync.py` 第 210-212 行改为：允许 `https` 且域名在显式白名单内；保留禁止明文 HTTP、禁止 URL 内嵌凭证 | 需要维护白名单；凭证仍需出本机 |
| **B. 直连 Supabase**（更彻底） | 用 `SUPABASE_SERVICE_ROLE_KEY` 直接写表，绕过 Web API | 少一跳、少一个凭证；但需把 `/api/automation/*` 里的匹配/校验逻辑（如 `marketIntelMatch.ts` 的主客队名+日期匹配）下沉到脚本，改动较大 |
| **C. 隧道** | 云端通过内网隧道访问本地 Web | 不推荐：仍然依赖本地机器开机，失去迁移意义 |

建议：**先 A（快），后续可选迁 B（稳）**。

---

## 5. 云主机选型

| 方案 | 规格 | 适用性 | 说明 |
|---|---|---|---|
| **国内轻量云主机**（阿里云/腾讯云等，2 核 2G 起） | 常驻进程 + 持久盘 | ⭐ **推荐** | 直连体彩官网最稳；Playwright 常驻运行；成本低 |
| 海外 VPS | 同左 | ⚠ 有风险 | 体彩官网、部分国内数据源可能不可达 |
| 容器平台（Cloud Run / SAE 等） | 无状态、按请求计费 | ✗ | 需要常驻调度 + 持久盘 + 浏览器，模型不匹配 |
| **Vercel** | Serverless | ✗ | 有函数执行时长上限，跑不了 Playwright 长任务和本地文件读写；展示层继续留在 Vercel |

规格要点：2 核 2G 起步（Chromium 吃内存，建议 2-4G）；系统盘之外**必须挂持久盘**放 `artifacts/` 与 `data/`；出网需能访问体彩官网、The Odds API、API-Football、Supabase。

---

## 6. 分阶段实施路线

### 阶段 0：解耦改造（在本地完成，零风险，不改现有跑法）

1. **路径与配置集中化**：新增 `config/runtime.json`（或环境变量）承载 base_url、代理开关、chrome channel 等；把提示词里的硬编码路径改为配置读取。
2. **抽出编排脚本**：把 heartbeat 提示词的阶段命令固化为 `scripts/orchestrator.py`（先只在本地跑，行为与现状一致）。
3. **调度抽象**：新增 `scripts/schedule_backend.py`，把"重排下一次唤醒"抽象成接口；本地实现仍写 Codex，云端实现写自有队列。
4. **同步地址可配置**：按 4.4-A 放开校验（同时在本地保持只用 loopback，行为不变）。
5. **补回归测试**：`next_controller_task.py` 的时间计算（含跨天、兜底、停售跳过）、时区换算。

> 阶段 0 结束时，本地仍按原方式运行，但所有云端替换点都已就位。

### 阶段 1：单机云化

1. 采购国内轻量云主机，挂持久盘，固定 `Asia/Shanghai`。
2. 部署 Python（>=3.11，`football-predictor/requirements.txt`）+ Node + Chromium。
3. 迁移 `artifacts/`、`data/` 到持久盘；密钥写入 `/etc/ball-match/env`（600）。
4. 部署 `controller.service` + 看门狗 timer。
5. **影子运行**：云端只读执行（不写台账、不同步），与本地结果逐日比对。

### 阶段 2：切换与加固

1. 确认影子运行 N 日一致后，云端接管写入；**本地停用 heartbeat**（`docs/scheduled_tasks.md` 第 15、275、292 行明确：任何时刻只允许一个 ACTIVE 控制器）。
2. 加监控告警：进程存活、阶段完成、`pending_reschedule`/`pending_keys` 非空、采集失败率。
3. 加备份：持久盘快照 + 台账文件异地副本。

### 阶段 3（可选）

按 4.4-B 直连 Supabase，减少对 Web API 与本地凭证的依赖。

---

## 7. 切换与回滚

**切换前置**：影子运行结果与本地一致；云端写入闸门（硬锁、在售、去重）验证通过。

**切换步骤**：

1. 本地总控进入暂停（不删除，作为恢复模板——对应 `docs/scheduled_tasks.md` 第 242-245 行的"暂停恢复模板"机制）。
2. 云端 `controller.service` 设为启用并启动。
3. 回读云端 `heartbeat.json` 与下一次 `run_at`，确认与注册表一致。
4. 观察首个完整销售日（10:00 → 次日 10:00）全链路。

**回滚步骤**：

1. 停用云端 `controller.service`（`systemctl stop`）。
2. 恢复本地 heartbeat（重排到最近的合法 `run_at`）。
3. 核查切换期间是否有遗漏阶段，按 `docs/scheduled_tasks.md` 第 67 行的"迟采"规则补做，**不倒填赛前时间**。

**硬约束**：迁移期间与迁移后，任何时刻**不得同时启用两个控制器**。

---

## 8. 风险清单

| 风险 | 影响 | 缓解 |
|---|---|---|
| 体彩官网对云 IP 不可达/风控 | 采集全断 | 阶段 1 前先实测；不可达则走方案 C（采集留本地） |
| 常驻进程静默死亡 | 漏跑阶段 | systemd `Restart=always` + 看门狗 timer + 告警 |
| 时区错排（历史发生过） | 任务错点、误判漏跑 | 固定 `Asia/Shanghai`，保留并强化回归测试 |
| 持久盘丢失 | 台账/注册表损坏 | 定时快照 + 台账异地备份 |
| 密钥在云端明文落盘 | 泄露 | secret 注入、文件 600、`check_secrets.py` 纳入启动自检 |
| 双控制器并行 | 重复入账、台账污染 | 切换流程强约束 + 状态互锁 |
| 配额与出口 IP 策略冲突 | 外盘源失败 | 迁移前后各跑一次额度自检（`/v4/sports/` 只读回读） |

---

## 9. 待确认事项

1. **体彩官网云 IP 可达性**——决定走方案 B（整体上云）还是方案 C（采集留本地）。建议先做一次目标云区域实测。
2. **云厂商与区域**——是否已有阿里云/腾讯云账号？
3. **报告是否保留 LLM 生成**——决定是否引入 4.2 路线 B。
4. **模型与训练数据体量**——`artifacts/models/`、`data/p0.sqlite3` 是否需要在云上常驻，还是走对象存储。
5. **阶段 0 是否立即启动**——该阶段在本地即可完成、零风险，是任何云方案的公共前置。

---

## 10. 附：最小改动清单（文件级）

| 文件 | 改动 |
|---|---|
| `football-predictor/scripts/run_controller_data_sync.py` | 第 210-212 行地址校验：放开为 HTTPS + 域名白名单 |
| `football-predictor/scripts/fetch_lottery_gov_spf.mjs` 等 4 个 mjs | 默认 channel 改 `chromium`；代理分支改为可配置 |
| `football-predictor/scripts/verify_controller_runtime_schedule.py` | 由"读桌面 sqlite"改为"读自有 heartbeat/运行日志"（或整体不再需要） |
| `football-predictor/scripts/next_controller_task.py` | **逻辑不变**，仅调整输出去向（复用） |
| `football-predictor/docs/controller_heartbeat_prompt.md` | 提示词固化为 `orchestrator.py` 阶段函数；文档降级为规则说明 |
| `football-predictor/docs/scheduled_tasks.md` | 新增"云端运行"小节，登记新的调度真源与核验方式 |
| 新增 `football-predictor/scripts/orchestrator.py` | 阶段编排主循环 |
| 新增 `football-predictor/scripts/schedule_backend.py` | 调度后端抽象（本地 Codex / 云端自有队列） |
| 新增 `deploy/systemd/controller.service`、`controller-watchdog.timer` | 云端常驻与看门狗 |

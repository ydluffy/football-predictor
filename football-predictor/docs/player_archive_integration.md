# 球员档案补齐与接入边界

## 当前缺口

133 人的逐人资料、缺失字段、来源候选和官方证据统一导出到
`artifacts/data/player_enrichment_queue_latest.json`。候选资料不能冒充已确认档案。
官方来源页面球队和历史比赛所属球队分开保留，不根据当前名单重写历史。

2026-10-22 在保留日常采集 30 次额度的策略下，API-Football 本轮补档预算为零。
未额外购买服务，未发送球员档案请求。仍有 67 人未取得该来源详细档案。

额度允许时从项目目录续跑，已取得档案者自动跳过：

```powershell
.\.venv\Scripts\python.exe scripts/enrich_player_profiles.py --fetch --max-requests 67 --reserve 30
.\.venv\Scripts\python.exe scripts/reconcile_football_data_catalog.py --record-corroboration
.\.venv\Scripts\python.exe scripts/build_player_enrichment_queue.py
```

这不是定时任务，需实际执行；请求失败或额度不足时仍保留缺失值。

## 已检查的接入位置

- `src/world_cup/api_football_adapter.py` 的伤停和首发转换已保留 `source_player_id`。
- `src/data/api_football_prematch.py` 生成赛前信号时使用姓名作为 subject，后续应保留来源、球员 ID、球队 ID 与比赛 ID 的关联。
- 不以补充生日或身高直接改变伤停置信度或预测概率。

## 建议实施顺序（尚未上线）

1. 同来源按 provider + player_id 关联档案；姓名只作显示，不替代 ID。
2. 以影子输出记录匹配成功、缺失 ID、未知 ID、球队冲突与资料过期；不修改现有预测结果。
3. 跨来源必须经独立审核批准绑定；官方资料候选、同名与生日冲突不能自动放行。
4. 回放按 observed_at 截断，禁止把赛后取得的首发、伤停或转会信息倒灌到赛前。
5. 对比错配率、漏配率和回放结果，通过后再接入正式特征；云端发布前另做数据库迁移与权限审查。

本轮仅补档及调查接入位置，没有修改生产信号、预测模型或部署。

## 2026-10-23 离线影子接入结果

新增 `src/data/player_archive_shadow.py` 和 `scripts/check_player_archive_shadow.py`。
按 api_football 球员 ID 查询统一档案，并要求球员、球队、比赛三元组存在于已归档的 membership_observation。
未知来源、缺失或无效球员 ID、未知球员、缺少比赛上下文、未验证比赛归属分别报告，不以姓名兜底。

实测 136 条归档观测（90 条伤停、46 条阵容）全部成功关联。这里的阵容观测不全等同于首发。
这是参与建档数据的样本内链路核验，不是独立样本识别率，更不是模型准确率。
所有输出强制 `prediction_features_allowed=false`；当前档案不能作为历史赛前特征使用。
SQLite 以只读模式打开，脚本只写 `artifacts/data/player_archive_shadow_latest.json`。
相关 23 项测试通过，含未知 ID、错误球队、错误比赛、跨来源拒绝及暂定档案隔离。

运行：`.\.venv\Scripts\python.exe scripts/check_player_archive_shadow.py`。
尚未连接在线日常采集入口；正式接入前须以新增采集批次做独立核验，并实现 as-of 时间截断。

## 2026-10-24 as-of 时间截断

`attach(row, profiles, memberships, as_of=...)` 增加 as-of 闸门：档案的每个字段只在
其证据时间（`provenance.observed_at`，跨来源字段取 `binding.observations.observed_at`）
不晚于截断点时进入 `archive_fields`，其余进 `archive_withheld_fields`，并给出
`archive_as_of_status`（`within_cutoff`/`truncated`）。取不到证据时间的字段一律扣留，
不假定它早于截断点。`as_of` 为空时行为不变（仍是当前快照口径）。`prediction_features_allowed`
在所有分支保持 `false`。

回放脚本默认按每条信号的 `observed_at` 截断，`--as-of <ISO-8601>` 可改为统一固定截断，
摘要增加 `linked_fields`、`withheld_fields` 与 `as_of_basis`。

实测（136 条归档信号）：按信号 `observed_at`（2026-10-21T13:09Z）截断时可用字段为 0；
按固定截断 2026-10-23 时可用字段 434、扣留 15。原因是本批档案快照（2026-10-22T05:29Z 起）
晚于这批信号采集时刻，属赛后取得的信息，不能回灌这批赛前信号。这验证了截断闸门有效，
也说明**现有档案对历史信号只能做快照口径的旁证，不能直接作为赛前特征**。

仍待完成：新增采集批次的独立核验；`src/data/api_football_prematch.py` 目前只把球员姓名写入
`subject`，在线入口保留 `source_player_id` 需一并改动已验证的赛前字段契约，须与云端库迁移、
权限审查一并进行。

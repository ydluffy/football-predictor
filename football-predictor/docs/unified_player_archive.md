# 多来源统一球员档案

执行 `scripts/build_unified_player_archive.py`，产物为 `artifacts/data/unified_player_archive_latest.json`。
它使用已归档资料，不请求网络、不修改原始 SQLite 记录、不写生产库。

## 2026-10-23 实测

- 133 人全部输出；85 人有生日，69 人有位置，82 人有国籍字段。
- 55 人满足姓名兼容、生日一致、历史球队关联一致且无本地资料冲突的规则。
- 14 人只有完整姓名与球队唯一对应，资料用于 reference_only，不批准跨源绑定。
- 64 人没有形成新来源绑定；仍可保留其已有的同来源档案。
- 真正字段缺口：生日 48 人、位置 64 人、国籍 51 人。已填字段包含上述暂定参考资料，不等于全部核验完成。

## 消费约定

- `fields` 每个值附带来源和证据；`conflicts` 保留不同值，不静默覆盖。
- `binding.approved` 表示本次派生档案的规则核验结果，`approval_type=rule_based`，不是人工审核或数据库身份合并。
- `reference_only` 不得直接用于生产特征。原始候选未反向写入 API-Football profile。
- 按 `api_id` 查询原来源身份。跨来源只有批准的 binding 可进入下一步影子接入验证；正式生产仍未启用。
- `provenance` 与 binding 的 observations 保留时间和证据。该产物是当前快照，历史回测必须另做 as-of 截断，不能直接使用最新快照。
- 队伍匹配是历史关联佐证，不把名单中出现视为当前合同或转会确认。

后续接入位置见 `player_archive_integration.md`。旧的补档清单是 API 来源缺口，不能替代这份统一档案的字段缺口统计。

# Verifier Design (Skeleton)

## 目标

为后续接入 MiroThinker / 研究代理 / 其他 provider 预留统一的 verifier 接口与数据结构，用于对单场比赛的上下文信息做证据收集与风险标注。

## 关键声明

- 当前实现为 skeleton：只提供 schemas + 抽象接口 + 本地 mock 规则实现
- 不调用任何外部 API（不接真实模型）
- verifier 不直接覆盖主模型概率输出；只产出 `VerificationResult`，用于后续人工复核或流程编排

## 数据结构（pydantic）

- `MatchContext`：单场比赛的结构化输入（match_id/date/league/球队/odds/xg/伤停/盘口波动等）
- `EvidenceItem`：单条证据（source_type/content/confidence/timestamp）
- `EvidenceBundle`：一场比赛的证据集合（match + items）
- `VerificationResult`：最终验证结果（risk_flags/source_confidence/conflict_notes/manual_review_required/summary）

## 接口定义

`VerifierBase` 抽象接口包含：

- `collect_evidence(match_context) -> EvidenceBundle`
- `verify_local(bundle) -> dict`
- `verify_global(bundle) -> dict`
- `generate_result(bundle, local_result, global_result) -> VerificationResult`

## Mock 实现

`MockVerifier` 仅基于简单规则生成风险标注，用于联调与测试：

- `abs(line_move)` 过大：`line_move_risk`
- `injury_flag == 1`：`injury_risk`
- odds 缺失、非法、或 implied probability sum 异常：`data_quality_risk`

后续接入真实 provider 时，可复用 `EvidenceBundle`/`VerificationResult` 的结构，并将 `verify_local/verify_global` 替换为真实的证据检索与推理实现。


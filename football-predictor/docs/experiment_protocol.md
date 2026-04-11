# Experiment Protocol (Phase 7)

目标：用统一的时间切分评估与记录产物，验证 logit / lightgbm / stacking_oof 的增益与互补性，并在 Phase 7 引入 v3 特征后做对比，同时结合 verifier 风险标记与错误分析观察潜在关联。

## 关键声明

- stacking 为 prototype（非 OOF），仅用于快速验证互补性
- stacking_oof 为当前推荐 stacking 方案（训练集内部 OOF）
- SHAP 为可选增强：缺失或运行不稳定时会跳过，不影响主流程成功
 - verifier 当前为 mock 后处理：仅输出辅助风险标记，不覆盖主模型概率

## 推荐实验顺序（更新：Phase 7）

### 1) 跑 logit v2（基线）

```bash
python scripts/run_train.py --model-type logit --feature-version v2 --calibration none --cv false
```

关注：

- `artifacts/eval/model_compare.csv`：brier/logloss、reliability_gap_mean
- `artifacts/eval/reliability_table.csv`：可靠度分桶

### 2) 跑 lightgbm v2（候选提升模型）

```bash
python scripts/run_train.py --model-type lightgbm --feature-version v2 --calibration none --cv false
```

关注：

- `artifacts/eval/lightgbm_feature_importance.csv`：特征重要性（gain/split + rank）

### 3) 跑 lightgbm v2 + calibration（建议 sigmoid）

```bash
python scripts/run_train.py --model-type lightgbm --feature-version v2 --calibration sigmoid --cv false
```

关注：

- `artifacts/eval/calibration_compare.csv`：raw vs calibrated
- `artifacts/eval/model_compare.csv`：最终对比指标（brier/logloss）

### 4) 跑 stacking_oof（推荐方案）

```bash
python scripts/run_train.py --model-type stacking_oof --feature-version v2 --calibration none --cv false
```

关注：

- `artifacts/eval/model_compare.csv`：`notes=oof_stacking`

### 5) 跑 logit v3（Phase 7 特征对比）

```bash
python scripts/run_train.py --model-type logit --feature-version v3 --calibration none --cv false
```

关注：

- `artifacts/eval/model_compare.csv`：与 v2 的差异（brier/logloss、reliability_gap_mean、n_features）

### 6) 跑 lightgbm v3（Phase 7 特征对比）

```bash
python scripts/run_train.py --model-type lightgbm --feature-version v3 --calibration none --cv false
```

### 7) 跑 lightgbm v3 + calibration（建议 sigmoid）

```bash
python scripts/run_train.py --model-type lightgbm --feature-version v3 --calibration sigmoid --cv false
```

### 8) 比较错误分析与 verifier 风险标签（联动观察）

```bash
python scripts/run_train.py --model-type lightgbm --feature-version v3 --calibration sigmoid --cv false --use-verifier true
```

关注：

- `artifacts/eval/verifier_results.csv`：`risk_flags/manual_review_required`
- `artifacts/eval/error_analysis_with_risk.csv`：把错误样本与 risk_flags 通过 match_id 关联，便于观察 high_confidence_errors 是否更常伴随 line_move_risk / injury_risk

### 9) 查看 league_metrics 与 feature_importance（以及可选 SHAP）

- 若输入数据包含 `league` 列，会生成：`artifacts/eval/league_metrics.csv`
- lightgbm 单次评估会生成：`artifacts/eval/lightgbm_feature_importance.csv`
- 若 shap 可用且成功运行，会生成：`artifacts/eval/lightgbm_shap_summary.csv`

## 输出产物一览

- `artifacts/eval/model_compare.csv`：核心对比表（推荐主要看这个）
- `artifacts/eval/metrics.json`：最近一次单次评估指标（覆盖）
- `artifacts/eval/run_summary.csv`：单次评估汇总（追加）
- `artifacts/eval/feature_compare.csv`：特征版本对比（追加）
- `artifacts/eval/reliability_table.csv`：可靠度分桶（覆盖）
- `artifacts/eval/league_metrics.csv`：联赛分层（追加，取决于输入是否含 league）
- `artifacts/eval/lightgbm_feature_importance.csv`：LightGBM 特征重要性（覆盖）
- `artifacts/eval/lightgbm_shap_summary.csv`：SHAP summary（可选，覆盖）
- `artifacts/eval/high_confidence_errors.csv`：高置信错判样本（开启 verifier 时会附带 risk 字段）
- `artifacts/eval/underestimated_draws.csv`：低估平局样本（阶段性近似；开启 verifier 时会附带 risk 字段）
- `artifacts/eval/error_analysis_with_risk.csv`：错误分析扩展表（match_id 关联 verifier_results）

# Baseline Benchmark

## 数据字段

训练/预测使用 `data/raw/sample_matches.csv`，读取并校验以下必需字段：

- `match_id`
- `odds_home`
- `odds_draw`
- `odds_away`
- `actual_result`

## 特征

由 `features.basic_features.build_basic_features` 生成，当前版本为 `basic_v1`，包含：

- implied probabilities：`implied_prob_home/draw/away = 1 / odds_*`
- implied probabilities normalization：`implied_prob_*_norm`（三类概率按行归一化，和为 1）
- odds normalization：`odds_home_norm/odds_draw_norm/odds_away_norm`（按列 min-max 到 [0,1]）
- odds diff：`odds_diff = odds_home - odds_away`

## 标签编码

`actual_result` 作为三分类标签，取值：

- `H`：主胜
- `D`：平
- `A`：客胜

## 训练流程

1. `ingest.load_data.load_matches` 读取并输出标准 schema
2. `features.basic_features.build_basic_features` 构造 `X/y`
3. `models.baseline_logit.BaselineLogitModel.train` 训练多分类 Logistic Regression
4. `models.baseline_logit.BaselineLogitModel.predict_proba` 输出 `p_home/p_draw/p_away`
5. `evaluate.metrics.compute_metrics` 计算评估指标

入口：`orchestrator.predict_pipeline.run_pipeline`

## 评估方法

使用：

- Brier Score（多分类版本）：`mean(sum((p - onehot(y))^2))`
- LogLoss（多分类）：`sklearn.metrics.log_loss`

## 产物路径

由 `config.settings` 统一管理，默认输出到：

- 模型：`artifacts/models/baseline.pkl`
- 预测结果：`artifacts/eval/results.csv`
- 指标明细：`artifacts/eval/metrics.json`
- 运行汇总（追加）：`artifacts/eval/run_summary.csv`

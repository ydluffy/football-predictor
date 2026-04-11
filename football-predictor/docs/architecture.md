# Architecture

## Flow

1. Ingest: `ingest.load_data.load_matches_csv` 读取 `data/raw/matches.csv`
2. Features: `features.basic_features.build_training_frame` 生成训练用 `X/y`
3. Model: `models.baseline_logit.train_baseline_logit` 训练 Logistic Regression
4. Evaluate: `evaluate.metrics.classification_metrics` 输出评估指标
5. Orchestrate: `orchestrator.predict_pipeline.train_and_save` 统一编排并将模型/指标保存到 `artifacts/`
6. API: `api.main` 启动服务并加载最新模型，提供 `/predict`

## Artifacts

- `artifacts/models/`：模型文件（pickle）
- `artifacts/eval/`：评估指标（json）
- `artifacts/logs/`：运行日志（loguru）

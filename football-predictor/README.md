# football-predictor

一个最小可运行的足球比赛胜负（主队胜）预测项目骨架，包含数据读取、特征、基线模型训练、评估、模型落盘以及 FastAPI 推理服务。

## 目录结构

- `data/`：数据分层（raw/interim/processed）
- `artifacts/`：产物（models/eval/logs）
- `src/`：业务代码（config/ingest/features/models/evaluate/orchestrator/api/utils）
- `tests/`：pytest 单测
- `scripts/`：命令行脚本

## 快速开始

在项目根目录执行：

```bash
cd football-predictor
python -m venv .venv
.venv\\Scripts\\activate
pip install -U pip
pip install -e .
```

## 准备数据

默认从 `data/raw/matches.csv` 读取。`features.basic_features` 会根据以下字段推断标签：

- `home_goals` 与 `away_goals`（主队进球 > 客队进球 => 1）
  - 或者 `result` 字段为 `H/A/D`（`H` => 1）

你可以自行加入更多数值列作为特征，例如：`home_shots/away_shots/home_xg/away_xg/...`

### CSV 模板（标准填写）

项目提供可直接填写/导入的标准 CSV 模板（含 3 行示例数据）：

- `data/templates/matches_minimal_template.csv`：最小闭环（match base + odds basic）
- `data/templates/matches_v2_template.csv`：在 minimal 基础上增加 v2 字段（xG / injury_flag / line_move）
- `data/templates/matches_v3_template.csv`：在 v2 基础上增加 v3 字段（odds sequence / momentum 序列等）

填写约定：

- `actual_result` 仅允许 `H` / `D` / `A`
- `odds_*` 建议为 decimal odds 且 > 1.0
- `date` 建议为 `YYYY-MM-DD`（用于时间切分与 CV）

## 运行训练

```bash
python scripts/run_train.py
```

示例：

- 使用 mock（默认 sample）数据训练：

```bash
python scripts/run_train.py --model-type logit --feature-version v1 --calibration none --cv false
```

- 使用真实导入后的标准化数据训练：

```bash
python scripts/run_train.py --model-type logit --feature-version v1 --calibration none --cv false --data-path data/processed/real_matches_standardized.csv
```

运行后 CLI 会打印输入数据集路径与行数摘要：

```
data_flow.input_dataset_path=E:\...\data\processed\real_matches_standardized.csv
data_flow.input_dataset_row_count=552
```

## 无真实数据的一键联调

生成 mock v1/v2/v3 数据，并自动跑一条训练命令（lightgbm + v3 + sigmoid + cv=false），同时输出数据校验与缺失报告：

```bash
python scripts/bootstrap_mock_data.py
```

只生成 mock 数据与报告、不运行训练：

```bash
python scripts/bootstrap_mock_data.py --run-train false
```

## Research Director（多 Agent 工作流）

可手动触发三类 workflow，并输出本次执行的 `run_id`、关键产物路径与 decision（若有）。

示例：

```bash
python scripts/run_research_director.py --workflow daily_prediction --data-mode mock --model-type logit --feature-version v3 --calibration none --use-verifier true
python scripts/run_research_director.py --workflow post_match_learning --data-mode real --matches-path data/processed/real_matches_standardized.csv
python scripts/run_research_director.py --workflow candidate_upgrade --data-mode mock --allow-high-risk false
```

参数说明（与现有训练系统对齐）：

- `--workflow`: `daily_prediction` / `post_match_learning` / `candidate_model_upgrade`（也支持别名 `candidate_upgrade`）
- `--model-type`: `logit` / `lightgbm` / `stacking` / `stacking_oof`
- `--feature-version`: `v1` / `v2` / `v3`
- `--calibration`: `none` / `sigmoid` / `isotonic`
- `--use-verifier`: `true` / `false`
- `--data-mode`: `mock` / `real`
  - `mock`: 自动调用 DataScout 生成 mock 数据并执行后续步骤
  - `real`: 若未显式提供 `--raw-matches-csv/--mapping-path`，会尝试使用默认路径（`data/external/incoming_matches.csv` 与 `data/mappings/example_mapping_*.json`）
  - `real` 模式 CLI 会额外打印 preflight 诊断信息（raw/mapping 是否存在、date 解析比例、row_count 等），并在 workflow 执行后打印 standardized/validation/missing 产物路径（若有）

### Registry 查询

打印当前 production model 与最近若干 candidate（不强制执行 workflow）：

```bash
python scripts/run_research_director.py --show-registry true
python scripts/run_research_director.py --show-registry true --registry-limit 10
```

与 workflow 参数同时存在时，会先执行 workflow，再输出 registry 摘要：

```bash
python scripts/run_research_director.py --workflow candidate_model_upgrade --show-registry true --allow-high-risk true
```

### 默认任务配置（样例）

仓库提供一份默认任务样例配置：[research_jobs.yaml](file:///e:/ball-match-prediction-system/football-predictor/config/research_jobs.yaml)，包含：

- `daily_prediction_mock`
- `daily_prediction_real`
- `post_match_learning_mock`
- `weekly_candidate_upgrade`

每个任务包含：`workflow/model_type/feature_version/calibration/use_verifier/data_mode/trigger`。

### 本地调度（单进程）

通过 `artifacts/research/schedules/scheduler_config.json` 配置定时任务，支持：

- trigger `interval`：按秒间隔触发
- trigger `cron`：5 字段 cron（minute hour day month weekday）

示例配置：

```json
{
  "schema_version": "research_scheduler_config_v1",
  "jobs": [
    {
      "job_id": "daily_v3",
      "workflow": "daily_prediction",
      "trigger": { "type": "interval", "seconds": 3600 },
      "model_type": "logit",
      "feature_version": "v3",
      "calibration": "none",
      "use_verifier": true,
      "data_mode": "mock"
    },
    {
      "job_id": "post_match_00_00",
      "workflow": "post_match_learning",
      "trigger": { "type": "cron", "cron": "0 0 * * *" },
      "model_type": "logit",
      "feature_version": "v3",
      "calibration": "none",
      "use_verifier": false,
      "data_mode": "real"
    }
  ]
}
```

启动调度器：

```bash
python scripts/run_research_director.py --scheduler true
```

启动后会打印已注册任务；每次任务执行仍会生成 `run_id`、execution record、以及研究报告输出。

### 手动跑单次 workflow

```bash
python scripts/run_research_director.py --workflow daily_prediction --data-mode mock --model-type logit --feature-version v3 --calibration none --use-verifier true
python scripts/run_research_director.py --workflow post_match_learning --data-mode real --matches-path data/processed/real_matches_standardized.csv
python scripts/run_research_director.py --workflow candidate_model_upgrade --allow-high-risk true --data-mode real
```

### 查看 registry

```bash
python scripts/run_research_director.py --show-registry true
python scripts/run_research_director.py --show-registry true --registry-limit 10
```

## 导入真实 CSV（只做导入/清洗/校验，不训练）

接入流程：

1. 准备原始 CSV（外部数据源导出；列名可保持原样）
2. 准备 mapping JSON（把外部列名映射到项目标准字段；示例见 `data/mappings/`）
3. 运行导入脚本 `import_real_csv.py`
4. 检查 standardized 数据 + validation + missing report + 映射报告
5. 确认无误后再运行 `run_train.py` 训练/评估

```bash
python scripts/import_real_csv.py --input-path path/to/raw.csv --mapping-path data/mappings/example_mapping_v2.json --feature-version v2
```

最小示例命令（按 feature_version）：

```bash
python scripts/import_real_csv.py --input-path path/to/raw.csv --mapping-path data/mappings/example_mapping_minimal.json --feature-version v1
python scripts/import_real_csv.py --input-path path/to/raw.csv --mapping-path data/mappings/example_mapping_v2.json --feature-version v2
python scripts/import_real_csv.py --input-path path/to/raw.csv --mapping-path data/mappings/example_mapping_v3.json --feature-version v3
```

输出：

- `data/interim/imported_preview.csv`（导入预览，最多 200 行）
- `data/processed/real_matches_standardized.csv`（标准化后数据）
- `artifacts/eval/dataset_validation.json`
- `artifacts/eval/dataset_missing_report.csv`
- `artifacts/eval/import_summary.json`
- `artifacts/eval/field_mapping_report.csv`

导入后训练（示例：lightgbm + v3）：

```bash
python scripts/run_train.py --model-type lightgbm --feature-version v3 --calibration none --cv false
```

运行 v1（仅赔率基础特征）：

```bash
python scripts/run_train.py --feature-version v1
```

运行 v2（赔率 + xG + injury_flag + line_move）：

```bash
python scripts/run_train.py --feature-version v2
```

运行 v3（v2 + odds sequence + kelly proxy + ExpDecay momentum；缺字段会安全降级）：

```bash
python scripts/run_train.py --feature-version v3
```

## Phase 7（v3 特征对比）示例命令

```bash
python scripts/run_train.py --model-type logit --feature-version v3 --calibration none --cv false
python scripts/run_train.py --model-type lightgbm --feature-version v3 --calibration none --cv false
python scripts/run_train.py --model-type lightgbm --feature-version v3 --calibration sigmoid --cv false
python scripts/run_train.py --model-type stacking_oof --feature-version v3 --calibration none --cv false
python scripts/run_train.py --model-type lightgbm --feature-version v3 --calibration sigmoid --cv false --use-verifier true
```

校准对比（单次评估模式）：

```bash
python scripts/run_train.py --feature-version v2 --calibration none
python scripts/run_train.py --feature-version v2 --calibration sigmoid
```

## Phase 3（训练/评估统一入口）

单次 train/test（按 date 时间切分，输出可靠度表）：

```bash
python scripts/run_train.py --model-type logit --feature-version v2 --calibration sigmoid --cv false
```

时间序列交叉验证（expanding window，输出 cv_results.csv；不会影响单次训练产物文件）：

```bash
python scripts/run_train.py --model-type logit --feature-version v2 --cv true
```

## Phase 4（模型类型切换：logit vs lightgbm）

logit + v2：

```bash
python scripts/run_train.py --model-type logit --feature-version v2 --cv false
```

lightgbm + v2：

```bash
python scripts/run_train.py --model-type lightgbm --feature-version v2 --cv false
```

lightgbm + cv=true：

```bash
python scripts/run_train.py --model-type lightgbm --feature-version v2 --cv true
```

lightgbm + sigmoid calibration（会写入 calibration_compare.csv）：

```bash
python scripts/run_train.py --model-type lightgbm --feature-version v2 --calibration sigmoid --cv false
```

## Phase 5（stacking prototype）

stacking prototype（logit + lightgbm → LogisticRegression meta，prototype：非 OOF）：

```bash
python scripts/run_train.py --model-type stacking --feature-version v2 --calibration none --cv false
```

## Phase 6（OOF stacking：推荐方案）

stacking_oof（logit + lightgbm → LogisticRegression meta，meta features 来自训练集内部 OOF 概率）：

```bash
python scripts/run_train.py --model-type stacking_oof --feature-version v2 --calibration none --cv false
```

注意：

- `stacking` 是 prototype（非 OOF），用于快速验证互补性
- `stacking_oof` 是当前推荐的正式 stacking 方案
- 当前阶段 `--cv true` 不支持 `stacking_oof`（后续再做 nested/OOF CV），会显式报错

verifier（可选后处理，默认关闭）：

- `--use-verifier true`：在单次评估（`--cv false`）模式下，对测试集逐行做 verifier 风险标注，仅生成辅助产物，不修改概率与评估指标
- `--cv true` 时不会启用 verifier

lightgbm 特征重要性导出：

- 单次训练 `--model-type lightgbm` 会自动生成：`artifacts/eval/lightgbm_feature_importance.csv`

league-level 输出说明：

- 若输入数据包含 `league` 列，单次训练会生成：`artifacts/eval/league_metrics.csv`

SHAP（可选增强）：

- 若 `shap` 可用且成功运行，会生成：`artifacts/eval/lightgbm_shap_summary.csv`（缺失时会跳过，不影响训练成功）

模型对比结果：

- `artifacts/eval/model_compare.csv`（每次单次训练追加一行，可对比不同 model_type/feature_version/calibration_method 的指标）
- `model_compare.csv` 额外包含 `reliability_gap_mean` 与 `notes`（例如：stacking 标注 prototype，stacking_oof 标注 oof，lightgbm 标注特征重要性导出；若 `--use-verifier true` 会追加 verifier_enabled）
- 模型与实验顺序说明见：`docs/model_stack.md`
- 推荐实验顺序见：`docs/experiment_protocol.md`

训练完成后会在：

- `artifacts/models/logit_baseline.pkl`：LogisticRegression 模型文件（`--model-type logit`）
- `artifacts/models/lightgbm_baseline.pkl`：LightGBM 模型文件（`--model-type lightgbm`）
- `artifacts/models/stacking_meta.pkl`：stacking prototype 模型文件（`--model-type stacking`）
- `artifacts/models/stacking_oof_meta.pkl`：OOF stacking 模型文件（`--model-type stacking_oof`）
- `artifacts/eval/results.csv`：预测结果（包含 `model_type` 列）
- `artifacts/eval/metrics.json`：单次评估指标（包含 `model_type`）
- `artifacts/eval/run_summary.csv`：单次评估汇总（追加写入，包含 `model_type`）
- `artifacts/eval/feature_compare.csv`：特征版本对比（追加写入，包含 `model_type`）
- `artifacts/eval/reliability_table.csv`：可靠度分桶统计表
- `artifacts/eval/model_compare.csv`：模型对比表（追加写入）
- `artifacts/eval/calibration_compare.csv`：校准对比表（仅当 `--calibration != none` 时生成/追加）
- `artifacts/eval/cv_results.csv`：时间序列 CV 结果（仅当 `--cv true` 时生成）
- `artifacts/eval/cv_league_summary.csv`：时间序列 CV 的 league 聚合结果（仅当 `--cv true` 且输入包含 league 时生成）
- `artifacts/eval/verifier_results.csv`：verifier 风险标注结果（仅当 `--use-verifier true` 且 `--cv false` 时生成）
- `artifacts/eval/high_confidence_errors.csv`：高置信错判样本（当前由 error_analysis 导出；开启 verifier 时会附带 risk 字段）
- `artifacts/eval/underestimated_draws.csv`：低估平局样本（阶段性近似；开启 verifier 时会附带 risk 字段）
- `artifacts/eval/error_analysis_with_risk.csv`：错误分析扩展表（match_id 关联 verifier_results，用于观察风险标记与错判的关系；仅当 `--use-verifier true` 时生成）
- `artifacts/logs/app.log`：日志

## 启动 API

```bash
uvicorn api.main:app --reload
```

检查健康状态：

```bash
curl http://127.0.0.1:8000/health
```

预测示例：

```bash
curl -X POST http://127.0.0.1:8000/predict ^
  -H \"Content-Type: application/json\" ^
  -d \"{\\\"features\\\": {\\\"diff_shots\\\": 3, \\\"home_form\\\": 1}}\"
```

## 运行测试

```bash
pytest
```

# SHAP Notes

## 是否默认启用

默认尝试启用，但不会作为训练主流程的成功条件：

- 当 `model_type=lightgbm` 时，会尝试生成 SHAP summary
- 若 shap 依赖不可用或运行异常，则会跳过，不影响训练与评估产物输出

## 依赖要求

- 需要额外安装：`shap`
- 如果环境安装/运行不稳定，建议先只使用 `lightgbm_feature_importance.csv` 作为解释方式

## 回退逻辑

- 若 `import shap` 失败：记录并跳过（不抛出到主流程）
- 若模型不是 LightGBM 或缺少 `booster_`：视为不支持，记录并跳过

## 产物

- `artifacts/eval/lightgbm_shap_summary.csv`（仅在 shap 可用且成功运行时生成）

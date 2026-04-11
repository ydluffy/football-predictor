# Model Stack

## 已支持模型

- LogisticRegression（`model_type=logit`）
- LightGBM（`model_type=lightgbm`）
- stacking prototype（`model_type=stacking`）
- OOF stacking（`model_type=stacking_oof`）

## 模型定位

- logit：稳定、可解释、适合作为概率基线（便于做校准与可靠度分析）
- lightgbm：引入非线性交互能力，作为候选提升模型（用于和 logit 做并行对比）
- stacking prototype：用于验证 logit 与 lightgbm 是否存在互补增益（当前为 prototype，非 OOF）
- stacking_oof：Phase 6 主 stacking 方案（基模型 OOF 概率作为 meta features，再训练 LogisticRegression 元模型）

## LightGBM 当前暂不包含

- 自动调参
- SHAP（当前为可选增强，不作为主流程阻塞项）
- 联赛分层训练（已支持 league_metrics.csv 产物）
- 类别不平衡专项处理

## stacking_oof（Phase 6 主方案）

当前已实现更严谨的 OOF stacking：

- 基模型：logit + lightgbm
- 元模型：LogisticRegression
- 训练：在训练集内部使用 StratifiedKFold 生成 OOF 概率作为 meta features，再训练元模型
- 推理：使用全量训练集训练好的两套基模型生成概率，再由元模型输出最终概率

## stacking prototype（当前实现说明）

当前已实现一个简化版 stacking prototype（不做复杂 OOF 工程），用于快速验证 logit 与 lightgbm 是否存在互补增益：

- 基模型：logit + lightgbm
- 元模型：LogisticRegression
- 训练：在同一训练集上先训练基模型，再用基模型在训练集上的概率输出作为 meta features 训练元模型

注意：这不是严格的 OOF stacking，下一阶段再升级为 time-aware 的 OOF stacking。

## 推荐实验顺序

1. 先跑 logit v2，确认特征与时间切分评估逻辑稳定
2. 再跑 lightgbm v2，观察是否带来 Brier / LogLoss 改善
3. 再比较 calibration 前后（none vs sigmoid/isotonic），确认概率质量是否提升
4. 再跑 stacking prototype，验证 logit 与 lightgbm 是否存在互补增益
5. 最后查看 league_metrics 与 feature_importance（以及可选的 SHAP）

## 运行示例

logit v2（单次评估）：

```bash
python scripts/run_train.py --model-type logit --feature-version v2 --calibration none --cv false
```

lightgbm v2（单次评估）：

```bash
python scripts/run_train.py --model-type lightgbm --feature-version v2 --calibration none --cv false
```

校准对比（建议先 sigmoid）：

```bash
python scripts/run_train.py --model-type logit --feature-version v2 --calibration sigmoid --cv false
python scripts/run_train.py --model-type lightgbm --feature-version v2 --calibration sigmoid --cv false
```

时间序列 CV（expanding window）：

```bash
python scripts/run_train.py --model-type logit --feature-version v2 --cv true
python scripts/run_train.py --model-type lightgbm --feature-version v2 --cv true
```

stacking prototype（单次评估）：

```bash
python scripts/run_train.py --model-type stacking --feature-version v2 --calibration none --cv false
```

stacking_oof（单次评估，推荐方案）：

```bash
python scripts/run_train.py --model-type stacking_oof --feature-version v2 --calibration none --cv false
```

## 对比产物

- `artifacts/eval/model_compare.csv`：单次评估后追加一行，用于对比不同 `model_type/feature_version/calibration_method`
- `artifacts/eval/lightgbm_feature_importance.csv`：仅 lightgbm 单次评估时生成
- `artifacts/eval/league_metrics.csv`：输入包含 league 时生成
- `artifacts/eval/lightgbm_shap_summary.csv`：仅当 shap 可用且成功运行时生成（可选）

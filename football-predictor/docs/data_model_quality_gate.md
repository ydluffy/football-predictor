# 数据与模型质量门禁

`scripts/check_data_model_quality.py` 把数据和模型健康状态统一为一个可审计、可阻断的 JSON 报告。策略由 `config/data_model_quality_gate.json` 管理，代码、CI 与生产任务共用同一组阈值。

## 五项门禁

| 检查 | 指标 | 默认阈值 |
| --- | --- | --- |
| 数据新鲜度 | 当前数据中最新 `snapshot_at` 相对执行时间的年龄 | 不超过 36 小时 |
| 必填字段缺失 | 必填单元格整体缺失率 / 单列最大缺失率 | 不超过 2% / 5% |
| 赔率覆盖 | `odds_home`、`odds_draw`、`odds_away` 同时为有效十进制赔率的行占比 | 不低于 95% |
| 特征漂移 | 当前窗口相对审核基准窗口的 PSI | PSI > 0.1 记为漂移；单特征不超过 0.25，漂移特征比例不超过 20% |
| 模型校准 | Brier、平均可靠性差距、校准前后 Brier 变化、样本数 | 见策略文件 |

缺失输入列、不可解析时间、空数据、缺少校准指标都属于输入错误，不会降级为通过。

`snapshot_at` 是本批特征/赔率完成采集的 UTC 时间，不能用比赛开球时间代替。这样即使数据中包含未来赛程，也不会掩盖抓取任务已经停止的问题。

## 生产运行

```powershell
.\scripts\project.ps1 data-model-quality `
  --dataset path/to/current_scoring_snapshot.csv `
  --reference path/to/approved_reference.csv `
  --metrics artifacts/eval/model_compare.csv
```

输出默认为 `artifacts/eval/data_model_quality_gate.json`：

- `status=pass`，退出码 `0`：允许进入预测发布或模型晋级；
- `status=fail`，退出码 `1`：指标越过策略阈值；
- `status=error`，退出码 `2`：输入、配置或文件格式不可信。

`--as-of` 只用于历史回填和确定性的 CI 检查；在线任务应省略该参数，让门禁使用当前 UTC 时间。

## 基准与指标输入约定

漂移基准应来自已审核、表现稳定且与当前特征版本一致的生产窗口。更新基准是一次受控治理动作，应保留来源时间、特征版本和审核记录，不能由待检测批次自动覆盖。

模型指标可使用 JSON 或 CSV。至少需要：

- `n_samples`（或 `sample_count`）；
- `brier_calibrated`（或 `brier`）；
- `brier_raw`（缺失时回退到 `brier`）；
- `reliability_gap_mean`（也接受 `reliability_gap` 或 `ece`）。

CSV 存在 `run_time` 时会选择时间最新的一行，否则使用最后一行。CI 使用版本化小样本验证完整门禁链路；生产数据和运行报告保持为本地产物，不提交仓库。

# v2 候选模型与组合策略影子升级

## 状态

- 启动日期：2026-08-16
- 运行模式：`shadow_only`
- 生产模型、生产候选逻辑和投注台账：未修改
- 单场模型结论：`shadow_candidate`
- 组合策略结论：代码与护栏已就绪，真实影子组合仍等待独立模型概率
- 每日旁路：已写入生产调度规范；独立影子台账为 `data/manual/shadow_portfolio_ledger_v2.csv`

## 单场模型 v2

v2 保留净胜球九分类框架，但不再直接使用候选模型的完整概率。每个外层留出赛季只用更早赛季训练；模型权重只通过外层测试季之前的最近一个赛季选择。

- `-2/-1` 最大候选权重为 50%。
- `+1/+2` 因 v1 最近赛季不稳定，最大候选权重为 25%。
- 内层验证改善不足 0.0005 时自动退回历史盘口基线。
- 不读取收盘赔率，不允许未来赛季参与权重选择。
- 即使统计闸门通过，也只能输出影子概率，不能触发真实方案。

2026-08-16 回测覆盖 9,523 场、38,092 个整数让球场景。相对历史盘口基线的平均 Log Loss 差值为 -0.002781，聚类 Bootstrap 95% 区间为 [-0.003391, -0.002147]。最近两个留出赛季四个让球档位均未退化，联赛和平均校准闸门通过。

仍未通过的部署闸门：

- 历史体彩赔率尚未完成同场同时间对齐；
- 独立已结算影子方案不足 300 个；
- 因此不得验证或宣称真实正期望收益，不得替换生产配置。

运行命令：

```powershell
.\.venv\Scripts\python.exe scripts\run_sporttery_handicap_shadow_v2.py `
  --predictions-output artifacts\eval\sporttery_handicap_shadow_v2_predictions_2026-08-16.csv `
  --folds-output artifacts\eval\sporttery_handicap_shadow_v2_folds_2026-08-16.csv `
  --json-output artifacts\eval\sporttery_handicap_shadow_v2_2026-08-16.json `
  --markdown-output artifacts\eval\sporttery_handicap_shadow_v2_2026-08-16.md
```

## 组合策略 v2

组合层只接受带独立模型概率和完整来源标记的候选，硬约束如下：

- 市场隐含概率或赔率倒数不能冒充模型概率；
- 默认最多 2 串，拒绝 3 串及以上；
- 默认赔率上限 4.00；
- 模型概率先扣除不确定性，再要求至少 2.5% 的保守边际；
- 总影子投入不超过预算的 50%，单候选不超过 15%；
- 单场暴露不超过 20%，单联赛暴露不超过 30%；
- 使用 0.15 倍凯利，且仅记录模拟仓位，不写真实台账。

2026-08-16 当前两套生产候选只有市场去水概率，组合 v2 正确拒绝两套候选，影子投入为 0 元。这是预期的安全行为，不是任务失败。

同日已将21场终版输入送入 v2 推理旁路；由于赛事训练域或安全外盘快照闸门，21场全部保持 `blocked`，没有生成影子组合，也没有写入影子台账。

输入字段模板见 `artifacts/data/shadow_portfolio_v2_input_audit_2026-08-16.csv`。运行命令：

```powershell
.\.venv\Scripts\python.exe scripts\build_shadow_portfolio_v2.py `
  --candidates-csv artifacts\data\shadow_portfolio_v2_input_audit_2026-08-16.csv `
  --output artifacts\betting\shadow_portfolio_v2_2026-08-16.csv `
  --audit-output artifacts\betting\shadow_portfolio_v2_audit_2026-08-16.json
```

## 每日影子运行要求

1. 官方四玩法终版抓取和原生产闸门照常运行。
2. 只有受控训练域、赛前安全快照和受支持让球同时满足时，生成 v2 影子概率。
3. 原生产方案照常生成；v2 另行生成影子候选，不互相覆盖。
4. 赛后逐腿结算影子选择，并累计 Log Loss、Brier、ECE、收益、最大回撤和赛事暴露。
5. 未达到晋级闸门时只更新研究报告，不修改生产配置。

旁路推理命令：

```powershell
.\.venv\Scripts\python.exe scripts\predict_sporttery_handicap_shadow_v2.py `
  --market-csv <当次终版让球市场CSV> `
  --analysis-at <当次分析时间> `
  --output artifacts\data\sporttery_handicap_shadow_v2_predictions_<时间>.csv `
  --audit-output artifacts\data\sporttery_handicap_shadow_v2_predictions_<时间>.json
```

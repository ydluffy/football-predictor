# 世界杯预测复盘闭环

本阶段目标是把“赛前预测”和“赛后结果”分开保存，避免赛后才生成或修改预测，导致模型评估失真。

## 已实现

- 保存赛前预测快照：`artifacts/prediction_snapshots/world_cup_prediction_snapshot_YYYY-MM-DD.csv`
- 保存快照清单：同名 `.json`
- 读取 ESPN 世界杯 scoreboard 中已完赛比分
- 对增强预测进行逐场评分：
  - 胜平负是否命中
  - 第一比分是否命中
  - 前两个比分是否命中
  - 大小 2.5 球是否命中
  - 让球建议是否命中，仅对明确推荐让球的场次计分
  - Log Loss、Brier、实际/预期进球比
  - 雷速情报覆盖场次
- 输出分组统计：`artifacts/reviews/world_cup_review_group_stats_YYYY-MM-DD.csv`
- 按以下维度观察模型是否稳定：
  - 信心等级
  - 胜平负预测方向
  - 大小球方向
  - 让球建议
  - 阵容确认状态
  - 雷速情报覆盖状态

## 使用方式

```powershell
.\.venv\Scripts\python.exe scripts\run_world_cup_prediction_review.py `
  --snapshot-date 2026-06-16 `
  --predictions artifacts\predictions\world_cup_lineup_adjusted_with_leisu_2026-06-16.csv `
  --scoreboard data\external\espn-world-cup\scoreboard_2026.json `
  --output-dir artifacts\reviews
```

输出：

- `artifacts/reviews/world_cup_review_ledger_YYYY-MM-DD.csv`
- `artifacts/reviews/world_cup_review_group_stats_YYYY-MM-DD.csv`
- `artifacts/reviews/world_cup_review_summary_YYYY-MM-DD.json`
- `artifacts/reviews/世界杯预测复盘_YYYY-MM-DD.md`

## 当前 2026-06-16 快照复盘状态

在 2026-06-25 刷新 ESPN scoreboard 后，当前快照包含 57 场预测：

- 已结算：39
- 待结算：18
- 胜平负命中率：74.4%
- 第一比分命中率：7.7%
- 前两比分命中率：12.8%
- 大小 2.5 命中率：53.8%
- Log Loss：0.8144，优于均匀基线 1.0986
- 实际/预期进球比：1.14，说明本届样本目前比模型预期略偏大球

这些数字仍然只是早期样本，不能直接证明模型长期可靠，但已经能用于定位优化方向。

## 初步观察

- 胜平负方向目前明显好于随机基线，但仍需更长样本验证。
- 比分预测 Top2 命中率偏低，这是正常但需要优化的弱项。
- 大小球只有 53.8%，说明总进球校准需要单独优化。
- 当前唯一一场雷速情报覆盖比赛为伊朗 vs 新西兰，模型预测主胜但实际 2:2，因此不能从 1 场样本判断雷速情报价值。
- 有首发确认的样本目前太少，阵容修正效果不能下结论。

## 评估原则

1. 快照应在赛前创建。
2. 快照默认不覆盖，防止赛后污染预测记录。
3. 复盘只评价已经完赛的比赛。
4. 当前指标用于持续观察模型，不应在少量样本下直接判断模型“可靠”或“不可靠”。

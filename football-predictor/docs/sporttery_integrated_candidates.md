# 体彩综合投注候选表

更新时间：2026-07-05

## 目的

综合投注候选表把不同玩法放到同一张表里，避免只看单一玩法或只看正 EV。

当前覆盖：

- 胜平负
- 让球胜平负
- 总进球数
- 比分最佳 EV 项

输出脚本：

```powershell
.\.venv\Scripts\python.exe scripts\build_sporttery_integrated_candidates.py `
  --predictions artifacts\predictions\world_cup_lineup_adjusted_real_sporttery_2026-07-04_2300_calibrated.csv `
  --output artifacts\predictions\sporttery_integrated_candidates_2026-07-04_2300_calibrated.csv
```

## 分级规则

候选分为：

| 等级 | 含义 |
|---|---|
| `main_candidate` | 方向性候选，概率较高 |
| `single_candidate` | 可单独关注 |
| `small_stake_candidate` | 小注候选 |
| `longshot_only` | 高赔率长尾，只能小注 |
| `watch` | 观察，不进入主推 |

## 风险降级

以下情况会自动降级：

1. 淘汰赛校准结果与原始玩法选择冲突。
2. 风险标记过多，例如高平局风险、深盘修正、点球尾部风险。
3. 比分项概率过低，即使 EV 为正也降级。
4. 总进球精确项与校准大小球方向冲突。

## 例子

2026-07-04 23:00 校准版：

| 比赛 | 玩法 | 原选择 | 校准 | 最终等级 | 说明 |
|---|---|---|---|---|---|
| Paraguay vs France | 让球 | 让负 | 让胜 | `single_candidate` | 正EV但与深盘校准冲突，被降级 |
| Paraguay vs France | 比分 | away_other | 无 | `watch` | EV高但概率低，不能主推 |
| Canada vs Morocco | 总进球 | 1球 | 小2.5 | `small_stake_candidate` | 与校准方向一致，但风险标记多 |

## 输出文件

最新示例：

```text
artifacts/predictions/sporttery_integrated_candidates_2026-07-04_2300_calibrated.csv
```

审计文件：

```text
artifacts/predictions/sporttery_integrated_candidates_2026-07-04_2300_calibrated.json
```

## 后续增强

1. 增加半全场玩法候选。
2. 为比分玩法输出 Top N EV，而不是只输出最佳 EV。
3. 引入资金分配建议。
4. 建立候选表赛后复盘，统计各等级命中率和 ROI。

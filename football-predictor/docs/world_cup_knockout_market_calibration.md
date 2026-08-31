# 世界杯淘汰赛让球与总进球校准层

更新时间：2026-07-05

## 背景

2026-07-04 两场复盘暴露出一个问题：模型的胜负方向和晋级方向能命中，但让球、总进球和比分容易失真。

典型样本：

| 比赛 | 模型方向 | 实际 | 暴露问题 |
|---|---|---|---|
| Canada vs Morocco | 摩洛哥胜、加拿大+1让胜、小2.5 | 0-3 | 低估热门打穿能力 |
| Paraguay vs France | 法国胜、法国穿-2、大2.5 | 0-1 | 高估强队深盘和大球 |

因此新增一层 `knockout_market_calibration`。它不替代基础模型，只对淘汰赛的让球和总进球输出风险修正。

## 新增输出字段

预测 CSV 新增：

| 字段 | 含义 |
|---|---|
| `knockout_calibration_applied` | 是否启用淘汰赛校准 |
| `knockout_calibrated_handicap_result` | 校准后的让球建议 |
| `knockout_calibrated_handicap_confidence` | 校准后的让球置信度 |
| `knockout_calibrated_total_goals_pick` | 校准后的大小球方向 |
| `knockout_calibrated_total_goals_confidence` | 校准后的大小球置信度 |
| `knockout_calibration_risk_flags` | 风险标记 |

## 风险标记

| 标记 | 含义 |
|---|---|
| `high_90m_draw_risk` | 90分钟平局风险高 |
| `penalty_tail_risk` | 点球尾部风险高 |
| `low_total_draw_cluster` | 低总进球和平局聚集 |
| `favorite_blowout_tail` | 强队大胜尾部存在 |
| `deep_spread_conservative_override` | 深盘淘汰赛保守修正 |
| `draw_risk_spread_dampener` | 平局风险削弱穿盘判断 |
| `over_total_knockout_dampener` | 大球信号在淘汰赛中降权 |
| `under_total_favorite_can_break_game` | 小球信号存在被强队打穿风险 |

## 当前效果

用 2026-07-04 23:00 预测快照回测：

| 比赛 | 原让球 | 校准让球 | 原大小球 | 校准大小球 | 说明 |
|---|---|---|---|---|---|
| Canada vs Morocco | 让胜 | 让胜 | 小2.5 | 小2.5 | 保留原判断，但标记高平局/点球/低总进球风险 |
| Paraguay vs France | 让负 | 让胜 | 大2.5 | 大2.5 | 深盘从追法国穿盘改为保守受让方向 |

这说明校准层已经能修正“强队深盘过度追穿”的一类错误；但对 Canada vs Morocco 这种“低总进球模型被热门打穿”的场景还需要继续优化。

## 下一步

1. 给总进球加入“热门打穿风险”特征：外盘热门程度、体彩客胜过热、让球盘方向和赔率压缩。
2. 建立淘汰赛复盘样本表，按风险标记统计命中率。
3. 把 `knockout_calibrated_*` 字段用于候选表筛选，正 EV 但风险标记过多时降级。

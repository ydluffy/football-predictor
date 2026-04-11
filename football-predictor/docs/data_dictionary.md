# 数据字典（Football Predictor）

本数据字典定义了足球预测项目的标准字段集合，按模块组织。字段的“缺失处理”描述的是当前代码路径下的默认行为（重点：训练/特征工程不应因可选字段缺失而失败）。

## 1) Match Base

| 字段名 | 类型 | 必填 | 示例值 | 用于哪个特征模块 | 缺失时如何处理 |
|---|---|---:|---|---|---|
| match_id | string | 是 | `m000123` | 所有模块（关联键） | 若缺失：数据校验报错；训练入口需有唯一标识 |
| date | string/date | 否 | `2025-08-01` | 时间切分/时间序列 CV | 缺失：单次训练退化为不切分（train=test）；CV 会报错（缺 date） |
| league | string | 否 | `EPL` | league_metrics / cv_league_summary / error_analysis_with_risk | 缺失：不输出 league 聚合；错误分析表 league 为空 |
| home_team | string | 否 | `Arsenal` | verifier（MatchContext）/后续扩展 | 缺失：不影响训练；verifier 中为空 |
| away_team | string | 否 | `Chelsea` | verifier（MatchContext）/后续扩展 | 缺失：不影响训练；verifier 中为空 |
| actual_result | string | 是 | `H` / `D` / `A` | 训练标签/评估 | 若缺失：数据校验报错；训练无法进行 |

## 2) Odds Basic

| 字段名 | 类型 | 必填 | 示例值 | 用于哪个特征模块 | 缺失时如何处理 |
|---|---|---:|---|---|---|
| odds_home | float | 是 | `1.95` | v1/v2/v3 基础赔率特征 | 若缺失或非数：数据校验报错 |
| odds_draw | float | 是 | `3.25` | v1/v2/v3 基础赔率特征 | 若缺失或非数：数据校验报错 |
| odds_away | float | 是 | `4.10` | v1/v2/v3 基础赔率特征 | 若缺失或非数：数据校验报错 |

## 3) Odds Sequence（宽表快照）

### 3.1 Open/Last（推荐）

| 字段名 | 类型 | 必填 | 示例值 | 用于哪个特征模块 | 缺失时如何处理 |
|---|---|---:|---|---|---|
| odds_home_open | float | 否 | `2.05` | odds_sequence_features / kelly_features | 缺失或 NaN：对应行相关特征降级为 0 |
| odds_draw_open | float | 否 | `3.30` | odds_sequence_features / kelly_features | 同上 |
| odds_away_open | float | 否 | `3.80` | odds_sequence_features / kelly_features | 同上 |
| odds_home_last | float | 否 | `1.98` | odds_sequence_features / kelly_features | 同上 |
| odds_draw_last | float | 否 | `3.35` | odds_sequence_features / kelly_features | 同上 |
| odds_away_last | float | 否 | `3.90` | odds_sequence_features / kelly_features | 同上 |

### 3.2 可选 t1/t2（用于 recent move）

| 字段名 | 类型 | 必填 | 示例值 | 用于哪个特征模块 | 缺失时如何处理 |
|---|---|---:|---|---|---|
| odds_home_t1 | float | 否 | `2.01` | odds_sequence_features（recent_home_move） | 若 t1/t2 任一缺失：recent_*_move=0 |
| odds_home_t2 | float | 否 | `1.98` | odds_sequence_features（recent_home_move） | 同上 |
| odds_draw_t1 | float | 否 | `3.32` | odds_sequence_features（recent_draw_move） | 同上 |
| odds_draw_t2 | float | 否 | `3.35` | odds_sequence_features（recent_draw_move） | 同上 |
| odds_away_t1 | float | 否 | `3.85` | odds_sequence_features（recent_away_move） | 同上 |
| odds_away_t2 | float | 否 | `3.90` | odds_sequence_features（recent_away_move） | 同上 |

## 4) xG / Team Strength

### 4.1 单场 xG（v2/v3）

| 字段名 | 类型 | 必填 | 示例值 | 用于哪个特征模块 | 缺失时如何处理 |
|---|---|---:|---|---|---|
| xg_home | float | 否 | `1.45` | v2/v3（xg_diff/xg_sum） | 缺失：按 0 处理 |
| xg_away | float | 否 | `0.92` | v2/v3（xg_diff/xg_sum） | 缺失：按 0 处理 |

### 4.2 最近 3 场 xG/xGA（v3 momentum）

| 字段名 | 类型 | 必填 | 示例值 | 用于哪个特征模块 | 缺失时如何处理 |
|---|---|---:|---|---|---|
| home_xg_last_1 | float | 否 | `1.6` | momentum_features（home_attack_momentum） | 缺失/NaN：该项跳过；若整行都无有效值则输出 0 |
| home_xg_last_2 | float | 否 | `1.2` | momentum_features | 同上 |
| home_xg_last_3 | float | 否 | `0.9` | momentum_features | 同上 |
| away_xg_last_1 | float | 否 | `1.1` | momentum_features（away_attack_momentum） | 同上 |
| away_xg_last_2 | float | 否 | `0.8` | momentum_features | 同上 |
| away_xg_last_3 | float | 否 | `0.7` | momentum_features | 同上 |
| home_xga_last_1 | float | 否 | `0.9` | momentum_features（home_defense_momentum） | 同上 |
| home_xga_last_2 | float | 否 | `0.8` | momentum_features | 同上 |
| home_xga_last_3 | float | 否 | `0.7` | momentum_features | 同上 |
| away_xga_last_1 | float | 否 | `1.2` | momentum_features（away_defense_momentum） | 同上 |
| away_xga_last_2 | float | 否 | `1.0` | momentum_features | 同上 |
| away_xga_last_3 | float | 否 | `0.9` | momentum_features | 同上 |

## 5) Context

| 字段名 | 类型 | 必填 | 示例值 | 用于哪个特征模块 | 缺失时如何处理 |
|---|---|---:|---|---|---|
| injury_flag | int(0/1) | 否 | `1` | v2/v3（injury_flag）+ mock_verifier | 缺失：按 0 处理；verifier 中为空/不触发 injury_risk |
| line_move | float | 否 | `-0.12` | v2/v3（line_move）+ mock_verifier | 缺失：按 0 处理；verifier 中为空/不触发 line_move_risk |


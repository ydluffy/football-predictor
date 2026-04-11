# 数据契约（Data Contract）

本数据契约定义“训练/评估入口所接受的最小数据要求”、可选扩展字段、以及数据质量校验与产物约定，目标是保证在没有真实数据时也能建立标准化数据流（模板 + mock + 校验 + 报告）。

## 1) 数据集级契约

### 1.1 最小可训练输入（必须满足）

- 文件格式：CSV（UTF-8）
- 行粒度：一行 = 一场比赛
- 必需列（缺失则应视为数据不可用）：
  - `match_id`（string，建议全局唯一）
  - `odds_home`, `odds_draw`, `odds_away`（float，decimal odds）
  - `actual_result`（string：`H`/`D`/`A`）

### 1.2 可选列（缺失不影响训练，但会影响能力/产物）

- 时间相关：
  - `date`（用于 time-based split / time series CV）
- 分层评估：
  - `league`（用于 league_metrics / cv_league_summary / error_analysis_with_risk）
- v2 特征增强：
  - `xg_home`, `xg_away`
  - `injury_flag`（0/1）
  - `line_move`（float）
- v3（Phase 7）扩展：
  - 赔率快照：`odds_*_open/odds_*_last` 或 `odds_*_t1/t2`
  - 动量序列：`home/away xg/xga last_1..3`

## 2) 字段级约束（关键字段）

- `match_id`
  - 必须非空；推荐唯一
  - 允许重复但会触发质量告警（duplicate_match_id）
- `odds_home/odds_draw/odds_away`
  - 必须为可解析的数值
  - 值建议 > 1.0；若 <=1.0 视为质量风险（warning）
- `actual_result`
  - 必须属于 `H/D/A`（大小写不敏感）

## 3) 训练入口兼容性声明

- 单次训练（cv=false）：
  - `date` 存在：按 date 做 time-based split
  - `date` 缺失：退化为 train=test（仅用于联调，不推荐用于评估）
- 时间序列 CV（cv=true）：
  - 必须提供 `date`
  - 仅支持 `model_type=logit|lightgbm`（stacking/stacking_oof 当前显式不支持外层 CV）

## 4) Data Foundation 产物契约（用于本地联调）

### 4.1 模板

- `data/templates/matches_template.csv`
  - 包含必需列 + 可选扩展列的标准表头
  - 可直接填充后用于训练入口

### 4.2 mock 数据

- `data/mock/mock_matches.csv`
  - synthetic/mock 数据集（可重复生成：seed 固定）
  - 覆盖常见可选字段（date/league/快照/动量等）

### 4.3 质量与缺失报告

- `artifacts/eval/data_quality_report.json`
  - 数据集级统计：行数、match_id 去重/重复、日期范围、league 分布、errors/warnings、按列缺失率等
- `artifacts/eval/data_missing_report.csv`
  - 每列缺失率明细（missing_count/missing_rate）

## 5) verifier 与错误分析的契约关系

- verifier 当前为可选后处理（`--use-verifier true`）：
  - 不要求把 verifier 输出并入主 `results.csv`
  - 会生成 `artifacts/eval/verifier_results.csv`（按 match_id 对应风险标记）
- 错误分析扩展表：
  - `artifacts/eval/error_analysis_with_risk.csv` 会通过 `match_id` 将错误样本与 `verifier_results.csv` 关联
  - 用于后续观察 high_confidence_errors 是否更常伴随 `line_move_risk` / `injury_risk`


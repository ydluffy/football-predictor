# Feature Spec (Phase 7)

## 范围

本文件描述 Phase 7 新增特征（赔率时序、Kelly proxy、ExpDecay 动量）在统一入口中的落地方式：`feature_version=v1/v2/v3` 的差异、各新增公式、字段来源（真实字段 vs proxy）、以及缺字段时的安全降级规则。

关键原则：

- `v1/v2` 逻辑保持不变，`v3` 仅在其基础上追加特征
- 允许宽表模拟：不要求实时爬虫或外部数据源
- 缺字段/NaN 不报错：相关特征按约定安全降级为 0

## Feature Versions

- `v1`：基础赔率特征（仅依赖 `odds_home/odds_draw/odds_away`）
- `v2`：`v1` + `xg_home/xg_away` + `injury_flag` + `line_move`
- `v3`：`v2` + odds sequence（赔率时序特征）+ kelly proxy（市场概率变化代理）+ momentum（ExpDecay 攻防动量代理）

## 输入字段约定（宽表模拟）

### 1) 基础赔率（真实字段，必需）

- `odds_home`, `odds_draw`, `odds_away`（decimal odds）

### 2) 赔率快照序列（真实字段，可选）

支持多种形式，若缺失会回退到使用基础赔率（等价于 open=last=基础赔率）：

- Open/Last 形式（推荐，宽表示例）：
  - `odds_home_open`, `odds_home_last`
  - `odds_draw_open`, `odds_draw_last`
  - `odds_away_open`, `odds_away_last`
- Open/Close 形式（兼容）：
  - `odds_home_open`, `odds_home_close`
  - `odds_draw_open`, `odds_draw_close`
  - `odds_away_open`, `odds_away_close`
- 多快照形式：
  - `odds_home_t1 ... odds_home_tN`（t 越小越早；取最小 t 为 open，最大 t 为 last）
  - `odds_draw_t1 ... odds_draw_tN`
  - `odds_away_t1 ... odds_away_tN`

宽表字段缺失与 NaN 处理：

- 若某行缺失 open/last（或为 NaN），本阶段相关特征统一安全降级为 0（不会报错）
- 若仅存在部分时序字段（例如只有 t1 没有 t2），依赖该对字段的特征（例如 recent_move）降级为 0

### 3) 动量序列（真实字段，可选）

用于构造攻防动量 proxy（不等价于真实球队强弱），当前实现使用 xG/xGA 的最近 3 场序列：

- `home_xg_last_1`, `home_xg_last_2`, `home_xg_last_3`
- `away_xg_last_1`, `away_xg_last_2`, `away_xg_last_3`
- `home_xga_last_1`, `home_xga_last_2`, `home_xga_last_3`
- `away_xga_last_1`, `away_xga_last_2`, `away_xga_last_3`

## 特征定义

### 0) v1 基础赔率特征（derived，非 proxy）

输入：`odds_home/odds_draw/odds_away`

- `norm_home, norm_draw, norm_away`：归一化 implied prob
  - `imp_home = 1/odds_home`（draw/away 同理）
  - `norm_home = imp_home / (imp_home + imp_draw + imp_away)`（draw/away 同理）
- `odds_diff_home_away = odds_home - odds_away`
- `home_vs_avg = odds_home - mean(odds_home, odds_draw, odds_away)`（draw/away 同理）

### 1) v2 增量特征（真实字段 + 简单派生）

输入（若缺失则安全降级为 0）：

- `xg_home`, `xg_away`
- `injury_flag`
- `line_move`

特征：

- `xg_diff = xg_home - xg_away`
- `xg_sum = xg_home + xg_away`
- `injury_flag`：缺失时视为 0
- `line_move`：缺失时视为 0

### 2) v3：odds sequence（derived，非 proxy）

输入（任一字段缺失或 NaN 时，对应行安全降级为 0）：

- `odds_*_open` 与 `odds_*_last`（或 close/t 序列）
- 可选：`odds_*_t1`, `odds_*_t2`（用于 recent move）

特征：

- 开盘到临盘变化：
  - `delta_home_open_last = odds_home_last - odds_home_open`
  - `delta_draw_open_last = odds_draw_last - odds_draw_open`
  - `delta_away_open_last = odds_away_last - odds_away_open`
- 相对变化率：
  - `pct_home_open_last = delta_home_open_last / odds_home_open`（draw/away 同理；若 open=0 或缺失则为 0）
- 方向特征（0/1）：
  - `home_odds_drop_flag = 1(delta_home_open_last < 0)`（draw/away 同理）
- 波动强度：
  - `odds_move_abs_sum = |delta_home_open_last| + |delta_draw_open_last| + |delta_away_open_last|`
  - `odds_move_max_abs = max(|delta_home_open_last|, |delta_draw_open_last|, |delta_away_open_last|)`
- 若存在 `t1/t2`：
  - `recent_home_move = odds_home_t2 - odds_home_t1`（draw/away 同理；缺任一字段则为 0）

### 3) v3：kelly proxy（proxy，明确非真实 Kelly）

当前版本不引入“模型预测概率”参与 Kelly 的真实计算，仅做市场侧的变化代理：

基础：把赔率转换为归一化 implied prob（同 v1 的 `norm_*`），分别在 open 与 last 上计算：

- `norm_*_open`：由 `odds_*_open` 归一化得到
- `norm_*_last`：由 `odds_*_last`（或 close / 最大 t）归一化得到

输出特征：

- `kelly_proxy_home/draw/away = norm_home/draw/away_last`
- `delta_kelly_proxy_home/draw/away = norm_*_last - norm_*_open`
- `kelly_direction_home/draw/away = sign(delta_kelly_proxy_*)`（取值 -1/0/1）
- `kelly_proxy_spread = max(kelly_proxy_home, kelly_proxy_draw, kelly_proxy_away) - min(...)`
- `kelly_proxy_max_shift = max(abs(delta_kelly_proxy_home), abs(delta_kelly_proxy_draw), abs(delta_kelly_proxy_away))`

降级规则：

- 若 open/last 无法构成完整三赔率（任一 outcome 缺失/非正/NaN），该行所有 kelly proxy 特征降级为 0

### 4) v3：ExpDecay 攻防动量（proxy，阶段性）

顺序假设：

- `*_last_1` 表示最近一场，权重最高
- `*_last_3` 表示更久远一场，权重最低

指数衰减均值：

- `exp_decay_mean([v1, v2, v3], decay=λ) = (v1 + λ*v2 + λ^2*v3) / (1 + λ + λ^2)`
- 当前默认 `λ=0.85`

输出特征：

- `home_attack_momentum = exp_decay_mean([home_xg_last_1, home_xg_last_2, home_xg_last_3], 0.85)`
- `away_attack_momentum = exp_decay_mean([away_xg_last_1, away_xg_last_2, away_xg_last_3], 0.85)`
- `home_defense_momentum = exp_decay_mean([home_xga_last_1, home_xga_last_2, home_xga_last_3], 0.85)`
- `away_defense_momentum = exp_decay_mean([away_xga_last_1, away_xga_last_2, away_xga_last_3], 0.85)`
- `attack_momentum_diff = home_attack_momentum - away_attack_momentum`
- `defense_momentum_diff = home_defense_momentum - away_defense_momentum`

## 兼容性说明

- v3 中：
  - odds sequence：缺少 open/last 或 NaN → 对应行降级为 0
  - recent_move：缺少 t1/t2 或 NaN → 对应行降级为 0
  - kelly proxy：open/last 任一 outcome 缺失/非正/NaN → 对应行降级为 0
  - momentum：缺少 last_1..3 或 NaN → 对应行按可用值计算；若该行无有效值则为 0

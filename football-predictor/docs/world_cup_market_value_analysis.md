# 世界杯市场价值分析

本阶段把中国体彩胜平负和让球胜平负赔率接入预测输出，用于比较“模型概率”和“市场隐含概率”。

## 核心思路

1. 读取中国体彩十进制赔率。
2. 将赔率转换为隐含概率。
3. 对隐含概率做去水处理，使三项概率之和等于 1。
4. 计算模型概率与市场概率的差值：

```text
value_edge = model_probability - market_probability
```

5. 计算简单期望收益指标：

```text
expected_value = model_probability * decimal_odds - 1
```

## 新增输出字段

胜平负市场：

- `spf_market_home_probability`
- `spf_market_draw_probability`
- `spf_market_away_probability`
- `spf_value_best_result`
- `spf_value_best_edge`
- `spf_value_best_expected_value`
- `spf_value_signal`

让球胜平负市场：

- `handicap_market_home_probability`
- `handicap_market_draw_probability`
- `handicap_market_away_probability`
- `handicap_value_best_result`
- `handicap_value_best_edge`
- `handicap_value_best_expected_value`
- `handicap_value_signal`

## 信号解释

- `positive`：模型概率比市场去水概率高至少 5 个百分点，且简单 EV 为正。
- `probability_edge_only`：模型概率高于市场概率，但按当前赔率计算 EV 仍为负。
- `watch`：有最优方向，但优势不足 5 个百分点。
- `no_market`：当前场次没有对应赔率，例如普通胜平负未开售。

## 使用方式

先刷新体彩官网数据：

```powershell
.\.venv\Scripts\python.exe scripts\refresh_lottery_gov_spf.py --date 2026-06-26
```

再运行预测：

```powershell
.\.venv\Scripts\python.exe scripts\run_world_cup_lineup_adjusted.py --as-of-date 2026-06-25 --sporttery-markets data\manual\sporttery_handicap_markets_2026-06-26.csv
```

## 注意事项

- 该模块用于分析模型与市场的分歧，不代表自动投注建议。
- 赔率和盘口会变化，应尽量保存开盘、临场、收盘多个快照。
- 当本地 fixture 日期和体彩开赛日期跨午夜时，系统允许同队名前后 1 天匹配。
- 价值信号需要赛后长期复盘验证，短期单场命中不能证明模型有效。

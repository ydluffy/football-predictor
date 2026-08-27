# 世界杯临场首发修正

## 目标

在基础胜平负、比分和总进球模型之外，加入临场首发信息。
该模块只在双方都已有确认 11 人首发时启用，避免用赛前大名单猜测首发。

## 当前特征

首发修正层使用统一球员数据契约中的信息：

- 是否确认 11 人首发
- 首发可用率
- 上一场首发保留率
- 国家队出场经验
- 首发之间共同出场次数
- 近 14 天负荷

当前 ESPN 公开数据已经能提供名单和首发，但还没有可靠伤停和俱乐部近期表现。
因此修正幅度被限制得很小，并且没有信息时不会强行调整。

## 调整逻辑

1. 如果任一球队没有确认 11 人首发：不调整预期进球。
2. 如果双方都有确认首发：计算双方首发强度分差。
3. 将强度分差转成很小的进球倍率。
4. 重新生成胜平负、比分、让球和总进球概率。

## 当前 2026-06-16 结果

刷新后，真实球队未来赛程 57 场，其中 1 场双方首发已确认：

- Iran vs New Zealand

该场双方现有首发强度分差为 0，因此首发修正层启用但不改变概率。
这是预期行为：当球员能力、伤停和俱乐部状态信息不足时，模型保持保守。

## 使用命令

先刷新实时球员数据：

```powershell
.\.venv\Scripts\python.exe scripts\import_espn_world_cup_live.py `
  --download true `
  --as-of-date 2026-06-16
```

再生成首发修正版预测：

```powershell
.\.venv\Scripts\python.exe scripts\run_world_cup_lineup_adjusted.py `
  --as-of-date 2026-06-16 `
  --output artifacts\predictions\world_cup_lineup_adjusted_2026-06-16.csv `
  --audit-output artifacts\predictions\world_cup_lineup_adjusted_2026-06-16.json
```

## 下一步

首发修正层已经接入预测链路。下一阶段最关键的是补球员强度来源：

- 俱乐部最近 90 天出场分钟
- 进球、助攻、xG、xA
- 位置分层能力评分
- 可靠伤停和停赛状态
- 跨数据源球员身份映射

# 世界杯球员强度代理

## 当前阶段

项目已加入第一版球员强度代理，用来支持临场首发修正。

当前可用数据包括：

- 球员年龄
- 场上位置
- 本届世界杯国家队出场
- 本届世界杯国家队首发
- 本届世界杯出场分钟

暂未接入：

- 俱乐部最近 90 天出场
- 俱乐部进球、助攻、xG、xA
- 权威身价或能力评分
- 可靠伤停和停赛

因此这版强度代理只做小幅修正，不会大幅改变基础模型概率。

## 评分逻辑

每名球员生成：

- `age_score`：按位置峰值年龄计算
- `experience_score`：根据本届世界杯出场分钟计算
- `starter_score`：根据本届世界杯首发次数计算
- `player_strength_score`：综合分
- `relative_player_strength`：队内相对强度
- `player_strength_confidence`：证据置信度

强度层只在双方确认 11 人首发时参与预测。

## 2026-06-16 结果

生成球员强度表：

- 球员数：1,251
- 有比赛证据球员：776
- 平均证据置信度：0.078

当前 Iran vs New Zealand 已触发首发修正：

- 主胜基础概率：0.76456
- 主胜修正后概率：0.76489
- 最可能比分：2:0、1:0

修正很小，说明模型目前仍然主要依赖球队级实力和进球模型。
这是当前数据质量下更安全的状态。

## 使用命令

```powershell
.\.venv\Scripts\python.exe scripts\build_world_cup_player_strength.py `
  --as-of-date 2026-06-16 `
  --output data\player_level\espn_world_cup_2026\player_strengths.csv `
  --audit-output artifacts\data\world_cup_player_strength_2026-06-16.json
```

生成强度表后，首发修正版预测脚本会自动读取：

```powershell
.\.venv\Scripts\python.exe scripts\run_world_cup_lineup_adjusted.py `
  --as-of-date 2026-06-16 `
  --output artifacts\predictions\world_cup_lineup_adjusted_2026-06-16.csv `
  --audit-output artifacts\predictions\world_cup_lineup_adjusted_2026-06-16.json
```

## 下一步

下一阶段应接入俱乐部近期状态。它比年龄和本届出场更能解释：

- 球员是否保持比赛节奏
- 主力是否刚经历高负荷
- 前锋和中场近期进攻贡献
- 门将和后卫近期防守表现
- 首发阵容和替补阵容的真实强弱差

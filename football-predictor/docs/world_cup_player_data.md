# 世界杯球员与阵容数据层

## 当前状态

球员级数据契约、身份映射、导入校验和赛前特征管线已经完成。

当前仓库尚未接入覆盖全部世界杯国家队的真实球员数据，因此这些特征不会自动进入正式预测模型。只有达到覆盖率和历史回测要求后，候选特征才允许晋级。

## 数据表

### players.csv

球员主表。`player_id` 是项目内部稳定身份，不能使用容易变化的球员姓名作为主键。

### player_aliases.csv

保存不同数据源中的球员 ID 和姓名到内部 `player_id` 的映射，防止重名、改名、重音符号和不同语言拼写造成重复球员。

### squads.csv

国家队名单和预计角色：

- `starter`：预计首发
- `substitute`：预计替补
- `squad`：入选名单但角色未确定

### availability.csv

赛前最新可用状态：

- `available`
- `doubtful`
- `injured`
- `suspended`
- `unavailable`

### club_appearances.csv

球员俱乐部逐场表现，包括分钟、首发、进球、助攻、xG 和 xA。

### national_appearances.csv

国家队逐场出场与首发，用于计算国家队经验、共同首发和阵容延续性。

## 已实现特征

- 预计首发人数
- 首发可用率
- 伤停、停赛和存疑人数
- 预计首发近 30/90 天俱乐部出场分钟
- 近 90 天每 90 分钟进球助攻
- 近 90 天每 90 分钟 xG+xA
- 近 14 天比赛负荷
- 平均国家队出场经验
- 预计首发之间的历史共同首发次数
- 与上一场国家队首发的保留率
- 同俱乐部首发球员组合数
- 首发球员俱乐部集中度

每个特征都会生成主队值、客队值和双方差值。

## 时间安全

俱乐部和国家队出场记录必须严格早于比赛日期。名单和伤停只读取比赛日当时最新快照。未来比赛、未来伤停更新和赛后确认信息不会进入赛前特征。

## 使用方式

复制 `data/templates/world_cup_*.csv` 模板并填入真实数据，然后运行：

```powershell
.\.venv\Scripts\python.exe scripts\build_world_cup_squad_features.py `
  --data-dir data/player_level/world_cup `
  --fixtures data/templates/world_cup_squad_feature_fixtures.csv
```

## 晋级门槛

- 球员身份解析率至少 98%
- 预计首发伤停覆盖率至少 95%
- 近期俱乐部分钟覆盖率至少 90%
- 每队需要 11 名预计首发
- 至少使用两届历史大赛进行严格时间回测
- Log Loss 或总进球指标必须在未参与选择的赛事中改善

在达到这些门槛前，球员特征只能作为研究快照，不能替换当前球队级模型。

## 首批真实数据

StatsBomb Open Data 的 2018 和 2022 世界杯阵容已经接入，共 128 场、1,328 名球员和 6,130 条球员比赛记录。历史首发与分钟覆盖率为 100%，但当前 2026 首发、伤停和俱乐部状态覆盖为 0%，因此尚未进入当前预测。

详细审计见 `docs/world_cup_real_player_data.md`。

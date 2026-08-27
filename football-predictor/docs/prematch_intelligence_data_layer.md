# 通用赛前情报数据层

## 目的

项目此前的确认阵容、伤停和球员强度主要服务世界杯，不能自动泛化到俱乐部联赛。本数据层统一保存能够证明“在分析时点已经知道”的赛前新增信息，供日常分析、研究回测和覆盖审计复用。

## 核心文件

- `config/prematch_data_sources.json`：来源许可、允许信号类型和自动导入权限。
- `data/manual/prematch_intelligence.csv`：实际赛前情报长表；初始只有表头。
- `data/templates/prematch_intelligence.csv`：填写示例，不属于实际数据。
- `src/data/prematch_intelligence.py`：规范化、许可检查、时间点过滤和特征聚合。
- `scripts/validate_prematch_intelligence.py`：生成只含合规记录的模型输入和验证审计，不覆盖人工原表。
- `scripts/audit_prematch_intelligence_coverage.py`：覆盖率与时间戳审计。
- `data/manual/sporttery_snapshot_index.csv`：体彩官方赔率不可变快照索引，记录哈希以及每批安全/不安全场次。
- `scripts/import_api_football_daily_intelligence.py`：按当天扫描自动唯一映射API-Football场次；确认阶段采集伤停/日历，终版阶段采集伤停/确认首发。
- `scripts/import_football_data_org_schedule_load.py`：API-Football历史日历受套餐限制时，使用football-data.org可访问赛事生成七天负荷后备。

## 时间闸门

每条记录必须同时满足：

1. `observed_at <= analysis_at`；
2. `analysis_at < kickoff_at`；
3. `observed_at <= kickoff_at`；
4. 若有 `expires_at`，则 `expires_at >= analysis_at`；
5. 来源、许可状态和信号类型与配置完全一致。

任何开赛后补录、缺少观测时间、许可不匹配或来源未登记的记录都不能进入特征。历史赛后阵容只能形成未来比赛的滚动历史强度，不得反写成当场赛前确认阵容。

自动化在使用数据前运行：

```powershell
.\.venv\Scripts\python.exe scripts\validate_prematch_intelligence.py
```

模型只能读取生成的 `data/processed/prematch_intelligence_validated.csv`，不得直接读取未经验证的人工长表。

## 支持的信息类型

- `absence`：伤停、停赛、出战存疑；`numeric_value` 表示影响强度。
- `confirmed_starter`：确认首发球员；两队各至少 11 条确认记录才设置 `both_lineups_confirmed=1`。
- `team_strength`、`prematch_xg`：明确带赛前快照时间的球队强度或 xG。
- `travel_km`、`timezone_shift_hours`：本场旅行和时区负担。
- `cross_comp_matches_7d`：包含联赛、杯赛和洲际赛事的七天比赛负荷。
- `odds_snapshot`：带 API/抓取时间的赔率快照，继续由赔率历史文件保存，配置中只声明使用权限。

所有数值都配套 `*_available` 特征。数值为零且可用性为零只表示缺失，不能解释为“没有伤停”“没有旅行”或“阵容完整”。

## 当前覆盖结论

截至2026-08-16，通用赛前表已有52条通过验证的记录：22条确认首发（1场）、16条带时间戳伤停（2场）、14条七天赛程负荷（7场），全部具有赛前 `observed_at`。工程上的“长期零行”问题已经解决，但样本仍远低于训练门槛，只能用于对应单场分析和后续积累。赛前xG、旅行距离和时区变化仍无通用记录；不得用空值或零值替代。

11:05确认阶段运行：

```powershell
.\.venv\Scripts\python.exe scripts\import_api_football_daily_intelligence.py --scan-json <确认扫描JSON> --date <销售日> --stage confirm
.\.venv\Scripts\python.exe scripts\import_football_data_org_schedule_load.py --scan-json <确认扫描JSON> --date <销售日>
```

每个动态终版时间组在体彩刷新后运行：

```powershell
.\.venv\Scripts\python.exe scripts\import_api_football_daily_intelligence.py --scan-json <本时间组扫描JSON> --date <销售日> --stage final
.\.venv\Scripts\python.exe scripts\build_daily_prematch_features.py --scan-json <本时间组扫描JSON> --analysis-at <终版分析时间>
```

确认模式只有最近7个日期接口全部成功时才接受API-Football的零负荷；套餐拒绝任一日期时不写负荷，并调用football-data.org后备。终版模式只请求仍未开赛且唯一映射场次的伤停和首发。阵容接口空表只表示“尚未发布/不覆盖”，不得写“阵容完整”。

逐场特征输出固定带 `*_available` 字段。现阶段该输出只能进入中文终版报告和影子研究，审计固定写入 `production_probability_change_allowed=false`、`stake_increase_allowed=false`；达到两赛季、每联赛500场和98%时间/映射通过率前，不得作为训练特征或提高投注置信度。

体彩扫描现已自动写入 `data/external/sporttery/snapshots/` 和索引。批次中已开赛/停售场次与仍未开赛场次分别记录，历史研究只能选择 `safe_match_numbers`；不得因为同批次包含过期场次而丢弃仍安全的观测，也不得把整个批次统一标记为安全。

## 启用研究的最低条件

- 单项信号至少覆盖两个完整赛季；
- 每个待研究联赛至少 500 场具有双队可用数据；
- 观测时间、开赛时间、来源许可和球队映射通过率均至少 98%；
- 使用时间顺序留出，并与同场市场概率做配对比较；
- 未达到覆盖条件时只能用于单场人工分析，不得训练或提高自动投注置信度。

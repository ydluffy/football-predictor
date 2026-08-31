# ESPN 俱乐部赛季统计接入

## 当前完成

项目已从 ESPN 公开俱乐部 roster 接口抓取球员赛季汇总统计，并写入：

- `data/player_level/espn_world_cup_2026/club_season_stats.csv`

来源示例：

- `https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/teams/20232/roster`
- `https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/teams/359/roster`

这些接口返回俱乐部 roster，并在部分球员上包含赛季统计。

## 已接入字段

- 出场次数 `appearances`
- 首发代理值 `starts_proxy`
- 进球 `goals`
- 助攻 `assists`
- 射门 `shots`
- 射正 `shots_on_target`
- 门将扑救 `saves`
- 失球 `goals_conceded`
- 黄牌、红牌

注意：这是赛季汇总，不是逐场比赛日志；没有精确比赛日期、逐场分钟和 xG/xA。

## 2026-06-16 覆盖率

- 请求俱乐部：138
- 匹配世界杯球员赛季统计：307 行
- 球员强度中有有效赛季出场统计：191 人
- 赛季统计有效覆盖率：15.3%
- 最近 90 天逐场俱乐部状态覆盖率：0%

## 模型使用方式

球员强度表现在会低权重吸收 ESPN 俱乐部赛季统计：

- `club_season_activity_score`
- `club_season_attack_score`
- `club_season_appearances`
- `club_season_goals`
- `club_season_assists`

因为它不是逐场 90 天数据，所以只作为轻量状态代理，不能替代真正的近期分钟和 xG/xA。

## 当前预测影响

在 2026-06-16 的 Iran vs New Zealand 中：

- 基础主胜概率：0.76456
- 加入首发和俱乐部赛季统计后：0.76391

变化很小，符合当前覆盖率和证据质量。

## 后续优先级

下一步仍应寻找或购买更完整的逐场数据源：

1. 最近 90 天逐场分钟
2. 最近 14 天负荷
3. 逐场进球、助攻、xG、xA
4. 门将扑救和后卫防守数据

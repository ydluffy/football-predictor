# 中国体彩和雷速数据接入状态

## 中国体彩

尝试访问中国竞彩网公开 Web API：

- `https://webapi.sporttery.cn/gateway/jc/football/getMatchInfoV1.qry`
- `https://webapi.sporttery.cn/gateway/jc/football/getMatchResultV1.qry`

当前运行环境被腾讯云 WAF 拦截，无法稳定获取 JSON 数据。
因此体彩数据暂未写入模型。

后续如果需要继续接入，建议使用：

- 官方允许的数据接口或合作数据服务
- 浏览器人工下载后的 CSV
- 运行在不触发 WAF 的本地网络环境中的同一导入脚本

## 雷速体育

雷速官网首页可公开访问，并包含世界杯赛程、比赛 ID、中文球队名、分析页和情报页链接。

已接入：

- `data/external/leisu_public_matches.csv`

可用字段：

- 雷速比赛 ID
- 赛事名称
- 中文主客队
- 日期和时间文本
- 详情页、数据分析页、赛事情报页 URL
- 情报数量

限制：

- 详情页和情报页当前返回 403/405 或访问频繁限制
- 未使用 App 私有接口
- 未绕过验证码或登录限制

当前雷速数据适合作为外部赛程和情报链接索引，不直接进入概率模型。

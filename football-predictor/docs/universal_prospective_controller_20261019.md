# 通用后备前瞻研究接入：2026-10-19

用户授权补齐验证并接入赛前冻结/赛后评分。本文件更新此前“尚未接入”的状态，原历史阶段记录仍保留。

## 验证

`artifacts/eval/universal_new_leagues_20261019/summary.json`：采用多机构赛前收盘均值AvgCH/AvgCD/AvgCA作为历史代理，不混用开盘填补。法乙349、瑞超306、巴甲555，共1,210场测试全部配对有效报价。逐联赛/日历年指标、校准分箱、时间块区间已保存。三个联赛通用模型均弱于市场：Log Loss分别1.080269/1.024988/1.024515，市场1.049348/0.984212/0.990236。因此只开展前瞻模拟，不升生产。

这不是新的训练或测试集调参。法乙2021/22原始下载超时缺口仍存在；本次补齐的是新联赛测试比赛的同场市场评价，不谎称全部历史已补齐。历史收盘代理无逐条采集时间，不等于同时间体彩验证。

## 路由与账本

原独立入口freeze成功后，自动运行`scripts/run_universal_comparison.py freeze`。参数为本批销售日、唯一batch-id、扫描、市场CSV、READY门禁及刚生成的专用预测CSV。检查四输入哈希、扫描身份、预测时间及模型哈希；二次核验门禁后独占写入新文件。既有回执同输入只读复用，输入改变报错。

只纳入专用预测明确outside_training_leagues或unknown_or_ambiguous_training_team、且通用模型可精确识别并有足够近期历史的比赛。专用已覆盖不重复加入；原after_kickoff/训练截止等安全阻断不允许用后备绕过。通用自身仍会拒绝未知/歧义/陈旧/杯赛/国家队。

新账本`artifacts/data/universal_comparison/`独立保存JSON、MD、预测及回执。市场/通用/固定50%融合每组每玩法12元理论预算，单关资格未核验。现有公共比较代码的independent组在此新账中明确映射为universal_fallback。每批仍维持原正式稳健/价值预算，不提高金额。

READY/开赛/硬锁/停售条件沿用原门禁，不能用早盘、旧门禁或已过锁补写。本次接入不生成午间赛前冻结，今天21:00起各批到期后才执行。能否覆盖需以当批实时输入为准，当前8/8只是预检。

## 结算

原`scripts/run_independent_comparison.py settle`自动调用通用`settle-pending`，读取同一官方赛果CSV，处理前一销售日及更早的通用快照。亦可手动运行：

```powershell
.\.venv\Scripts\python.exe scripts/run_universal_comparison.py settle-pending --results-csv <官方赛果CSV>
```

赛果须比赛号码、球队、开赛日、完赛状态唯一匹配。缺失、延期或歧义保持pending；明确官方无效场次按既有退款规则结算理论资金，剔除概率评分。评分分别包含胜平负、让球三项Log Loss/Brier，以及九档净胜球Log Loss/Brier/归一化有序RPS；按组汇总并记录唯一比赛数。分组理论投入、返奖、净收益和ROI另报，不把七项评分算成七场。

按赛果与评分代码哈希保存新版审计，结果修订不覆盖原快照。原专用模型与通用后备预测比赛集合不同，不能直接按总体命中率/返奖排名。研究失败保存audits，不阻断原正式流程；报告须写失败，不能把退出成功等同于有效覆盖。

`prospective_shadow_enabled=true`表示研究挂钩启用；`live_controller_enabled=false`表示不晋级生产概率。总控仍是原2026-09，没有新增自动化，13:00复盘排程不变。

盘口差的下一步研究规范：`docs/goal_margin_improvement_protocol_20261019.md`。该特征实验尚未训练，不能因为规范落地而宣称概率改进。

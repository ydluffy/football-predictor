# Vercel 一键部署（零基础照做版）

这个仓库已经改造成：**只部署一个 Next.js 项目（`web/`）即可上线**。

上线后你能用：
- `/setup`：自动检查环境变量是否配置正确 + 一键导入比赛数据
- `/fixtures`：查看赛程
- `/predictions`：查看预测
- `/chat`：自然语言对话（会调用工具查赛程/跑预测）

## 1. 在 Vercel 导入项目
1. 打开 Vercel → `Add New...` → `Project`
2. 选择你的 Git 仓库（`ball-match-prediction-system`）
3. 在项目配置中将 `Root Directory` 设置为 `web`
4. 保持 Framework Preset 为 `Next.js`，安装和构建命令使用默认值
5. 点击 `Deploy`

说明：Next.js 的 `package.json` 位于 `web/`。Vercel 必须从这个目录检测、安装和构建项目。

## 2. 配置环境变量（必须）
进入 Vercel 项目：`Settings` → `Environment Variables` → 逐条添加：

### Supabase（后端数据存储）
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

### football-data.org（比赛数据）
- `FOOTBALL_DATA_API_KEY`

### OpenRouter（聊天大模型）
- `OPENROUTER_API_KEY`
- `OPENROUTER_MODEL`（可选，默认 `deepseek/deepseek-chat`）

添加完后，点击 `Save`。

## 3. 重新部署
环境变量保存后：
- 回到 `Deployments` → 选择最新一次部署 → `Redeploy`

## 4. 上线后怎么验证
1. 打开你的线上域名，访问：`/setup`
2. 确认环境变量项全部是 ✅
3. 在 `/setup` 点击“导入”（默认导入今天的数据）
4. 去 `/fixtures` 看赛程是否出现
5. 去 `/predictions` 看胜平负概率条
6. 去 `/chat` 输入：`今天有什么比赛？` 或 `帮我预测今天的比赛`

## 常见问题
### 1) /chat 没反应或提示配置未就绪
去 `/setup` 页面，看哪一项是 ❌，回 Vercel 环境变量补齐，然后重新部署。

### 2) 导入失败（football-data.org 限流）
免费层是 10 次/分钟。系统已做了节流，但如果你频繁点导入，可能触发限流。等 1-2 分钟再试。

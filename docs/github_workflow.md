# GitHub 协作流程

这份文档只解决一件事：如何把当前项目稳定地交给 GitHub 管理，并让你、Trae Work、本地 Codex、Coze 云端电脑上的智能体都按同一套 Git 流程协作。

## 当前原则

1. GitHub 是唯一代码真源
2. 不直接把工作推到 `main`
3. 每个任务在独立分支完成
4. 合并前必须跑检查
5. 生成产物、台账、缓存和本地环境文件不入库

## 日常流程

### 第一步：先看状态

开始任何 Git 操作前，先执行：

```powershell
git status --short
git branch --show-current
git remote -v
```

这三条命令必须先看，避免在错误分支上提交，或把代码推到错误远程。

### 第二步：创建任务分支

不要在 `main` 上直接开发。建议：

```powershell
git checkout -b chore/cloud-collab-setup
```

常见命名方式：

- `docs/<topic>`：只改文档
- `chore/<topic>`：治理、配置、基础设施
- `feature/<topic>`：新功能
- `fix/<topic>`：缺陷修复
- `agent/codex/<topic>`：Codex 独立任务
- `agent/coze/<topic>`：Coze 云端独立任务

## 提交前检查

提交前至少执行与本次改动相关的检查。

### Python 相关

在仓库根目录执行：

```powershell
.\scripts\project.ps1 test
```

如果只改了治理、文档、部分模块，也可以按需运行：

```powershell
.\scripts\project.ps1 python-lint
.\scripts\project.ps1 python-typecheck
```

### Web 相关

```powershell
.\scripts\project.ps1 web-lint
.\scripts\project.ps1 web-typecheck
.\scripts\project.ps1 web-build
```

### 全量验证

```powershell
.\scripts\project.ps1 verify
```

## 提交流程

### 暂存改动

```powershell
git add .
```

如果你只想提交部分改动，不要直接 `git add .`，而是明确指定路径。

### 提交

```powershell
git commit -m "chore: checkpoint local automation and collaboration baseline"
```

提交信息建议结构：

- `docs: ...`
- `chore: ...`
- `feature: ...`
- `fix: ...`
- `refactor: ...`
- `test: ...`

### 推送

```powershell
git push -u origin chore/cloud-collab-setup
```

第一次推送新分支时，必须带 `-u`。

## PR 流程

推送完成后，在 GitHub 发起 PR。

PR 描述至少包含：

- 改了什么
- 为什么改
- 改动范围
- 是否影响自动化总控
- 是否影响数据库
- 是否跑过测试

如果是文档类 PR，也要明确“这只是规范文档更新，没有改生产逻辑”。

## 让 Codex 执行 Git 操作的推荐话术

给 Codex 下 Git 指令时，统一这样说：

```text
先检查 git 状态、当前分支和 remote，再执行。不要直接往 main 推送。遇到权限、认证、冲突、危险操作时先停下来汇报。
```

推荐完整模板：

```text
请先执行并展示：
- git status --short
- git branch --show-current
- git remote -v

然后基于当前改动创建新分支，完成 add / commit / push，但不要直接 push 到 main。
如果遇到权限、认证、remote 异常、冲突、历史改写风险，请先停止并告诉我。
```

## 云端电脑拉代码流程

云端电脑不靠手动传文件。统一使用 Git：

```powershell
git clone https://github.com/ydluffy/football-predictor.git
cd football-predictor
git checkout <你的任务分支>
```

如果仓库是私有的，先在云端电脑完成 GitHub 登录，再 clone。

## 何时用 `pull`

开始工作前，先同步：

```powershell
git pull --rebase
```

如果你在任务分支上工作，先确认自己当前分支再执行。

## 明确禁止的操作

以下操作除非你本人明确授权，否则任何智能体都不要做：

- `git push origin main`
- `git reset --hard`
- `git clean -fd`
- `git rebase -i`
- 强推 `git push --force`
- 删除远程分支
- 重写别人的提交历史

## 当前仓库的特殊注意事项

1. 本仓库有本地自动化总控在持续工作，提交前先看 `git status --short`
2. `football-predictor/artifacts/`、`data/manual/`、`data/raw/` 等目录属于本地产物，不入库
3. 根目录和 `football-predictor/` 的文档已经明确了“代码入库，产物留本地”的治理规则，提交时不要把这些边界打破

## 推荐节奏

最稳的节奏是：

1. 先在任务分支开发
2. 本地跑检查
3. push 到 GitHub
4. 发 PR
5. 验收通过后再合并

如果当天有自动化总控正在运行，尽量避免在未检查状态前做大规模 Git 操作。

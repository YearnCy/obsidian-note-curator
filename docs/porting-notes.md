# 实现与移植说明

面向维护者：这份 skill 在 DeepSeek Harness（DSH）里的执行层细节，以及从上游 WorkBuddy 版本合并时保留了什么、改了什么。

方法论文档（`references/spiral-teaching.md`、`narrative-style.md`、`note-style.md`）在两边应保持一致；差异集中在**执行层**——沙箱、shell、CLI、浏览器。

## 一、执行环境要求

- Python 3.8+，五个脚本只用标准库，无需安装任何包
- Windows 会话用 `pwsh`，macOS / Linux 用 `bash`；示例统一用正斜杠，两种 shell 都接受
- 官方 Obsidian CLI 可选（Obsidian 1.12+ 且应用正在运行），缺失时自动降级
- 配图渲染可选：`render_diagram.py` 用本机 Edge / Chrome 的无头模式截图

## 二、DSH 适配要点

1. **Frontmatter 用 DSH 规范**：`name` + `description` + `whenToUse` + `argument-hint`，触发词写进 description；去掉上游 WorkBuddy 专有的 `agent_created`。
2. **生态假设收紧**：上游依赖的兄弟 skill（`obsidian-markdown` / `obsidian-bases` / `obsidian-cli` / `obsidian-tasks`）在 DSH 里通常未安装。这里改为「未安装时由自带 `references/obsidian-syntax.md` 兜底，`.base` 与任务插件在用户确认采用之前不假设存在」。
3. **命令约定本地化**：待写入内容先用 agent 的 `write` 工具落到工作区 `.note-staging/`，再经 `--content-file` 交给 `note.py`；不依赖 `/tmp` 或 shell heredoc。
4. **`references/env-notes.md` 按 DSH 重写**：pwsh 无 coreutils、Python 解释器选择、**沙箱写入边界**、BOM 与 frontmatter 陷阱、官方 CLI 自定义安装目录探测不到、配图渲染链在沙箱内的降级方式、PowerShell 管道编码坑。

## 三、脚本层面的改动

- **`vault.py`**：跳过目录加入 `.dsh` / `.workbuddy` / `.embeddedskills` / `.note-staging`，避免把项目级 skill 根的 `SKILL.md` 或暂存片段误当笔记。
- **`ob.py`** 叠加三层沙箱防护：
  - `open` 默认只打印 `obsidian://` URI（`--launch` 仅供沙箱外手动使用）；
  - `probe` / `exec` 先做运行态检查（Windows 用 Toolhelp32 进程快照，避免崩溃后 `obsidian.json` 残留的 `open` 标记误判），未运行直接退出码 3 降级；
  - 候选列表**永久剔除 `Obsidian.exe`**：那是 200MB+ 的 Electron 主程序，在沙箱里启动会在单实例转发之前打开 `obsidian.log`，EPERM 直接崩溃。
  - 另修：补齐原脚本缺失的 `import webbrowser`；`exec` 对子进程启动失败优雅降级；`list_vaults` 按「`vaults.json` 的 default → 是否打开 → 最后打开时间」排序，避免把「最早添加的库」误当主库。
- **`step_audit.py`**：新增 `--vault` / `--root`，与 `vault.py` 共用仓库解析；整篇没有 H2 时退回按 H1 分组；跳过 frontmatter，避免 `tags` 里的词被当成术语。
- **`render_diagram.py`**：新增 `--format svg`（不栅格化，由 Obsidian 原生渲染）作为沙箱内的等效退路；临时 HTML 与浏览器 profile 放在 `<pic-root>/.figrender-tmp/`（系统临时目录会被沙箱拦截）；对「启动浏览器失败」「图片目录不可写」给出可执行建议而不是堆栈。

## 四、已知问题与修复：沙箱内拉起 Obsidian

**症状**：整理接近结束时弹出两个错误框 —— Electron 主进程 EPERM 无法打开 `%APPDATA%\obsidian\obsidian.log`，随后 `Obsidian.exe` 报 `0x80000003` 应用程序错误。

**原因**（两个都已堵掉）：① 从沙箱内的 shell 拉起 Obsidian GUI（`open` 里的 `os.startfile`），子进程继承沙箱文件权限，连自己的日志都写不了；② `ob.py` 曾把 PATH 里的 `Obsidian.exe` 当作 CLI 候选执行——即使 Obsidian 已在运行，第二个实例也会在单实例转发之前初始化日志而崩溃。

**修复**：`open` 默认只打印 URI；`probe` / `exec` 先做运行态检查；候选列表永久剔除 `Obsidian.exe`（含 `OBSIDIAN_CLI` 指向它的情况）。

## 五、验证记录

- `vault.py`：`tree` / `meta` / `links` / `audit` / `outline` / `search` / `find` 在真实笔记库上只读跑通
- `note.py`：`outline` / `insert`（dry-run 与正式写入 + 备份）/ `renumber` / `frontmatter` 用一次性测试库冒烟验证
- `step_audit.py`：在含代码块与表格的教学笔记上验证章节分组、首次出现、标题内高风险标记
- `render_diagram.py`：SVG 与 HTML 片段各渲染一张，验证尺寸推导、2 倍缩放、命名与嵌入语法
- `ob.py`：Obsidian 关闭时 `probe` / `exec` / `open` 三条降级路径（确认全程未 spawn 任何 Obsidian 进程）

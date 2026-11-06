# obsidian-note-curator —— DSH 版 Obsidian 笔记整理 skill

把一次对话的成果变成可长期复用的知识资产：**放进正确的位置、选择正确的读者任务、一次写对理解台阶、给出可验证结果、串上下一步链接**。

本目录是 WorkBuddy 的 `obsidian-note-curator` skill 的 **DeepSeek Harness（DSH）移植版**：方法论跟随上游，执行层按 DSH 的沙箱与工具链重写。

## 这一版相对上一版的重构

上一版是 2026-09-17 的移植（七步工作流、四类笔记、dry-run 纪律）。这一版把上游 2026-10 的「循环深入」方法论整套接进来，并把「补台阶」从写作习惯升级为**可审计的交付环节**：

- **第一优先级改为「首写铺满台阶」**：不再「先写正文、发现跳跃再补前置」，改为按 `简 C → 简 B → 深 A → 深 B → 深 C` 一次排好；核心概念走**三拍**（痛点 → 骨架 → 真实源码与行号），并在笔记开头写**读者起点契约**
- **新增 `references/spiral-teaching.md`**：三拍判据、概念登记表、反例库、倒读/删后读前/起点回看三种人工检查
- **新增 `references/narrative-style.md`**：场景先行、承认抽象、逐步演算、保留试错、代码与输出成对、换角度验证；以及「图的职责」分类
- **`references/note-style.md` 升级**：三拍写进文风基线，附件目录改为 `<vault>/BaiduSyncdisk/pic/<笔记名>/`，新增配图目录/命名/底色/分辨率规范，检查清单加两条硬项
- **模板升级**：`sub-note.md` / `explanation-note.md` 增加「读者起点」callout 与三拍骨架
- **新增 `scripts/step_audit.py`**：按 H2 章节列出每个技术标识符的首次出现位置，交付前逐条人工确认（退出码 1 = 有术语首次出现在标题里）
- **新增 `scripts/render_diagram.py`**：SVG / HTML 片段 → PNG，落到 `BaiduSyncdisk/pic/<笔记名>/` 并打印 `![[笔记名/图名.png]]`，不依赖 ImageMagick / Playwright
- **`ob.py` 吸收上游主库排序**：`vaults.json` 的 `default` 在 `vaults` 列表里置顶，再按「是否打开 → 最后打开时间」排序；同时**保留**上一版全部沙箱防护
- **工作流由七步扩为八步**：写作与写入之间插入「出图并渲染」，验证一步加入台阶审计与配图清单
- **`vaults.json` 登记主库 `upup`**：避免多库机器上外部工具把旧素材库当默认库

## 环境要求

- **Python 3.8+**（仅标准库，零依赖）。Windows 用 `python`，macOS/Linux 用 `python3`
- **官方 Obsidian CLI 可选**：Obsidian 1.12+ 且应用正在运行；没有也能完整使用（自动降级为文件扫描）。见 `references/obsidian-cli.md`
- **配图渲染可选**：`render_diagram.py` 用本机 Edge / Chrome 的无头模式截图；不画图时不需要
- DSH 任意配置了 `dsh-skill` + `dsh-skill-filesystem` + `dsh-tool-skill` 的 profile（默认 `web` / `headless` 均满足）

## 安装

把本目录（整个 `obsidian-note-curator` 文件夹）复制到任意一个 DSH skill 根下：

| 层级 | 路径 | 说明 |
|---|---|---|
| 用户级 | `~/.agents/skills/obsidian-note-curator/` | 本机所有项目可用 |
| 用户级 | `~/.dsh/skills/obsidian-note-curator/` | DSH 配置根，同样全局可用 |
| 项目级 | `<git 仓库根>/.dsh/skills/obsidian-note-curator/` | 随仓库提交，团队 / 多电脑共享，推荐 |
| 自定义 | `Config.customSkillDirs` 中登记的目录 | 其他位置 |

```powershell
Copy-Item -Recurse -Force "C:\path\to\obsidian-note-curator" "$env:USERPROFILE\.agents\skills\"
```

**热加载**：DSH 监听 skill 根目录，新 skill 无需重启即可进入会话目录；下一个请求里模型即可通过 `skill` 工具加载，或由用户输入 `/obsidian-note-curator` 显式调用。改 `SKILL.md` 正文即时生效。

## 快速开始

1. **把笔记库文件夹本身作为 DSH 会话的工作区打开**（最省事：零参数，且不受沙箱写入限制）
2. 环境自检：`python scripts/ob.py probe` —— `available: false`（退出码 3）是正常现象，直接降级
3. 只看盘子：`python scripts/vault.py tree`；做体检：`python scripts/vault.py audit`
4. 按 `SKILL.md` 的八步工作流整理：挑内容与类型 → 定位笔记 → 依赖审计与螺旋规划 → 按类型写作 → 出图 → dry-run 确认后写入 → 挂链接维护 MOC → 台阶审计与验证汇报

## 文件布局

```
obsidian-note-curator/
├── SKILL.md                        # DSH skill 入口：frontmatter + 八步工作流 + 沙箱纪律
├── README.md                       # 本文件
├── vaults.json                     # 仓库别名表（机器相关，不要提交进笔记库 git）
├── scripts/
│   ├── vault.py                    # 扫描 / 链接图 / 健康巡检 / 大纲 / 检索 / 查找
│   ├── note.py                     # 章节级编辑 / dry-run / 重编号 / frontmatter / 备份
│   ├── step_audit.py               # 台阶审计：术语首次出现位置清单
│   ├── render_diagram.py           # SVG/HTML → PNG，落到笔记图片目录
│   └── ob.py                       # 官方 CLI 封装（沙箱安全：只打印 URI、运行态检查、主库排序）
├── references/
│   ├── spiral-teaching.md          # 循环深入：三拍 / 起点契约 / 审计 / 反例（第一优先级）
│   ├── narrative-style.md          # 叙述技法：场景、演算、试错、验证；图的职责
│   ├── note-style.md               # 四类笔记骨架、文风、配图、代码/来源规范（核心）
│   ├── style-rationale.md          # 文风设计依据
│   ├── ecosystem-design.md         # 能力边界与生态分层
│   ├── integration-playbook.md     # 定位、差距分析、落笔顺序
│   ├── moc-system.md               # MOC 与 Bases 分工
│   ├── obsidian-syntax.md          # 语法基线
│   ├── diagrams.md                 # Mermaid 选图与限制
│   ├── obsidian-cli.md             # 两套 CLI 的区分与降级
│   ├── env-notes.md                # DSH 执行层注意（pwsh / Python / 沙箱 / 浏览器 / 换行）
│   ├── task-integration.md         # 知识待办与任务系统边界
│   └── git-sync.md                 # 多机 Git 同步
└── assets/templates/
    ├── sub-note.md                 # 教程（含读者起点）
    ├── explanation-note.md         # 解释（三拍骨架）
    ├── how-to-note.md              # 操作指南
    ├── reference-note.md           # 参考
    └── topic-moc.md                # 主题 MOC
```

## 仓库定位（零配置）

`--root <绝对路径>` → `--vault <别名>`（查 `vaults.json`）→ 从当前工作区向上找 `.obsidian/`（找不到再查直接子目录的唯一候选）→ `vaults.json` 的 `default`。**仓库路径零硬编码**：换电脑、换 clone 位置都不用改 skill。`vault.py`、`step_audit.py`、`render_diagram.py` 共用这一套解析顺序。

## 多电脑 + Git 同步

- `vaults.json` 里的 `path` 是机器相关绝对路径，**不要提交进笔记库的 git 仓库**
- 同一时间只在一台机器上做整理（写入是整段插入，双机改同一篇会产生大块冲突）
- 笔记统一 UTF-8 + LF；`.note-curator-backups/` 建议加入 `.gitignore`（它是库内恢复副本，不必进版本库）
- 完整纪律见 `references/git-sync.md`

## 与 WorkBuddy 原 skill 的差异（DSH 适配）

1. **Frontmatter 改为 DSH 规范**：`name` + `description` + `whenToUse` + `argument-hint`，触发词写进 description；去掉 WorkBuddy 专有的 `agent_created`
2. **生态假设调整**：原 skill 依赖的兄弟 skill（`obsidian-markdown` / `obsidian-bases` / `obsidian-cli` / `obsidian-tasks`）在 DSH 里通常不存在，`SKILL.md` 与 `ecosystem-design.md` / `task-integration.md` 已改为「未安装时由本 skill 自带基线兜底、未确认采用前不假设存在」
3. **命令约定 DSH 化**：shell 工具分平台（Windows `pwsh` / POSIX `bash`）；待写入内容用 `write` 工具落到工作区 `.note-staging/`（替代 `/tmp` heredoc）；明确 `read`/`write`/`edit` 与脚本的分工
4. **`references/env-notes.md` 按 DSH 重写**：pwsh 无 coreutils、Python 解释器选择、**沙箱写入边界**、BOM 与 frontmatter 陷阱、官方 CLI 自定义安装目录探测不到、配图渲染链在沙箱内的降级方式
5. **脚本适配**：
   - `vault.py` 跳过目录加入 `.dsh` / `.workbuddy` / `.embeddedskills`，避免把项目级 skill 根里的 `SKILL.md` 误当笔记
   - `ob.py` 叠加沙箱防护：`open` 默认只打印 `obsidian://` URI（`--launch` 仅供沙箱外手动使用）；`probe` / `exec` 先做运行态检查（Windows 进程快照优先，避免崩溃后残留的 `open` 标记误判），未运行直接降级；补齐原脚本缺失的 `import webbrowser`；`exec` 增加子进程启动失败的优雅降级
   - `ob.py` **只执行 CLI 瘦转发器**：候选列表剔除 `Obsidian.exe`（200MB+ 的 GUI 主程序），并在执行前二次过滤——`OBSIDIAN_CLI` 指向它也拒绝。沙箱内启动 `Obsidian.exe` 会在单实例转发之前打开 `obsidian.log`，EPERM 崩溃
   - `step_audit.py` / `render_diagram.py` 新增 `--vault` / `--root`，与 `vault.py` 共用仓库解析；后者对「沙箱内启动浏览器失败」「图片目录不可写」给出可执行建议而不是堆栈
6. **方法论内容跟随上游**：三拍、起点契约、叙述技法、配图规范已同步；MOC 三层结构、dry-run 与备份纪律未改动

## 已知问题与修复（沙箱内拉起 Obsidian）

**症状**：整理接近结束时弹出两个错误框 —— Electron 主进程 EPERM 无法打开 `%APPDATA%\obsidian\obsidian.log`，随后 Obsidian.exe 报 `0x80000003` 应用程序错误。

**原因**（两个都堵掉了）：① 从 DSH 沙箱内的 shell 拉起 Obsidian GUI（`open` 的 `os.startfile`），子进程继承沙箱文件权限，连自己的日志都写不了；② `ob.py` 曾把 PATH 里的 `Obsidian.exe` 当作 CLI 候选执行——那是 200MB+ 的 GUI 主程序，即使 Obsidian 已在运行，第二个实例也会在单实例转发之前初始化日志而崩溃。

**修复**：`open` 默认只打印 `obsidian://` URI；`probe` / `exec` 先做运行态检查；候选列表**永久剔除 `Obsidian.exe`**（含 `OBSIDIAN_CLI` 指向它的情况）。见上文差异第 5 条。

## 验证

- `vault.py`：tree / meta / links / audit / outline / search / find 在真实库上只读跑通
- `note.py`：outline / insert（dry-run 与正式写入 + 备份）/ renumber / frontmatter 用一次性测试库冒烟验证
- `step_audit.py`：在含代码块与表格的教学笔记上验证章节分组、首次出现、标题内高风险标记
- `render_diagram.py`：SVG 与 HTML 片段各渲染一张，验证尺寸推导、2 倍缩放、命名与嵌入语法
- `ob.py`：Obsidian 关闭时的 probe / exec / open 三条降级路径（确认全程未 spawn 任何 Obsidian 进程）

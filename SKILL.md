---
name: obsidian-note-curator
description: >-
  当用户要求把对话结论沉淀为本地 Obsidian 笔记、把零散内容重构成教程/操作指南/解释/参考笔记、
  首次落笔就补齐教学台阶、建立或维护 MOC 阅读路径、检查笔记库健康度时使用。
  此 skill 以内容策展和循环深入教学法为核心：识别读者任务、选择笔记类型、按「三拍」铺满概念台阶、
  维护概念依赖与可验证主线，并给出可复核的台阶审计与配图。也兼容 /obsidian-note-curator 显式调用。
  不替代通用文件管理、任务系统或插件开发，仓库路径零硬编码，自动识别当前工作区，适合多电脑 + git 同步的场景。
whenToUse: >-
  用户说「记到笔记里」「整理进 Obsidian」「加到某篇笔记」「补充到知识体系」「梳理一下这块」
  「建个 MOC」「笔记之间关联一下」「检查一下笔记库」，或提问后要求把结论沉淀进笔记库时使用。
  不用于纯阅读笔记回答（不落盘）、批量重命名/搬家/删除等纯文件管理，也不用于 Obsidian 插件开发。
argument-hint: "[tree|meta|links|audit|outline|search|find|insert|frontmatter|step-audit|diagram|probe] ..."
---

# Obsidian 笔记整理（DSH 版）

把一次对话的成果变成可长期复用的知识资产。核心不是「记下来」，而是：
**放进正确的位置、选择正确的读者任务、一次写对理解台阶、给出可验证结果、串上下一步链接**。

> [!warning] 台阶在首写时铺满，不是等用户追问再补
> 教学类笔记（`tutorial` / `explanation`）的目标是**读者一次读完就能懂**。若读者需要追问「这是什么」「为什么不是那样」，说明台阶没铺够。
> 因此不采用「先写正文、发现跳跃再追加前置」的做法——补出来的前置往往自己再带同样的坑，坑只是换了位置。
> 正确流程与判据见 `references/spiral-teaching.md`。这条要求是本 skill 的第一优先级，高于文风与结构美观。

本 skill 是 DeepSeek Harness（DSH）的本地 skill，处于 Obsidian 生态的「内容策展层」：

- 本 skill：决定内容该写成什么、应放在哪里、读者如何从浅到深理解
- `vault.py` / 官方 Obsidian CLI：提供检索、链接和结构事实
- `note.py`：安全地执行章节级写入、dry-run、重编号和备份
- `step_audit.py` / `render_diagram.py`：交付前的台阶审计与配图落盘
- Bases / 任务系统：只在已有明确需求和约定时承接多维筛选或可执行承诺

**DSH 环境下的生态说明**：原 skill 依赖的兄弟 skill（`obsidian-markdown`、`obsidian-bases`、`obsidian-cli`、`obsidian-tasks` 等）在 DSH 里通常并未安装。此时本 skill 自带的 `references/obsidian-syntax.md` 就是语法基线，`.base`、看板、任务插件相关能力一律**不假设存在**：需要时先问用户是否已采用，再决定是否接入。若用户确实装了同类 skill，仍按「内容组织归本 skill，语法/视图/CLI 全量手册归各自 skill」归口。

## 何时使用

- 用户要求把对话中的结论写入指定 Obsidian 笔记
- 用户要求把零散记录梳理成教程、操作指南、机制解释或速查笔记
- 用户要求**生成一份可直接读懂的教学文档**（没有反复追问的机会，必须一次成文）
- 用户要求补齐跳跃提问依赖的前置知识、维护 MOC 或建立笔记关联
- 用户要求检查断链、未核实事项、MOC 路径和笔记元数据等知识库健康问题

不用于：

- 只阅读笔记并回答问题、不落盘
- 批量重命名、搬家、删除等纯文件管理
- 开发 Obsidian 插件、安装插件、配置 Publish/Sync
- 把每一条知识待办自动变成任务

## 仓库识别

不写死笔记库路径。按以下优先级定位：

1. `--root <绝对路径>`：显式指定
2. `--vault <别名>`：读取本 skill 目录下 `vaults.json`
3. 自动识别：从当前工作区向上找 `.obsidian/`；找不到时检查当前工作区的直接子目录
4. `vaults.json` 的 `default`：兜底

**最省事的方式是把笔记库本身作为 DSH 会话的工作区打开**（此时所有命令零参数，且不受沙箱写入限制）。多电脑使用 Git 同步时，每台机器在本地打开 clone 后的笔记库即可；`vaults.json` 是机器相关配置，不要提交到笔记库 Git 仓库。

`default` 不只做兜底：`ob.py vaults` 也把它排在最前。Obsidian 注册表里「添加库的先后」不代表「你现在在用哪个库」，外部工具常取第一条当主库，所以主库要显式登记。

## 命令约定（DSH）

- `PY` = 本机 Python 3：Windows 上用 `python`，macOS/Linux 上用 `python3`。全部脚本只用标准库，**无需安装任何依赖**。
- `SK` = 本 skill 的 `scripts/` 目录。加载本 skill 时 DSH 会给出 skill 的资源基路径，`SK` 即该目录下的 `scripts/`；先用命令工具确认实际路径。
- 用 DSH 的 shell 工具执行脚本：Windows 会话用 `pwsh`，macOS/Linux 会话用 `bash`。路径统一用正斜杠，示例：

  ```bash
  python "$SK/vault.py" tree
  ```

  `references/` 里的示例以 skill 根目录为 cwd、直接写 `python scripts/...`，两种写法等价。
- **待写入内容一律先用 DSH 的 `write` 工具落到临时文件**（工作区下 `.note-staging/xxx.md`），再经 `--content-file` 交给 `note.py`；落盘确认后删除临时文件。不要依赖 shell heredoc 或 `/tmp`。
- 读笔记正文用 DSH 的 `read` 工具（带行号）；结构定位、链接图、健康巡检、台阶审计用脚本。

## 环境与能力边界

### 1. 文件扫描永远可用（只读）

```bash
"$PY" "$SK/vault.py" tree
"$PY" "$SK/vault.py" links
"$PY" "$SK/vault.py" audit
```

`step_audit.py` 和 `render_diagram.py` 同样通过 `--vault` / `--root` 定位仓库，与 `vault.py` 的解析顺序一致。

### 2. 官方 CLI 是增强项，不是依赖

```bash
"$PY" "$SK/ob.py" probe
```

- `available: true`：可用官方 Obsidian CLI 做链接感知的移动/重命名和应用级检查
- `available: false`（退出码 `3`）：正常降级到 `vault.py` 和 `note.py`，不要尝试安装或注册 CLI
- **CLI 要求 Obsidian 已在运行**：脚本会先检查运行态，未运行直接降级，**绝不从 DSH 沙箱里拉起 GUI**（详见文末「DSH 集成注意」）
- DSH 沙箱内官方 CLI 往往连不上正在运行的 Obsidian（命名管道受限，表现为 `The CLI is unable to find Obsidian`）。这是**正常降级**：`vault.py` + `note.py` 才是主力，不要为此反复排错或改配置
- 官方 / 社区两套 CLI 的区别和完整降级策略见 `references/obsidian-cli.md`

DSH 沙箱写入边界、Windows/pwsh 差异、Python 解释器、换行编码等执行层问题，见 `references/env-notes.md`（默认不必读，排查失败时再查）。

## 核心工作流

### 第 1 步：确定整理范围与笔记类型

从对话中截取最终结论、已验证实践、可复现命令、真实踩坑和待核实边界。不要复制试错过程、闲聊和被推翻结论。

先确定读者任务：

| 用户需要 | `note_type` | 主写法 |
|---|---|---|
| 首次完整跑通 | `tutorial` | 一条最短主线，每步有预期结果 |
| 已知背景下完成操作 | `how-to` | 前置状态、直接步骤、验收与恢复 |
| 理解原理、取舍或因果 | `explanation` | 问题、模型、对照、边界、下一问 |
| 快速查参数、接口或版本 | `reference` | 准确表格、最小示例、权威来源 |

拿不准整理哪些内容或笔记类型时，列出候选范围让用户确认；不要静默替用户丢弃原话。

### 第 2 步：定位目标笔记

按 `references/integration-playbook.md` 的决策树定位：

```bash
"$PY" "$SK/vault.py" find --query "GPIO"
"$PY" "$SK/vault.py" meta
"$PY" "$SK/vault.py" search --pattern "gpiod"
"$PY" "$SK/vault.py" tree
```

歧义时列出候选让用户选择。新建前先判断内容是否本应是现有笔记的一节；只有独立、可复用的知识单元才创建子笔记。

### 第 3 步：读取上下文，做依赖审计与螺旋规划

必读：目标笔记全文、所属主题 MOC、阅读路径相邻笔记、反向链接。必要时执行：

```bash
"$PY" "$SK/vault.py" outline --file "Linux驱动.md"
"$PY" "$SK/vault.py" links
"$PY" "$SK/vault.py" audit
```

将新内容判为：

- **已有**：不重复写，补链接或修正边界
- **顺延**：自然加深；进入已有主线的下一节或进阶区
- **跨域**：属于其他主题；在正确主题落笔并建立双向链接
- **缺口**：新内容依赖尚未解释的概念

遇到缺口时**不要线性追加**（「笔记只有第 2 层，用户问第 5 层，就先补第 3、4 层再写第 5 层」）。那样补出来的 3、4 层自己仍可能用未解释的概念解释概念，坑只是换了个位置。

改为按螺旋规划一次性铺完：

1. 列出缺口概念，为每个概念找到它的**上游麻烦**——不解决它会撞什么墙（这一步只用读者已会的东西描述）
2. 排出 `简 C → 简 B → 深 A → 深 B → 深 C` 的顺序，每个概念只加深一层
3. 给每个核心概念分配**三拍**：痛点（不给名字）→ 骨架（最小结构）→ 真实来源（源码 + 行号）
4. 在笔记开头写**读者起点契约**：假设读者已会什么、本文从零讲什么

判据：任何一节只能依赖此前已解释过的概念。完整方法与反例库见 `references/spiral-teaching.md`。

### 第 4 步：按笔记类型写作

严格以 `references/note-style.md` 为准（叙述技法见 `references/narrative-style.md`）：

- 教程：先给「完成后得到什么」，再给单一路径；每步写「目标 → 操作 → 预期 → 观察」
- 解释：先讲旧问题与心智模型，再讲规则、对照、例外和下一问
- 操作指南：明确起始状态、完成标准与恢复路径
- 参考：提供稳定可检索事实，不承担首次教学

补充材料、可选方案、参数速查和深解释不要打断教程最短路径。

首次出现的**核心概念**按三拍引入（见第 3 步第 3 条），**一般术语**当场给一句可操作的定义，已有独立笔记时使用 `[[wikilink]]`。场景先行、逐步演算、保留试错、换角度验证这四条技法能显著降低台阶的阅读成本，但不要为了技法而技法。

写作时逐节自问两句：

- 「这一节用到的名词，都在前面解释过了吗？」
- 「把后面几节遮住，这一节能独立读懂吗？」

两句都成立才继续写下一节。写完再回头补台阶，成本高且容易补成另一个坑。

### 第 5 步：出图并渲染进笔记

教学类笔记的图和文字同等重要。图的职责分类见 `references/narrative-style.md` 第二节；尺寸、命名、目录见 `references/note-style.md` 第七节第 2 条。

流程：

1. 写完一节，判断这一节是否涉及**多轮状态变化、并列对比、分层包含、流程时序**。是则画图，否则跳过（不要为了「有图」而画）
2. 先写图的 SVG 或 HTML 片段到工作区临时文件（可用对话里的图直接落盘）
3. 渲染进笔记图片目录：

```bash
"$PY" "$SK/render_diagram.py" --vault upup --note "MCU/xxx.md" \
  --svg .note-staging/figs/01.svg --name "01-分层结构"
```

4. 按脚本打印的嵌入语法写进笔记：`![[<笔记名>/<图名>.png]]`
5. 图下补 1~2 句说明它体现了什么

> [!tip] 不要手工截图
> 交给脚本才能保证尺寸、底色、命名和目录一致。手工截图会产生信息不一致的图片，后续很难检索和替换。
> 用户机器上图片目录已按 `BaiduSyncdisk/pic/<笔记名>/` 同步，别存到别处。

**沙箱内出图**：`--format png` 需要在本机启动 Edge/Chrome，DSH 沙箱内通常跑不起来（见 `references/env-notes.md`）。两条等效退路：

```bash
# 1) 不栅格化：SVG 直接入库，由 Obsidian 原生渲染（尺寸/命名/目录仍由脚本统一）
"$PY" "$SK/render_diagram.py" --vault upup --note "MCU/xxx.md" \
  --format svg --svg .note-staging/figs/01.svg --name "01-分层结构"

# 2) 仍要 PNG：在用户批准的一次性宽权限下重试同一条命令，或把命令交给用户在普通终端执行
```

语法使用 `references/obsidian-syntax.md`，Mermaid 图示使用 `references/diagrams.md`。图只在结构、时序、状态或层级难以用文字表达时出现。

### 第 6 步：先 dry-run，再正式写入

章节级编辑只用 `note.py`：

```bash
# 1) 用 write 工具把要插入的内容写到 .note-staging/sec.md
# 2) 先看 diff
"$PY" "$SK/note.py" insert --file "Linux驱动.md" \
  --heading "二、核心概念" --position under --content-file .note-staging/sec.md \
  --renumber --dry-run

# 3) 确认后正式写入；默认在库内创建 .note-curator-backups/ 备份
"$PY" "$SK/note.py" insert --file "Linux驱动.md" \
  --heading "二、核心概念" --position under --content-file .note-staging/sec.md \
  --renumber
```

- `--position under`：插入该章节末尾；`before` / `after`：贴着标题插入
- 标题不存在时使用 `--create-heading`
- 插入十进制章节后使用 `--renumber`（中文编号章不受影响）
- 正式写入默认把原文件保存到 `<vault>/.note-curator-backups/<时间戳>/`；该目录不参与扫描
- 只有用户明确说明已有独立恢复措施时才使用 `--no-backup`
- 整节替换用 `replace --heading`（只替换该标题下的正文、保留标题行，务必先看 dry-run diff）；需要追加到文末时用 `append`
- diff 出现删除行明显多于新增行时，停下检查，通常是误用了 `replace`

更新 frontmatter：

```bash
"$PY" "$SK/note.py" frontmatter --file "Linux驱动.md" \
  --set note_type=tutorial --set status=reviewed --set updated=2026-09-17 --dry-run
```

新笔记从 `assets/templates/` 选择：`sub-note.md`（教程）、`explanation-note.md`、`how-to-note.md` 或 `reference-note.md`；新建或重建主题 MOC 时用 `topic-moc.md` 作骨架。

### 第 7 步：维护链接、MOC 和可选的任务出口

完成后：

1. 将线性学习笔记加入主题 MOC 的「阅读路径」，位置反映依赖与难度（新建 MOC 用 `assets/templates/topic-moc.md`）
2. 将同层旁支放入 MOC 的「分支地图」；不必把每篇参考笔记塞进阅读路径
3. 正文中首次出现的已有独立概念加 `[[wikilink]]`
4. 在底部明确「下一步 / 深入理解 / 所属主题」
5. 更新 `updated`，并根据事实状态设置 `status`

MOC 与 Bases 的分工见 `references/moc-system.md`：MOC 管顺序和叙事，Bases 管多维筛选。没有真实筛选需求时不创建 `.base`。

对待办采取渐进策略，详见 `references/task-integration.md`：

- 知识缺口默认保留为 `> [!question] 待办`，必要时设 `status: needs-verify`
- 只有用户要求跟踪、vault 已有明确任务约定、且任务有可验收外部行动时，才交给现有任务系统
- 不自动安装插件、不猜测任务字段、不把每个知识疑问制造成任务

### 第 8 步：验证并汇报

```bash
"$PY" "$SK/vault.py" links
"$PY" "$SK/vault.py" audit
"$PY" "$SK/vault.py" outline --file "..."
```

`tutorial` / `explanation` 必须额外跑台阶审计：

```bash
"$PY" "$SK/step_audit.py" --vault upup --file "网络设备运行机制.md"
```

脚本按章节（优先 H2，整篇没有 H2 时退回 H1）列出每个技术标识符的**首次出现位置**，输出待人工确认的清单。它不作判断，只把需要过一遍的行摊出来。

对清单里每一条回到该行问一句：**读者读到这里时，认识这个词吗？**

- 认识（前文铺过）→ 通过
- 不认识但本行就打比方讲清了 → 通过（相当于就地一拍）
- 不认识且直接拿去解释别的概念 → **必须改写，不能交付**

标记 `[表格/多为预告]` 的多是目录或对照表里的提前提及，可判为通过；标记 `[标题内]` 的由脚本计为高风险，需优先处理。

官方 CLI 可用时，补充调用 `unresolved`、`backlinks`；Mermaid / Callout 渲染用 `ob.py open` 打印的 URI 交用户在 Obsidian 里目测。

汇报必须包含：

- 修改了哪些笔记和章节
- 新增的阅读台阶、主线步骤或机制解释
- **台阶审计结果**：术语总数、需还原检查的条目、实际改写了哪几处
- **生成的图**：每张图的路径、出现在哪一节、解决什么问题
- MOC / wikilink 联动
- 验证结果（链接、结构、待核实项）
- 仍待用户确认或需要外部验证的内容

## 知识库健康巡检

`vault.py audit` 是只读报告，不自动改写笔记，也不自动创建任务：

```bash
"$PY" "$SK/vault.py" audit --long-lines 400
```

报告包括：断链、孤儿、无出链、缺少或非法的 `note_type` / `status`、缺少 `updated`、超过行数阈值的复查项、待核实项、待办、MOC 阅读路径，以及「声明所属 MOC 但未进入阅读路径」的笔记。

把结果当作**复查队列**，不是自动重构命令：参考笔记、旁支或历史笔记可能合理地不在阅读路径中；先判断读者价值再修改。

## 硬约束

- **禁止用未解释的概念解释另一个概念**；`tutorial` / `explanation` 必须在首写时按三拍铺满台阶，不得留待用户追问再补
- 只给一句定义就往下走、或直接贴真实结构不给骨架，都不算完成教学
- 不删除或压缩用户已有叙述，除非用户明确要求重写
- 不编造源码、寄存器地址、命令输出、版本兼容性或实测结论
- 落盘前必须先 dry-run 并实际检查 diff
- 一次整理最多实质修改 3 篇笔记；跨度更大时优先主线，其余明确列为待办
- 不改写用户的行话和项目命名
- CLI 不可用时静默降级，不阻塞整理工作
- 禁止未授权的删除、Publish、Sync 恢复、插件安装/卸载、`reload` 或 `restart`
- 所有笔记统一 UTF-8 + LF；Git 同步规则见 `references/git-sync.md`

## DSH 集成注意

- **禁止从沙箱内拉起 Obsidian**：沙箱里 spawn 的 Obsidian.exe 会继承沙箱文件权限，连自己的日志 `obsidian.log` 都写不了（EPERM 崩溃弹窗 + 0x80000003）。`ob.py` 已内置防护：`open` 默认只打印 `obsidian://` URI（把链接交给用户点击，**不要加 `--launch`**）；`probe` / `exec` 检测到 Obsidian 未运行（进程快照判定，崩溃后残留的 `open` 标记不算数）时直接降级退出码 3。
- **沙箱写入边界**：DSH 的 shell 工具默认只允许写会话工作区。把笔记库本身作为工作区打开就没有这个问题；否则**只读命令**（tree/meta/links/audit/outline/search/find/step_audit）正常可用，但 `note.py` 落盘、`.note-curator-backups/` 备份与 `render_diagram.py` 写图片都会被沙箱拒绝。遇到拒绝时不要反复重试：改为只读分析并提示用户调整工作区或沙箱策略；配图可以先 `--pic-root .note-staging/pic` 出图，再由用户授权移动。
- **配图渲染依赖本机浏览器**：`render_diagram.py --format png` 用 Edge / Chrome 的无头模式截图。沙箱内启动浏览器会因 ACL 授权失败（`Failed to grant sandbox access`）而拿不到图；处理顺序是：先 `--format svg`（Obsidian 原生渲染 `![[x.svg|宽]]`，尺寸与命名仍一致），仍要 PNG 时在用户批准的一次性宽权限下重试，或把命令交给用户在普通终端执行。`--pic-root .note-staging/pic` 可用于先出图、再授权移动。
- **工具分工**：`read` / `write` / `edit` 工具用于读笔记和写 `.note-staging/` 临时内容文件；`vault.py` / `note.py` / `step_audit.py` / `render_diagram.py` / `ob.py` 用于结构感知的检索、审计、配图与章节级编辑。不要用 shell 的 `cat` / 重定向手工改笔记（会绕过编号体系、dry-run 与备份）。
- **扫描噪音**：脚本已把 `.note-curator-backups`、`.note-staging`、`.dsh`、`.workbuddy`、`.agents`、`__pycache__` 等目录排除在笔记扫描之外，项目级 skill 根里的 `SKILL.md` 与暂存片段不会被误当笔记。

## 资源索引

| 文件 | 用途 |
|---|---|
| `references/spiral-teaching.md` | **循环深入教学法**：三拍、读者起点契约、概念登记表、审计方法、反例库（第一优先级） |
| `references/narrative-style.md` | **叙述技法**：场景先行、逐步演算、保留试错、换角度验证；图的职责分类 |
| `references/note-style.md` | 核心文风、四类笔记骨架、配图规范、代码/命令/验证/来源规范 |
| `references/style-rationale.md` | 参考 Fast DDS、Django、Rust Book、Diátaxis 后的文风设计依据 |
| `references/ecosystem-design.md` | 能力边界、生态分层、功能准入与明确延后项 |
| `references/integration-playbook.md` | 目标定位、差距分析、落笔顺序、跨笔记联动 |
| `references/moc-system.md` | MOC、子笔记粒度、MOC 与 Bases 分工 |
| `references/obsidian-syntax.md` | wikilink、embed、callout、frontmatter、Mermaid 最小语法基线 |
| `references/diagrams.md` | Mermaid 选图、模板与渲染限制 |
| `references/obsidian-cli.md` | 官方 / 社区 CLI 区分、可用性判断、调用和降级策略 |
| `references/env-notes.md` | DSH 执行层注意：pwsh 差异、Python 解释器、沙箱写入、浏览器渲染、换行编码 |
| `references/task-integration.md` | 知识待办与外部任务系统的边界 |
| `references/git-sync.md` | 多机 Git 同步与冲突预防 |
| `assets/templates/sub-note.md` | 教程笔记模板（含读者起点契约） |
| `assets/templates/explanation-note.md` | 机制解释模板（三拍骨架） |
| `assets/templates/how-to-note.md` | 操作指南模板 |
| `assets/templates/reference-note.md` | 参考笔记模板 |
| `assets/templates/topic-moc.md` | 主题 MOC 模板（阅读路径 / 分支地图 / 维护状态） |
| `scripts/vault.py` | 扫描、链接图、健康巡检（`tree` / `meta` / `links` / `audit` / `outline` / `search` / `find`） |
| `scripts/note.py` | 章节级编辑、dry-run、重编号、frontmatter、自动备份 |
| `scripts/step_audit.py` | 台阶审计：按章节列出术语首次出现位置，供交付前人工确认 |
| `scripts/render_diagram.py` | SVG/HTML → PNG（`--format svg` 可跳过栅格化），按 `<vault>/BaiduSyncdisk/pic/<笔记名>/` 落盘并给出嵌入语法 |
| `scripts/ob.py` | 官方 Obsidian CLI 探测、调用和 URI 打开（沙箱安全，主库优先排序） |

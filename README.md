# obsidian-note-curator

把对话结论写成「读者一次就能读懂」的 Obsidian 笔记。

这是一个面向 AI agent 的 skill。它不负责把内容抄进文件，而负责判断**该写成哪类笔记、放进库里什么位置、按什么顺序铺理解台阶**，并在落盘前用脚本把「读者会不会卡在这里」摊成一张可以逐条过的清单。

> *English:* An agent skill that curates conversations into Obsidian notes. It picks the reader's task (tutorial / how-to / explanation / reference), plans concept order with a spiral method (three beats per core concept), renders diagrams through a script, and audits the result for unexplained terms before anything is written.

作者：[YearnCy](https://github.com/YearnCy)

---

## 它解决的三类失败

大多数「帮我记到笔记里」的失败，不是没记住，而是记住的方式让下一篇没法用。

| 症状 | 常见做法 | 这里的应对 |
|---|---|---|
| 记下来了，但下次找不到，也不知道从哪读起 | 扔进一个按日期命名的文件 | 先定读者任务 → 选四类笔记之一 → 挂进主题 MOC 的阅读路径 |
| 记下来了，但读的时候处处卡壳 | 用尚未解释的概念去解释下一个概念 | 首写就铺满台阶：核心概念走三拍，开头写读者起点契约 |
| 记下来了，但和库里其他笔记没关系 | 每篇自成孤岛 | 依赖审计 → 判断已有 / 顺延 / 跨域 / 缺口，再决定落笔位置 |

第三条还有个隐性的坑：**发现跳跃就回来补前置**，补出来的前置往往又用未解释的概念解释概念，坑只是换了位置。所以这里的顺序是反的——先把概念序列排好，再动笔。

## 核心方法：循环深入

一句话：任何复杂概念都不该「先定义再用」，而应「先撞墙、再给形、最后给实」。

**顺序不是 `C → B → A`，是螺旋：**

```
简 C  →  简 B  →  深 A  →  深 B  →  深 C
 ↑                                    ↓
 └────────── 每个概念只加深一层 ────────┘
```

**每个核心概念登场三次（三拍）：**

| 拍 | 读者此刻的状态 | 写什么 | 禁止 |
|---|---|---|---|
| 一 · 痛点 | 「这里好像缺个东西」 | 场景推演、朴素做法撞墙、由此提炼出的硬需求 | 出现这个概念的**名字** |
| 二 · 骨架 | 「它大概长这样」 | 裁剪到 4~8 个字段的最小结构，每个字段注明被哪条需求逼出来 | 直接贴完整真实结构 |
| 三 · 真实 | 「原来实现里是这样」 | 真实源码 / 配置，带文件路径、起始行号、以及**裁剪掉了什么** | 不给行号，或不说裁剪范围 |

**开头先写读者起点契约**，否则「什么算没解释过」没有判据：

```markdown
> [!info] 读者起点
> 假设你会：C 语法、module_init / module_exit、基本 struct 用法。
> 本文从零讲：blk-mq、tag、request、hctx —— 不需要任何前置。
```

判据只有一条：**任何一节只能依赖此前已经解释过的东西**。写完一节自问两句——这一节用到的名词前面讲过吗？把后文遮住，这一节能独立读懂吗？

配套的叙述技法（场景先行、逐步演算、保留试错、换角度验证）在 `references/narrative-style.md`；方法本体、概念登记表与反例库在 `references/spiral-teaching.md`。

## 四类笔记

按读者任务选型，不按内容长短选型：

| 读者想做什么 | `note_type` | 骨架 |
|---|---|---|
| 首次完整跑通 | `tutorial` | 完成后得到什么 → 单一路径，每步写「目标 → 操作 → 预期 → 观察」 |
| 在已知背景下完成某操作 | `how-to` | 起始状态 → 直接步骤 → 验收标准 → 失败恢复 |
| 理解原理、取舍或因果 | `explanation` | 它解决什么问题 → 朴素做法撞墙 → 正式结构 → 规则与对照 → 边界 → 下一问 |
| 快速查参数、接口或版本 | `reference` | 准确表格 + 最小示例 + 权威来源，不承担首次教学 |

模板在 `assets/templates/`，文风与配图规范在 `references/note-style.md`。

## 交付前的两道闸

**第一道：写入永远先看 diff。** 章节级编辑只走 `note.py`，先 `--dry-run` 看 unified diff，确认后再正式写入；默认把原文件备份到 `<vault>/.note-curator-backups/<时间戳>/`。删除行明显多于新增行时停下——那通常是误用了整节替换。

**第二道：台阶审计。** 教学类笔记交付前必须跑：

```bash
python scripts/step_audit.py --file "网络设备运行机制.md"
```

它按章节列出每个技术标识符的**首次出现位置**，不做判断，只把需要人眼过一遍的行摊出来；有术语首次出现在标题里时退出码为 `1`。然后对每一条回到该行问一句：**读者读到这里时，认识这个词吗？**

- 认识（前文铺过）→ 通过
- 不认识但本行就地打了比方讲清 → 通过
- 不认识，却被直接拿去解释别的概念 → **必须改写，不能交付**

脚本抓不到的部分用三种人工检查兜：倒读法（从末节往回读）、删后读前（心理删掉第 N 节之后，看前 N 节能否独立读懂）、起点回看（核对开头契约里承诺「从零讲」的概念是否真有一拍）。

## 安装

整个文件夹放进任意一个 agent 的 skill 根目录即可，无构建、无依赖。

DeepSeek Harness（DSH）按优先级扫描这些根，放哪一层决定谁能看到：

| Rank | 位置 | 作用域 |
|---|---|---|
| 100 | `<projectRoot>/.dsh/skills/` | 当前项目 |
| 200 | `<projectRoot>/.agents/skills/` | 当前项目（agent 通用） |
| 300 | `Config.customSkillDirs` 中登记的目录 | 自定义 |
| 400 | `~/.dsh/skills/` | 本机全部项目 |
| 500 | `~/.agents/skills/` | 本机全部项目（agent 通用） |

```powershell
# 用户级安装（Windows PowerShell）
git clone https://github.com/YearnCy/obsidian-note-curator.git "$env:USERPROFILE\.dsh\skills\obsidian-note-curator"
```

```bash
# macOS / Linux
git clone https://github.com/YearnCy/obsidian-note-curator.git ~/.dsh/skills/obsidian-note-curator
```

DSH 监听 skill 根目录，装好即热加载，无需重启。其他 agent 只要支持「一个目录 + 一份 `SKILL.md`」的约定，把目录放进去即可；`SKILL.md` 的 frontmatter 是标准形态（`name` / `description` / `whenToUse` / `argument-hint`）。

**要求**：Python 3.8+（五个脚本只用标准库）。Obsidian 官方 CLI 与配图渲染都是可选项，缺了自动降级。

## 快速开始

最省事的用法是把笔记库本身作为 agent 会话的工作区打开——此时所有命令零参数，且不受写入沙箱限制。

```bash
python scripts/vault.py tree            # 看库的结构
python scripts/vault.py audit           # 体检：断链 / 孤儿 / 元数据 / 阅读路径漏项
python scripts/vault.py find --query GPIO
python scripts/vault.py outline --file "Linux驱动.md"
```

```bash
python scripts/note.py insert --file "Linux驱动.md" \
  --heading "二、核心概念" --position under \
  --content-file .note-staging/sec.md --renumber --dry-run
```

```bash
python scripts/step_audit.py --file "网络设备运行机制.md"
python scripts/render_diagram.py --note "MCU/xxx.md" --svg figs/01.svg --name "01-分层结构"
```

笔记库不在当前工作区时，用 `--root <库绝对路径>` 或 `--vault <别名>`（别名登记在 `vaults.json`，见 `vaults.example.json`）显式指定。

## 目录结构

```
obsidian-note-curator/
├── SKILL.md                  # 入口：八步工作流、硬约束、环境边界
├── README.md
├── vaults.example.json       # 仓库别名表模板（vaults.json 含本机路径，已 gitignore）
├── scripts/
│   ├── vault.py              # 扫描 / 链接图 / 健康巡检 / 大纲 / 检索 / 查找
│   ├── note.py               # 章节级编辑 / dry-run / 重编号 / frontmatter / 备份
│   ├── step_audit.py         # 台阶审计：术语首次出现位置
│   ├── render_diagram.py     # SVG / HTML 片段 → PNG，落到笔记图片目录
│   └── ob.py                 # 官方 Obsidian CLI 封装（探测、调用、URI 打开）
├── references/               # 方法论与规范（spiral-teaching / narrative-style / note-style 为核心）
└── assets/templates/         # tutorial / how-to / explanation / reference / MOC 五份模板
```

## 设计取舍

- **零依赖**。五个脚本只用标准库。skill 会被复制到各种机器上，装依赖是最容易让它在别人手里失效的一步。
- **写入永不直接改文件**。章节级编辑、dry-run、备份、重编号是一套的，绕过它就是在赌手写 diff 不出错。
- **图交给脚本，不手工截图**。尺寸、底色、命名、目录由 `render_diagram.py` 统一，`![[笔记名/图名.png]]` 由它打印；沙箱里起不来浏览器时退到 `--format svg`，由 Obsidian 原生渲染。
- **不为「有图」而画图**。图只在多轮状态、并列对比、分层包含、流程时序难以用文字表达时出现，且图下必须有说明。
- **单次整理最多实质改 3 篇**。跨度更大时优先主线，其余列为待办——一次改十篇的 diff 没人能审。
- **CLI 只是增强项**。没有官方 Obsidian CLI 时静默降级到文件操作，不阻塞整理。
- **方法论优先于版式**。句子怎么写是次要的，概念按什么顺序出现才是读者能不能读懂的主因。

## 已知限制

- 不做批量重命名、搬家、删除；不做插件开发、Publish / Sync 配置。
- 只覆盖 Obsidian Markdown 生态；`.base` 视图与任务插件在用户确认采用之前一律不假设存在。
- `render_diagram.py` 需要本机安装 Edge / Chrome；受限沙箱内可能无法启动浏览器，此时用 `--format svg`。
- `step_audit.py` 只抽取反引号标识符、`struct/enum/union` 名、全大写宏与函数调用——它给出的是**待确认清单**，不是结论。
- 仓库别名 `vaults.json` 是机器相关配置，不进版本库。

## 实现与移植说明

DSH 适配细节（沙箱写入边界、pwsh 差异、官方 CLI 的降级路径、配图渲染的沙箱退路）见 [docs/porting-notes.md](docs/porting-notes.md)。

## 许可证

尚未指定。在明确许可之前，请把它当作「可读、可参考」，商业使用请先联系作者。

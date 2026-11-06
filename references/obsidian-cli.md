# Obsidian CLI 速查（本 skill 场景裁剪版）

本 skill 支持两种 CLI 路线，但只把**官方 CLI**作为可写入的链接感知重构工具。先识别工具，不混用命令语法。

## 零、先区分两套 CLI

| 路线 | 可执行名 | 典型语法 | 状态 | 本 skill 的使用方式 |
|---|---|---|---|---|
| 官方 Obsidian CLI（1.12+） | `obsidian` / Windows `Obsidian.com` | `obsidian search query="rpmsg"`、`obsidian move path="a.md" to="b.md"` | 由运行中的 Obsidian 通过 IPC 提供 | `scripts/ob.py` 的唯一封装目标；优先使用 |
| 社区 `obsidian-cli` | `obsidian-cli` | `obsidian-cli search-content "rpmsg"`、`obsidian-cli move old new` | 独立工具，语法不同 | 不由 `ob.py` 调用；仅可在用户已验证并明确选择时单独使用 |

**不要把两套命令拼在一起。** 例如 `obsidian-cli print-default` 不是官方 CLI 命令，`obsidian property:set` 不是社区 CLI 命令。

> **`Obsidian.exe` 不是 CLI，永远不要执行它。** Windows 安装目录里有两个同族文件：
> `Obsidian.com`（约 20KB 的 CLI 瘦转发器，官方 CLI 的真身）和 `Obsidian.exe`
> （200MB+ 的 Electron 主程序）。在 DSH 沙箱里启动 `Obsidian.exe` 会走 `main.js` 初始化，
> 在单实例转发**之前**就去打开 `C:\Users\<you>\AppData\Roaming\obsidian\obsidian.log`，
> 沙箱拒绝后直接崩溃（Electron 报错框 + `0x80000003`），即使 Obsidian 已经开着也一样。
> `ob.py` 已从候选里剔除任何指向 `Obsidian.exe` 的路径（含 `OBSIDIAN_CLI`），
> 但你在终端里手工敲 `Obsidian.exe version` 依然会触发。

### 先判断本机装的是哪套

```bash
# 类 Unix（macOS / Linux）
command -v obsidian        # 有输出 → 可能是官方 CLI（Windows 上多为 Obsidian.com）
command -v obsidian-cli    # 有输出 → 社区版
obsidian version           # 官方 CLI 返回版本号（≥ 1.12 才可用）；社区版不认这个子命令

# Windows PowerShell
Get-Command obsidian, obsidian-cli -ErrorAction SilentlyContinue
```

判读规则：

- 两套都没输出 → 未安装任何 CLI，直接走 `vault.py` / `note.py` 降级路径
- 只有 `obsidian` → 官方 CLI；再用 `obsidian version` 确认 ≥ 1.12
- 只有 `obsidian-cli` → 社区版；本 skill 不自动调用它，仅在用户明确要求时单独使用
- 两套都有 → **优先官方 CLI**，社区版只作为用户点名的补充

不用手工判断也可以：`python <skill>/scripts/ob.py probe` 会直接给出可用性与原因。

本 skill 的安全降级路径始终是 `scripts/vault.py` 和 `scripts/note.py`，不要求安装社区 CLI。

## 一、官方 CLI 的启用前提

| 检查项 | 要求 | 检查方法 |
|---|---|---|
| Obsidian 版本 | ≥ 1.12 | 应用内 设置 → 关于 |
| 应用状态 | Obsidian 正在运行 | 保持桌面应用开启 |
| 终端转发器 | Windows 安装版通常为 `Obsidian.com` | `python scripts/ob.py probe` 会列出可用结果 |
| 终端权限 | 普通用户，不要管理员 | 管理员终端可能导致 IPC 失效 |
| CLI 开关 | 在 Obsidian 设置中开启 | 设置 → 通用 → 高级 → Command line interface |

启用后验证：

```bash
python scripts/ob.py probe
```

- `available: true`：可使用官方 CLI
- 返回码 `3`：CLI 不可用，**正常降级**到文件扫描和章节编辑；不要反复安装或重试
- 开关未打开时应用可能返回码为 `0` 但输出 `Command line interface is not enabled`；`ob.py` 已将它判为不可用
- 在 DSH 沙箱内，即使 Obsidian 正在运行，CLI 也常常连不上（命名管道受限），表现为
  `The CLI is unable to find Obsidian. Please make sure Obsidian is running and try again.`。
  这是**正常降级**，不是配置坏了：继续用 `vault.py` / `note.py` 即可，`ob.py` 会把这次探测的实际
  输出附在 `reason` 里便于确认

**DSH 沙箱纪律**：`ob.py` 绝不会从沙箱里拉起 Obsidian GUI。`probe` / `exec` 会先用进程快照
判断 Obsidian 是否已在运行（崩溃后 `obsidian.json` 残留的 `open` 标记不算数），未运行直接
退出码 `3` 降级。需要打开 GUI 时，把 `open` 打印的 URI 交给用户，或请用户手动启动 Obsidian。

## 二、调用约定

一律通过 `scripts/ob.py exec` 调官方 CLI，不要在工作流中手写不同平台的 `obsidian` 路径：

```bash
python scripts/ob.py exec --vault "My Notes" backlinks path="Linux内核/GPIO 子系统.md" format=json
```

- `--vault` 会转为命令最前面的 `vault=<name>`
- `path=<仓库相对路径>` 是精确定位，优先于 `file=<笔记名>` 的模糊解析
- 退出码 `3` 表示需要走文件系统降级路径
- 对版本敏感、没把握的命令先执行 `python scripts/ob.py exec help <command>`

## 三、本 skill 高频官方 CLI 命令

### 1. 链接图与结构验证

```bash
obsidian vault="My Notes" backlinks path="Linux内核/GPIO 子系统.md" format=json
obsidian vault="My Notes" links path="Linux内核/GPIO 子系统.md" format=json
obsidian vault="My Notes" unresolved format=json
obsidian vault="My Notes" orphans format=json
obsidian vault="My Notes" deadends format=json
```

新增 wikilink 必须可解析。CLI 不可用时以 `python scripts/vault.py links` 或 `audit` 为准。

### 2. 检索与读取

```bash
obsidian vault="My Notes" search query="rpmsg" format=json
obsidian vault="My Notes" read path="Linux驱动.md"
```

### 3. 结构化属性

```bash
obsidian vault="My Notes" properties path="Linux驱动.md" format=json
obsidian vault="My Notes" property:set path="Linux驱动.md" name=status value=reviewed
obsidian vault="My Notes" property:set path="Linux驱动.md" name=updated value="2026-09-17"
```

正文的章节级写入仍优先用 `scripts/note.py`，因为它支持 dry-run、自动备份和编号重排。

### 4. 链接感知的重构

```bash
obsidian vault="My Notes" rename file="Linux驱动" name="Linux驱动（整理中）"
obsidian vault="My Notes" move path="Linux驱动.md" to="Linux内核/Linux驱动.md"
```

只在移动或重命名已有笔记时用官方 CLI，因为它会改写全库 wikilink。CLI 不可用时不自动降级为文件移动；保留操作并请用户选择启用 CLI 或人工确认迁移计划。

### 5. 模板与 Bases

```bash
obsidian vault="My Notes" templates
obsidian vault="My Notes" base:query path="索引.base" view="待维护" format=json
```

Bases 的角色是多维筛选，MOC 的角色仍是阅读顺序，详见 `references/moc-system.md`。

## 四、降级路径

| 需求 | 官方 CLI 可用时 | CLI 不可用时 |
|---|---|---|
| 断链、孤儿、无出链 | `unresolved` / `orphans` / `deadends` | `python scripts/vault.py links` |
| 库健康审计 | CLI 链接查询 + 读取属性 | `python scripts/vault.py audit` |
| 正则检索 | `search query=` | `python scripts/vault.py search --pattern "正则"` |
| 查反向链接 | `backlinks path=` | `vault.py links` 的 `incoming` |
| 章节级编辑 | `note.py` 仍优先 | `note.py` |
| frontmatter | `property:*` | `note.py frontmatter` |
| 移动/重命名 | `move` / `rename` | 不自动移动；先征得用户确认 |

GUI 打开笔记不依赖官方 CLI。**默认只打印 `obsidian://` URI、不拉起 GUI**：
DSH 沙箱内 spawn 的 Obsidian.exe 会继承沙箱文件权限，写不了自己的日志而崩溃。
把链接交给用户点击打开即可：

```bash
python scripts/ob.py open --vault "My Notes" --path "Linux内核/GPIO 子系统.md"
python scripts/ob.py open --abs-path "/绝对路径/到/笔记.md"
```

`--launch` 仅限在 DSH 沙箱之外手动使用。

## 五、禁止事项

- 禁止 `reload` / `restart`，会中断当前会话
- 禁止删除、Publish、Sync 恢复、插件装卸，除非用户明确点名目标与影响范围
- 禁止用 `eval` 修改 Obsidian 应用状态；只读诊断可在必要时使用
- 禁止管理员权限终端作为判断 CLI 是否损坏的依据
- 禁止把社区 `obsidian-cli` 命令与官方 `obsidian` 命令混用

# 运行环境注意事项（可选阅读）

本文件记录在 DSH 里使用本 skill 时，真正会绊住脚本调用、导致「命令写对了却跑不起来」的环境问题。
默认不必读；只有排查执行失败时再查。

## 一、shell 工具与文本处理

DSH 的 shell 工具分平台：Windows 会话是 `pwsh`，macOS/Linux 会话是 `bash`。
调用示例统一用 POSIX 写法（`"$SK/vault.py"`），两种 shell 都接受正斜杠路径。

- **不要在 shell 里拼 coreutils**：Windows 上没有 `grep` / `head` / `wc` / `dirname` 这类工具，
  `cat file | grep xxx`、`ls | head` 会直接失败
- 文本处理、文件清点、正则检索一律交给 Python：
  `vault.py search --pattern "..."` 替代 `grep`，`vault.py tree` 替代 `ls -R`
- 需要「先写脚本再执行」时，把脚本写到**会话工作区内**（如 `.note-staging/`）再运行；
  写到系统临时目录可能被沙箱隔离，后续读不到
- 参数用绝对路径，或「skill 资源基路径 + 正斜杠」的写法，避免相对路径在不同 cwd 下解析出歧义
- **不要把脚本输出用 `|` 交给另一个 Python 进程解析**：PowerShell 会按控制台代码页解码管道文本，
  UTF-8 中文被按 GBK 读会把引号吃掉，`json.load` 报 `Expecting ',' delimiter`。改用重定向落文件再读：
  `python scripts/step_audit.py ... --json > .note-staging/audit.json`

## 二、Python 解释器

- Windows 用 `python`，macOS/Linux 用 `python3`，要求 Python 3.8+
- 如果 `python` 指向 Microsoft Store 的占位程序或不在 PATH，先用 `python --version` /
  `py -3 --version` 确认，再改用可用解释器的绝对路径
- 本 skill 的五个脚本只用标准库，无需安装任何依赖；环境里没有第三方包也能跑

## 三、沙箱写入边界

- 脚本写入（`note.py` 落盘与 `.note-curator-backups/` 备份）受 DSH 文件沙箱限制：
  **默认只有会话工作区内的路径可写**
- 最省事的做法是把笔记库本身作为会话工作区打开；否则用 `--root` 指向库外时，
  只读命令照常可用，写入会被沙箱拒绝
- 被拒绝时不要换写法反复重试，直接向用户说明「需要把笔记库设为工作区，或放宽沙箱策略」
- 库内备份目录 `.note-curator-backups/` 同样受该限制
- `render_diagram.py` 写的是**笔记库里的图片目录**，受限情况同上。可以先 `--pic-root .note-staging/pic`
  把图输出到工作区，确认无误后再由用户授权移动

## 四、Obsidian 官方 CLI 在 Windows 上的差异
- 官方 CLI 的终端转发器在 Windows 上通常是 `Obsidian.com`，不在 PATH 里也属正常；
  **自定义安装目录（非默认路径）脚本探测不到**，需要用户自行加入 PATH 或设置环境变量 `OBSIDIAN_CLI`
- 统一用 `python <skill>/scripts/ob.py probe` 判断可用性；返回退出码 `3` 表示不可用，
  **正常降级**到 `vault.py` / `note.py`，不要反复安装或排查
- **CLI 要求 Obsidian 已在运行**：`ob.py` 会先用进程快照检查运行态，未运行直接降级，
  绝不从沙箱里拉起 GUI（沙箱内启动的 Obsidian 会因继承文件权限而写不了自己的日志，导致崩溃弹窗）
- **PATH 里同时有 `Obsidian.com` 和 `Obsidian.exe` 是正常的，但只有前者是 CLI**：
  `.com` 是约 20KB 的瘦转发器，`.exe` 是 200MB+ 的 GUI 主程序。执行后者会在
  打开 `obsidian.log` 时 EPERM 崩溃。`ob.py` 已把任何指向 `Obsidian.exe` 的配置
  （包括环境变量 `OBSIDIAN_CLI`）从候选中剔除，这是硬约束，不要绕过
- **沙箱内官方 CLI 通常不可用**：即使 Obsidian 正在运行，瘦转发器也会返回
  `The CLI is unable to find Obsidian`（命名管道受限或开关未启用），这是正常降级结果，
  不是环境坏了；继续用 `vault.py` / `note.py`
- 本 skill 不依赖任何社区 CLI；两套 CLI 的区分见 `references/obsidian-cli.md`

## 五、配图渲染链（render_diagram.py）

- 渲染引擎是**本机已安装的 Edge / Chrome**（无头模式截图），不需要 ImageMagick / Inkscape /
  Playwright / cairosvg。找不到浏览器时脚本会列出候选路径并退出，属环境缺失而非参数错误
- **沙箱内 PNG 出不来是预期结果**：DSH 沙箱下 Edge 的子进程拿不到 profile 目录的 ACL 授权，
  报 `Failed to grant sandbox access ... (0x5)` / `Shared Dictionary: 拒绝访问`，最后没有 PNG。
  `--no-sandbox` / `--single-process` 都绕不过。按以下顺序处理：
  1. 用 `--format svg`：SVG 直接进图片目录，Obsidian 原生渲染 `![[笔记名/图名.svg|宽]]`，
     尺寸、命名、目录仍由脚本统一，只是少了「所有主题下像素一致」这一层
  2. 仍要 PNG：经用户批准用一次性宽权限重试同一条命令，或把命令交给用户在普通终端执行
  （脚本的临时 HTML 与浏览器 profile 放在 `<pic-root>/.figrender-tmp/`，不再用系统临时目录 ——
  沙箱会拦截 `%LOCALAPPDATA%\Temp\dsh-*`）
- 图片默认落在 `<vault>/BaiduSyncdisk/pic/<笔记名>/`，vault 没有 `BaiduSyncdisk` 时退化为 `<vault>/pic/`。
  目录里已有历史图片不按 `NN-描述` 命名，新图统一带序号，便于按正文顺序排
- 输出是 2 倍图（`--scale 2`），默认底色 `#2b2b2b` 对齐 Obsidian 深色主题；浅色主题用户用 `--bg "#ffffff"`

## 六、换行与编码

- 脚本写入一律 UTF-8 + LF（`note.py` 显式使用 `newline="\n"`）；
  Windows 上建议 `git config core.autocrlf false`（详见 `git-sync.md`）
- 不要批量转换历史笔记的换行符，否则 Git 会显示整库改动、diff 失去可读性
- 用 DSH `write` 工具生成临时内容文件时是 UTF-8 无 BOM；不要用会把 BOM 写进文件头的命令 ——
  BOM 会导致 frontmatter 正则（`\A---`）不匹配，表现为「明明有 frontmatter 却读不到」
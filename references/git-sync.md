# 多机 git 同步注意事项

本 skill 面向「多台电脑 + git 同步笔记库」的场景。脚本侧已保证：UTF-8 编码、LF 换行、
无第三方依赖、路径零硬编码。剩下的坑都在 git 与 Obsidian 这一侧。

---

## 一、推荐的 .gitignore（放在笔记库根目录）

```gitignore
# Obsidian 的工作区状态：频繁变动且机器相关，不同步
.obsidian/workspace.json
.obsidian/workspace-mobile.json
.obsidian/workspace/
.obsidian/cache

# 回收站与系统垃圾
.trash/
.DS_Store
Thumbs.db
desktop.ini

# 本 skill 的别名表（含本机绝对路径，见 vaults.json 注释）
# 注意：这个文件在 skill 目录里，不在笔记库里，正常不会被提交；
# 如果你把它复制进了笔记库，务必加进 .gitignore
vaults.json

# note.py 正式写入前创建的本地恢复副本
# 备份只用于本机快速恢复，Git 历史仍是长期变更记录
.note-curator-backups/
```

`.obsidian/` 里的**插件与主题配置值得同步**（community-plugins.json、app.json、
hotkeys.json、appearance.json），这样另一台机器打开库时体验一致。

---

## 二、双机操作纪律

| 场景 | 做法 |
|---|---|
| 开始整理前 | `git pull`，避免在旧版本上改 |
| 整理结束 | 当天 `git commit && git push`，不要攒 |
| 两台机器同时改了同一篇 | 冲突时手工 merge；skill 整理的 diff 都是整段插入，通常很好合 |
| 新机器第一次用 | clone → 在 Obsidian 里 Open folder as vault → 设为 DSH 会话工作区 → 完事 |

**最重要的纪律：同一时间只在一台机器上做整理。** skill 的写入是整段插入/替换，
两台机器同时对同一篇做整理会产生大块冲突，merge 很痛苦。

---

## 三、大文件与二进制

- `*.assets/` 里的截图会越攒越大。如果库超过几百 MB，考虑给图片类资产上
  `git lfs`（`git lfs track "*.png" "*.jpg"`），或把 assets 排除出 git、改用图床。
- Excalidraw 文件（`*.excalidraw.md`）本质是 JSON，diff 可读性差，merge 冲突时
  直接保留一边再用 Obsidian 打开确认即可。

---

## 四、换行符

笔记统一 LF（`note.py` 写入时强制）。Windows 上确认 git 配置，避免被自动转成 CRLF：

```bash
git config core.autocrlf false
git config core.eol lf
```

库里已有 CRLF 的历史笔记时，**不要批量转换**——一次性全库换行会让 git 显示整个库被改动。
碰到哪篇改哪篇，让 diff 保持可读。

---

## 五、和本 skill 的配合点

- 整理产生的 `updated: YYYY-MM-DD` frontmatter 会变，属于正常提交内容。
- 整理后的断链检查（`vault.py links`）在 pull 之后、push 之前各跑一次最稳妥；需要看元数据和 MOC 路径时再跑 `vault.py audit`。
- `note.py` 的 `.note-curator-backups/` 不同步；它只防范本机写入事故，Git 提交才是跨机恢复依据。
- 另一台机器上 CLI 是否启用互不影响：`ob.py` 每台机器独立探测，探测不到就降级。

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vault.py — 笔记仓库结构扫描（不依赖 Obsidian 运行状态）。

子命令:
  tree      输出笔记目录树（人类可读）
  meta      输出全部笔记的元信息（JSON：frontmatter / 标题 / 字数 / 修改时间）
  links     输出 wikilink 图（JSON：出链 / 反向链接 / 断链 / 孤儿笔记）
  audit     输出知识库健康报告（JSON：链接、MOC 路径、元数据、待核实项）
  outline   输出单篇笔记的标题大纲（带行号）
  search    正则全文检索（JSON）
  find      按文件名模糊查找（JSON）

通用参数:
  --root <dir>        显式指定仓库根目录（最高优先）
  --vault <key>       使用 ../vaults.json 中登记的仓库别名（可选）
  都不给时自动识别：从当前目录向上找 .obsidian/，或在当前目录的直接子目录里
  找唯一候选。找不到则给出可操作指引。

示例:
  python vault.py tree                              # 工作区即笔记库，零参数
  python vault.py links --root /path/to/vault
  python vault.py outline --file "Linux驱动.md"
  python vault.py search --pattern "rpmsg" --context 2
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
VAULTS_JSON = SKILL_ROOT / "vaults.json"

SKIP_DIRS = {
    ".obsidian", ".git", ".github", ".trash", ".stfolder", ".stversions",
    "node_modules", ".opencode", ".agents", ".claude", ".copilot", ".vscode",
    ".note-curator-backups", "__pycache__", ".idea",
    # DSH / 常见 agent 目录：项目级 skill 根 <repo>/.dsh/skills 里的 SKILL.md
    # 不能当作笔记扫描，同理跳过 .workbuddy 与嵌入式工具配置目录。
    ".dsh", ".workbuddy", ".embeddedskills",
    # DSH 工作流把待写入内容暂存在工作区 .note-staging/；
    # 工作区常常就是笔记库本身，不能让暂存文件被当成笔记。
    ".note-staging",
}
SKIP_SUFFIXES = (".assets", "_files")
NOTE_SUFFIX = ".md"
WIKILINK_RE = re.compile(r"(!?)\[\[([^\]\|#]+)(#[^\]\|]*)?(?:\|([^\]]*))?\]\]")
MDLINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
FENCE_RE = re.compile(r"^\s*(```|~~~)")
VALID_NOTE_TYPES = {"tutorial", "how-to", "explanation", "reference"}
VALID_STATUSES = {"draft", "reviewed", "needs-verify", "archived"}


def _utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


# --------------------------------------------------------------------------
# 仓库定位：--root → --vault 别名 → 工作区自动识别 → vaults.json default 兜底
# --------------------------------------------------------------------------

def load_vaults() -> dict:
    """读取 vaults.json 别名表。文件缺失或为空是正常情况（零配置模式）。"""
    if not VAULTS_JSON.exists():
        return {}
    try:
        return json.loads(VAULTS_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[warn] 读取 vaults.json 失败: {exc}", file=sys.stderr)
        return {}


def detect_vault_root(start: Path) -> tuple[Path | None, list[Path]]:
    """自动识别 Obsidian 仓库根。

    1) 从 start 逐级向上找含 .obsidian/ 的目录（工作区在仓库内 → 命中）
    2) 找不到时，在 start 的直接子目录里找（工作区是仓库的父目录 → 命中唯一候选）
    返回 (仓库根, 候选列表)。多个候选时不擅自选择，交由调用方报错。
    """
    cur = start.resolve()
    for parent in (cur, *cur.parents):
        if (parent / ".obsidian").is_dir():
            return parent, []
    try:
        candidates = sorted(
            (p for p in cur.iterdir()
             if p.is_dir() and p.name not in SKIP_DIRS and (p / ".obsidian").is_dir()),
            key=lambda p: p.name.lower(),
        )
    except OSError:
        candidates = []
    if len(candidates) == 1:
        return candidates[0], []
    return None, candidates


def resolve_root(args: argparse.Namespace) -> Path:
    """解析仓库根目录。优先级：--root > --vault 别名 > 工作区自动识别 > vaults.json default。"""
    if getattr(args, "root", None):
        root = Path(args.root)
        if not root.is_dir():
            raise SystemExit(f"--root 指定的目录不存在：{root}")
        return root

    config = load_vaults()
    vaults = config.get("vaults") or {}

    key = getattr(args, "vault", None)
    if key:
        entry = vaults.get(key)
        if not entry:
            raise SystemExit(
                f"vaults.json 中未登记 {key!r}。可用别名：{list(vaults) or '（空）'}；"
                f"或省略 --vault 让脚本自动识别当前工作区。"
            )
        return Path(entry["path"])

    detected, candidates = detect_vault_root(Path.cwd())
    if detected:
        return detected
    if candidates:
        raise SystemExit(
            "当前工作区下发现多个 Obsidian 仓库，请用 --root 指定其一：\n  "
            + "\n  ".join(str(c) for c in candidates)
        )

    default_key = config.get("default")
    if default_key and default_key in vaults:
        return Path(vaults[default_key]["path"])

    raise SystemExit(
        "未找到 Obsidian 仓库：当前目录及其上层都没有 .obsidian/ 目录。\n"
        "任选其一解决：\n"
        "  1) 在笔记库目录内运行（把工作区设为笔记库）；\n"
        "  2) 加 --root <仓库绝对路径>；\n"
        "  3) 在 vaults.json 里登记别名后用 --vault <别名>。"
    )


# --------------------------------------------------------------------------
# 笔记遍历
# --------------------------------------------------------------------------

def iter_notes(root: Path, include_excalidraw: bool = False) -> list[Path]:
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS and not d.endswith(SKIP_SUFFIXES)
        ]
        for name in filenames:
            if not name.endswith(NOTE_SUFFIX):
                continue
            if not include_excalidraw and name.endswith(".excalidraw.md"):
                continue
            out.append(Path(dirpath) / name)
    return sorted(out, key=lambda p: str(p).lower())


def read_note(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """返回 (frontmatter 字典, 正文)。未使用 YAML 库，只做保守的简易解析。"""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    data: dict = {}
    current_key = None
    for line in match.group(1).splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        item = re.match(r"\s*-\s+(.*)$", line)
        if item and current_key:
            data.setdefault(current_key, [])
            if isinstance(data[current_key], list):
                data[current_key].append(_scalar(item.group(1)))
            continue
        kv = re.match(r"([A-Za-z0-9_\-\u4e00-\u9fff]+)\s*:\s*(.*)$", line)
        if kv:
            current_key = kv.group(1)
            value = kv.group(2).strip()
            data[current_key] = [] if value == "" else _scalar(value)
    return data, text[match.end():]


def _scalar(raw: str):
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        return [x.strip().strip("'\"") for x in inner.split(",") if x.strip()]
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
        return raw[1:-1]
    return raw


def extract_headings(text: str) -> list[dict]:
    """提取标题，自动跳过围栏代码块内的伪标题。"""
    headings, in_fence, fence_mark = [], False, ""
    for lineno, line in enumerate(text.splitlines(), start=1):
        m = FENCE_RE.match(line)
        if m:
            if not in_fence:
                in_fence, fence_mark = True, m.group(1)
            elif m.group(1) == fence_mark:
                in_fence = False
            continue
        if in_fence:
            continue
        hm = re.match(r"^(#{1,6})\s+(.*)$", line)
        if hm:
            headings.append({
                "line": lineno,
                "level": len(hm.group(1)),
                "title": hm.group(2).strip(),
            })
    return headings


def extract_links(text: str) -> list[str]:
    """返回笔记正文中的 wikilink 目标（去重、保持顺序）。"""
    body = text
    fm = FRONTMATTER_RE.match(text)
    if fm:
        body = text[fm.end():]
    targets: list[str] = []
    for m in WIKILINK_RE.finditer(body):
        target = m.group(2).strip()
        if target and target not in targets:
            targets.append(target)
    return targets


def resolve_target(root: Path, source: Path, target: str) -> str | None:
    """把 wikilink 目标解析成仓库相对路径；解析不出返回 None。"""
    clean = target.split("#")[0].strip().replace("\\", "/")
    if not clean:
        return None
    for candidate in (
        source.parent / f"{clean}.md",
        root / f"{clean}.md",
        source.parent / clean,
        root / clean,
    ):
        if candidate.is_file():
            return str(candidate.relative_to(root)).replace("\\", "/")
    # 退化为按 basename 全库匹配
    base = os.path.basename(clean).lower()
    for note in iter_notes(root):
        if note.stem.lower() == base or note.name.lower() == base:
            return str(note.relative_to(root)).replace("\\", "/")
    return None


def build_link_graph(root: Path, include_excalidraw: bool = False) -> dict:
    """构建链接图，供 links 与 audit 共用。"""
    notes = iter_notes(root, include_excalidraw)
    rel = {note: str(note.relative_to(root)).replace("\\", "/") for note in notes}
    text_by_note = {note: read_note(note) for note in notes}
    outgoing: dict[str, list[str]] = {}
    unresolved: list[dict] = []

    for note in notes:
        key = rel[note]
        resolved: list[str] = []
        for target in extract_links(text_by_note[note]):
            hit = resolve_target(root, note, target)
            if hit:
                resolved.append(hit)
            else:
                unresolved.append({"from": key, "target": target})
        outgoing[key] = resolved

    incoming: dict[str, list[str]] = {path: [] for path in rel.values()}
    for source, targets in outgoing.items():
        for target in targets:
            incoming.setdefault(target, []).append(source)

    return {
        "notes": notes,
        "rel": rel,
        "text_by_note": text_by_note,
        "outgoing": outgoing,
        "incoming": incoming,
        "unresolved": unresolved,
        "orphans": [path for path, sources in incoming.items() if not sources],
        "deadends": [path for path, targets in outgoing.items() if not targets],
    }


def is_moc_note(note: Path, text: str) -> bool:
    """按文件名或 tags 判定 MOC；避免要求历史 MOC 全量补元数据。"""
    frontmatter, _ = parse_frontmatter(text)
    tags = frontmatter.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]
    stem = note.stem.strip().casefold()
    return stem == "moc" or stem.endswith(" moc") or any(
        str(tag).strip().casefold() == "moc" for tag in tags
    )


def section_content(text: str, headings: list[dict], heading: dict) -> str:
    """返回某标题下的内容，直到下一个同级或更高等级标题。"""
    lines = text.splitlines(keepends=True)
    start = heading["line"]
    end = len(lines)
    for candidate in headings:
        if candidate["line"] > heading["line"] and candidate["level"] <= heading["level"]:
            end = candidate["line"] - 1
            break
    return "".join(lines[start:end])


def moc_reading_path_index(root: Path, graph: dict) -> tuple[list[dict], set[str]]:
    """提取每个 MOC 的“阅读路径”目标，保留未解析目标供审计显示。"""
    entries: list[dict] = []
    listed_notes: set[str] = set()
    for note in graph["notes"]:
        text = graph["text_by_note"][note]
        if not is_moc_note(note, text):
            continue
        targets: list[str] = []
        unresolved: list[str] = []
        headings = extract_headings(text)
        for heading in headings:
            if "阅读路径" not in heading["title"]:
                continue
            for target in extract_links(section_content(text, headings, heading)):
                hit = resolve_target(root, note, target)
                if hit:
                    targets.append(hit)
                    listed_notes.add(hit)
                else:
                    unresolved.append(target)
        entries.append({
            "path": graph["rel"][note],
            "reading_path": targets,
            "unresolved_reading_path": unresolved,
        })
    return entries, listed_notes


# --------------------------------------------------------------------------
# 子命令
# --------------------------------------------------------------------------

def cmd_tree(args: argparse.Namespace) -> int:
    root = resolve_root(args)
    notes = iter_notes(root, args.include_excalidraw)
    print(f"{root}  ({len(notes)} 篇笔记)")

    def walk(folder: Path, prefix: str = "") -> None:
        entries = sorted(
            [p for p in folder.iterdir()
             if p.is_dir() and p.name not in SKIP_DIRS and not p.name.endswith(SKIP_SUFFIXES)
             and any(note.relative_to(root).parts[:len(p.relative_to(root).parts)]
                     == p.relative_to(root).parts for note in notes)],
            key=lambda p: p.name.lower(),
        )
        files = sorted(
            [p for p in folder.iterdir()
             if p.is_file() and p.suffix == NOTE_SUFFIX
             and (args.include_excalidraw or not p.name.endswith(".excalidraw.md"))],
            key=lambda p: p.name.lower(),
        )
        items = [("d", p) for p in entries] + [("f", p) for p in files]
        for kind, item in items:
            connector = "└── " if item is items[-1][1] else "├── "
            if kind == "d":
                print(f"{prefix}{connector}{item.name}/")
                walk(item, prefix + ("    " if connector == "└── " else "│   "))
            else:
                print(f"{prefix}{connector}{item.stem}")

    walk(root)
    return 0


def cmd_meta(args: argparse.Namespace) -> int:
    root = resolve_root(args)
    rows = []
    for note in iter_notes(root, args.include_excalidraw):
        text = read_note(note)
        fm, body = parse_frontmatter(text)
        headings = extract_headings(body)
        rows.append({
            "path": str(note.relative_to(root)).replace("\\", "/"),
            "title": note.stem,
            "h1": next((h["title"] for h in headings if h["level"] == 1), ""),
            "tags": fm.get("tags", []),
            "aliases": fm.get("aliases", []),
            "frontmatter": fm,
            "headings": [h["title"] for h in headings],
            "chars": len(body),
            "modified": datetime.fromtimestamp(note.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


def cmd_links(args: argparse.Namespace) -> int:
    root = resolve_root(args)
    graph = build_link_graph(root, args.include_excalidraw)
    print(json.dumps({
        "root": str(root),
        "count": len(graph["notes"]),
        "outgoing": graph["outgoing"],
        "incoming": graph["incoming"],
        "unresolved": graph["unresolved"],
        "orphans": graph["orphans"],
        "deadends": graph["deadends"],
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    """输出只读健康报告；不把提示直接变成文件改动或任务。"""
    root = resolve_root(args)
    graph = build_link_graph(root, args.include_excalidraw)
    mocs, listed_notes = moc_reading_path_index(root, graph)
    non_mocs = [
        note for note in graph["notes"]
        if not is_moc_note(note, graph["text_by_note"][note])
    ]

    missing_updated: list[str] = []
    missing_note_type: list[str] = []
    long_notes: list[dict] = []
    needs_verify: list[dict] = []
    notes_marked_needs_verify: list[str] = []
    invalid_note_type: list[dict] = []
    invalid_status: list[dict] = []
    open_questions: list[dict] = []
    declared_moc_not_listed: list[dict] = []

    for note in graph["notes"]:
        path = graph["rel"][note]
        text = graph["text_by_note"][note]
        frontmatter, _ = parse_frontmatter(text)
        if not frontmatter.get("updated"):
            missing_updated.append(path)
        note_type = str(frontmatter.get("note_type", "")).strip()
        status = str(frontmatter.get("status", "")).strip()
        if not is_moc_note(note, text) and not note_type:
            missing_note_type.append(path)
        elif note_type and note_type not in VALID_NOTE_TYPES:
            invalid_note_type.append({"path": path, "note_type": note_type})
        if status and status not in VALID_STATUSES:
            invalid_status.append({"path": path, "status": status})
        if status == "needs-verify":
            notes_marked_needs_verify.append(path)
        line_count = len(text.splitlines())
        if args.long_lines > 0 and line_count > args.long_lines:
            long_notes.append({"path": path, "lines": line_count})
        for lineno, line in enumerate(text.splitlines(), start=1):
            if re.match(r"^\s*>\s*\[!warning\]\s*待核实", line, re.IGNORECASE):
                needs_verify.append({"path": path, "line": lineno, "title": line.strip()})
            if re.match(r"^\s*>\s*\[!question\]", line, re.IGNORECASE):
                open_questions.append({"path": path, "line": lineno, "title": line.strip()})

    for note in non_mocs:
        path = graph["rel"][note]
        frontmatter, _ = parse_frontmatter(graph["text_by_note"][note])
        if frontmatter.get("moc") and path not in listed_notes:
            declared_moc_not_listed.append({
                "path": path,
                "moc": frontmatter["moc"],
            })

    unlisted_notes = [graph["rel"][note] for note in non_mocs if graph["rel"][note] not in listed_notes]
    summary = {
        "unresolved_links": len(graph["unresolved"]),
        "orphans": len(graph["orphans"]),
        "deadends": len(graph["deadends"]),
        "missing_updated": len(missing_updated),
        "missing_note_type": len(missing_note_type),
        "long_notes": len(long_notes),
        "needs_verify_callouts": len(needs_verify),
        "notes_marked_needs_verify": len(notes_marked_needs_verify),
        "invalid_note_type": len(invalid_note_type),
        "invalid_status": len(invalid_status),
        "open_questions": len(open_questions),
        "unlisted_from_reading_paths": len(unlisted_notes),
        "declared_moc_not_listed": len(declared_moc_not_listed),
    }
    print(json.dumps({
        "root": str(root),
        "count": len(graph["notes"]),
        "rules": {"long_lines": args.long_lines},
        "summary": summary,
        "unresolved": graph["unresolved"],
        "orphans": graph["orphans"],
        "deadends": graph["deadends"],
        "missing_updated": missing_updated,
        "missing_note_type": missing_note_type,
        "long_notes": long_notes,
        "needs_verify": needs_verify,
        "notes_marked_needs_verify": notes_marked_needs_verify,
        "invalid_note_type": invalid_note_type,
        "invalid_status": invalid_status,
        "open_questions": open_questions,
        "mocs": mocs,
        "unlisted_from_reading_paths": unlisted_notes,
        "declared_moc_not_listed": declared_moc_not_listed,
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_outline(args: argparse.Namespace) -> int:
    root = resolve_root(args)
    note = root / args.file
    if not note.is_file():
        hits = [n for n in iter_notes(root) if args.file.lower() in str(n).lower()]
        if len(hits) == 1:
            note = hits[0]
        elif not hits:
            print(f"未找到笔记：{args.file}", file=sys.stderr)
            return 4
        else:
            print("匹配到多篇，请指定完整路径：", file=sys.stderr)
            for h in hits:
                print("  " + str(h.relative_to(root)), file=sys.stderr)
            return 4
    headings = extract_headings(read_note(note))
    print(f"# {note.relative_to(root)}")
    for h in headings:
        indent = "  " * (h["level"] - 1)
        print(f"L{h['line']:<5}{indent}{'#' * h['level']} {h['title']}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    root = resolve_root(args)
    pattern = re.compile(args.pattern, re.IGNORECASE if args.ignore_case else 0)
    hits = []
    for note in iter_notes(root, args.include_excalidraw):
        lines = read_note(note).splitlines()
        for i, line in enumerate(lines, start=1):
            if pattern.search(line):
                lo = max(1, i - args.context)
                hi = min(len(lines), i + args.context)
                hits.append({
                    "path": str(note.relative_to(root)).replace("\\", "/"),
                    "line": i,
                    "match": line.strip(),
                    "context": lines[lo - 1:hi],
                })
                if len(hits) >= args.limit:
                    break
        if len(hits) >= args.limit:
            break
    print(json.dumps({"pattern": args.pattern, "count": len(hits), "hits": hits},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_find(args: argparse.Namespace) -> int:
    root = resolve_root(args)
    key = args.query.lower()
    hits = [str(n.relative_to(root)).replace("\\", "/")
            for n in iter_notes(root, True) if key in str(n.relative_to(root)).lower()]
    print(json.dumps(hits, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Obsidian 仓库扫描")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--root", help="仓库根目录（最高优先）")
        p.add_argument("--vault", help="vaults.json 中的别名（可选；缺省自动识别工作区）")
        p.add_argument("--include-excalidraw", action="store_true")

    p = sub.add_parser("tree", help="目录树")
    common(p); p.set_defaults(func=cmd_tree)

    p = sub.add_parser("meta", help="全部笔记元信息 JSON")
    common(p); p.set_defaults(func=cmd_meta)

    p = sub.add_parser("links", help="链接图 / 断链 / 孤儿")
    common(p); p.set_defaults(func=cmd_links)

    p = sub.add_parser("audit", help="知识库健康报告 JSON")
    common(p)
    p.add_argument("--long-lines", type=int, default=400,
                   help="超过此行数的笔记进入复查清单；0 表示关闭（默认：400）")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("outline", help="单篇标题大纲")
    common(p); p.add_argument("--file", required=True); p.set_defaults(func=cmd_outline)

    p = sub.add_parser("search", help="正则检索")
    common(p)
    p.add_argument("--pattern", required=True)
    p.add_argument("--context", type=int, default=1)
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--ignore-case", action="store_true", default=True)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("find", help="按文件名查找")
    common(p); p.add_argument("--query", required=True); p.set_defaults(func=cmd_find)
    return parser


def main() -> int:
    _utf8()
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

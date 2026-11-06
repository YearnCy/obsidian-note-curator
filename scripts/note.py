#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""note.py — 单篇笔记的章节级读写（保持编号体系，支持 dry-run）。

子命令:
  outline      输出标题大纲（带行号，供定位插入点）
  insert       在指定标题下/前/后插入内容
  replace      替换指定标题下的正文（保留标题行）
  append       追加到文件末尾
  renumber     重排「十进制编号」标题（一、二、三 这类中文编号不动）
  frontmatter  读取或更新 YAML frontmatter

通用参数:
  --file <path>   仓库相对路径；找不到时会按文件名模糊匹配
  --vault <key> / --root <dir>   仓库定位；都不给时自动识别当前工作区（向上找 .obsidian/）
  --content-file <path> / --content <text> / -   插入内容来源
  --dry-run       只打印 unified diff，不落盘（默认关闭，建议先跑一次）
  --no-backup      正式写入时跳过库内备份；默认在 .note-curator-backups/ 保存原文件

示例:
  python note.py outline --file "Linux驱动.md"
  python note.py insert --file "Linux驱动.md" \
      --heading "二、模块的编译与检查" --position under --content-file .note-staging/sec.md --dry-run
  python note.py frontmatter --file "Linux驱动.md" \
      --set tags='["linux","驱动"]' --set updated=2026-09-03
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vault import (  # noqa: E402
    FRONTMATTER_RE, FENCE_RE, extract_headings, iter_notes, read_note, resolve_root,
)

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
NUMBER_PREFIX_RE = re.compile(
    r"^\s*(?:"
    r"[一二三四五六七八九十百]+[、.]"
    r"|[（(]\d+[)）]"
    r"|第[一二三四五六七八九十百]+[章节部分]"
    r"|\d+(?:\.\d+)*[.、)]?"
    r")\s*"
)
DECIMAL_HEADING_RE = re.compile(r"^(\d+(?:\.\d+)*)[\s.、]+(.*)$")


def _utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def resolve_note(root: Path, file_arg: str) -> Path:
    direct = root / file_arg
    if direct.is_file():
        return direct
    hits = [n for n in iter_notes(root, True) if file_arg.lower() in str(n).lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise SystemExit(f"未找到笔记：{file_arg}")
    raise SystemExit("匹配到多篇，请用完整相对路径：\n  " +
                     "\n  ".join(str(h.relative_to(root)) for h in hits))


def normalize(title: str) -> str:
    return NUMBER_PREFIX_RE.sub("", title).strip().lower()


def find_heading(headings: list[dict], target: str) -> dict | None:
    """按标题文本匹配：完全匹配 → 去编号后匹配 → 以目标结尾。"""
    t = target.strip().lstrip("#").strip()
    for h in headings:
        if h["title"] == t:
            return h
    tn = normalize(t)
    for h in headings:
        if normalize(h["title"]) == tn:
            return h
    for h in headings:
        if normalize(h["title"]).endswith(tn) or tn.endswith(normalize(h["title"])):
            return h
    return None


def section_range(lines: list[str], headings: list[dict], heading: dict) -> tuple[int, int]:
    """返回 (标题行 index, 章节结束行 index)，均为 0-based 半开区间。"""
    start = heading["line"] - 1
    end = len(lines)
    for h in headings:
        if h["line"] - 1 > start and h["level"] <= heading["level"]:
            end = h["line"] - 1
            break
    # 回退掉章节末尾的空行，避免插入后出现大片空隙
    while end > start and not lines[end - 1].strip():
        end -= 1
    return start, end


def load_content(args: argparse.Namespace) -> str:
    if getattr(args, "content_file", None):
        if args.content_file == "-":
            return sys.stdin.read()
        return Path(args.content_file).read_text(encoding="utf-8")
    if getattr(args, "content", None) is not None:
        return args.content.replace("\\n", "\n").replace("\\t", "\t")
    raise SystemExit("需要 --content-file 或 --content")


def backup_path(root: Path, note: Path) -> Path:
    """返回本次修改的库内备份路径；备份目录被 vault.py 自动跳过。"""
    rel = note.relative_to(root)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return root / ".note-curator-backups" / stamp / rel


def create_backup(root: Path, note: Path) -> Path:
    """在正式写入前复制原文件，使用 copy2 保留时间戳供人工恢复。"""
    target = backup_path(root, note)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(note, target)
    return target


def write_out(root: Path, path: Path, old: str, new: str, dry_run: bool,
              backup: bool = True) -> int:
    if dry_run:
        diff = difflib.unified_diff(
            old.splitlines(keepends=True), new.splitlines(keepends=True),
            fromfile=f"a/{path.name}", tofile=f"b/{path.name}",
        )
        sys.stdout.writelines(diff)
        print(f"\n[dry-run] 未写入：{path}")
        return 0
    if old == new:
        print(f"[ok] 内容无变化：{path}")
        return 0
    saved = create_backup(root, path) if backup else None
    path.write_text(new, encoding="utf-8", newline="\n")
    if saved:
        print(f"[backup] 原文件已保存到 {saved}")
    print(f"[ok] 已写入 {path}")
    return 0


# --------------------------------------------------------------------------
# 子命令
# --------------------------------------------------------------------------

def cmd_outline(args: argparse.Namespace) -> int:
    root = resolve_root(args)
    note = resolve_note(root, args.file)
    text = read_note(note)
    headings = extract_headings(text)
    has_fm = FRONTMATTER_RE.match(text) is not None
    print(f"# {note.relative_to(root)}   ({len(text)} 字符, {len(headings)} 个标题, "
          f"{'有' if has_fm else '无'} frontmatter)")
    for h in headings:
        indent = "  " * (h["level"] - 1)
        print(f"L{h['line']:<5}{indent}{'#' * h['level']} {h['title']}")
    return 0


def cmd_insert(args: argparse.Namespace) -> int:
    root = resolve_root(args)
    note = resolve_note(root, args.file)
    text = read_note(note)
    lines = text.splitlines(keepends=True)
    headings = extract_headings(text)
    content = load_content(args)
    if content and not content.endswith("\n"):
        content += "\n"

    heading = find_heading(headings, args.heading) if args.heading else None
    if heading is None:
        if not args.create_heading:
            raise SystemExit(
                f"未找到标题 {args.heading!r}。可加 --create-heading 在末尾新建该标题。\n"
                f"现有标题：{', '.join(h['title'] for h in headings)}"
            )
        block = f"\n{args.heading}\n\n{content}"
        new = text.rstrip("\n") + "\n" + block
        return write_out(root, note, text, new, args.dry_run, args.backup)

    block = content if content.endswith("\n") else content + "\n"
    if args.position == "before":
        idx = heading["line"] - 1
        new = "".join(lines[:idx]) + block + "\n" + "".join(lines[idx:])
    elif args.position == "after":
        idx = heading["line"]
        new = "".join(lines[:idx]) + "\n" + block + "".join(lines[idx:])
    else:  # under
        start, end = section_range(lines, headings, heading)
        new = "".join(lines[:end]) + "\n" + block + "".join(lines[end:])

    if args.renumber:
        new = renumber_text(new)
    return write_out(root, note, text, new, args.dry_run, args.backup)


def cmd_replace(args: argparse.Namespace) -> int:
    root = resolve_root(args)
    note = resolve_note(root, args.file)
    text = read_note(note)
    lines = text.splitlines(keepends=True)
    headings = extract_headings(text)
    heading = find_heading(headings, args.heading)
    if heading is None:
        raise SystemExit(f"未找到标题 {args.heading!r}")
    content = load_content(args)
    if content and not content.endswith("\n"):
        content += "\n"
    start, end = section_range(lines, headings, heading)
    new = "".join(lines[:start + 1]) + "\n" + content + "".join(lines[end:])
    if args.renumber:
        new = renumber_text(new)
    return write_out(root, note, text, new, args.dry_run, args.backup)


def cmd_append(args: argparse.Namespace) -> int:
    root = resolve_root(args)
    note = resolve_note(root, args.file)
    text = read_note(note)
    content = load_content(args)
    new = text.rstrip("\n") + "\n\n" + content.strip("\n") + "\n"
    return write_out(root, note, text, new, args.dry_run, args.backup)


def renumber_text(text: str) -> str:
    """重排以十进制开头的标题编号（如 2.1 / 2.1.1），中文编号标题保持不动。

    层级关系取自编号本身的位数（2.1 → 深度 2），而不是 # 的个数，这样
    「一、二、三」这类中文编号的章标题不会打乱子节的计数。
    遇到的第一个十进制标题作为种子，保持其原始编号，后续同级递增。
    """
    lines = text.splitlines(keepends=True)
    stack: list[int] = []
    in_fence, fence_mark = False, ""
    for i, line in enumerate(lines):
        m = FENCE_RE.match(line)
        if m:
            if not in_fence:
                in_fence, fence_mark = True, m.group(1)
            elif m.group(1) == fence_mark:
                in_fence = False
            continue
        if in_fence:
            continue
        hm = HEADING_RE.match(line)
        if not hm:
            continue
        dm = DECIMAL_HEADING_RE.match(hm.group(2))
        if not dm:
            continue

        stack = _next_number(stack, dm.group(1))
        prefix = ".".join(str(n) for n in stack)
        # 只替换标题文本部分，保留原本的 # 层级与行尾换行
        lines[i] = f"{hm.group(1)} {prefix} {dm.group(2)}{line[hm.end():]}"
    return "".join(lines)


def _next_number(stack: list[int], raw: str) -> list[int]:
    """根据前一个标题的编号栈，算出当前标题应有的编号。"""
    parts = [int(p) for p in raw.split(".") if p.isdigit()]
    if not parts:
        return stack
    if not stack:
        return list(parts)  # 首个十进制标题：沿用原编号作为起点
    depth = len(parts)
    if len(stack) >= depth:
        return stack[:depth - 1] + [stack[depth - 1] + 1]
    return stack + [1] * (depth - len(stack))


def cmd_renumber(args: argparse.Namespace) -> int:
    root = resolve_root(args)
    note = resolve_note(root, args.file)
    text = read_note(note)
    new = renumber_text(text)
    return write_out(root, note, text, new, args.dry_run, args.backup)


# ---------- frontmatter ----------

def parse_fm(text: str) -> tuple[list[list], dict[str, list[str]], list[str], str]:
    """返回 (字段列表, 各字段原始行块, 字段顺序, 正文)。

    原始行块用于在更新 frontmatter 时**原样保留未被修改字段的写法**，
    避免只改一个字段却把整个 frontmatter 重排一遍。
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return [], {}, [], text
    raw_lines = m.group(1).splitlines()
    data: list[list] = []
    blocks: dict[str, list[str]] = {}
    order: list[str] = []
    current = None
    for line in raw_lines:
        if not line.strip():
            continue
        item = re.match(r"\s*-\s+(.*)$", line)
        if item and current is not None:
            current[1].append(item.group(1).strip().strip("'\""))
            blocks[current[0]].append(line)
            continue
        kv = re.match(r"([A-Za-z0-9_\-\u4e00-\u9fff]+)\s*:\s*(.*)$", line)
        if kv:
            current = [kv.group(1), []]
            value = kv.group(2).strip()
            if value and value != "[]":
                current[1] = [v.strip().strip("'\"") for v in value.strip("[]").split(",") if v.strip()]
            data.append(current)
            blocks[current[0]] = [line]
            order.append(current[0])
            if value == "[]":
                current = None
    return data, blocks, order, text[m.end():]


_NEEDS_QUOTE = set(":#[]{},")


def _render_scalar(value: str) -> str:
    """纯量：含 YAML 特殊字符时加双引号，保证可解析。"""
    if value and value[0] not in _NEEDS_QUOTE and not any(c in _NEEDS_QUOTE for c in value):
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _fmt_value(values: list[str], force_list: bool = False) -> list[str]:
    """按值的形状渲染：单值→纯量（必要时加引号），多值/显式列表→YAML 列表。"""
    if not values:
        return ["[]"]
    if len(values) == 1 and not force_list:
        return [_render_scalar(values[0])]
    return ["\n" + "\n".join(f"  - {_render_scalar(v)}" for v in values)]


def _parse_set(raw: str):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def cmd_frontmatter(args: argparse.Namespace) -> int:
    root = resolve_root(args)
    note = resolve_note(root, args.file)
    text = read_note(note)
    data, blocks, order, body = parse_fm(text)

    if not args.set and not args.remove:
        out = {k: (v if len(v) != 1 else v[0]) for k, v in data}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    # 只重渲染被 --set / --remove 触及的字段，其余原样输出原始行块
    changed: dict[str, tuple[list[str], bool]] = {}
    for raw in args.set or []:
        if "=" not in raw:
            raise SystemExit(f"--set 需要 key=value 形式：{raw}")
        key, value = raw.split("=", 1)
        parsed = _parse_set(value)
        values = parsed if isinstance(parsed, list) else [str(parsed)]
        values = [str(v) for v in values]
        changed[key] = (values, isinstance(parsed, list))
        for row in data:
            if row[0] == key:
                row[1] = values
                break
        else:
            data.append([key, values])
            order.append(key)

    removed = set(args.remove or [])
    keys = [k for k in order if k not in removed]
    for key in changed:
        if key not in keys:
            keys.append(key)

    lines = ["---"]
    for key in keys:
        if key in changed:
            values, force_list = changed[key]
            rendered = _fmt_value(values, force_list)
            if len(rendered) == 1 and rendered[0].startswith("\n"):
                lines.append(f"{key}:{rendered[0]}")
            else:
                lines.append(f"{key}: {rendered[0]}")
        else:
            lines.extend(blocks.get(key, []))
    lines.append("---")
    new = "\n".join(lines) + "\n" + body
    return write_out(root, note, text, new, args.dry_run, args.backup)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="单篇笔记章节级编辑")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--vault"), p.add_argument("--root")
        p.add_argument("--file", required=True)
        p.add_argument("--backup", dest="backup", action="store_true",
                       help="正式写入时创建 .note-curator-backups 备份（默认已开启）")
        p.add_argument("--no-backup", dest="backup", action="store_false",
                       help="正式写入时不创建 .note-curator-backups 备份（仅在已有独立恢复措施时使用）")
        p.set_defaults(backup=True)

    def content_src(p: argparse.ArgumentParser) -> None:
        p.add_argument("--content-file")
        p.add_argument("--content")

    p = sub.add_parser("outline"); common(p); p.set_defaults(func=cmd_outline)

    p = sub.add_parser("insert"); common(p); content_src(p)
    p.add_argument("--heading")
    p.add_argument("--position", choices=("under", "before", "after"), default="under")
    p.add_argument("--create-heading", action="store_true")
    p.add_argument("--renumber", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_insert)

    p = sub.add_parser("replace"); common(p); content_src(p)
    p.add_argument("--heading", required=True)
    p.add_argument("--renumber", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_replace)

    p = sub.add_parser("append"); common(p); content_src(p)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_append)

    p = sub.add_parser("renumber"); common(p)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_renumber)

    p = sub.add_parser("frontmatter"); common(p)
    p.add_argument("--set", action="append", metavar="KEY=VALUE")
    p.add_argument("--remove", action="append", metavar="KEY")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_frontmatter)
    return parser


def main() -> int:
    _utf8()
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

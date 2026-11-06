#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""step_audit.py — 教学台阶审计（列出术语的首次出现位置，供交付前人工确认）。

扫描一篇 Markdown 笔记，按 H2 章节分组列出每个技术标识符的「首次出现位置」，
输出一张待人工审查的清单。脚本不作判断（不猜「算不算解释过」），只把需要
人眼过一遍的行摊出来——判断留给写的人。

用法:
    python step_audit.py --file "网络设备运行机制.md"
    python step_audit.py --vault upup --file "Linux驱动/网络设备运行机制.md"
    python step_audit.py --root D:/ObNote/UpUp --file "网络设备运行机制.md" --json
    python step_audit.py --file note.md --chapter 2    # 只看第 2 章

退出码:
    0  正常
    1  发现高风险项（术语首次出现在标题里）
    2  文件不可读 / 找不到笔记
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vault import iter_notes, resolve_root  # noqa: E402

# 出现频率极高、几乎不需要逐次铺垫的通用词
DEFAULT_SKIP = {
    "API", "CPU", "GPU", "RAM", "ROM", "OK", "ERR", "NULL", "TODO", "NOTE",
    "README", "JSON", "YAML", "HTTP", "HTTPS", "URL", "URI", "UTF", "GNU",
    "IP", "TCP", "UDP", "MAC", "MTU", "FAQ", "DRV", "MSG", "ID", "IO",
    "TRUE", "FALSE", "MAX", "MIN", "EOF", "SPDX", "GPL", "RST", "XML",
    "HTML", "CSS", "SQL", "PIN", "GPIO", "DMA", "IRQ", "ISR", "PCI",
    "USB", "SPI", "I2C", "UART", "CAN", "ADC", "PWM", "RTC",
}

# 提取规则：反引号标识符、struct/enum/union 名、全大写宏、函数调用
RE_BACKTICK = re.compile(r"`([A-Za-z_][A-Za-z0-9_.\-]{1,63})`")
RE_TYPEDEF = re.compile(r"\b(?:struct|enum|union)\s+([A-Za-z_][A-Za-z0-9_]{1,63})")
RE_MACRO = re.compile(r"\b([A-Z][A-Z0-9_]{2,40})\b")
RE_CALL = re.compile(r"\b([a-z_][a-z0-9_]{2,40})\s*\(")


def _utf8() -> None:
    """让 Windows 下的中文输出不被控制台代码页吃掉。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def resolve_note(root: Path, file_arg: str) -> Path:
    """按 note.py 的同一套规则定位笔记：绝对/相对路径 → 仓库相对 → 文件名模糊匹配。"""
    direct = Path(file_arg)
    if direct.is_absolute() and direct.is_file():
        return direct
    candidate = root / file_arg
    if candidate.is_file():
        return candidate
    key = file_arg.replace("\\", "/").lower()
    hits = [n for n in iter_notes(root, True) if key in str(n).lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise SystemExit(f"未找到笔记：{file_arg}（仓库根：{root}）")
    raise SystemExit(
        "匹配到多篇，请用完整相对路径：\n  "
        + "\n  ".join(str(h.relative_to(root)) for h in hits)
    )


def looks_like_code(line: str) -> bool:
    """粗判一行是不是代码（不是 fenced block，而是行内像代码）。"""
    s = line.strip()
    return bool(
        s.endswith(";")
        or s.endswith("{")
        or s.endswith("}")
        or s.startswith("#include")
        or s.startswith("#define")
    )


def extract_terms(line: str, in_fence: bool):
    """返回本行出现的术语集合。"""
    terms = set()

    # 反引号：无论在不在代码块里都提取（正文里的 `sk_buff` 最典型）
    for m in RE_BACKTICK.finditer(line):
        terms.add(m.group(1))

    # struct/enum/union：任何位置都算
    for m in RE_TYPEDEF.finditer(line):
        terms.add("struct " + m.group(1))

    # 宏与函数调用只在代码块外或代码行里提取，避免正文里的大写强调词被误收
    if in_fence or looks_like_code(line):
        for m in RE_MACRO.finditer(line):
            terms.add(m.group(1))
        for m in RE_CALL.finditer(line):
            terms.add(m.group(1) + "()")

    return terms


def scan(path: Path, skip: set):
    """返回 (chapters, records)。

    chapters: [{index, title, line}]
    records:  [{term, line, chapter_index, in_fence, in_heading, in_table, snippet}]
    records 按首次出现排序。
    """
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"无法读取文件: {exc}", file=sys.stderr)
        sys.exit(2)

    lines = raw.splitlines()

    # 章节按 H2 分组；有些笔记只用 H1 作主章节（本库里确有这种写法），
    # 此时退回按 H1 分组，否则整篇会挤进「开篇」一章，清单失去意义。
    h2_exists = any(re.match(r"^##\s+\S", ln) for ln in lines)
    chapter_re = r"^##\s+\S" if h2_exists else r"^#\s+\S"

    chapters = [{"index": 0, "title": "（开篇，未进入任何章节）", "line": 0}]
    records = {}
    in_fence = False
    in_frontmatter = False
    cur_chapter = 0

    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()

        # frontmatter 里的 tags / aliases 不是正文术语
        if lineno == 1 and stripped == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            if stripped == "---":
                in_frontmatter = False
            continue

        # 切换代码块状态（``` 或 ~~~）
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue

        # 章节切换
        if not in_fence and re.match(chapter_re, line):
            chapters.append(
                {
                    "index": len(chapters),
                    "title": re.sub(r"^#+\s*", "", stripped),
                    "line": lineno,
                }
            )
            cur_chapter = len(chapters) - 1
            continue

        is_heading = (not in_fence) and bool(re.match(r"^#{1,6}\s", line))
        is_table = (not in_fence) and stripped.startswith("|")

        for term in extract_terms(line, in_fence):
            if term in skip or term in records:
                continue
            records[term] = {
                "term": term,
                "line": lineno,
                "chapter_index": cur_chapter,
                "in_fence": in_fence,
                "in_heading": bool(is_heading),
                "in_table": bool(is_table),
                "snippet": stripped[:110],
            }

    return chapters, sorted(records.values(), key=lambda r: r["line"])


def render(chapters, records, only_chapter=None):
    by_chapter = {}
    for rec in records:
        by_chapter.setdefault(rec["chapter_index"], []).append(rec)

    out = []
    out.append("=" * 68)
    out.append("教学台阶审计：技术术语首次出现清单")
    out.append("=" * 68)
    out.append(f"章节 {len(chapters) - 1} 个，术语 {len(records)} 个（已按首次出现排序）")
    out.append("")
    out.append("审查方法：对每一条回到该行，问一句")
    out.append("    「读者读到这里时，认识这个词吗？」")
    out.append("    认识 → 通过 ｜ 不认识但本行就打比方讲清了 → 通过（就地一拍）")
    out.append("    不认识且直接拿来解释别的 → 必须改写")
    out.append("")

    risk = []
    for ch in chapters:
        idx = ch["index"]
        if only_chapter is not None and idx != only_chapter:
            continue
        bucket = by_chapter.get(idx, [])
        if not bucket:
            continue
        head = f"第 {idx} 章  {ch['title']}" if idx else ch["title"]
        out.append(head)
        out.append("-" * len(head))
        for rec in bucket:
            flags = []
            if rec["in_heading"]:
                flags.append("标题内")
                risk.append(rec)
            if rec["in_fence"]:
                flags.append("代码块内")
            if rec.get("in_table"):
                flags.append("表格/多为预告")
            flag_s = ("  [" + "/".join(flags) + "]") if flags else ""
            out.append(f"  行 {rec['line']:>5}  {rec['term']:<28}{flag_s}")
            out.append(f"              {rec['snippet']}")
        out.append("")

    if risk:
        out.append("=" * 68)
        out.append("高风险：以下术语首次出现在标题里（读者还没读到正文）")
        out.append("=" * 68)
        for rec in risk:
            out.append(f"  行 {rec['line']:>5}  {rec['term']}")
        out.append("")

    return "\n".join(out), risk


def main():
    _utf8()
    ap = argparse.ArgumentParser(description="教学台阶审计：列出术语首次出现位置")
    ap.add_argument("--file", required=True, help="笔记路径；给 --vault/--root 时可用仓库相对路径")
    ap.add_argument("--vault", help="vaults.json 中的仓库别名")
    ap.add_argument("--root", help="仓库绝对路径（优先于 --vault）")
    ap.add_argument("--json", action="store_true", help="输出 JSON（建议重定向到文件，别用管道）")
    ap.add_argument("--all", action="store_true",
                    help="兼容保留：审计只看首次出现，此开关不改变输出")
    ap.add_argument("--chapter", type=int, default=None, help="只显示指定章节序号（0=开篇）")
    ap.add_argument("--no-skip", action="store_true", help="不过滤通用词")
    args = ap.parse_args()

    root = resolve_root(args)
    path = resolve_note(root, args.file)
    chapters, records = scan(path, set() if args.no_skip else DEFAULT_SKIP)

    if args.json:
        payload = {
            "file": str(path),
            "root": str(root),
            "chapters": chapters,
            "terms": records,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    text, risk = render(chapters, records, args.chapter)
    print(f"文件：{path}")
    print(text)
    return 1 if risk else 0


if __name__ == "__main__":
    sys.exit(main())

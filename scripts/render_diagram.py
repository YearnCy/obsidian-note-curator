#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_diagram.py — 把 SVG / HTML 片段渲染成 PNG，并放进笔记的图片目录。

为什么要这个脚本：对话里产出的图（SVG / HTML 片段）本身只是文本，必须落成
图片文件才能嵌进 Obsidian。本脚本调用本机浏览器的无头模式截图，不依赖
ImageMagick / Inkscape / Playwright / cairosvg。

目录约定（与 note-style.md 第七节一致）：
    <vault>/BaiduSyncdisk/pic/<笔记名>/<图名>.png
    若 vault 没有 BaiduSyncdisk 目录，退化为 <vault>/pic/<笔记名>/<图名>.png
    嵌入语法：![[<笔记名>/<图名>.png]]

用法：
    # 单张（SVG）；--note 可给仓库相对路径
    python render_diagram.py --vault upup --note "MCU/xxx.md" \\
        --svg figs/a.svg --name "01-四指针关系"

    # 单张（HTML 片段，不带 <html>/<body>）
    python render_diagram.py --root D:/Notes --note "xxx.md" --html figs/b.html \\
        --name "02-tag池" --width 640 --height 220

    # 批量
    python render_diagram.py --note "xxx.md" --manifest figs.json

    # 沙箱内写不进笔记库时：先渲染到工作区，再由用户授权移动
    python render_diagram.py --note "xxx.md" --svg a.svg --name "01-xxx" \\
        --pic-root .note-staging/pic

manifest 格式：
    [{"name":"01-四指针","svg":"a.svg","width":680,"height":300},
     {"name":"02-tag池","html":"b.html","width":640,"height":220}]

输出：每张图一行，打印可直接粘贴的嵌入语法 ![[笔记名/图名.png]]
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

BROWSER_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

DEFAULT_BG = "#2b2b2b"      # 与 Obsidian 深色主题一致
DEFAULT_W = 680
DEFAULT_H = 400


def _utf8() -> None:
    """让 Windows 下的中文输出不被控制台代码页吃掉。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def find_browser() -> str:
    for p in BROWSER_CANDIDATES:
        if os.path.isfile(p):
            return p
    for name in ("msedge", "chrome", "chromium"):
        hit = shutil.which(name)
        if hit:
            return hit
    raise SystemExit(
        "找不到可用的无头浏览器（Edge / Chrome / Chromium）。\n"
        "装一个即可，或把已安装的浏览器路径写进 BROWSER_CANDIDATES。"
    )


def make_workdir(pic_root: Path) -> Path:
    """渲染临时目录放在图片根下，而不是系统临时目录。

    DSH 沙箱会拦截系统临时目录（`%LOCALAPPDATA%\\Temp\\dsh-*`）里的写入，
    放在图片根下则「能写图片的地方就一定能写临时文件」。
    """
    workdir = Path(pic_root) / ".figrender-tmp"
    try:
        workdir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SystemExit(
            f"无法创建渲染临时目录：{workdir}\n{exc}\n"
            "改用 --pic-root <工作区内目录>，或把笔记库设为会话工作区。"
        )
    return workdir


def find_vault(start: Path) -> Path:
    """从笔记路径向上找 .obsidian，返回 vault 根。"""
    cur = start if start.is_dir() else start.parent
    for _ in range(12):
        if (cur / ".obsidian").is_dir():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return start.parent


def resolve_pic_root(vault: Path, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    if (vault / "BaiduSyncdisk").is_dir():
        return vault / "BaiduSyncdisk" / "pic"
    return vault / "pic"


def svg_size(svg_text: str):
    """从 viewBox 或 width/height 提取尺寸。"""
    m = re.search(r'viewBox\s*=\s*"([\d.\-\s]+)"', svg_text, re.I)
    if m:
        parts = [float(x) for x in m.group(1).replace(",", " ").split()]
        if len(parts) == 4 and parts[2] > 0 and parts[3] > 0:
            return int(round(parts[2])), int(round(parts[3]))
    w = re.search(r'\bwidth\s*=\s*"(\d+)"', svg_text, re.I)
    h = re.search(r'\bheight\s*=\s*"(\d+)"', svg_text, re.I)
    if w and h:
        return int(w.group(1)), int(h.group(1))
    return None


def html_size(fragment: str):
    """从 data-w / data-h 提取尺寸。"""
    w = re.search(r'data-w\s*=\s*"(\d+)"', fragment)
    h = re.search(r'data-h\s*=\s*"(\d+)"', fragment)
    if w and h:
        return int(w.group(1)), int(h.group(1))
    return None


def wrap(body_inner: str, w: int, h: int, bg: str, is_svg: bool) -> str:
    svg_css = "svg{display:block;width:100%;height:100%;}" if is_svg else ""
    # SVG 片段常带 width="100%"，这里统一交给 CSS 控制，避免被原属性覆盖
    if is_svg:
        body_inner = re.sub(
            r'(<svg\b[^>]*?)\swidth\s*=\s*"[^"]*"', r"\1", body_inner, count=1, flags=re.I
        )
        body_inner = re.sub(
            r'(<svg\b[^>]*?)\sheight\s*=\s*"[^"]*"', r"\1", body_inner, count=1, flags=re.I
        )
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
html,body{{margin:0;padding:0;background:{bg};}}
body{{width:{w}px;height:{h}px;overflow:hidden;}}
{svg_css}
</style></head>
<body>{body_inner}</body></html>
"""


def shoot(browser: str, html_path: Path, png_path: Path, w: int, h: int,
          scale: int, workdir: Path) -> None:
    """调用浏览器无头模式截图。"""
    profile = workdir / "browserdata"
    cmd = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-first-run",
        "--no-default-browser-check",
        f"--force-device-scale-factor={scale}",
        f"--window-size={w},{h}",
        f"--user-data-dir={profile}",
        f"--screenshot={png_path}",
        html_path.as_uri(),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=90)
    except OSError as exc:
        raise SystemExit(
            f"无法启动浏览器进程：{exc}\n"
            "在 DSH 沙箱里 spawn 浏览器常被拒绝（命名管道 / 临时目录限制）。\n"
            "两个可选做法：\n"
            "  1) 把这条命令原样交给用户在普通终端里执行；\n"
            "  2) 先用 --pic-root <工作区内目录> 出图，确认后再移到笔记库。"
        )
    if not png_path.is_file() or png_path.stat().st_size == 0:
        msg = (proc.stderr or b"").decode("utf-8", "replace")[-800:]
        raise SystemExit(f"截图失败：{png_path}\n{msg}")


def ensure_out_dir(pic_root, note_name) -> Path:
    out_dir = Path(pic_root) / note_name
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SystemExit(
            f"无法创建图片目录：{out_dir}\n{exc}\n"
            "DSH 沙箱默认只允许写会话工作区。把笔记库设为工作区，"
            "或改用 --pic-root <工作区内目录> 先出图。"
        )
    return out_dir


def emit_svg(pic_root, note_name, item):
    """不栅格化，直接把 SVG 放进图片目录。

    Obsidian 原生渲染 `![[x.svg]]`，所以沙箱里跑不起浏览器时这是等效方案：
    尺寸、命名、目录仍由本脚本统一，只是少了「所有主题下像素一致」这一层。
    """
    if "svg" not in item:
        raise SystemExit(f"{item['name']}: --format svg 只支持 --svg 输入")
    src = Path(item["svg"])
    if not src.is_file():
        raise SystemExit(f"找不到 SVG：{src}")
    text = src.read_text(encoding="utf-8", errors="replace")
    auto = svg_size(text)
    w = item.get("width") or (auto[0] if auto else DEFAULT_W)

    out_dir = ensure_out_dir(pic_root, note_name)
    dst = out_dir / f"{item['name']}.svg"
    dst.write_text(text, encoding="utf-8")

    size_kb = dst.stat().st_size / 1024
    print(f"[OK] {dst}  ({w}px 宽, {size_kb:.0f} KB)")
    print(f"     嵌入：![[{note_name}/{item['name']}.svg|{int(w)}]]")
    return dst


def render_one(browser, vault, pic_root, note_name, item, scale, bg, workdir):
    name = item["name"]
    w = item.get("width")
    h = item.get("height")
    is_svg = "svg" in item

    if is_svg:
        src = Path(item["svg"])
        if not src.is_file():
            raise SystemExit(f"找不到 SVG：{src}")
        text = src.read_text(encoding="utf-8", errors="replace")
        auto = svg_size(text)
        body = text
    else:
        raw = item.get("html")
        if raw and Path(raw).is_file():
            body = Path(raw).read_text(encoding="utf-8", errors="replace")
        elif raw:
            body = raw
        else:
            raise SystemExit(f"{name}: 需要 svg 或 html 字段")
        auto = html_size(body)

    if not w or not h:
        if auto:
            w = w or auto[0]
            h = h or auto[1]
        else:
            w = w or DEFAULT_W
            h = h or DEFAULT_H

    html_text = wrap(body, int(w), int(h), item.get("bg", bg), is_svg)
    tmp_html = workdir / f"{name}.html"
    tmp_html.write_text(html_text, encoding="utf-8")

    out_dir = ensure_out_dir(pic_root, note_name)
    png = out_dir / f"{name}.png"

    shoot(browser, tmp_html, png, int(w), int(h), scale, workdir)

    size_kb = png.stat().st_size / 1024
    print(f"[OK] {png}  ({int(w) * scale}x{int(h) * scale}, {size_kb:.0f} KB)")
    print(f"     嵌入：![[{note_name}/{name}.png]]")
    return png


def main():
    _utf8()
    ap = argparse.ArgumentParser(description="SVG/HTML → PNG，并放进笔记图片目录")
    ap.add_argument("--note", help="笔记 md 路径；给 --vault/--root 时可用仓库相对路径")
    ap.add_argument("--vault", help="vaults.json 中的仓库别名（与 --note 相对路径配合）")
    ap.add_argument("--root", help="仓库绝对路径（优先于 --vault）")
    ap.add_argument("--pic-root", help="手动指定 pic 根目录（优先于库内约定）")
    ap.add_argument("--note-name", help="手动指定子目录名（默认取笔记文件名）")
    ap.add_argument("--svg", help="SVG 文件路径")
    ap.add_argument("--html", help="HTML 片段文件路径，或直接给片段字符串")
    ap.add_argument("--name", help="输出图片名（不含后缀），建议 NN-描述性中文名")
    ap.add_argument("--width", type=int, help="CSS 像素宽")
    ap.add_argument("--height", type=int, help="CSS 像素高")
    ap.add_argument("--bg", default=DEFAULT_BG, help=f"背景色，默认 {DEFAULT_BG}")
    ap.add_argument("--scale", type=int, default=2, help="缩放倍数，默认 2（高清）")
    ap.add_argument(
        "--format", choices=("png", "svg"), default="png",
        help="png（默认，需本机浏览器）或 svg（不栅格化，Obsidian 原生渲染；沙箱内出图用）",
    )
    ap.add_argument("--manifest", help="批量 JSON 文件")
    ap.add_argument("--keep-temp", action="store_true", help="保留临时 HTML 供排查")
    args = ap.parse_args()

    if not args.note and not (args.pic_root and args.note_name):
        ap.error("需要 --note，或同时给 --pic-root 与 --note-name")

    # 仓库定位：给了 --vault/--root 时，--note 允许写仓库相对路径
    vault = None
    if args.vault or args.root:
        from vault import resolve_root

        vault = resolve_root(args)
        if args.note:
            cand = Path(args.note)
            if not cand.is_absolute():
                cand = vault / cand
            args.note = str(cand)

    note = Path(args.note) if args.note else None
    note_name = args.note_name or (note.stem if note else None)
    if note:
        # --note 只用来推导「vault + 图片子目录」，不要求笔记已经落盘：
        # 常见顺序是先出图、再写笔记。子目录名取文件名（不含 .md）。
        vault = vault or find_vault(note)
        pic_root = resolve_pic_root(vault, args.pic_root)
    else:
        pic_root = Path(args.pic_root)

    items = []
    if args.manifest:
        items = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    else:
        if not args.name:
            ap.error("单张模式需要 --name")
        item = {"name": args.name}
        if args.svg:
            item["svg"] = args.svg
        elif args.html:
            item["html"] = args.html
        else:
            ap.error("需要 --svg 或 --html")
        if args.width:
            item["width"] = args.width
        if args.height:
            item["height"] = args.height
        items = [item]

    made = []
    print(f"图片目录：{Path(pic_root) / note_name}")
    if args.format == "svg":
        print("输出格式：svg（不栅格化，由 Obsidian 渲染）")
        print()
        for item in items:
            made.append(emit_svg(pic_root, note_name, item))
        print(f"\n完成 {len(made)} 张。")
        return 0

    browser = find_browser()
    workdir = make_workdir(pic_root)
    try:
        print(f"渲染引擎：{browser}")
        print()
        for item in items:
            made.append(
                render_one(browser, vault, pic_root, note_name, item, args.scale,
                           args.bg, workdir)
            )
    finally:
        if not args.keep_temp:
            shutil.rmtree(workdir, ignore_errors=True)
        else:
            print(f"\n临时目录保留在：{workdir}")

    print(f"\n完成 {len(made)} 张。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

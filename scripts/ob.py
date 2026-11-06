#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ob.py — 官方 Obsidian CLI 解析 / 调用 / 降级封装。

只封装 Obsidian 1.12+ 的官方 IPC CLI；不调用语法不同的社区 obsidian-cli。
把「官方 CLI 在哪、能不能用、用不了怎么办」一次性封装掉，供 SKILL.md 中的工作流调用。

只执行 CLI 的瘦转发器（Windows 上是约 20KB 的 `Obsidian.com`）。**绝不执行
`Obsidian.exe`**：那是 200MB+ 的 Electron 主程序，沙箱内启动会在单实例转发之前
就去开 `obsidian.log`，EPERM 直接崩溃（Electron 报错框 + 0x80000003）。

DSH 沙箱纪律：绝不从脚本里拉起 Obsidian GUI。CLI 调用要求 Obsidian 已在运行；
open 默认只打印 URI，把链接交给用户打开。

子命令:
  probe                 探测 CLI 可执行文件并报告可用状态（JSON，要求 Obsidian 已在运行）
  vaults                列出 Obsidian 已注册的仓库（JSON）
  exec                  执行一条官方 CLI 命令（自动在最前面插入 vault= 参数）
  open                  生成 obsidian:// URI（默认只打印；--launch 才拉起 GUI，沙箱内禁用）

退出码:
  0 成功
  3 CLI 不可用（调用方应降级为直接文件操作）
  4 参数错误

示例:
  python ob.py probe
  python ob.py vaults
  python ob.py exec --vault "My Notes" backlinks path="topic/note.md" format=json
  python ob.py open --vault "My Notes" --path "topic/note.md"   # 只打印 URI，交用户打开
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.parse
import webbrowser
from pathlib import Path

DEFAULT_TIMEOUT = 30
NOT_ENABLED_MARK = "Command line interface is not enabled"

SKILL_ROOT = Path(__file__).resolve().parent.parent
VAULTS_JSON = SKILL_ROOT / "vaults.json"


def _utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


# --------------------------------------------------------------------------
# CLI 可执行文件解析
# --------------------------------------------------------------------------

def _app_paths_dir() -> str | None:
    """从 Windows App Paths 注册表读出 Obsidian.exe 的安装目录。"""
    if os.name != "nt":
        return None
    import winreg

    subs = (
        (winreg.HKEY_CURRENT_USER,
         r"Software\Microsoft\Windows\CurrentVersion\App Paths\Obsidian.exe"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"Software\Microsoft\Windows\CurrentVersion\App Paths\Obsidian.exe"),
    )
    for root, sub in subs:
        try:
            with winreg.OpenKey(root, sub) as key:
                return winreg.QueryValue(key, None)
        except OSError:
            continue
    return None


def _is_gui_binary(path: str) -> bool:
    """判断候选是否为 Obsidian GUI 主程序（Windows 上是 ~215MB 的 Electron 本体）。

    沙箱内启动它会走 main.js 初始化、在单实例转发之前就打开 obsidian.log，
    直接 EPERM 崩溃（Electron 弹窗 + 0x80000003）。官方 CLI 在 Windows 上是
    20KB 级的瘦转发器 `Obsidian.com`，**绝不能把 `Obsidian.exe` 当 CLI 调用**。
    """
    return os.path.basename(path).strip().lower() == "obsidian.exe"


def _candidates() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(source: str, path: str | None) -> None:
        if not path:
            return
        key = os.path.normcase(os.path.abspath(path))
        if key in seen:
            return
        seen.add(key)
        found.append((source, path))

    add("env", os.environ.get("OBSIDIAN_CLI") or os.environ.get("COPILOT_OBSIDIAN_CLI"))

    # 只找官方 CLI 的瘦转发器；不带 Obsidian.exe —— GUI 主程序不是 CLI。
    for name in ("obsidian", "Obsidian.com"):
        add(f"PATH:{name}", shutil.which(name))

    if os.name == "nt":
        exe = _app_paths_dir()
        if exe:
            add("AppPaths", os.path.join(os.path.dirname(exe), "Obsidian.com"))
        for directory in (
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Obsidian"),
            os.path.expandvars(r"%LOCALAPPDATA%\Obsidian"),
            r"C:\Program Files\Obsidian",
        ):
            add("known-dir", os.path.join(directory, "Obsidian.com"))
    elif sys.platform == "darwin":
        add("known-dir", "/Applications/Obsidian.app/Contents/MacOS/obsidian")
        add("known-dir", os.path.expanduser("~/Applications/Obsidian.app/Contents/MacOS/obsidian"))
    else:
        add("known-dir", os.path.expanduser("~/.local/bin/obsidian"))
        add("known-dir", "/usr/local/bin/obsidian")

    # 最后一道闸：任何指向 Obsidian.exe 的配置（含 OBSIDIAN_CLI）一律拒绝执行。
    return [(s, p) for s, p in found
            if os.path.exists(p) and not _is_gui_binary(p)]


def resolve_cli(timeout: int = DEFAULT_TIMEOUT) -> dict:
    """按顺序探测候选可执行文件，返回第一个真正可用的。

    注意两点：
    1. 开关未打开时 Obsidian.com 仍会返回退出码 0，只是打印
       “Command line interface is not enabled”，必须把这种情况判为不可用。
    2. 只执行瘦转发器；`Obsidian.exe`（GUI 主程序）在执行前就被拦掉。
    失败时把最后一次探测的实际输出带进 reason，便于排查（沙箱内常见
    “The CLI is unable to find Obsidian”，属命名管道受限导致的正常降级）。
    """
    last_error: str | None = None
    for source, path in _candidates():
        if _is_gui_binary(path):  # 双保险：候选来自 OBSIDIAN_CLI 等外部配置时也拦住
            continue
        try:
            proc = subprocess.run(
                [path, "version"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=timeout, shell=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            last_error = f"{source} 无法执行：{exc}"
            continue
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        if proc.returncode == 0 and NOT_ENABLED_MARK not in out:
            return {
                "available": True,
                "executable": path,
                "source": source,
                "version": out,
            }
        last_error = f"{source} 退出码 {proc.returncode}：{out[:200]}"
    reason = (
        "未找到可用的官方 Obsidian CLI。请在 Obsidian 中打开 "
        "设置 → 通用 → 高级 → Command line interface，"
        "并确认 Obsidian 应用处于运行状态、终端未以管理员身份启动。"
    )
    if last_error:
        reason += f"（最后一次探测：{last_error}）"
    return {
        "available": False,
        "executable": None,
        "source": None,
        "reason": reason,
    }


# --------------------------------------------------------------------------
# 仓库注册表
# --------------------------------------------------------------------------

def obsidian_json_path() -> Path:
    """各平台的 obsidian.json 位置（Obsidian 注册的仓库列表）。"""
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "obsidian" / "obsidian.json"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json"
    return Path.home() / ".config" / "obsidian" / "obsidian.json"


def _norm_path(p: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(p))) if p else ""


def preferred_vault_path() -> str | None:
    """`vaults.json` 的 `default` 别名指向的仓库路径。

    这是「主库」的显式声明，排序时置顶 —— 不依赖 obsidian.json 的键顺序，
    也不依赖 `open` 状态（Obsidian 一关，open 就全变 false）。
    """
    try:
        cfg = json.loads(VAULTS_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    key = cfg.get("default")
    if not key:
        return None
    entry = (cfg.get("vaults") or {}).get(key) or {}
    return entry.get("path") or None


def list_vaults() -> list[dict]:
    """列出 Obsidian 已注册的仓库，按「谁更像主库」排序。

    顺序**不沿用 obsidian.json 里键的书写顺序** —— 那是「在 Obsidian 里添加库的先后」，
    跟「你现在在用哪个库」无关，容易被误当成默认库。排序依据依次为：

      1) `vaults.json` 里 `default` 登记的主库（显式声明，最可靠）
      2) 当前打开的库（`open: true`）
      3) 最后打开时间（`ts`）倒序
      4) 都没有时保持原顺序
    """
    path = obsidian_json_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    preferred = _norm_path(preferred_vault_path() or "")
    out = []
    for vid, meta in (data.get("vaults") or {}).items():
        vpath = meta.get("path", "")
        out.append({
            "id": vid,
            "name": os.path.basename(vpath.rstrip("\\/")),
            "path": vpath,
            "exists": os.path.isdir(vpath),
            "open": bool(meta.get("open")),
            "ts": meta.get("ts", 0),
            "preferred": bool(preferred) and _norm_path(vpath) == preferred,
        })
    out.sort(key=lambda v: (not v["preferred"], not v["open"], -(v["ts"] or 0)))
    return out


def find_vault(name: str) -> dict | None:
    target = name.strip().strip('"').lower()
    for vault in list_vaults():
        if vault["name"].lower() == target or vault["id"].lower() == target:
            return vault
    return None


# --------------------------------------------------------------------------
# 运行态检查（DSH 沙箱纪律：绝不 spawn Obsidian GUI）
# --------------------------------------------------------------------------

NOT_RUNNING_REASON = (
    "Obsidian 未在运行。本脚本不会从沙箱里拉起 GUI——子进程会继承沙箱文件权限，"
    "Obsidian 连自己的日志都写不了（EPERM 崩溃）。请先手动启动 Obsidian 再重试。"
)


def _obsidian_process_alive() -> bool | None:
    """Windows 上用 Toolhelp32 快照检查 Obsidian.exe 进程是否存在。

    不 spawn 任何子进程、不碰管道（沙箱安全）。返回 None 表示查不到/查询失败，
    调用方按未知处理；其他平台同样返回 None。
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        kernel32.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(wintypes.ULONG)),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_wchar * 260),
            ]

        snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS
        if not snapshot or snapshot == ctypes.c_void_p(-1).value:
            return None
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        found = False
        try:
            if kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
                while True:
                    if entry.szExeFile.lower() == "obsidian.exe":
                        found = True
                        break
                    if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                        break
        finally:
            kernel32.CloseHandle(snapshot)
        return found
    except Exception:
        return None


def is_obsidian_running() -> bool:
    """Obsidian 是否已在运行。

    Windows 上以 Toolhelp32 进程快照为准——obsidian.json 的 open 标记在
    崩溃/强杀后会残留 stale true；快照不可用（非 Windows 或探测失败）时
    退回 obsidian.json 的 open 标记。
    """
    alive = _obsidian_process_alive()
    if alive is not None:
        return alive
    return any(v.get("open") for v in list_vaults())


# --------------------------------------------------------------------------
# 子命令
# --------------------------------------------------------------------------

def cmd_probe(args: argparse.Namespace) -> int:
    vaults = list_vaults()
    if not is_obsidian_running():
        info = {
            "available": False,
            "executable": None,
            "source": None,
            "reason": NOT_RUNNING_REASON,
            "vaults": vaults,
        }
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 3
    info = resolve_cli(args.timeout)
    info["vaults"] = vaults
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0 if info["available"] else 3


def cmd_vaults(args: argparse.Namespace) -> int:
    print(json.dumps(list_vaults(), ensure_ascii=False, indent=2))
    return 0


def cmd_exec(args: argparse.Namespace) -> int:
    if not is_obsidian_running():
        print(json.dumps({
            "ok": False,
            "reason": NOT_RUNNING_REASON,
            "action": "fallback_to_filesystem",
        }, ensure_ascii=False, indent=2))
        return 3

    info = resolve_cli(args.timeout)
    if not info["available"]:
        print(json.dumps({
            "ok": False,
            "reason": info["reason"],
            "action": "fallback_to_filesystem",
        }, ensure_ascii=False, indent=2))
        return 3

    argv = [info["executable"]]
    if args.vault:
        # vault= 必须是命令之前的最前一个参数
        argv.append(f"vault={args.vault}")
    argv += args.rest
    if args.format and not any(a.startswith("format=") for a in args.rest):
        argv.append(f"format={args.format}")

    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=args.timeout, shell=False,
        )
    except subprocess.TimeoutExpired:
        print(json.dumps({"ok": False, "reason": "CLI 调用超时",
                          "argv": argv[1:]}, ensure_ascii=False))
        return 3
    except OSError as exc:
        print(json.dumps({"ok": False, "reason": f"无法启动 CLI 进程：{exc}",
                          "argv": argv[1:]}, ensure_ascii=False, indent=2))
        return 3

    payload = {
        "ok": proc.returncode == 0,
        "argv": argv[1:],
        "exit": proc.returncode,
        "stdout": (proc.stdout or "").rstrip("\n"),
        "stderr": (proc.stderr or "").rstrip("\n"),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if proc.returncode == 0 else 3


def cmd_open(args: argparse.Namespace) -> int:
    """生成 obsidian:// URI。默认只打印、不拉起 GUI；--launch 才尝试打开。

    DSH 沙箱下禁止 --launch：os.startfile / webbrowser 从沙箱进程 spawn 出的
    Obsidian.exe 会继承沙箱文件权限，写不了自己的日志（EPERM 崩溃弹窗）。
    """
    if args.abs_path:
        query = {"path": os.path.abspath(args.abs_path)}
    elif args.vault and args.path:
        query = {"vault": args.vault, "path": args.path.lstrip("/")}
    else:
        print("需要 --abs-path，或同时提供 --vault 与 --path", file=sys.stderr)
        return 4

    uri = "obsidian://open?" + urllib.parse.urlencode(query, quote_via=urllib.parse.quote)
    if not args.launch:
        print(json.dumps({
            "ok": True,
            "uri": uri,
            "launched": False,
            "hint": "未拉起 GUI。把 URI 交给用户（粘贴到浏览器地址栏即可打开笔记），"
                    "或让用户自行在 Obsidian 中打开。",
        }, ensure_ascii=False))
        return 0

    try:
        if os.name == "nt":
            os.startfile(uri)  # noqa: S606
        else:
            webbrowser.open(uri)
    except OSError as exc:
        print(json.dumps({"ok": False, "uri": uri, "error": str(exc)},
                         ensure_ascii=False))
        return 3
    print(json.dumps({"ok": True, "uri": uri, "launched": True}, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="官方 Obsidian CLI 封装")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("probe", help="探测 CLI 可用性（要求 Obsidian 已在运行）").set_defaults(func=cmd_probe)
    sub.add_parser("vaults", help="列出已注册仓库").set_defaults(func=cmd_vaults)

    p_exec = sub.add_parser("exec", help="执行官方 Obsidian CLI 命令")
    p_exec.add_argument("--vault", help="仓库名或 ID")
    p_exec.add_argument("--format", help="自动追加 format=<值>")
    p_exec.add_argument("rest", nargs=argparse.REMAINDER,
                        help="CLI 参数，例如 backlinks path=\"a.md\"")
    p_exec.set_defaults(func=cmd_exec)

    p_open = sub.add_parser(
        "open", help="生成 obsidian:// URI（默认只打印；--launch 拉起 GUI，沙箱内禁用）")
    p_open.add_argument("--vault")
    p_open.add_argument("--path")
    p_open.add_argument("--abs-path")
    p_open.add_argument("--print-only", action="store_true",
                        help="已废弃：现在默认只打印 URI，此开关仅为兼容保留")
    p_open.add_argument("--launch", action="store_true",
                        help="尝试拉起 Obsidian GUI（仅限 DSH 沙箱之外使用）")
    p_open.set_defaults(func=cmd_open)
    return parser


def main() -> int:
    _utf8()
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

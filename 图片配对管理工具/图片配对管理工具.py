# -*- coding: utf-8 -*-
"""
图片配对管理工具  IMAGE-TXT MANAGER
------------------------------------
功能一：文件检查 —— 扫描文件夹（含子文件夹），找出"有图片但没有同名 txt"的图片，可一键导出清单。
功能二：文件重命名 —— 先处理所选文件夹本身（如有图片），再递归子文件夹（按名称自然排序先小后大），
                    按"图片 + 同名 txt 一一对应"的逻辑批量重命名（编号/前缀/后缀）。

UI 参考：WHITE AI STUDIO（深色复古棕 / 暖琥珀点缀 / 自定义标题栏）
运行环境：Python 3.8+（tkinter 标准库），无第三方依赖。
"""
import os
import re
import json
import sys
import ctypes
import threading
import shutil
import tkinter as tk
from tkinter import ttk

APP_TITLE = "图片配对管理工具"
APP_SUBTITLE = "IMAGE-TXT MANAGER"

# ---------------- 常量 ----------------
IMAGE_EXTS = {
    ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp",
    ".tif", ".tiff", ".heic", ".heif", ".jfif", ".avif",
}
TXT_EXT = ".txt"
ILLEGAL_CHARS = set('<>:"/\\|?*')

# ---------------- 配色（深色复古棕） ----------------
C_BG        = "#1c1715"
C_PANEL     = "#241e1b"
C_CARD      = "#2a2320"
C_BORDER    = "#3b312c"
C_TEXT      = "#e7dccb"
C_MUTED     = "#a09080"
C_ACCENT    = "#d9a05b"
C_ACCENT_D  = "#b9823f"
C_OK        = "#8fbf7f"
C_WARN      = "#c98f4a"
C_DANGER    = "#c96f5b"
C_SEL       = "#4a3b2f"
C_HOVER     = "#3a2f28"
C_CLOSE     = "#a33a2c"

# 字体（在 App 启动时根据本机已安装字体选择）
FONT_UI = ("Microsoft YaHei UI", 11)
FONT_SMALL = ("Microsoft YaHei UI", 10)
FONT_CAPTION = ("Segoe UI", 8)
FONT_HEAD = ("Microsoft YaHei UI", 12, "bold")
FONT_BIG = ("Segoe UI", 19, "bold")
FONT_TITLE = ("Microsoft YaHei UI", 13, "bold")

_PREFERRED_CN_FONTS = [
    "思源黑体", "HarmonyOS Sans SC", "MiSans", "Source Han Sans CN",
    "Noto Sans CJK SC", "Microsoft YaHei UI", "Microsoft YaHei", "SimHei",
]
_PREFERRED_EN_FONTS = ["Segoe UI", "Microsoft YaHei UI", "思源黑体"]


def _init_fonts(root):
    """按本机已安装字体挑选 UI 字体，并写入模块级常量。"""
    global FONT_UI, FONT_SMALL, FONT_CAPTION, FONT_HEAD, FONT_BIG, FONT_TITLE
    try:
        import tkinter.font as tkfont
        fams = set(tkfont.families(root))
    except Exception:
        fams = set()
    cn = next((f for f in _PREFERRED_CN_FONTS if f in fams), "Microsoft YaHei UI")
    en = next((f for f in _PREFERRED_EN_FONTS if f in fams), "Segoe UI")
    FONT_UI = (cn, 11)
    FONT_SMALL = (cn, 10)
    FONT_CAPTION = (en, 8)
    FONT_HEAD = (cn, 12, "bold")
    FONT_BIG = (en, 19, "bold")
    FONT_TITLE = (cn, 13, "bold")


# ---------------- DPI ----------------
def _get_dpi():
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return max(72, int(dpi))
    except Exception:
        return 96


def _workarea():
    """返回 (left, top, right, bottom) 工作区。"""
    try:
        class RECT(ctypes.Structure):
            _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                        ("r", ctypes.c_long), ("b", ctypes.c_long)]
        r = RECT()
        ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)
        if r.r > r.l and r.b > r.t:
            return (r.l, r.t, r.r, r.b)
    except Exception:
        pass
    try:
        wa = (0, 0, ctypes.windll.user32.GetSystemMetrics(0),
              ctypes.windll.user32.GetSystemMetrics(1))
        return wa
    except Exception:
        return (0, 0, 1920, 1080)


# ---------------- 核心逻辑 ----------------
def natural_key(s):
    """自然排序键：'2' < '10'，且不区分大小写。"""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]


def iter_dirs(root):
    """返回 root 自身 + 所有子文件夹（深度优先、每层按名称自然排序）。"""
    dirs = [root]
    for base, subdirs, _ in os.walk(root):
        subdirs.sort(key=natural_key)
        for sd in subdirs:
            dirs.append(os.path.join(base, sd))
    return dirs


def list_dir_files(d):
    """
    返回 (图片字典, txt字典)。键为"去扩展名后的小写化文件名"（Windows 文件名不区分大小写，
    因此 PHOTO.jpg 与 photo.txt 视为同名配对），值为磁盘上的真实文件名。
    注：同一文件夹内若存在"同名但扩展名不同"的多张图片（如 a.jpg 与 a.png），
    字典只保留最后读取到的一个；属于设计限制，正常素材不会出现。
    """
    imgs = {}
    txts = {}
    try:
        names = os.listdir(d)
    except OSError:
        return imgs, txts
    for name in names:
        if name.startswith(".__pairtmp_"):
            continue   # 内部临时文件（重命名中断残留），不作为普通图片/txt 参与扫描
        p = os.path.join(d, name)
        if not os.path.isfile(p):
            continue
        stem, ext = os.path.splitext(name)
        ext = ext.lower()
        if ext in IMAGE_EXTS:
            imgs[stem.casefold()] = name
        elif ext == TXT_EXT:
            txts[stem.casefold()] = name
    return imgs, txts


def scan_missing(root):
    """
    扫描 root（含所有子文件夹），返回：
      missing: [(文件夹, 图片文件名), ...]  图片存在但同目录无同名 txt
      stats  : dict(dirs, imgs, txts, missing)
    """
    missing = []
    stats = {"dirs": 0, "imgs": 0, "txts": 0}
    for d in iter_dirs(root):
        imgs, txts = list_dir_files(d)
        stats["dirs"] += 1
        stats["imgs"] += len(imgs)
        stats["txts"] += len(txts)
        for stem in sorted(imgs, key=natural_key):
            if stem not in txts:
                missing.append((d, imgs[stem]))
    stats["missing"] = len(missing)
    return missing, stats


def validate_options(start, digits, prefix, suffix):
    """校验重命名选项，返回 (错误信息 or None)。"""
    if start < 0:
        return "起始编号不能为负数"
    if digits < 1 or digits > 12:
        return "编号位数需在 1 ~ 12 之间"
    bad = ILLEGAL_CHARS & set(prefix) or ILLEGAL_CHARS & set(suffix)
    if bad:
        return "前缀/后缀包含非法字符：" + " ".join(sorted(bad))
    if prefix + suffix == "":
        return "前缀和后缀不能同时为空（否则文件名只剩编号）"
    return None


def build_plan(root, start, digits, prefix, suffix):
    """
    生成重命名方案。
    规则：
      1) 先处理所选文件夹本身（如有图片）；再递归所有子文件夹，
         子文件夹按名称自然排序、先小后大（2 排在 10 前面）。
      2) 每个文件夹内，图片按名称自然排序逐个编号；编号全局连续，跨文件夹不重置。
      3) 同名 txt 与图片一一对应：图片改名，配套 txt 用同一新名。
      4) 不改变扩展名。
    返回 (rows, summary)。
      rows: [{folder, kind, old_name, new_name, status}]
      status: ok / same / conflict
    """
    imgs_top, _ = list_dir_files(root)
    has_top = bool(imgs_top)
    folders = iter_dirs(root)

    rows = []
    num = start
    n_folders_with_imgs = 0
    for d in folders:
        imgs, txts = list_dir_files(d)
        if not imgs:
            continue
        n_folders_with_imgs += 1
        # 该文件夹内"将被改走"的旧文件名集合（用于判断目标名是否会被腾空）。
        # 只有配对了图片的 txt 才会被改走；孤儿 txt 不会动，属于冲突源。
        old_img_names = set(imgs.values())
        old_txt_names = {txts[k] for k in txts if k in imgs}

        for stem in sorted(imgs, key=natural_key):
            old_img = imgs[stem]
            new_base = prefix + str(num).zfill(digits) + suffix
            new_img = new_base + os.path.splitext(old_img)[1]   # 保留原扩展名（含大小写）
            has_txt = stem in txts
            old_txt = txts[stem] if has_txt else None
            new_txt = new_base + TXT_EXT

            # 图片、txt 先各自判定状态
            if new_img == old_img:
                img_st = "same"
            elif os.path.exists(os.path.join(d, new_img)) and new_img not in old_img_names:
                img_st = "conflict"
            else:
                img_st = "ok"

            if has_txt:
                if new_txt == old_txt:
                    txt_st = "same"
                elif os.path.exists(os.path.join(d, new_txt)) and new_txt not in old_txt_names:
                    txt_st = "conflict"
                else:
                    txt_st = "ok"
                # 配对完整性：图片与配套 txt 必须同进同退。
                # 任一方 conflict 而另一方 ok 时，把 ok 的一方也标记为 conflict，
                # 防止执行后"图片改了名、txt 没跟上"导致一一对应被破坏。
                if img_st == "ok" and txt_st == "conflict":
                    img_st = "conflict"
                elif txt_st == "ok" and img_st == "conflict":
                    txt_st = "conflict"
            else:
                txt_st = None

            rows.append({"folder": d, "kind": "图片", "old_name": old_img,
                         "new_name": new_img, "status": img_st})
            if has_txt:
                rows.append({"folder": d, "kind": "TXT", "old_name": old_txt,
                             "new_name": new_txt, "status": txt_st})
            num += 1

    n_ok_img = sum(1 for r in rows if r["kind"] == "图片" and r["status"] == "ok")
    n_ok_txt = sum(1 for r in rows if r["kind"] == "TXT" and r["status"] == "ok")
    n_skip = sum(1 for r in rows if r["status"] != "ok")
    summary = {
        "folders": n_folders_with_imgs,
        "has_top": has_top,
        "images": sum(1 for r in rows if r["kind"] == "图片"),
        "txts": sum(1 for r in rows if r["kind"] == "TXT"),
        "ren_img": n_ok_img,
        "ren_txt": n_ok_txt,
        "skip": n_skip,
    }
    return rows, summary


def _unique_temp_name(d, base):
    i = 0
    while True:
        cand = os.path.join(d, f".__pairtmp_{i}__{base}")
        if not os.path.exists(cand):
            return cand
        i += 1


_TMP_PREFIX_RE = re.compile(r"^\.__pairtmp_\d+__(.+)$")


def cleanup_pairtmp(root, progress_cb=None):
    """
    恢复上次重命名中断残留的内部临时文件（. __pairtmp_N__新名）。
    临时名 = 前缀 + 最终名，因此去掉前缀即可恢复为最终名（如
    .__pairtmp_0__000001.jpg → 000001.jpg）。
    返回 (恢复数量, 失败列表)。App 启动时与每次执行重命名前调用。
    """
    restored = 0
    failures = []
    dirs = iter_dirs(root)
    total_dirs = len(dirs)
    done = 0
    for d in dirs:
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for name in names:
            m = _TMP_PREFIX_RE.match(name)
            if not m:
                continue
            target = m.group(1)
            src_abs = os.path.join(d, name)
            tgt_abs = os.path.join(d, target)
            if os.path.exists(tgt_abs):
                failures.append((src_abs, f"恢复目标已存在：{target}"))
                continue
            try:
                os.rename(src_abs, tgt_abs)
                restored += 1
            except OSError as e:
                failures.append((src_abs, str(e)))
        done += 1
        if progress_cb:
            progress_cb(done, total_dirs)
    return restored, failures


def execute_plan(rows, progress_cb=None):
    """
    执行重命名：只处理 status == 'ok' 的行。
    采用两阶段（先改临时名，再改最终名），避免任何中间冲突/覆盖。
    防御：
      - 目标名已被占用且不会被本计划腾空 → 该行跳过（文件保持原名，不执行）。
      - 第二阶段（临时名→最终名）失败 → 回滚恢复原文件名，绝不让文件残留在临时名。
    进度回调签名：progress_cb(done, total, phase)，phase=1 为腾名阶段、2 为定名阶段，
    done 始终不超过 total（每个阶段各自从 0 计到 total）。
    返回 (success_count, failures)
    """
    ops = []
    for r in rows:
        if r["status"] != "ok":
            continue
        ops.append((r["folder"], r["old_name"], r["new_name"]))

    total = len(ops)
    failures = []

    # 本计划中"将改走"的旧文件绝对路径集合：这些文件会先被改成临时名腾出目标名，
    # 因此目标名撞上它们才是安全的；撞上其他文件则跳过。
    will_move = {os.path.join(folder, old) for folder, old, _ in ops}

    # ---- 阶段 1：全部改成临时名（腾出目标名，避免中间冲突） ----
    done = 0
    temp_pairs = []
    for folder, old, new in ops:
        old_abs = os.path.join(folder, old)
        target = os.path.join(folder, new)
        if os.path.exists(target) and target not in will_move:
            failures.append((old_abs, f"目标文件已存在且不会腾出：{new}"))
            done += 1
            if progress_cb:
                progress_cb(done, total, 1)
            continue
        tmp = _unique_temp_name(folder, new)
        try:
            os.rename(old_abs, tmp)
            temp_pairs.append((folder, old, tmp, new))
        except OSError as e:
            failures.append((old_abs, str(e)))
        done += 1
        if progress_cb:
            progress_cb(done, total, 1)

    # ---- 阶段 2：临时名改成最终名（失败则回滚原名） ----
    for i, (folder, old, tmp, new) in enumerate(temp_pairs, 1):
        try:
            os.rename(tmp, os.path.join(folder, new))
        except OSError as e:
            failures.append((os.path.join(folder, new), str(e)))
            # 回滚：恢复原文件名，避免文件残留在临时名
            try:
                os.rename(tmp, os.path.join(folder, old))
            except OSError:
                pass
        if progress_cb:
            progress_cb(i, total, 2)

    return total - len(failures), failures


def export_missing(missing, path):
    """导出缺失清单：每个完整路径一行（UTF-8 with BOM，兼容记事本）。"""
    with open(path, "w", encoding="utf-8-sig", newline="\n") as f:
        for d, name in missing:
            f.write(os.path.join(d, name) + "\n")
    return len(missing)


# ---------------- 批量复制（读取 TXT 清单 → 复制文件） ----------------
def read_txt_any_encoding(path):
    """读取文本文件，自动识别编码（UTF-8 BOM / UTF-8 / GBK）。"""
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("gbk", errors="replace")


def parse_paths_from_txt(text):
    """
    从清单文本中解析路径列表。每行一个路径，兼容：
      - 纯路径
      - 带引号（如文件资源管理器复制出来的 "F:\\xx\\a.jpg"）
      - 含制表符的导出格式（取制表符前部分）
      - 空行、以 # 或 // 开头的注释行
    """
    paths = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#") or line.startswith("//"):
            continue
        if "\t" in line:
            line = line.split("\t", 1)[0]
        line = line.strip().strip('"').strip()
        if not line:
            continue
        paths.append(line)
    return paths


def load_paths_from_txts(txt_paths):
    """读取一个或多个 TXT 清单，返回 (路径列表, [(文件, 错误)])。"""
    paths = []
    read_errors = []
    for tp in txt_paths:
        try:
            text = read_txt_any_encoding(tp)
            paths.extend(parse_paths_from_txt(text))
        except OSError as e:
            read_errors.append((tp, str(e)))
    return paths, read_errors


def _unique_dest(dest, base):
    """目标已存在同名时生成 '名称 (n).扩展名'。"""
    stem, ext = os.path.splitext(base)
    i = 1
    while True:
        cand = os.path.join(dest, f"{stem} ({i}){ext}")
        if not os.path.exists(cand):
            return cand
        i += 1


def copy_files(paths, dest, on_dup="rename", progress_cb=None):
    """
    将 paths 中的文件复制到 dest。
    on_dup: "rename"=同名自动加序号 / "skip"=同名跳过（绝不覆盖）。
    返回统计 dict。
    """
    copied = renamed = skipped = 0
    invalid = []
    failed = []
    total = len(paths)
    done = 0
    for p in paths:
        if not os.path.isfile(p):
            invalid.append(p)
            done += 1
            if progress_cb:
                progress_cb(done, total)
            continue
        base = os.path.basename(p)
        target = os.path.join(dest, base)
        if os.path.exists(target):
            if on_dup == "skip":
                skipped += 1
                done += 1
                if progress_cb:
                    progress_cb(done, total)
                continue
            target = _unique_dest(dest, base)
        try:
            shutil.copy2(p, target)
            if target != os.path.join(dest, base):
                renamed += 1
            else:
                copied += 1
        except OSError as e:
            failed.append((p, str(e)))
        done += 1
        if progress_cb:
            progress_cb(done, total)
    return {"copied": copied, "renamed": renamed, "skipped": skipped,
            "invalid": invalid, "failed": failed}


# ---------------- GUI ----------------
def make_button(parent, text, command, kind="secondary", font=None):
    """自制扁平按钮：primary=琥珀实底，secondary=深色描边。"""
    if kind == "primary":
        bg, fg, abg, afg = C_ACCENT, "#1c1715", C_ACCENT_D, "#1c1715"
    else:
        bg, fg, abg, afg = C_PANEL, C_TEXT, C_SEL, C_TEXT
    return tk.Button(
        parent, text=text, command=command, font=font or FONT_UI,
        bg=bg, fg=fg, activebackground=abg, activeforeground=afg,
        relief="flat", bd=0, padx=16, pady=7, cursor="hand2",
        highlightthickness=1, highlightbackground=C_BORDER,
        highlightcolor=C_BORDER,
    )


class DarkDialog(tk.Toplevel):
    """深色模态对话框：自定义标题栏（可拖动），整体深色，替换原生白色弹窗。
    f 为 DPI 缩放系数：窗口尺寸按 f 放大，避免字体（已按 tk scaling 放大）溢出窗口。"""

    def __init__(self, parent, title, w, h, f=1.0):
        super().__init__(parent)
        self.configure(bg=C_BG)
        self.overrideredirect(True)
        self._result = None
        self._drag = None
        self._f = max(1.0, f)
        w2, h2 = max(320, round(w * self._f)), max(240, round(h * self._f))

        bar = tk.Frame(self, bg=C_PANEL, height=max(34, round(34 * self._f)))
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text=title, bg=C_PANEL, fg=C_TEXT, font=FONT_SMALL).pack(side="left", padx=12)
        self._close_btn = tk.Button(bar, text="✕", command=self._cancel, font=("Segoe UI", 11),
                                    bg=C_PANEL, fg=C_TEXT, activebackground=C_CLOSE,
                                    activeforeground=C_TEXT, relief="flat", bd=0, width=5,
                                    cursor="hand2", takefocus=0)
        self._close_btn.pack(side="right", fill="y")
        bar.bind("<Button-1>", self._bar_press)
        bar.bind("<B1-Motion>", self._bar_move)

        self.body = tk.Frame(self, bg=C_BG)
        self.body.pack(fill="both", expand=True,
                       padx=max(14, round(18 * self._f)),
                       pady=(max(8, round(10 * self._f)), max(12, round(14 * self._f))))

        self.update_idletasks()
        try:
            px, py, pw, ph = (parent.winfo_rootx(), parent.winfo_rooty(),
                              parent.winfo_width(), parent.winfo_height())
            x = px + (pw - w2) // 2
            y = py + (ph - h2) // 2
            x = max(0, min(x, parent.winfo_screenwidth() - w2 - 8))
            y = max(0, min(y, parent.winfo_screenheight() - h2 - 8))
            self.geometry(f"{w2}x{h2}+{x}+{y}")
        except Exception:
            self.geometry(f"{w2}x{h2}")
        self.transient(parent)
        self.grab_set()
        self.focus_force()
        self.lift()
        # 点击弹窗时确保其在前（但不全局置顶，避免挡住其他应用）
        self.bind("<FocusIn>", lambda e: self.lift())
        # 维护父窗口的对话框计数，供主窗口在有弹窗打开时不抢 Z 序（防遮挡双保险）
        try:
            parent._dlg_count = getattr(parent, "_dlg_count", 0) + 1

            def _dec(e):
                if e.widget is self:
                    parent._dlg_count = max(0, parent._dlg_count - 1)
            self.bind("<Destroy>", _dec)
        except Exception:
            pass

    def _bar_press(self, e):
        self._drag = (e.x_root - self.winfo_x(), e.y_root - self.winfo_y())

    def _bar_move(self, e):
        if self._drag:
            self.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")

    def _cancel(self):
        self._result = None
        self.destroy()

    def _finish(self, value):
        self._result = value
        self.destroy()

    def run(self):
        self.wait_window()
        return self._result


def _dialog_buttons(dialog, ok_text, cancel_text):
    """深色对话框底部按钮条，返回 (确定按钮, 取消按钮)。
    固定贴在窗口底部（side='bottom'）：即使上方内容区（如文件树）占用全部高度，
    确定/取消也始终可见，不会被挤出窗口。"""
    row = tk.Frame(dialog.body, bg=C_BG)
    row.pack(side="bottom", fill="x", pady=(12, 0))
    btn_ok = make_button(row, ok_text, None, kind="primary")
    btn_ok.pack(side="right")
    btn_cancel = None
    if cancel_text:
        btn_cancel = make_button(row, cancel_text, None)
        btn_cancel.pack(side="right", padx=(0, 10))
    return btn_ok, btn_cancel


def list_drives():
    """返回本机所有可访问的盘符，如 ['C:\\', 'D:\\', ...]。"""
    drives = []
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        p = f"{letter}:\\"
        try:
            if os.path.exists(p):
                drives.append(p)
        except Exception:
            pass
    return drives or ["C:\\"]


DRIVES_SENTINEL = "::DRIVES::"


def _paste_menu(widget):
    """给输入框添加右键菜单（粘贴/复制/全选）。Ctrl+V 系统自带，无需重复绑定。"""
    try:
        menu = tk.Menu(widget, tearoff=0)
    except Exception:
        return

    def popup(e):
        try:
            menu.delete(0, "end")
            menu.add_command(label="粘贴", command=lambda: widget.event_generate("<<Paste>>"))
            menu.add_command(label="复制", command=lambda: widget.event_generate("<<Copy>>"))
            menu.add_command(label="全选", command=lambda: widget.event_generate("<<SelectAll>>"))
            menu.tk_popup(e.x_root, e.y_root)
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass

    widget.bind("<Button-3>", popup)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self._dpi = _get_dpi()
        self._f = self._dpi / 96.0
        try:
            self.tk.call("tk", "scaling", self._dpi / 72.0)
        except Exception:
            pass
        _init_fonts(self)

        self.title(f"{APP_TITLE} · {APP_SUBTITLE}")
        self.configure(bg=C_BG)
        self._cfg = self._load_cfg()
        self._check_rows = []
        self._plan_rows = []
        self._busy = False

        # 窗口尺寸：随 DPI 缩放，并限制在工作区内
        wa = _workarea()
        wa_w, wa_h = wa[2] - wa[0], wa[3] - wa[1]
        base_w, base_h = 1280, 840
        self._win_w = min(round(base_w * self._f), max(wa_w - 20, 900))
        self._win_h = min(round(base_h * self._f), max(wa_h - 20, 620))
        self._min_w = min(round(1060 * self._f), wa_w - 20)
        self._min_h = min(round(680 * self._f), wa_h - 20)
        self.geometry(f"{self._win_w}x{self._win_h}+{(wa_w - self._win_w) // 2}+{(wa_h - self._win_h) // 2}")

        # 自定义标题栏（去掉系统白边，但保留任务栏按钮）
        self._frameless()
        self._maximized = False
        self._prev_geo = None
        self._drag = None
        self._resize = None
        self._title_buttons = set()

        self._set_window_icon()
        self._build_styles()
        self._build_title_bar()
        self._build_tabs()
        self._build_check_tab()
        self._build_rename_tab()
        self._build_copy_tab()
        self._show_tab("check")
        self._apply_cfg_to_ui()

        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_motion)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Double-Button-1>", self._on_double)
        self.bind("<Motion>", self._on_hover)
        self.bind("<Alt-F4>", lambda e: self._on_close())
        self.bind("<Map>", self._on_map)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(120, self._focus_and_lift)
        self.after(400, self._recover_pairtmp)

    def _recover_pairtmp(self):
        """启动时恢复上次重命名中断残留的临时文件（去前缀即最终名）。"""
        for key in ("last_folder_rn", "last_folder"):
            p = (self._cfg.get(key) or "").strip().strip('"')
            if not p or not os.path.isdir(p):
                continue
            try:
                restored, fails = cleanup_pairtmp(p)
                if restored:
                    msg = f"检测到上次重命名中断，已自动恢复 {restored} 个文件为最终名。"
                    if fails:
                        msg += f"\n{len(fails)} 个无法恢复：目标名已被占用。"
                    self._msg("已恢复上次中断", msg, "info")
                break
            except Exception:
                break

    # ---------- 样式（必须调用，否则 ttk 控件会渲染成默认白色） ----------
    def _build_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Treeview", background=C_CARD, fieldbackground=C_CARD,
                        foreground=C_TEXT, borderwidth=0,
                        rowheight=max(26, round(34 * self._f)),
                        font=FONT_SMALL, relief="flat")
        style.configure("Treeview.Heading", background=C_PANEL, foreground=C_MUTED,
                        borderwidth=0, relief="flat",
                        font=("Microsoft YaHei UI", 9, "bold"),
                        padding=(6, 6))
        style.map("Treeview",
                  background=[("selected", C_SEL)],
                  foreground=[("selected", C_TEXT)])
        style.map("Treeview.Heading", background=[("active", C_PANEL)])
        style.configure("Vertical.TScrollbar", background=C_PANEL, troughcolor=C_BG,
                        bordercolor=C_BG, arrowcolor=C_MUTED, relief="flat")
        style.configure("TEntry", fieldbackground=C_PANEL, foreground=C_TEXT,
                        bordercolor=C_BORDER, insertcolor=C_TEXT, padding=6)
        style.configure("TCombobox", fieldbackground=C_PANEL, background=C_PANEL,
                        foreground=C_TEXT, arrowcolor=C_MUTED, bordercolor=C_BORDER,
                        padding=6)
        style.map("TCombobox",
                  fieldbackground=[("readonly", C_PANEL)],
                  selectbackground=[("readonly", C_PANEL)],
                  selectforeground=[("readonly", C_TEXT)],
                  foreground=[("readonly", C_TEXT)],
                  background=[("readonly", C_PANEL)])
        try:
            self.option_add("*TCombobox*Listbox.background", C_PANEL)
            self.option_add("*TCombobox*Listbox.foreground", C_TEXT)
            self.option_add("*TCombobox*Listbox.selectBackground", C_SEL)
            self.option_add("*TCombobox*Listbox.selectForeground", C_TEXT)
        except Exception:
            pass

    # ---------- 配置 ----------
    def _cfg_path(self):
        base = os.path.dirname(os.path.abspath(sys.argv[0]))
        return os.path.join(base, "pairtool_config.json")

    def _load_cfg(self):
        try:
            with open(self._cfg_path(), "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_cfg(self):
        def safe_int(var, default):
            try:
                return int(var.get())
            except Exception:
                return default
        cfg = {
            "last_folder": self.var_check_folder.get(),
            "last_folder_rn": self.var_rn_folder.get(),
            "start": safe_int(self.var_start, 1),
            "digits": safe_int(self.var_digits, 6),
            "prefix": self.var_prefix.get(),
            "suffix": self.var_suffix.get(),
        }
        try:
            with open(self._cfg_path(), "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _apply_cfg_to_ui(self):
        if self._cfg.get("last_folder"):
            self.var_check_folder.set(self._cfg["last_folder"])
        if self._cfg.get("last_folder_rn"):
            self.var_rn_folder.set(self._cfg["last_folder_rn"])
        try:
            self.var_start.set(int(self._cfg.get("start", 1)))
        except Exception:
            self.var_start.set(1)
        try:
            self.var_digits.set(int(self._cfg.get("digits", 6)))
        except Exception:
            self.var_digits.set(6)
        self.var_prefix.set(self._cfg.get("prefix", ""))
        self.var_suffix.set(self._cfg.get("suffix", ""))

    # ---------- 图标 ----------
    def _set_window_icon(self):
        base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(sys.argv[0]))
        try:
            img32 = tk.PhotoImage(file=os.path.join(base, "icon_win_32.png"))
            img256 = tk.PhotoImage(file=os.path.join(base, "icon_win_256.png"))
            self.iconphoto(True, img32, img256)
            self._icon32, self._icon256 = img32, img256  # 防止被回收
        except Exception:
            pass

    # ---------- 自定义标题栏 ----------
    def _build_title_bar(self):
        self._bar_h = max(40, int(46 * self._f))
        bar = tk.Frame(self, bg=C_PANEL, height=self._bar_h, highlightthickness=0)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        tk.Frame(bar, bg=C_ACCENT, width=3).pack(side="left", fill="y", padx=(16, 10))
        col = tk.Frame(bar, bg=C_PANEL)
        col.pack(side="left")
        tk.Label(col, text=APP_TITLE, bg=C_PANEL, fg=C_TEXT, font=FONT_TITLE).pack(anchor="w")
        tk.Label(col, text=APP_SUBTITLE, bg=C_PANEL, fg=C_MUTED, font=FONT_CAPTION).pack(anchor="w")

        btns = tk.Frame(bar, bg=C_PANEL)
        btns.pack(side="right", fill="y")
        specs = [("—", self._minimize, "最小化"),
                 ("□", self._toggle_max, "最大化"),
                 ("✕", self._on_close, "关闭")]
        for glyph, cmd, tip in specs:
            b = tk.Button(btns, text=glyph, command=cmd, font=("Segoe UI", 12),
                          bg=C_PANEL, fg=C_TEXT, activebackground=C_HOVER,
                          activeforeground=C_TEXT, relief="flat", bd=0,
                          width=5, cursor="hand2", takefocus=0)
            if tip == "关闭":
                b.config(activebackground=C_CLOSE)
            b.pack(side="left", fill="y", padx=1)
            self._title_buttons.add(str(b))
        self._max_btn = btns.winfo_children()[-2]

        tk.Label(bar, text="本地工具 · 文件不离开你的电脑", bg=C_PANEL, fg=C_MUTED,
                 font=FONT_SMALL).pack(side="right", padx=(0, 14))

    def _minimize(self):
        self.iconify()

    def _toggle_max(self):
        wa = _workarea()
        wa_w, wa_h = wa[2] - wa[0], wa[3] - wa[1]
        if self._maximized:
            self.geometry(self._prev_geo or f"{self._win_w}x{self._win_h}")
            self._maximized = False
        else:
            self._prev_geo = self.geometry()
            self.geometry(f"{wa_w}x{wa_h}+{wa[0]}+{wa[1]}")
            self._maximized = True
        self._max_btn.config(text="❐" if self._maximized else "□")

    def _on_map(self, e):
        if self.state() == "normal":
            self.after(10, self._frameless)
            # 有弹窗打开时不要 lift 抢层级，避免把弹窗盖到身后
            if getattr(self, "_dlg_count", 0) == 0:
                self.after(40, self.lift)

    def _focus_and_lift(self):
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _frameless(self):
        """去掉系统标题栏但保留任务栏按钮：直接修改 Win32 窗口样式，
        而不是用 overrideredirect（后者会让窗口没有任务栏图标、失焦后无法找回）。
        窗口始终是普通顶层窗口：任务栏有按钮、可最小化恢复、可 Alt+Tab。"""
        try:
            hwnd = ctypes.windll.user32.GetAncestor(self.winfo_id(), 2)  # GA_ROOT
            GWL_STYLE = -16
            WS_CAPTION = 0x00C00000
            WS_THICKFRAME = 0x00040000
            WS_SYSMENU = 0x00080000
            WS_MINIMIZEBOX = 0x00020000
            WS_MAXIMIZEBOX = 0x00010000
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
            style &= ~(WS_CAPTION | WS_THICKFRAME | WS_SYSMENU |
                       WS_MINIMIZEBOX | WS_MAXIMIZEBOX)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style)
            flags = 0x0001 | 0x0002 | 0x0010 | 0x0020 | 0x0040  # NOSIZE|NOMOVE|NOACTIVATE|FRAMECHANGED|SHOWWINDOW
            if getattr(self, "_dlg_count", 0) > 0:
                flags |= 0x0004   # SWP_NOZORDER：有弹窗打开时不改变 Z 序，避免盖住弹窗
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, flags)
        except Exception:
            pass

    def _edge_zone(self, x, y):
        if self._maximized:
            return None
        w, h = self.winfo_width(), self.winfo_height()
        m = max(5, int(5 * self._f))
        top, bot = y < m, y > h - m
        left, right = x < m, x > w - m
        if top and left: return "nw"
        if top and right: return "ne"
        if bot and left: return "sw"
        if bot and right: return "se"
        if top: return "n"
        if bot: return "s"
        if left: return "w"
        if right: return "e"
        return None

    def _on_press(self, e):
        if self._maximized:
            return
        wid = str(e.widget)
        if wid in self._title_buttons:
            return
        x = e.x_root - self.winfo_rootx()
        y = e.y_root - self.winfo_rooty()
        z = self._edge_zone(x, y)
        if z:
            self._resize = (z, e.x_root, e.y_root,
                            self.winfo_x(), self.winfo_y(),
                            self.winfo_width(), self.winfo_height())
            return
        if 0 <= y < self._bar_h:
            self._drag = (e.x_root, e.y_root, self.winfo_x(), self.winfo_y())

    def _on_motion(self, e):
        if self._resize:
            self._do_resize(e.x_root, e.y_root)
        elif self._drag:
            gx = self._drag[2] + (e.x_root - self._drag[0])
            gy = self._drag[3] + (e.y_root - self._drag[1])
            self.geometry(f"+{gx}+{gy}")

    def _do_resize(self, cx, cy):
        zone, sx, sy, gx, gy, gw, gh = self._resize
        dx, dy = cx - sx, cy - sy
        mw, mh = self._min_w, self._min_h
        nw, nh, nx, ny = gw, gh, gx, gy
        if "e" in zone:
            nw = max(mw, gw + dx)
        if "s" in zone:
            nh = max(mh, gh + dy)
        if "w" in zone:
            nw = max(mw, gw - dx)
            nx = gx + gw - nw
        if "n" in zone:
            nh = max(mh, gh - dy)
            ny = gy + gh - nh
        self.geometry(f"{nw}x{nh}+{nx}+{ny}")

    def _on_release(self, e):
        self._resize = None
        self._drag = None

    def _on_double(self, e):
        if self._maximized:
            return
        if str(e.widget) in self._title_buttons:
            return
        y = e.y_root - self.winfo_rooty()
        if 0 <= y < self._bar_h:
            self._toggle_max()

    def _on_hover(self, e):
        if self._maximized or self._resize or self._drag:
            return
        x = e.x_root - self.winfo_rootx()
        y = e.y_root - self.winfo_rooty()
        z = self._edge_zone(x, y)
        cursors = {"n": "sb_v_double_arrow", "s": "sb_v_double_arrow",
                   "e": "sb_h_double_arrow", "w": "sb_h_double_arrow",
                   "ne": "size_ne_sw_cursor", "sw": "size_ne_sw_cursor",
                   "nw": "size_nw_se_cursor", "se": "size_nw_se_cursor"}
        cur = cursors.get(z, "")
        if cur != getattr(self, "_last_cursor", None):
            self._last_cursor = cur
            try:
                self.configure(cursor=cur)
            except Exception:
                pass

    # ---------- 页签 ----------
    def _build_tabs(self):
        self.tab_bar = tk.Frame(self, bg=C_BG)
        self.tab_bar.pack(fill="x", padx=18, pady=(14, 0))
        self.tab_check_btn = tk.Button(
            self.tab_bar, text="文件检查", font=FONT_HEAD,
            command=lambda: self._show_tab("check"), cursor="hand2", relief="flat", bd=0)
        self.tab_rename_btn = tk.Button(
            self.tab_bar, text="文件重命名", font=FONT_HEAD,
            command=lambda: self._show_tab("rename"), cursor="hand2", relief="flat", bd=0)
        self.tab_copy_btn = tk.Button(
            self.tab_bar, text="批量复制", font=FONT_HEAD,
            command=lambda: self._show_tab("copy"), cursor="hand2", relief="flat", bd=0)
        self.tab_check_btn.pack(side="left", padx=(0, 22))
        self.tab_rename_btn.pack(side="left", padx=(0, 22))
        self.tab_copy_btn.pack(side="left")

        self.body = tk.Frame(self, bg=C_BG)
        self.body.pack(fill="both", expand=True, padx=18, pady=(8, 14))
        self.frame_check = tk.Frame(self.body, bg=C_BG)
        self.frame_rename = tk.Frame(self.body, bg=C_BG)
        self.frame_copy = tk.Frame(self.body, bg=C_BG)

    def _show_tab(self, which):
        for fr in (self.frame_check, self.frame_rename, self.frame_copy):
            fr.pack_forget()
        btns = {"check": self.tab_check_btn, "rename": self.tab_rename_btn,
                "copy": self.tab_copy_btn}
        for key, b in btns.items():
            b.config(fg=C_ACCENT if key == which else C_MUTED,
                     bg=C_BG, activebackground=C_BG)
        frame = {"check": self.frame_check, "rename": self.frame_rename,
                 "copy": self.frame_copy}[which]
        frame.pack(fill="both", expand=True)

    # ---------- 通用控件 ----------
    @staticmethod
    def _section_label(parent, text, caption):
        wrap = tk.Frame(parent, bg=C_BG)
        wrap.pack(fill="x", pady=(4, 8))
        tk.Label(wrap, text=text, bg=C_BG, fg=C_TEXT, font=FONT_HEAD).pack(side="left")
        tk.Label(wrap, text="  " + caption, bg=C_BG, fg=C_MUTED,
                 font=FONT_CAPTION).pack(side="left", pady=(3, 0))
        return wrap

    def _card(self, parent):
        f = tk.Frame(parent, bg=C_CARD, highlightthickness=1,
                     highlightbackground=C_BORDER, highlightcolor=C_BORDER)
        return f

    @staticmethod
    def _auto_wrap(label):
        def _fit(e):
            try:
                label.config(wraplength=max(200, e.width - 8))
            except Exception:
                pass
        label.bind("<Configure>", _fit)
        return label

    # ================= 页签一：文件检查 =================
    def _build_check_tab(self):
        tab = self.frame_check

        row = tk.Frame(tab, bg=C_BG)
        row.pack(fill="x")
        self.var_check_folder = tk.StringVar()
        self.entry_check = ttk.Entry(row, textvariable=self.var_check_folder, font=FONT_UI)
        self.entry_check.pack(side="left", fill="x", expand=True, ipady=5)
        _paste_menu(self.entry_check)
        make_button(row, "选择文件夹", self._pick_check_folder).pack(side="left", padx=(8, 0))
        self.btn_check_scan = make_button(row, "开始检查", self._start_check, kind="primary")
        self.btn_check_scan.pack(side="left", padx=(8, 0))

        hint = tk.Label(tab, text="支持图片：jpg / jpeg / png / bmp / gif / webp / tif / tiff / heic / heif / jfif / avif；"
                                  "txt 匹配只发生在同一个文件夹内，跨文件夹的同名文件互不影响。",
                        bg=C_BG, fg=C_MUTED, font=FONT_SMALL, justify="left", anchor="w")
        self._auto_wrap(hint).pack(fill="x", pady=(6, 0))

        cards = tk.Frame(tab, bg=C_BG)
        cards.pack(fill="x", pady=(12, 8))
        self._stat_vars = {}
        for key, label in (("dirs", "扫描目录"), ("imgs", "图片总数"),
                           ("txts", "TXT 总数"), ("missing", "缺 TXT 图片")):
            card = self._card(cards)
            card.pack(side="left", fill="x", expand=True, padx=(0, 10))
            self._stat_vars[key] = tk.StringVar(value="0")
            tk.Label(card, textvariable=self._stat_vars[key], bg=C_CARD, fg=C_ACCENT,
                     font=FONT_BIG).pack(pady=(12, 0))
            tk.Label(card, text=label, bg=C_CARD, fg=C_MUTED,
                     font=FONT_SMALL).pack(pady=(0, 12))

        self._section_label(tab, "缺失 TXT 的图片", "MISSING LIST")
        tree_wrap = tk.Frame(tab, bg=C_CARD, highlightthickness=1, highlightbackground=C_BORDER)
        tree_wrap.pack(fill="both", expand=True)
        cols = ("no", "folder", "name", "path")
        self.tree_check = ttk.Treeview(tree_wrap, columns=cols, show="headings",
                                       selectmode="browse")
        f = self._f
        for cid, title, width, anchor in (
                ("no", "序号", 70, "center"),
                ("folder", "所在文件夹", 330, "w"),
                ("name", "图片文件名", 260, "w"),
                ("path", "完整路径", 620, "w")):
            self.tree_check.heading(cid, text=title)
            self.tree_check.column(cid, width=round(width * f), anchor=anchor,
                                   stretch=(cid == "path"))
        vsb = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree_check.yview)
        self.tree_check.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree_check.pack(fill="both", expand=True)

        bottom = tk.Frame(tab, bg=C_BG)
        bottom.pack(fill="x", pady=(10, 0))
        self.btn_check_save = make_button(bottom, "保存缺失清单…", self._save_check_list, kind="primary")
        self.btn_check_save.pack(side="left")
        self.lbl_check_status = tk.Label(bottom, text="就绪", bg=C_BG, fg=C_MUTED,
                                         font=FONT_SMALL, anchor="e")
        self.lbl_check_status.pack(side="right", fill="x", expand=True)

    def _pick_check_folder(self):
        d = self._ask_dir("选择要检查的文件夹", self.var_check_folder.get().strip().strip('"'))
        if d:
            self.var_check_folder.set(d)

    def _start_check(self):
        root = self.var_check_folder.get().strip().strip('"')
        if not root or not os.path.isdir(root):
            self._msg("提示", "请先选择一个有效的文件夹。", "warn")
            return
        self._set_busy(True, self.btn_check_scan)
        for k in self._stat_vars:
            self._stat_vars[k].set("…")
        self.lbl_check_status.config(text="正在扫描文件结构…")

        def work():
            missing, stats = scan_missing(root)
            self.after(0, lambda: self._on_check_done(missing, stats, root))

        threading.Thread(target=work, daemon=True).start()

    def _on_check_done(self, missing, stats, root):
        self._check_rows = missing
        self._set_busy(False, self.btn_check_scan)
        for key, val in (("dirs", stats["dirs"]), ("imgs", stats["imgs"]),
                         ("txts", stats["txts"]), ("missing", stats["missing"])):
            self._stat_vars[key].set(str(val))
        for i in self.tree_check.get_children():
            self.tree_check.delete(i)
        cap = 2000  # 预览上限：避免一次插入上万行导致界面卡顿
        shown = 0
        for idx, (d, name) in enumerate(missing, 1):
            if shown >= cap:
                break
            try:
                folder_shown = os.path.relpath(d, root)
                if folder_shown == ".":
                    folder_shown = "（所选文件夹）"
            except Exception:
                folder_shown = d
            self.tree_check.insert("", "end", values=(idx, folder_shown, name, os.path.join(d, name)))
            shown += 1
            if shown % 250 == 0:
                self.update_idletasks()
        if missing:
            extra = f"（预览显示前 {shown} 条，导出时包含全部 {len(missing)} 条）" if shown < len(missing) else ""
            self.lbl_check_status.config(
                text=f"共发现 {len(missing)} 张图片缺少同名 txt{extra}，可点击右侧按钮导出清单。",
                fg=C_DANGER)
        else:
            self.lbl_check_status.config(text="所有图片都有同名 txt，未发现缺失。", fg=C_OK)
        self._save_cfg()

    def _save_check_list(self):
        if not self._check_rows:
            self._msg("提示", "当前没有可导出的缺失清单，请先执行“开始检查”。")
            return
        root = self.var_check_folder.get().strip().strip('"')
        initial_dir = root or os.path.expanduser("~")
        path = self._ask_save("保存缺失清单", initial_dir, "缺失TXT的图片清单.txt")
        if not path:
            return
        try:
            n = export_missing(self._check_rows, path)
            self._msg("完成", f"已导出 {n} 条路径到：\n{path}")
        except OSError as e:
            self._msg("导出失败", f"无法写入文件：\n{e}", "error")

    # ================= 页签二：文件重命名 =================
    def _build_rename_tab(self):
        tab = self.frame_rename

        row = tk.Frame(tab, bg=C_BG)
        row.pack(fill="x")
        self.var_rn_folder = tk.StringVar()
        self.entry_rn = ttk.Entry(row, textvariable=self.var_rn_folder, font=FONT_UI)
        self.entry_rn.pack(side="left", fill="x", expand=True, ipady=5)
        _paste_menu(self.entry_rn)
        make_button(row, "选择文件夹", self._pick_rn_folder).pack(side="left", padx=(8, 0))
        self.btn_rn_plan = make_button(row, "生成方案", self._start_plan, kind="primary")
        self.btn_rn_plan.pack(side="left", padx=(8, 0))

        opt = self._card(tab)
        opt.pack(fill="x", pady=(12, 0), padx=0)
        grid = tk.Frame(opt, bg=C_CARD)
        grid.pack(fill="x", padx=14, pady=12)
        grid.columnconfigure(9, weight=1)

        def lab(text):
            return tk.Label(grid, text=text, bg=C_CARD, fg=C_MUTED, font=FONT_SMALL)

        self.var_start = tk.IntVar(value=1)
        self.var_digits = tk.IntVar(value=6)
        self.var_prefix = tk.StringVar()
        self.var_suffix = tk.StringVar()

        lab("起始编号").grid(row=0, column=0, sticky="w", padx=(0, 6))
        sp_start = tk.Spinbox(grid, from_=0, to=9999999, textvariable=self.var_start,
                              width=8, font=FONT_SMALL, bg=C_PANEL, fg=C_TEXT,
                              buttonbackground=C_PANEL, relief="flat",
                              highlightthickness=1, highlightbackground=C_BORDER)
        sp_start.grid(row=0, column=1, sticky="w", padx=(0, 18), ipady=3)

        lab("编号位数").grid(row=0, column=2, sticky="w", padx=(0, 6))
        sp_digits = tk.Spinbox(grid, from_=1, to=12, textvariable=self.var_digits,
                               width=4, font=FONT_SMALL, bg=C_PANEL, fg=C_TEXT,
                               buttonbackground=C_PANEL, relief="flat",
                               highlightthickness=1, highlightbackground=C_BORDER)
        sp_digits.grid(row=0, column=3, sticky="w", padx=(0, 18), ipady=3)

        lab("前缀").grid(row=0, column=4, sticky="w", padx=(0, 6))
        ent_pre = ttk.Entry(grid, textvariable=self.var_prefix, width=14, font=FONT_SMALL)
        ent_pre.grid(row=0, column=5, sticky="w", padx=(0, 18), ipady=3)

        lab("后缀").grid(row=0, column=6, sticky="w", padx=(0, 6))
        ent_suf = ttk.Entry(grid, textvariable=self.var_suffix, width=14, font=FONT_SMALL)
        ent_suf.grid(row=0, column=7, sticky="w", padx=(0, 18), ipady=3)

        self.lbl_example = tk.Label(grid, text="命名示例：写真集000001.jpg", bg=C_CARD,
                                    fg=C_ACCENT, font=FONT_SMALL)
        self.lbl_example.grid(row=0, column=8, sticky="w")
        for v in (self.var_start, self.var_digits, self.var_prefix, self.var_suffix):
            v.trace_add("write", lambda *_: self._refresh_example())

        hint = tk.Label(tab,
                        text="规则：先处理所选文件夹本身（如有图片），再递归子文件夹（按名称从小到大排序，先小后大）；"
                             "编号全局连续，同名 txt 与图片使用同一新名，扩展名保持不变。",
                        bg=C_BG, fg=C_MUTED, font=FONT_SMALL, justify="left", anchor="w")
        self._auto_wrap(hint).pack(fill="x", pady=(6, 0))

        cards = tk.Frame(tab, bg=C_BG)
        cards.pack(fill="x", pady=(12, 8))
        self._rn_vars = {}
        for key, label in (("scope", "处理范围"), ("images", "图片"), ("txts", "TXT"),
                           ("ren", "将重命名"), ("skip", "跳过")):
            card = self._card(cards)
            card.pack(side="left", fill="x", expand=True, padx=(0, 10))
            self._rn_vars[key] = tk.StringVar(value="—")
            tk.Label(card, textvariable=self._rn_vars[key], bg=C_CARD, fg=C_ACCENT,
                     font=FONT_BIG).pack(pady=(10, 0))
            tk.Label(card, text=label, bg=C_CARD, fg=C_MUTED,
                     font=FONT_SMALL).pack(pady=(0, 10))

        self._section_label(tab, "重命名方案预览", "RENAME PREVIEW")
        tree_wrap = tk.Frame(tab, bg=C_CARD, highlightthickness=1, highlightbackground=C_BORDER)
        tree_wrap.pack(fill="both", expand=True)
        cols = ("folder", "kind", "old", "new", "status")
        self.tree_rn = ttk.Treeview(tree_wrap, columns=cols, show="headings", selectmode="browse")
        f = self._f
        for cid, title, width, anchor in (
                ("folder", "所在文件夹", 280, "w"),
                ("kind", "类型", 80, "center"),
                ("old", "原文件名", 280, "w"),
                ("new", "新文件名", 280, "w"),
                ("status", "状态", 180, "center")):
            self.tree_rn.heading(cid, text=title)
            self.tree_rn.column(cid, width=round(width * f), anchor=anchor,
                                stretch=(cid in ("old", "new")))
        vsb = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree_rn.yview)
        self.tree_rn.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree_rn.pack(fill="both", expand=True)

        bottom = tk.Frame(tab, bg=C_BG)
        bottom.pack(fill="x", pady=(10, 0))
        self.btn_rn_exec = make_button(bottom, "执行重命名", self._confirm_execute, kind="primary")
        self.btn_rn_exec.pack(side="left")
        self.lbl_rn_status = tk.Label(bottom, text="就绪", bg=C_BG, fg=C_MUTED,
                                      font=FONT_SMALL, anchor="e")
        self.lbl_rn_status.pack(side="right", fill="x", expand=True)

    def _pick_rn_folder(self):
        d = self._ask_dir("选择要重命名的文件夹", self.var_rn_folder.get().strip().strip('"'))
        if d:
            self.var_rn_folder.set(d)

    def _refresh_example(self):
        try:
            start = int(self.var_start.get())
            digits = int(self.var_digits.get())
        except Exception:
            return
        digits = max(1, min(12, digits))
        self.lbl_example.config(
            text="命名示例：" + self.var_prefix.get() + str(start).zfill(digits)
                 + self.var_suffix.get() + ".jpg")

    def _start_plan(self):
        root = self.var_rn_folder.get().strip().strip('"')
        if not root or not os.path.isdir(root):
            self._msg("提示", "请先选择一个有效的文件夹。", "warn")
            return
        try:
            start = int(self.var_start.get())
            digits = int(self.var_digits.get())
        except Exception:
            self._msg("提示", "起始编号和编号位数必须是整数。", "warn")
            return
        err = validate_options(start, digits, self.var_prefix.get(), self.var_suffix.get())
        if err:
            self._msg("选项有误", err, "warn")
            return
        self._set_busy(True, self.btn_rn_plan)
        self.lbl_rn_status.config(text="正在生成方案…")

        def work():
            rows, summary = build_plan(root, start, digits,
                                       self.var_prefix.get(), self.var_suffix.get())
            self.after(0, lambda: self._on_plan_done(rows, summary, root))

        threading.Thread(target=work, daemon=True).start()

    def _on_plan_done(self, rows, summary, root):
        self._plan_rows = rows
        self._set_busy(False, self.btn_rn_plan)
        sub_cnt = max(0, summary["folders"] - (1 if summary["has_top"] else 0))
        if summary["has_top"]:
            scope_txt = f"顶层 + 子文件夹（{sub_cnt} 个）"
        else:
            scope_txt = f"子文件夹（{sub_cnt} 个）"
        self._rn_vars["scope"].set(scope_txt)
        self._rn_vars["images"].set(str(summary["images"]))
        self._rn_vars["txts"].set(str(summary["txts"]))
        self._rn_vars["ren"].set(str(summary["ren_img"] + summary["ren_txt"]))
        self._rn_vars["skip"].set(str(summary["skip"]))

        for i in self.tree_rn.get_children():
            self.tree_rn.delete(i)
        cap = 2000  # 预览上限：方案仍包含全部行，执行时全部处理
        shown = 0
        for r in rows:
            if shown >= cap:
                break
            try:
                folder_shown = os.path.relpath(r["folder"], root)
                if folder_shown == ".":
                    folder_shown = "（所选文件夹）"
            except Exception:
                folder_shown = r["folder"]
            if r["status"] == "ok":
                status, color = "将重命名", C_OK
            elif r["status"] == "same":
                status, color = "名称不变", C_MUTED
            else:
                status, color = "冲突·目标已存在", C_DANGER
            self.tree_rn.insert("", "end", values=(folder_shown, r["kind"],
                                                   r["old_name"], r["new_name"], status),
                                tags=(color,))
            shown += 1
            if shown % 250 == 0:
                self.update_idletasks()
        self.tree_rn.tag_configure(C_OK, foreground=C_OK)
        self.tree_rn.tag_configure(C_MUTED, foreground=C_MUTED)
        self.tree_rn.tag_configure(C_DANGER, foreground=C_DANGER)

        if not rows:
            self.lbl_rn_status.config(text="未发现任何图片，无法生成方案。", fg=C_WARN)
        elif summary["skip"]:
            self.lbl_rn_status.config(
                text=f"方案已生成：将重命名 {summary['ren_img'] + summary['ren_txt']} 个文件，"
                     f"{summary['skip']} 项跳过（名称不变或目标已存在），请先核对预览。", fg=C_WARN)
        else:
            total = summary['ren_img'] + summary['ren_txt']
            extra = f"（预览显示前 {shown} 项，执行时全部处理）" if shown < total else ""
            self.lbl_rn_status.config(
                text=f"方案已生成：将重命名 {summary['ren_img']} 张图片、"
                     f"{summary['ren_txt']} 个 txt，共 {total} 个文件{extra}。",
                fg=C_OK)
        self._save_cfg()

    def _confirm_execute(self):
        if not self._plan_rows:
            self._msg("提示", "请先生成重命名方案。")
            return
        todo = [r for r in self._plan_rows if r["status"] == "ok"]
        conflicts = [r for r in self._plan_rows if r["status"] == "conflict"]
        if not todo:
            self._msg("提示", "方案中没有可执行的重命名项。")
            return
        msg = (f"将重命名 {len(todo)} 个文件：\n"
               f"  图片 {sum(1 for r in todo if r['kind'] == '图片')} 个、"
               f"txt {sum(1 for r in todo if r['kind'] == 'TXT')} 个。\n")
        if conflicts:
            msg += f"\n⚠ 另有 {len(conflicts)} 项因目标文件已存在被跳过（显示为红色）。\n"
        msg += "\n该操作会直接修改文件名，且不可撤销。确定执行吗？"
        if not self._confirm("确认执行", msg):
            return
        self._set_busy(True, self.btn_rn_exec)
        self.lbl_rn_status.config(text="正在重命名…")

        def work():
            folder = self.var_rn_folder.get().strip().strip('"')

            def progress(done, total, phase):
                if done % 20 == 0 or done == total:
                    self.after(0, lambda: self.lbl_rn_status.config(
                        text=f"正在重命名（第 {phase}/2 阶段）{done}/{total}…"))

            # 先恢复上次中断残留的临时文件，再执行本次重命名
            if os.path.isdir(folder):
                restored, _ = cleanup_pairtmp(folder, None)
                if restored:
                    self.after(0, lambda n=restored: self.lbl_rn_status.config(
                        text=f"已自动恢复 {n} 个上次中断的文件，正在重命名…"))
            ok, failures = execute_plan(self._plan_rows, progress)
            self.after(0, lambda: self._on_exec_done(ok, failures))

        threading.Thread(target=work, daemon=True).start()

    def _on_exec_done(self, ok_count, failures):
        self._set_busy(False, self.btn_rn_exec)
        if failures:
            msg = f"成功重命名 {ok_count} 个文件，{len(failures)} 个失败：\n"
            for p, e in failures[:5]:
                msg += f"  {p} → {e}\n"
            self._msg("重命名完成（有失败）", msg, "warn")
            self.lbl_rn_status.config(text=f"完成，但有 {len(failures)} 个文件失败。", fg=C_DANGER)
        else:
            self._msg("完成", f"成功重命名 {ok_count} 个文件。")
            self.lbl_rn_status.config(text=f"已成功重命名 {ok_count} 个文件。", fg=C_OK)
        self._start_plan()

    # ---------- 通用 ----------
    def _set_busy(self, busy, button):
        self._busy = busy
        button.config(state="disabled" if busy else "normal")

    # ================= 深色对话框（替代原生白色弹窗） =================
    def _msg(self, title, text, kind="info", w=500, h=250):
        dlg = DarkDialog(self, title, w, h, self._f)
        icon, color = {"info": ("✔", C_OK), "warn": ("⚠", C_WARN),
                       "error": ("✕", C_DANGER)}[kind]
        top = tk.Frame(dlg.body, bg=C_BG)
        top.pack(fill="both", expand=True, pady=(6, 10))
        tk.Label(top, text=icon, bg=C_BG, fg=color, font=("Segoe UI", 22, "bold")).pack(side="left", padx=(0, 14))
        lbl = tk.Label(top, text=text, bg=C_BG, fg=C_TEXT, font=FONT_UI,
                       justify="left", anchor="nw", wraplength=round(w * dlg._f) - 100)
        lbl.pack(side="left", fill="both", expand=True)
        btn, _ = _dialog_buttons(dlg, "确定", None)
        btn.config(command=lambda: dlg._finish(True))
        dlg.bind("<Return>", lambda e: dlg._finish(True))
        dlg.bind("<Escape>", lambda e: dlg._cancel())
        return dlg.run()

    def _confirm(self, title, text, w=520, h=300):
        dlg = DarkDialog(self, title, w, h, self._f)
        top = tk.Frame(dlg.body, bg=C_BG)
        top.pack(fill="both", expand=True, pady=(6, 10))
        tk.Label(top, text="?", bg=C_BG, fg=C_ACCENT, font=("Segoe UI", 22, "bold")).pack(side="left", padx=(0, 14))
        lbl = tk.Label(top, text=text, bg=C_BG, fg=C_TEXT, font=FONT_UI,
                       justify="left", anchor="nw", wraplength=round(w * dlg._f) - 100)
        lbl.pack(side="left", fill="both", expand=True)
        btn_ok, btn_cancel = _dialog_buttons(dlg, "确定", "取消")
        btn_ok.config(command=lambda: dlg._finish(True))
        btn_cancel.config(command=dlg._cancel)
        dlg.bind("<Return>", lambda e: dlg._finish(True))
        dlg.bind("<Escape>", lambda e: dlg._cancel())
        return bool(dlg.run())

    def _ask_dir(self, title, initial=""):
        """深色文件夹选择器：可粘贴/输入路径直接跳转，可切换任意盘符。"""
        if not initial or not os.path.isdir(initial):
            initial = os.path.expanduser("~")
        dlg = DarkDialog(self, title, 720, 560, self._f)
        state = {"current": os.path.abspath(initial)}
        self._dir_state = state
        drives = list_drives()
        f = dlg._f

        # ---- 路径输入（可粘贴）+ 转到 ----
        prow = tk.Frame(dlg.body, bg=C_BG)
        prow.pack(fill="x", pady=(0, 6))
        tk.Label(prow, text="路径：", bg=C_BG, fg=C_MUTED, font=FONT_SMALL).pack(side="left")
        var_path = tk.StringVar()
        ent_path = ttk.Entry(prow, textvariable=var_path, font=FONT_SMALL)
        ent_path.pack(side="left", fill="x", expand=True, ipady=3)

        def go_to():
            p = var_path.get().strip().strip('"')
            if not p:
                return
            p = os.path.abspath(p)
            if os.path.isdir(p):
                state["current"] = p
                refresh()
            else:
                err_lbl.config(text="该路径不存在或不是文件夹，请检查后重试。")

        make_button(prow, "转到", go_to).pack(side="left", padx=(8, 0))
        ent_path.bind("<Return>", lambda e: go_to())
        _paste_menu(ent_path)

        # ---- 驱动器下拉 ----
        drow = tk.Frame(dlg.body, bg=C_BG)
        drow.pack(fill="x", pady=(0, 4))
        tk.Label(drow, text="驱动器：", bg=C_BG, fg=C_MUTED, font=FONT_SMALL).pack(side="left")
        cb = ttk.Combobox(drow, values=drives, state="readonly", width=8, font=FONT_SMALL)
        cb.pack(side="left")

        def on_drive(e):
            v = cb.get()
            if v and os.path.isdir(v):
                state["current"] = v
                refresh()

        cb.bind("<<ComboboxSelected>>", on_drive)

        err_lbl = tk.Label(dlg.body, text="", bg=C_BG, fg=C_DANGER, font=FONT_SMALL, anchor="w")
        err_lbl.pack(fill="x", pady=(0, 2))
        path_lbl = tk.Label(dlg.body, text="", bg=C_BG, fg=C_ACCENT, font=FONT_SMALL,
                            anchor="w", wraplength=round(680 * f))
        path_lbl.pack(fill="x", pady=(0, 8))

        tree_wrap = tk.Frame(dlg.body, bg=C_CARD, highlightthickness=1, highlightbackground=C_BORDER)
        tree_wrap.pack(fill="both", expand=True)
        tree = ttk.Treeview(tree_wrap, show="tree", selectmode="browse", height=6)
        vsb = ttk.Scrollbar(tree_wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)

        def refresh():
            cur = state["current"]
            err_lbl.config(text="")
            for i in tree.get_children():
                tree.delete(i)
            if cur == DRIVES_SENTINEL:
                path_lbl.config(text="此电脑 · 请选择驱动器，或在上方输入完整路径后点“转到”")
                var_path.set("")
                cb.set("")
                for d in drives:
                    tree.insert("", "end", text=d, values=("dir", d))
                return
            path_lbl.config(text=cur)
            var_path.set(cur)
            curdrive = os.path.splitdrive(cur)[0] + "\\"
            cb.set(curdrive if curdrive in drives else "")
            try:
                entries = sorted(os.listdir(cur), key=str.casefold)
            except OSError:
                entries = []
            for name in entries:
                p = os.path.join(cur, name)
                if os.path.isdir(p):
                    tree.insert("", "end", text=name, values=("dir", p))
            if not entries:
                tree.insert("", "end", text="（无子文件夹）", values=("empty", ""))

        def go_up():
            cur = state["current"]
            if cur == DRIVES_SENTINEL:
                return
            parent = os.path.dirname(cur)
            if parent == cur:
                state["current"] = DRIVES_SENTINEL
            else:
                state["current"] = parent
            refresh()

        def enter_target():
            sel = tree.selection()
            if not sel:
                return
            vals = tree.item(sel[0])["values"]
            if vals and vals[0] == "dir" and len(vals) > 1:
                state["current"] = vals[1]
                refresh()

        tree.bind("<Double-Button-1>", lambda e: enter_target())
        tree.bind("<Return>", lambda e: enter_target())

        row = tk.Frame(dlg.body, bg=C_BG)
        row.pack(side="bottom", fill="x", pady=(10, 0))
        make_button(row, "上一级", go_up).pack(side="left")
        make_button(row, "进入所选文件夹", enter_target).pack(side="left", padx=(8, 0))

        def choose():
            if state["current"] == DRIVES_SENTINEL:
                err_lbl.config(text="请先进入或输入一个具体文件夹。")
                return
            dlg._finish(state["current"])

        btn_ok, btn_cancel = _dialog_buttons(dlg, "选择此文件夹", "取消")
        btn_ok.config(command=choose)
        btn_cancel.config(command=dlg._cancel)
        dlg.bind("<Escape>", lambda e: dlg._cancel())
        refresh()
        ent_path.focus_set()
        return dlg.run()

    def _ask_save(self, title, initial_dir="", initial_file="缺失TXT的图片清单.txt"):
        """深色保存对话框：选文件夹 + 输入文件名；可粘贴路径、切换任意盘符。"""
        dlg = DarkDialog(self, title, 720, 580, self._f)
        state = {"current": os.path.abspath(initial_dir or os.path.expanduser("~"))}
        self._dir_state = state
        self._var_save_name = tk.StringVar(value=initial_file)
        drives = list_drives()
        f = dlg._f

        prow = tk.Frame(dlg.body, bg=C_BG)
        prow.pack(fill="x", pady=(0, 6))
        tk.Label(prow, text="路径：", bg=C_BG, fg=C_MUTED, font=FONT_SMALL).pack(side="left")
        var_path = tk.StringVar()
        ent_path = ttk.Entry(prow, textvariable=var_path, font=FONT_SMALL)
        ent_path.pack(side="left", fill="x", expand=True, ipady=3)

        def go_to():
            p = var_path.get().strip().strip('"')
            if not p:
                return
            p = os.path.abspath(p)
            if os.path.isdir(p):
                state["current"] = p
                refresh()
            else:
                err_lbl.config(text="该路径不存在或不是文件夹，请检查后重试。")

        make_button(prow, "转到", go_to).pack(side="left", padx=(8, 0))
        ent_path.bind("<Return>", lambda e: go_to())
        _paste_menu(ent_path)

        drow = tk.Frame(dlg.body, bg=C_BG)
        drow.pack(fill="x", pady=(0, 4))
        tk.Label(drow, text="驱动器：", bg=C_BG, fg=C_MUTED, font=FONT_SMALL).pack(side="left")
        cb = ttk.Combobox(drow, values=drives, state="readonly", width=8, font=FONT_SMALL)
        cb.pack(side="left")

        def on_drive(e):
            v = cb.get()
            if v and os.path.isdir(v):
                state["current"] = v
                refresh()

        cb.bind("<<ComboboxSelected>>", on_drive)

        err_lbl = tk.Label(dlg.body, text="", bg=C_BG, fg=C_DANGER, font=FONT_SMALL, anchor="w")
        err_lbl.pack(fill="x", pady=(0, 2))
        path_lbl = tk.Label(dlg.body, text="", bg=C_BG, fg=C_ACCENT, font=FONT_SMALL,
                            anchor="w", wraplength=round(680 * f))
        path_lbl.pack(fill="x", pady=(0, 8))

        tree_wrap = tk.Frame(dlg.body, bg=C_CARD, highlightthickness=1, highlightbackground=C_BORDER)
        tree_wrap.pack(fill="both", expand=True)
        tree = ttk.Treeview(tree_wrap, show="tree", selectmode="browse", height=6)
        vsb = ttk.Scrollbar(tree_wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)

        def refresh():
            cur = state["current"]
            err_lbl.config(text="")
            for i in tree.get_children():
                tree.delete(i)
            if cur == DRIVES_SENTINEL:
                path_lbl.config(text="此电脑 · 请选择驱动器，或在上方输入完整路径后点“转到”")
                var_path.set("")
                cb.set("")
                for d in drives:
                    tree.insert("", "end", text=d, values=("dir", d))
                return
            path_lbl.config(text=cur)
            var_path.set(cur)
            curdrive = os.path.splitdrive(cur)[0] + "\\"
            cb.set(curdrive if curdrive in drives else "")
            try:
                entries = sorted(os.listdir(cur), key=str.casefold)
            except OSError:
                entries = []
            for name in entries:
                p = os.path.join(cur, name)
                if os.path.isdir(p):
                    tree.insert("", "end", text=name, values=("dir", p))
            if not entries:
                tree.insert("", "end", text="（无子文件夹）", values=("empty", ""))

        def go_up():
            cur = state["current"]
            if cur == DRIVES_SENTINEL:
                return
            parent = os.path.dirname(cur)
            if parent == cur:
                state["current"] = DRIVES_SENTINEL
            else:
                state["current"] = parent
            refresh()

        def enter_target():
            sel = tree.selection()
            if not sel:
                return
            vals = tree.item(sel[0])["values"]
            if vals and vals[0] == "dir" and len(vals) > 1:
                state["current"] = vals[1]
                refresh()

        tree.bind("<Double-Button-1>", lambda e: enter_target())

        row = tk.Frame(dlg.body, bg=C_BG)
        row.pack(side="bottom", fill="x", pady=(10, 0))
        make_button(row, "上一级", go_up).pack(side="left")
        make_button(row, "进入所选文件夹", enter_target).pack(side="left", padx=(8, 0))

        frow = tk.Frame(dlg.body, bg=C_BG)
        frow.pack(fill="x", pady=(10, 0))
        tk.Label(frow, text="文件名：", bg=C_BG, fg=C_MUTED, font=FONT_SMALL).pack(side="left")
        ent = ttk.Entry(frow, textvariable=self._var_save_name, font=FONT_SMALL)
        ent.pack(side="left", fill="x", expand=True, ipady=3)
        _paste_menu(ent)

        def do_save():
            if state["current"] == DRIVES_SENTINEL:
                err_lbl.config(text="请先进入或输入一个具体文件夹。")
                return
            name = self._var_save_name.get().strip()
            if not name:
                err_lbl.config(text="请输入文件名。")
                return
            state["saved"] = os.path.join(state["current"], name)
            dlg._finish(True)

        btn_ok, btn_cancel = _dialog_buttons(dlg, "保存", "取消")
        btn_ok.config(command=do_save)
        btn_cancel.config(command=dlg._cancel)
        dlg.bind("<Return>", lambda e: do_save())
        dlg.bind("<Escape>", lambda e: dlg._cancel())
        refresh()
        ent_path.focus_set()
        if dlg.run():
            return self._dir_state.get("saved")
        return None

    # ================= 页签三：批量复制 =================
    def _build_copy_tab(self):
        tab = self.frame_copy

        row = tk.Frame(tab, bg=C_BG)
        row.pack(fill="x")
        self.var_txt_list = tk.StringVar()
        self.entry_txts = ttk.Entry(row, textvariable=self.var_txt_list, font=FONT_UI)
        self.entry_txts.pack(side="left", fill="x", expand=True, ipady=5)
        _paste_menu(self.entry_txts)
        make_button(row, "选择 TXT…", self._pick_txt_files).pack(side="left", padx=(8, 0))

        hint = tk.Label(tab, text="TXT 中每行一个文件路径，兼容带引号、含制表符的导出格式；空行和 # 开头的注释行自动忽略。"
                                  "可粘贴多个 TXT 路径，用分号或换行分隔。",
                        bg=C_BG, fg=C_MUTED, font=FONT_SMALL, justify="left", anchor="w")
        self._auto_wrap(hint).pack(fill="x", pady=(6, 0))

        row2 = tk.Frame(tab, bg=C_BG)
        row2.pack(fill="x", pady=(10, 0))
        self.var_copy_dest = tk.StringVar()
        self.entry_dest = ttk.Entry(row2, textvariable=self.var_copy_dest, font=FONT_UI)
        self.entry_dest.pack(side="left", fill="x", expand=True, ipady=5)
        _paste_menu(self.entry_dest)
        make_button(row2, "选择文件夹…", self._pick_copy_dest).pack(side="left", padx=(8, 0))

        row3 = tk.Frame(tab, bg=C_BG)
        row3.pack(fill="x", pady=(10, 0))
        tk.Label(row3, text="同名文件：", bg=C_BG, fg=C_MUTED, font=FONT_SMALL).pack(side="left")
        self.var_dup = tk.StringVar(value="自动加序号")
        cb = ttk.Combobox(row3, textvariable=self.var_dup,
                          values=("自动加序号", "跳过"), state="readonly",
                          width=12, font=FONT_SMALL)
        cb.pack(side="left")
        self.btn_copy_start = make_button(row3, "开始复制", self._start_copy, kind="primary")
        self.btn_copy_start.pack(side="left", padx=(12, 0))
        self.lbl_copy_status = tk.Label(row3, text="就绪", bg=C_BG, fg=C_MUTED,
                                        font=FONT_SMALL, anchor="e")
        self.lbl_copy_status.pack(side="right", fill="x", expand=True)

        cards = tk.Frame(tab, bg=C_BG)
        cards.pack(fill="x", pady=(12, 8))
        self._copy_vars = {}
        for key, label in (("total", "读取路径"), ("valid", "有效文件"),
                           ("copied", "复制成功"), ("dup", "已存在处理"), ("failed", "失败")):
            card = self._card(cards)
            card.pack(side="left", fill="x", expand=True, padx=(0, 10))
            self._copy_vars[key] = tk.StringVar(value="—")
            tk.Label(card, textvariable=self._copy_vars[key], bg=C_CARD, fg=C_ACCENT,
                     font=FONT_BIG).pack(pady=(10, 0))
            tk.Label(card, text=label, bg=C_CARD, fg=C_MUTED,
                     font=FONT_SMALL).pack(pady=(0, 10))

        self._section_label(tab, "运行详情", "COPY LOG")
        self.lbl_copy_detail = tk.Label(tab, text="", bg=C_BG, fg=C_MUTED,
                                        font=FONT_SMALL, justify="left", anchor="nw")
        self._auto_wrap(self.lbl_copy_detail).pack(fill="both", expand=True, pady=(2, 0))

    def _split_txt_input(self):
        """从输入框解析 TXT 路径列表（支持 ; ； 换行 分隔，去引号）。"""
        out = []
        for raw in re.split(r"[;\n；]+", self.var_txt_list.get()):
            p = raw.strip().strip('"').strip()
            if p and p not in out:
                out.append(p)
        return out

    def _pick_txt_files(self):
        parts = self._split_txt_input()
        start = os.path.expanduser("~")
        for p in parts:
            if os.path.isfile(p):
                start = os.path.dirname(p)
                break
            if os.path.isdir(p):
                start = p
                break
        files = self._ask_files("选择清单 TXT 文件", start)
        if not files:
            return
        merged = list(parts)
        for fp in files:
            if fp not in merged:
                merged.append(fp)
        self.var_txt_list.set("；".join(merged))
        self.lbl_copy_status.config(text=f"已选择 {len(files)} 个 TXT 清单。")

    def _pick_copy_dest(self):
        d = self._ask_dir("选择复制目标文件夹", self.var_copy_dest.get().strip().strip('"'))
        if d:
            self.var_copy_dest.set(d)

    def _start_copy(self):
        txt_paths = self._split_txt_input()
        dest = self.var_copy_dest.get().strip().strip('"')
        if not txt_paths:
            self._msg("提示", "请先选择一个或多个清单 TXT 文件。", "warn")
            return
        if not dest or not os.path.isdir(dest):
            self._msg("提示", "请先选择一个有效的目标文件夹。", "warn")
            return
        self._set_busy(True, self.btn_copy_start)
        for k in self._copy_vars:
            self._copy_vars[k].set("…")
        self.lbl_copy_detail.config(text="")
        self.lbl_copy_status.config(text="正在读取清单…")
        dup = "rename" if self.var_dup.get() == "自动加序号" else "skip"

        def work():
            paths, read_errors = load_paths_from_txts(txt_paths)

            def progress(done, total):
                if done % 10 == 0 or done == total:
                    self.after(0, lambda: self.lbl_copy_status.config(
                        text=f"正在复制 {done}/{total}…"))

            result = copy_files(paths, dest, dup, progress)
            self.after(0, lambda: self._on_copy_done(
                paths, read_errors, result, txt_paths))

        threading.Thread(target=work, daemon=True).start()

    def _on_copy_done(self, paths, read_errors, result, txt_paths):
        self._set_busy(False, self.btn_copy_start)
        total = len(paths)
        valid = total - len(result["invalid"])
        dup_done = result["renamed"] + result["skipped"]
        self._copy_vars["total"].set(str(total))
        self._copy_vars["valid"].set(str(valid))
        self._copy_vars["copied"].set(str(result["copied"]))
        self._copy_vars["dup"].set(str(dup_done))
        self._copy_vars["failed"].set(str(len(result["failed"]) + len(read_errors)))

        if not paths and not read_errors:
            self.lbl_copy_status.config(text="清单中没有读取到任何路径。", fg=C_WARN)
            self.lbl_copy_detail.config(text="请检查 TXT 内容：每行应为一个完整文件路径。")
            self._msg("提示", "清单中没有读取到任何路径。\n请检查 TXT 内容（每行一个完整路径）。", "warn")
            return

        detail = []
        if read_errors:
            detail.append("清单读取失败：")
            for p, e in read_errors[:3]:
                detail.append(f"  {p} → {e}")
        if result["invalid"]:
            detail.append(f"无效路径 {len(result['invalid'])} 条：")
            for p in result["invalid"][:5]:
                detail.append(f"  {p}")
        if result["failed"]:
            detail.append(f"复制失败 {len(result['failed'])} 个：")
            for p, e in result["failed"][:5]:
                detail.append(f"  {p} → {e}")
        if result["renamed"]:
            detail.append(f"同名文件已自动加序号：{result['renamed']} 个")
        if result["skipped"]:
            detail.append(f"同名文件已跳过：{result['skipped']} 个")
        self.lbl_copy_detail.config(text="\n".join(detail) if detail else "全部成功，无异常。")

        ok = result["copied"]
        n_skip = len(read_errors) + len(result["invalid"]) + len(result["failed"]) + dup_done
        if n_skip == 0:
            self.lbl_copy_status.config(text=f"完成：成功复制 {ok} 个文件。", fg=C_OK)
            self._msg("完成", f"成功复制 {ok} 个文件到：\n{self.var_copy_dest.get()}")
        else:
            self.lbl_copy_status.config(
                text=f"完成：复制 {ok} 个，{n_skip} 项跳过/失败，详见下方详情。", fg=C_WARN)
            self._msg("完成（有跳过）",
                      f"成功复制 {ok} 个文件。\n"
                      f"同名处理 {dup_done} 个、无效路径 {len(result['invalid'])} 条、"
                      f"失败 {len(result['failed'])} 个、清单读取失败 {len(read_errors)} 个。\n"
                      f"详见下方“运行详情”。", "warn")

    def _ask_files(self, title, initial_dir=""):
        """深色文件选择器（多选）：浏览文件夹，选中其中的 *.txt 文件；可粘贴/输入路径跳转、切换盘符。"""
        if not initial_dir or not os.path.isdir(initial_dir):
            initial_dir = os.path.expanduser("~")
        dlg = DarkDialog(self, title, 720, 600, self._f)
        state = {"current": os.path.abspath(initial_dir)}
        self._dir_state = state
        drives = list_drives()
        f = dlg._f

        prow = tk.Frame(dlg.body, bg=C_BG)
        prow.pack(fill="x", pady=(0, 6))
        tk.Label(prow, text="路径：", bg=C_BG, fg=C_MUTED, font=FONT_SMALL).pack(side="left")
        var_path = tk.StringVar()
        ent_path = ttk.Entry(prow, textvariable=var_path, font=FONT_SMALL)
        ent_path.pack(side="left", fill="x", expand=True, ipady=3)

        def go_to():
            p = var_path.get().strip().strip('"')
            if not p:
                return
            p = os.path.abspath(p)
            if os.path.isdir(p):
                state["current"] = p
                refresh()
            else:
                err_lbl.config(text="该路径不存在或不是文件夹，请检查后重试。")

        make_button(prow, "转到", go_to).pack(side="left", padx=(8, 0))
        ent_path.bind("<Return>", lambda e: go_to())
        _paste_menu(ent_path)

        drow = tk.Frame(dlg.body, bg=C_BG)
        drow.pack(fill="x", pady=(0, 4))
        tk.Label(drow, text="驱动器：", bg=C_BG, fg=C_MUTED, font=FONT_SMALL).pack(side="left")
        cb = ttk.Combobox(drow, values=drives, state="readonly", width=8, font=FONT_SMALL)
        cb.pack(side="left")

        def on_drive(e):
            v = cb.get()
            if v and os.path.isdir(v):
                state["current"] = v
                refresh()

        cb.bind("<<ComboboxSelected>>", on_drive)

        err_lbl = tk.Label(dlg.body, text="", bg=C_BG, fg=C_DANGER, font=FONT_SMALL, anchor="w")
        err_lbl.pack(fill="x", pady=(0, 2))
        path_lbl = tk.Label(dlg.body, text="", bg=C_BG, fg=C_ACCENT, font=FONT_SMALL,
                            anchor="w", wraplength=round(680 * f))
        path_lbl.pack(fill="x", pady=(0, 8))

        sel_lbl = tk.Label(dlg.body, text="未选择文件", bg=C_BG, fg=C_MUTED,
                           font=FONT_SMALL, anchor="w")
        sel_lbl.pack(fill="x", pady=(0, 4))

        tree_wrap = tk.Frame(dlg.body, bg=C_CARD, highlightthickness=1, highlightbackground=C_BORDER)
        tree_wrap.pack(fill="both", expand=True)
        tree = ttk.Treeview(tree_wrap, show="tree", selectmode="extended", height=6)
        vsb = ttk.Scrollbar(tree_wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)

        def refresh():
            cur = state["current"]
            err_lbl.config(text="")
            for i in tree.get_children():
                tree.delete(i)
            if cur == DRIVES_SENTINEL:
                path_lbl.config(text="此电脑 · 请选择驱动器，或在上方输入完整路径后点“转到”")
                var_path.set("")
                cb.set("")
                for d in drives:
                    tree.insert("", "end", text=d, values=("dir", d))
                return
            path_lbl.config(text=cur)
            var_path.set(cur)
            curdrive = os.path.splitdrive(cur)[0] + "\\"
            cb.set(curdrive if curdrive in drives else "")
            try:
                entries = sorted(os.listdir(cur), key=str.casefold)
            except OSError:
                entries = []
            n_txt = 0
            for name in entries:
                p = os.path.join(cur, name)
                if os.path.isdir(p):
                    tree.insert("", "end", text=name, values=("dir", p))
                elif name.lower().endswith(".txt"):
                    tree.insert("", "end", text=name, values=("file", p))
                    n_txt += 1
            if not any(tree.item(i)["values"][0] == "dir" for i in tree.get_children()) and n_txt == 0:
                tree.insert("", "end", text="（无子文件夹，也无 TXT 文件）", values=("empty", ""))

        def go_up():
            cur = state["current"]
            if cur == DRIVES_SENTINEL:
                return
            parent = os.path.dirname(cur)
            if parent == cur:
                state["current"] = DRIVES_SENTINEL
            else:
                state["current"] = parent
            refresh()

        def selected_files():
            files = []
            for i in tree.selection():
                vals = tree.item(i)["values"]
                if vals and vals[0] == "file" and len(vals) > 1:
                    files.append(vals[1])
            return files

        def on_select(_e=None):
            n = len(selected_files())
            sel_lbl.config(text=f"已选中 {n} 个 TXT 文件" if n else "未选择文件")
            btn_ok.config(text=f"添加所选文件（{n}）")

        def enter_target():
            sel = tree.selection()
            if not sel:
                return
            vals = tree.item(sel[0])["values"]
            if vals and vals[0] == "dir" and len(vals) > 1:
                state["current"] = vals[1]
                refresh()
            elif vals and vals[0] == "file" and len(vals) > 1:
                dlg._finish([vals[1]])

        tree.bind("<<TreeviewSelect>>", on_select)
        tree.bind("<Double-Button-1>", lambda e: enter_target())
        tree.bind("<Return>", lambda e: enter_target())

        row = tk.Frame(dlg.body, bg=C_BG)
        row.pack(side="bottom", fill="x", pady=(10, 0))
        make_button(row, "上一级", go_up).pack(side="left")
        make_button(row, "进入所选文件夹", enter_target).pack(side="left", padx=(8, 0))

        def choose():
            files = selected_files()
            if not files:
                err_lbl.config(text="请先在列表中选择 TXT 文件（可多选）。")
                return
            dlg._finish(files)

        btn_ok, btn_cancel = _dialog_buttons(dlg, "添加所选文件（0）", "取消")
        btn_ok.config(command=choose)
        btn_cancel.config(command=dlg._cancel)
        dlg.bind("<Escape>", lambda e: dlg._cancel())
        refresh()
        ent_path.focus_set()
        return dlg.run()

    def _on_close(self):
        self._save_cfg()
        try:
            self.destroy()
        except Exception:
            pass


def _selftest():
    """
    隐藏自检：以 --selftest 参数运行时，在临时目录构造样例数据，执行
    扫描 → 生成方案 → 执行重命名 全流程，并把结果写入程序同目录的
    selftest_result.txt。仅用于交付前验证与用户故障排查。
    """
    import shutil
    import struct as _st
    import tempfile
    import zlib as _zl

    def make_png(path):
        sig = b"\x89PNG\r\n\x1a\n"
        def chunk(t, data):
            c = _st.pack(">I", len(data)) + t + data
            return c + _st.pack(">I", _zl.crc32(t + data) & 0xffffffff)
        ihdr = chunk(b"IHDR", _st.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        idat = chunk(b"IDAT", _zl.compress(b"\x00\xff\x00\x00"))
        iend = chunk(b"IEND", b"")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(sig + ihdr + idat + iend)

    lines = []
    tmp = tempfile.mkdtemp(prefix="pairtool_selftest_")
    try:
        root = os.path.join(tmp, "素材库")
        make_png(os.path.join(root, "01", "DSC1234.jpg"))
        open(os.path.join(root, "01", "DSC1234.txt"), "w").close()
        make_png(os.path.join(root, "01", "DSC1235.jpg"))
        make_png(os.path.join(root, "01", "photo.png"))
        open(os.path.join(root, "01", "photo.txt"), "w").close()
        make_png(os.path.join(root, "02", "DSC1234.jpg"))
        open(os.path.join(root, "02", "DSC1234.txt"), "w").close()
        make_png(os.path.join(root, "02", "only.bmp"))
        make_png(os.path.join(root, "top.jpg"))
        open(os.path.join(root, "top.txt"), "w").close()
        make_png(os.path.join(root, "root_only.webp"))

        missing, stats = scan_missing(root)
        assert stats["imgs"] == 7 and stats["txts"] == 4 and stats["missing"] == 3, stats
        assert {os.path.basename(d) + "/" + n for d, n in missing} == {
            "01/DSC1235.jpg", "02/only.bmp", "素材库/root_only.webp"}

        # 顶层 + 子文件夹都要处理：顶层先行，子文件夹按名称排序，编号全局连续
        rows, summary = build_plan(root, 1, 6, "写真集", "")
        assert summary["has_top"] and summary["images"] == 7, summary
        plan = {(os.path.relpath(r["folder"], root), r["kind"], r["old_name"]):
                (r["new_name"], r["status"]) for r in rows}
        assert plan[(".", "图片", "root_only.webp")][0] == "写真集000001.webp"
        assert plan[(".", "图片", "top.jpg")][0] == "写真集000002.jpg"
        assert plan[(".", "TXT", "top.txt")][0] == "写真集000002.txt"
        assert plan[("01", "图片", "DSC1234.jpg")][0] == "写真集000003.jpg"    # 01 先于 02
        assert plan[("01", "TXT", "DSC1234.txt")][0] == "写真集000003.txt"
        assert plan[("01", "图片", "DSC1235.jpg")][0] == "写真集000004.jpg"
        assert plan[("01", "图片", "photo.png")][0] == "写真集000005.png"
        assert plan[("02", "图片", "DSC1234.jpg")][0] == "写真集000006.jpg"    # 跨文件夹同名各自配对
        assert plan[("02", "TXT", "DSC1234.txt")][0] == "写真集000006.txt"
        assert plan[("02", "图片", "only.bmp")][0] == "写真集000007.bmp"
        assert all(s == "ok" for _, s in plan.values()), plan

        # 无顶层图片 → 只处理子文件夹（行为一致）
        root2 = os.path.join(tmp, "子文件夹")
        make_png(os.path.join(root2, "02", "c.jpg"))
        open(os.path.join(root2, "02", "c.txt"), "w").close()
        make_png(os.path.join(root2, "02", "d.jpg"))
        make_png(os.path.join(root2, "10", "e.png"))
        open(os.path.join(root2, "10", "e.txt"), "w").close()
        make_png(os.path.join(root2, "1", "a.jpg"))
        open(os.path.join(root2, "1", "a.txt"), "w").close()
        make_png(os.path.join(root2, "1", "b.jpg"))

        rows2, summary2 = build_plan(root2, 1, 6, "", "组")
        assert not summary2["has_top"] and summary2["ren_img"] == 5 and summary2["ren_txt"] == 3, summary2
        ok, fails = execute_plan([r for r in rows2 if r["status"] == "ok"])
        assert ok == 8 and not fails, (ok, fails)
        assert os.path.exists(os.path.join(root2, "1", "000001组.jpg"))
        assert os.path.exists(os.path.join(root2, "1", "000001组.txt"))
        assert os.path.exists(os.path.join(root2, "10", "000005组.png"))
        assert os.path.exists(os.path.join(root2, "10", "000005组.txt"))

        # 批量复制：TXT 清单解析 + 复制 + 同名处理
        src_dir = os.path.join(tmp, "copy_src")
        os.makedirs(src_dir)
        make_png(os.path.join(src_dir, "a.jpg"))
        make_png(os.path.join(src_dir, "b.png"))
        lst = os.path.join(tmp, "list.txt")
        with open(lst, "w", encoding="utf-8-sig", newline="\n") as f:
            f.write('"' + os.path.join(src_dir, "a.jpg") + '"\n')
            f.write(os.path.join(src_dir, "b.png") + "\t1024\n")
            f.write("\n# 注释行\n")
            f.write(os.path.join(src_dir, "nope.jpg") + "\n")
        paths, read_errors = load_paths_from_txts([lst])
        assert not read_errors and len(paths) == 3, (paths, read_errors)
        dest = os.path.join(tmp, "copy_dest")
        os.makedirs(dest)
        r1 = copy_files(paths, dest, "rename")
        assert r1["copied"] == 2 and len(r1["invalid"]) == 1, r1
        r2 = copy_files(paths[:1], dest, "rename")
        assert r2["renamed"] == 1 and r2["copied"] == 0, r2
        assert os.path.exists(os.path.join(dest, "a (1).jpg"))
        r3 = copy_files(paths[:1], dest, "skip")
        assert r3["skipped"] == 1 and r3["copied"] == 0, r3
        lines.append("SELFTEST COPY OK")

        # 配对完整性：txt 目标名被占 → 图片与配套 txt 都 conflict，绝不单独执行
        d3 = os.path.join(tmp, "pair_guard")
        os.makedirs(d3)
        open(os.path.join(d3, "a.jpg"), "w").close()
        open(os.path.join(d3, "a.txt"), "w").close()
        open(os.path.join(d3, "1.txt"), "w").close()   # 占位：a.txt 的目标名 1.txt
        rows3, _ = build_plan(d3, 1, 1, "", "")
        st3 = {(r["kind"], r["old_name"]): r["status"] for r in rows3}
        assert st3 == {("图片", "a.jpg"): "conflict", ("TXT", "a.txt"): "conflict"}, st3
        ok3, f3 = execute_plan(rows3)
        assert ok3 == 0 and not f3, (ok3, f3)
        assert sorted(os.listdir(d3)) == ["1.txt", "a.jpg", "a.txt"], os.listdir(d3)
        lines.append("SELFTEST PAIR-GUARD OK")

        # execute_plan 防御：目标被占且不会腾空 → 跳过、保持原名、无临时残留
        d4 = os.path.join(tmp, "exec_guard")
        os.makedirs(d4)
        open(os.path.join(d4, "a.jpg"), "w").close()
        open(os.path.join(d4, "1.jpg"), "w").close()   # 占位：a.jpg 的目标名 1.jpg（外部文件）
        rows4 = [{"folder": d4, "kind": "图片", "old_name": "a.jpg",
                  "new_name": "1.jpg", "status": "ok"}]
        ok4, f4 = execute_plan(rows4)
        assert ok4 == 0 and len(f4) == 1, (ok4, f4)
        assert os.path.exists(os.path.join(d4, "a.jpg")), "a.jpg 应保持原名"
        assert not any(n.startswith(".__pairtmp") for n in os.listdir(d4)), os.listdir(d4)
        lines.append("SELFTEST EXEC-GUARD OK")

        # 中断残留：临时文件不被扫描为普通图片；cleanup 去前缀恢复为最终名
        d5 = os.path.join(tmp, "recover")
        os.makedirs(d5)
        open(os.path.join(d5, ".__pairtmp_0__000001.jpg"), "w").close()
        open(os.path.join(d5, ".__pairtmp_3__000002.txt"), "w").close()
        open(os.path.join(d5, "normal.jpg"), "w").close()
        imgs5, txts5 = list_dir_files(d5)
        assert sorted(imgs5.values()) == ["normal.jpg"], (imgs5, txts5)
        assert txts5 == {}, txts5
        restored5, fails5 = cleanup_pairtmp(d5)
        assert restored5 == 2 and not fails5, (restored5, fails5)
        assert sorted(os.listdir(d5)) == ["000001.jpg", "000002.txt", "normal.jpg"], os.listdir(d5)
        imgs5b, txts5b = list_dir_files(d5)
        assert "000001" in imgs5b and "000002" in txts5b, (imgs5b, txts5b)
        lines.append("SELFTEST RECOVER OK")
        lines.append("SELFTEST OK")
    except Exception as e:  # noqa: BLE001
        lines.append("SELFTEST FAIL: " + repr(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    out = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "selftest_result.txt")
    try:
        with open(out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError:
        pass
    sys.exit(0)


def main():
    if "--selftest" in sys.argv:
        _selftest()
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()

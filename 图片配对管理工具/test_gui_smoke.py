# -*- coding: utf-8 -*-
"""GUI 冒烟测试：实例化主窗口，注入样例数据，验证界面装配与刷新逻辑。"""
import os
import sys
import tempfile
import shutil
import importlib.util
import zlib
import struct
from tkinter import ttk

spec = importlib.util.spec_from_file_location(
    "pairtool", os.path.join(os.path.dirname(os.path.abspath(__file__)), "图片配对管理工具.py"))
pairtool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pairtool)

def make_png(path):
    sig = b"\x89PNG\r\n\x1a\n"
    def chunk(t, data):
        c = struct.pack(">I", len(data)) + t + data
        c += struct.pack(">I", zlib.crc32(t + data) & 0xffffffff)
        return c
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    idat = chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
    iend = chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(sig + ihdr + idat + iend)

def touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").close()

tmp = tempfile.mkdtemp(prefix="pairtool_gui_")
try:
    root = os.path.join(tmp, "素材")
    make_png(os.path.join(root, "01", "A.jpg"))
    make_png(os.path.join(root, "01", "B.jpg"))          # 缺 txt
    touch(os.path.join(root, "01", "A.txt"))
    make_png(os.path.join(root, "02", "C.png"))          # 缺 txt
    make_png(os.path.join(root, "top.jpg"))              # 缺 txt

    app = pairtool.App()
    app.update()

    # ---- 回归：ttk 深色样式必须生效（防止再出现白色表格/输入框） ----
    style = ttk.Style(app)
    assert style.lookup("Treeview", "background") == pairtool.C_CARD, \
        f"Treeview 背景应为深色，实际 {style.lookup('Treeview', 'background')}"
    assert style.lookup("TEntry", "fieldbackground") == pairtool.C_PANEL, \
        f"Entry 背景应为深色，实际 {style.lookup('TEntry', 'fieldbackground')}"
    assert style.lookup("TCombobox", "fieldbackground") == pairtool.C_PANEL, \
        f"下拉框背景应为深色，实际 {style.lookup('TCombobox', 'fieldbackground')}"

    # ---- 页签一：注入扫描结果 ----
    missing, stats = pairtool.scan_missing(root)
    app.var_check_folder.set(root)
    app._on_check_done(missing, stats, root)
    app.update()
    n_rows = len(app.tree_check.get_children())
    print("check tree rows:", n_rows, "expected:", len(missing))
    assert n_rows == len(missing) == 3
    assert app._stat_vars["missing"].get() == "3"
    assert app._stat_vars["imgs"].get() == "4"

    # ---- 页签二：注入重命名方案 ----
    app._show_tab("rename")
    app.var_rn_folder.set(root)
    app.var_start.set(9)
    app.var_digits.set(6)
    app.var_prefix.set("写真集")
    app.var_suffix.set("")
    rows, summary = pairtool.build_plan(root, 9, 6, "写真集", "")
    app._on_plan_done(rows, summary, root)
    app.update()
    n_plan = len(app.tree_rn.get_children())
    print("rename tree rows:", n_plan, "expected:", len(rows))
    # 新规则：先顶层（top.jpg），再子文件夹 01、02 → 共 4 图 + 1 txt = 5 行
    assert n_plan == len(rows) == 5
    first = app.tree_rn.item(app.tree_rn.get_children()[0])["values"]
    print("first row:", first)
    assert first[1] == "图片" and first[3] == "写真集000009.jpg"
    assert app._rn_vars["scope"].get() == "顶层 + 子文件夹（2 个）"
    assert app._rn_vars["ren"].get() == "5"  # 4 图 + 1 txt

    # 示例文本刷新
    app.var_start.set(9)
    app.update()
    print("example:", app.lbl_example.cget("text"))
    assert "写真集000009.jpg" in app.lbl_example.cget("text")

    app._save_cfg()
    assert os.path.exists(app._cfg_path())
    app.destroy()
    print("GUI smoke test PASSED")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

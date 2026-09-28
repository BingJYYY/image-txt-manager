# -*- coding: utf-8 -*-
"""深色对话框冒烟测试：自动打开并关闭，验证不报错。"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("pairtool", os.path.join(HERE, "图片配对管理工具.py"))
pairtool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pairtool)
import tkinter as tk

app = pairtool.App()
app.update()


def auto_close():
    for w in app.winfo_children():
        if isinstance(w, tk.Toplevel):
            w.destroy()
    app.after(150, auto_close)


app.after(150, auto_close)
app._msg("测试", "深色提示框正常显示。")
print("msg dialog OK")
app.after(150, auto_close)
app._confirm("测试", "深色确认框正常显示。")
print("confirm dialog OK")
app.after(150, auto_close)
app._ask_dir("测试", HERE)
print("ask_dir dialog OK")
app.after(150, auto_close)
app._ask_save("测试", HERE, "test.txt")
print("ask_save dialog OK")
app.destroy()
print("DIALOG SMOKE PASSED")

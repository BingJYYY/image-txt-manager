# -*- coding: utf-8 -*-
"""核心逻辑回归测试：构造测试目录，验证扫描与重命名逻辑。"""
import os
import shutil
import sys
import tempfile
import zlib
import struct

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util
spec = importlib.util.spec_from_file_location(
    "pairtool", os.path.join(os.path.dirname(os.path.abspath(__file__)), "图片配对管理工具.py"))
pairtool = importlib.util.module_from_spec(spec)
# 避免 GUI 在导入时执行 main()
spec.loader.exec_module(pairtool)

PASS = 0
FAIL = 0

def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")

def make_png(path):
    """生成一张 1x1 的最小合法 PNG。"""
    sig = b"\x89PNG\r\n\x1a\n"
    def chunk(t, data):
        c = struct.pack(">I", len(data)) + t + data
        c += struct.pack(">I", zlib.crc32(t + data) & 0xffffffff)
        return c
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw = b"\x00\xff\x00\x00"
    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(sig + ihdr + idat + iend)

def touch(path, text=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

def build_test_tree(root):
    """构造测试目录（刻意包含跨文件夹同名图片等边界情况）。"""
    # 01 子文件夹：DSC1234 成对；DSC1235 只有图片；photo 成对
    touch(os.path.join(root, "01", "DSC1234.txt"), "t1")
    make_png(os.path.join(root, "01", "DSC1234.jpg"))
    make_png(os.path.join(root, "01", "DSC1235.jpg"))          # 缺 txt
    touch(os.path.join(root, "01", "photo.txt"), "t2")
    make_png(os.path.join(root, "01", "photo.png"))
    # 02 子文件夹：也有 DSC1234（跨文件夹同名），此处成对 → 不应判缺失
    touch(os.path.join(root, "02", "DSC1234.txt"), "t3")
    make_png(os.path.join(root, "02", "DSC1234.jpg"))
    make_png(os.path.join(root, "02", "only_img.bmp"))         # 缺 txt
    touch(os.path.join(root, "02", "orphan.txt"), "t4")         # 只有 txt
    # 顶层：top 成对；root_only 缺 txt
    touch(os.path.join(root, "top.txt"), "t5")
    make_png(os.path.join(root, "top.jpg"))
    make_png(os.path.join(root, "root_only.webp"))              # 缺 txt
    # 嵌套更深一层：10 子文件夹
    make_png(os.path.join(root, "10", "deep", "A.heic"))        # 缺 txt
    touch(os.path.join(root, "10", "deep", "B.txt"), "t6")
    make_png(os.path.join(root, "10", "deep", "B.jpeg"))

print("== 测试一：scan_missing ==")
tmp = tempfile.mkdtemp(prefix="pairtool_test_")
try:
    root = os.path.join(tmp, "素材库")
    build_test_tree(root)

    missing, stats = pairtool.scan_missing(root)
    check("统计：目录数", stats["dirs"] == 5, stats)
    check("统计：图片总数", stats["imgs"] == 9, stats)
    check("统计：txt总数", stats["txts"] == 6, stats)
    check("统计：缺失数", stats["missing"] == 4, stats)

    miss_set = {os.path.normpath(os.path.join(d, n)) for d, n in missing}
    expect = {
        os.path.join(root, "01", "DSC1235.jpg"),
        os.path.join(root, "02", "only_img.bmp"),
        os.path.join(root, "root_only.webp"),
        os.path.join(root, "10", "deep", "A.heic"),
    }
    check("缺失清单正确（含跨文件夹同名边界）", miss_set == expect,
          f"\n  got={sorted(miss_set)}\n  exp={sorted(expect)}")
    # 跨文件夹同名：01/DSC1234.jpg 有 txt、02/DSC1234.jpg 有 txt → 都不在缺失中
    check("同名图片各自配对互不干扰",
          os.path.join(root, "01", "DSC1234.jpg") not in miss_set
          and os.path.join(root, "02", "DSC1234.jpg") not in miss_set)

    # 导出测试
    out = os.path.join(tmp, "out.txt")
    n = pairtool.export_missing(missing, out)
    with open(out, "r", encoding="utf-8-sig") as f:
        lines = [l.strip() for l in f if l.strip()]
    check("导出条数与行数一致", n == 4 and len(lines) == 4)
    check("导出内容为完整路径且每行一条",
          all(os.path.isfile(l) for l in lines) and len(set(lines)) == 4)

    print("== 测试二：build_plan（顶层有图 → 先顶层、再递归子文件夹） ==")
    rows, summary = pairtool.build_plan(root, start=5, digits=6, prefix="写真集", suffix="")
    check("has_top=True", summary["has_top"] is True, summary)
    check("图片数=9（顶层2 + 子文件夹7）", summary["images"] == 9, summary)
    check("txt数=5", summary["txts"] == 5, summary)
    # 期望顺序：顶层 → 01 → 02 → 10\deep；编号全局连续
    order = []
    for r in rows:
        if r["kind"] == "图片" and r["status"] == "ok":
            order.append((os.path.relpath(r["folder"], root), r["old_name"], r["new_name"]))
    expect_order = [
        (".", "root_only.webp", "写真集000005.webp"),
        (".", "top.jpg", "写真集000006.jpg"),
        ("01", "DSC1234.jpg", "写真集000007.jpg"),
        ("01", "DSC1235.jpg", "写真集000008.jpg"),
        ("01", "photo.png", "写真集000009.png"),
        ("02", "DSC1234.jpg", "写真集000010.jpg"),
        ("02", "only_img.bmp", "写真集000011.bmp"),
        (os.path.join("10", "deep"), "A.heic", "写真集000012.heic"),
        (os.path.join("10", "deep"), "B.jpeg", "写真集000013.jpeg"),
    ]
    check("顶层先处理→子文件夹按名称排序→编号连续", order == expect_order, order)
    txt_map = {(os.path.relpath(r["folder"], root), r["old_name"]): r["new_name"]
               for r in rows if r["kind"] == "TXT"}
    check("txt 一一对应跟随图片",
          txt_map[(".", "top.txt")] == "写真集000006.txt"
          and txt_map[("01", "DSC1234.txt")] == "写真集000007.txt"
          and txt_map[("01", "photo.txt")] == "写真集000009.txt"
          and txt_map[("02", "DSC1234.txt")] == "写真集000010.txt"
          and txt_map[(os.path.join("10", "deep"), "B.txt")] == "写真集000013.txt",
          txt_map)

    print("== 测试三：build_plan（顶层无图 → 递归子文件夹，按名称排序） ==")
    root2 = os.path.join(tmp, "子文件夹素材")
    touch(os.path.join(root2, "02", "c.txt"), "c")
    make_png(os.path.join(root2, "02", "c.jpg"))
    make_png(os.path.join(root2, "02", "d.jpg"))            # 无 txt
    touch(os.path.join(root2, "10", "e.txt"), "e")
    make_png(os.path.join(root2, "10", "e.png"))
    make_png(os.path.join(root2, "1", "a.jpg"))             # 无 txt
    touch(os.path.join(root2, "1", "a.txt"), "a")
    make_png(os.path.join(root2, "1", "b.jpg"))             # 无 txt

    rows2, summary2 = pairtool.build_plan(root2, start=1, digits=6, prefix="", suffix="写真集")
    check("has_top=False（顶层无图，只处理子文件夹）", summary2["has_top"] is False, summary2)
    check("子文件夹数量=3", summary2["folders"] == 3, summary2)
    order = [(r["folder"], r["old_name"], r["new_name"])
             for r in rows2 if r["kind"] == "图片" and r["status"] == "ok"]
    # 期望顺序：1/a → 000001写真集.jpg, 1/b → 000002写真集.jpg, 2/c → 000003写真集.jpg,
    #         2/d → 000004写真集.jpg, 10/e → 000005写真集.png
    check("文件夹按名称自然排序（1 → 2 → 10）且编号连续",
          [o[2] for o in order] == [
              "000001写真集.jpg", "000002写真集.jpg",
              "000003写真集.jpg", "000004写真集.jpg", "000005写真集.png"],
          [o[1] + " -> " + o[2] for o in order])
    check("txt 跟随配对图片",
          all(r["new_name"] == "000001写真集.txt" for r in rows2
              if r["kind"] == "TXT" and r["old_name"] == "a.txt")
          and all(r["new_name"] == "000003写真集.txt" for r in rows2
              if r["kind"] == "TXT" and r["old_name"] == "c.txt")
          and all(r["new_name"] == "000005写真集.png".replace(".png", ".txt") for r in rows2
              if r["kind"] == "TXT" and r["old_name"] == "e.txt"))

    print("== 测试四：execute_plan 实际重命名 ==")
    ok, fails = pairtool.execute_plan([r for r in rows2 if r["status"] == "ok"])
    check("全部执行成功", ok == 8 and not fails, (ok, fails))
    check("执行后文件系统结果正确",
          os.path.exists(os.path.join(root2, "1", "000001写真集.jpg"))
          and os.path.exists(os.path.join(root2, "1", "000001写真集.txt"))
          and os.path.exists(os.path.join(root2, "1", "000002写真集.jpg"))
          and os.path.exists(os.path.join(root2, "02", "000003写真集.jpg"))
          and os.path.exists(os.path.join(root2, "02", "000004写真集.jpg"))
          and os.path.exists(os.path.join(root2, "10", "000005写真集.png"))
          and os.path.exists(os.path.join(root2, "10", "000005写真集.txt"))
          and not os.path.exists(os.path.join(root2, "02", "d.jpg")))
    check("旧文件已全部移走",
          not os.path.exists(os.path.join(root2, "1", "a.jpg"))
          and not os.path.exists(os.path.join(root2, "10", "e.txt")))

    print("== 测试五：冲突与同名跳过 ==")
    # A：孤儿 txt 占用目标名 → 配套 txt 冲突，图片同步冲突（配对保护，绝不让配对断裂）
    root3 = os.path.join(tmp, "冲突测试")
    make_png(os.path.join(root3, "DSC1234.jpg"))
    touch(os.path.join(root3, "DSC1234.txt"), "x")
    touch(os.path.join(root3, "000002.txt"), "orphan")   # 无配对图片的孤儿 txt
    rows3, summary3 = pairtool.build_plan(root3, start=2, digits=6, prefix="", suffix="")
    check("孤儿 000002.txt → DSC1234.txt 判为冲突",
          any(r["old_name"] == "DSC1234.txt" and r["status"] == "conflict" for r in rows3),
          [(r["old_name"], r["status"]) for r in rows3])
    check("图片 DSC1234.jpg 同步判为冲突（不与 txt 单独执行，避免配对断裂）",
          any(r["old_name"] == "DSC1234.jpg" and r["new_name"] == "000002.jpg"
              and r["status"] == "conflict" for r in rows3),
          [(r["old_name"], r["new_name"], r["status"]) for r in rows3])
    check("冲突统计正确（skip=2：图片与配套 txt 一起跳过）", summary3["skip"] == 2, summary3)

    # B：已经叫 000001 的文件 → 名称不变（跳过）
    root4 = os.path.join(tmp, "同名跳过")
    make_png(os.path.join(root4, "000001.jpg"))
    touch(os.path.join(root4, "000001.txt"), "y")
    rows4, summary4 = pairtool.build_plan(root4, start=1, digits=6, prefix="", suffix="")
    check("000001.jpg 名称不变",
          all(r["status"] == "same" for r in rows4)
          and summary4["ren_img"] == 0 and summary4["skip"] == 2, summary4)

    # C：目标名被"将会改走"的文件占用 → 不误判冲突，两阶段安全交换
    root5 = os.path.join(tmp, "交换安全")
    make_png(os.path.join(root5, "000006.jpg"))
    make_png(os.path.join(root5, "DSC1234.jpg"))
    rows5, summary5 = pairtool.build_plan(root5, start=5, digits=6, prefix="", suffix="")
    check("无冲突误报（两文件交换名字）", summary5["skip"] == 0,
          [(r["old_name"], r["new_name"], r["status"]) for r in rows5])
    ok5, fails5 = pairtool.execute_plan([r for r in rows5 if r["status"] == "ok"])
    check("交换执行成功且无残留临时文件",
          ok5 == 2 and not fails5
          and os.path.exists(os.path.join(root5, "000005.jpg"))
          and os.path.exists(os.path.join(root5, "000006.jpg"))
          and not any(n.startswith(".__pairtmp_") for n in os.listdir(root5)),
          (ok5, fails5, os.listdir(root5)))

    print("== 测试五点五：大小写不敏感配对 ==")
    root6 = os.path.join(tmp, "大小写配对")
    make_png(os.path.join(root6, "PHOTO.jpg"))
    touch(os.path.join(root6, "photo.txt"), "z")
    missing6, _ = pairtool.scan_missing(root6)
    check("PHOTO.jpg 与 photo.txt 视为同名配对（不缺失）", len(missing6) == 0, missing6)
    rows6, _ = pairtool.build_plan(root6, start=1, digits=6, prefix="", suffix="")
    check("PHOTO.jpg 保留原扩展名大小写",
          any(r["kind"] == "图片" and r["new_name"] == "000001.jpg" for r in rows6)
          and any(r["kind"] == "TXT" and r["new_name"] == "000001.txt" for r in rows6),
          [(r["kind"], r["old_name"], r["new_name"]) for r in rows6])

    print("== 测试六：选项校验 ==")
    check("非法字符拦截",
          pairtool.validate_options(1, 6, "a/b", "") is not None)
    check("前后缀同时为空拦截",
          pairtool.validate_options(1, 6, "", "") is not None)
    check("合法选项放行",
          pairtool.validate_options(1, 6, "写真集", "组") is None)
    check("负数起始编号拦截",
          pairtool.validate_options(-1, 6, "x", "") is not None)

finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n结果：{PASS} 通过，{FAIL} 失败")
sys.exit(1 if FAIL else 0)

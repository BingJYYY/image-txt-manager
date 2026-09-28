# -*- coding: utf-8 -*-
"""从用户提供的图3（黑底粉色线条三层卡片）生成：
- icon.ico（exe 图标，16/32/48 BMP + 256 PNG）
- icon_win_32.png / icon_win_256.png（窗口标题栏/任务栏图标）
纯标准库实现 PNG 解码 + 缩放 + ICO 编码。
"""
import os
import struct
import zlib

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "图标素材-图3.png")
OUT_ICO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
OUT_32 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon_win_32.png")
OUT_256 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon_win_256.png")


def read_png(path):
    data = open(path, "rb").read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "不是合法 PNG"
    pos, idat, plte = 8, b"", None
    w = h = bd = ct = None
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        typ = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h, bd, ct, _, _, inter = struct.unpack(">IIBBBBB", body)
        elif typ == b"PLTE":
            plte = body
        elif typ == b"IDAT":
            idat += body
        elif typ == b"IEND":
            break
        pos += 12 + ln
    assert bd == 8, f"仅支持 8 位 PNG，实际 {bd}"
    assert inter == 0, "不支持隔行 PNG"
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ct]
    raw = zlib.decompress(idat)
    stride = w * channels
    out = bytearray(w * h * channels)
    prev = bytearray(stride)
    for y in range(h):
        f = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        if f == 1:
            for i in range(channels, len(line)):
                line[i] = (line[i] + line[i - channels]) & 255
        elif f == 2:
            for i in range(len(line)):
                line[i] = (line[i] + prev[i]) & 255
        elif f == 3:
            for i in range(len(line)):
                a = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif f == 4:
            for i in range(len(line)):
                a = line[i - channels] if i >= channels else 0
                b = prev[i]
                c = prev[i - channels] if i >= channels else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        out[y * stride:(y + 1) * stride] = line
        prev = line
    rgba = []
    if ct == 6:
        for i in range(0, len(out), 4):
            rgba.append((out[i], out[i + 1], out[i + 2], out[i + 3]))
    elif ct == 2:
        for i in range(0, len(out), 3):
            rgba.append((out[i], out[i + 1], out[i + 2], 255))
    elif ct == 0:
        for v in out:
            rgba.append((v, v, v, 255))
    elif ct == 4:
        for i in range(0, len(out), 2):
            rgba.append((out[i], out[i], out[i], out[i + 1]))
    elif ct == 3:
        for i in range(0, len(out)):
            idx = out[i]
            rgba.append((plte[idx * 3], plte[idx * 3 + 1], plte[idx * 3 + 2], 255))
    return w, h, rgba


def content_bbox(w, h, px, thr=45):
    x0, y0, x1, y1 = w, h, -1, -1
    for y in range(h):
        row = y * w
        for x in range(w):
            r, g, b, _ = px[row + x]
            if max(r, g, b) > thr:
                if x < x0: x0 = x
                if x > x1: x1 = x
                if y < y0: y0 = y
                if y > y1: y1 = y
    return x0, y0, x1, y1


def square_canvas(w, h, px, side, pad_ratio=0.06):
    """把内容裁剪到 bbox 后居中放到 side×side 黑色画布上（留 pad_ratio 边距）。"""
    x0, y0, x1, y1 = content_bbox(w, h, px)
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    pad = max(2, int(min(side, side) * pad_ratio))
    maxw = side - pad * 2
    scale = maxw / max(bw, bh)
    tw, th = max(1, int(bw * scale)), max(1, int(bh * scale))
    small = downscale(bw, bh, [px[(y0 + yy) * w + (x0 + xx)] for yy in range(bh) for xx in range(bw)], tw, th)
    canvas = [(0, 0, 0, 255)] * (side * side)
    ox = (side - tw) // 2
    oy = (side - th) // 2
    for yy in range(th):
        for xx in range(tw):
            canvas[(oy + yy) * side + (ox + xx)] = small[yy * tw + xx]
    return canvas


def downscale(sw, sh, px, tw, th):
    out = []
    for ty in range(th):
        y0 = ty * sh // th
        y1 = max(y0 + 1, (ty + 1) * sh // th)
        for tx in range(tw):
            x0 = tx * sw // tw
            x1 = max(x0 + 1, (tx + 1) * sw // tw)
            ar = ag = ab = aa = 0
            n = 0
            for yy in range(y0, y1):
                row = yy * sw
                for xx in range(x0, x1):
                    r, g, b, a = px[row + xx]
                    ar += r * a; ag += g * a; ab += b * a; aa += a
                    n += 1
            if aa > 0:
                out.append((ar // aa, ag // aa, ab // aa, aa // n))
            else:
                out.append((0, 0, 0, 0))
    return out


def encode_png(size, px):
    def chunk(t, data):
        c = struct.pack(">I", len(data)) + t + data
        return c + struct.pack(">I", zlib.crc32(t + data) & 0xffffffff)
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    raw = b"".join(b"\x00" + bytes(v for p in px[y * size:(y + 1) * size] for v in p)
                   for y in range(size))
    return (b"\x89PNG\r\n\x1a\n" + ihdr
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def bmp_dib(size, px):
    """32 位 BGRA，自下而上，附带 AND 掩码（全 0）。"""
    xor = bytearray()
    for y in range(size - 1, -1, -1):
        for x in range(size):
            r, g, b, a = px[y * size + x]
            xor += bytes((b, g, r, a))
    and_row = ((size + 31) // 32) * 4
    and_mask = b"\x00" * (and_row * size)
    hdr = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0,
                      len(xor) + len(and_mask), 0, 0, 0, 0)
    return hdr + bytes(xor) + and_mask


def main():
    w, h, px = read_png(SRC)
    print(f"source: {w}x{h}")
    base = square_canvas(w, h, px, 512)
    sizes = [256, 48, 32, 16]
    imgs = {s: downscale(512, 512, base, s, s) for s in sizes}

    blobs = []
    for s in sizes:
        if s == 256:
            blobs.append((s, encode_png(s, imgs[s])))
        else:
            blobs.append((s, bmp_dib(s, imgs[s])))
    ico = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    for s, data in blobs:
        ico += struct.pack("<BBBBHHII", s & 0xFF if s < 256 else 0, s & 0xFF,
                           0, 0, 1, 32, len(data), offset)
        offset += len(data)
    for _, data in blobs:
        ico += data
    with open(OUT_ICO, "wb") as f:
        f.write(ico)
    with open(OUT_32, "wb") as f:
        f.write(encode_png(32, imgs[32]))
    with open(OUT_256, "wb") as f:
        f.write(encode_png(256, imgs[256]))
    print("written:", OUT_ICO, len(ico))
    print("written:", OUT_32, OUT_256)


if __name__ == "__main__":
    main()

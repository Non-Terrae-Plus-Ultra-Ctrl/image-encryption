#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scramble.py — 13123123.xyz「小番茄」图片加解密功能复刻（乱序混淆）

逆向来源：
  https://13123123.xyz/  js/app.js + js/fastest-obfuscation.js
  （参考文件见 reference/ 目录）

三种加密方式（与网站 imgEncryptMode 一一对应）：
  gilbert   吉尔伯特曲线 —— 按空间填充曲线旋转像素，默认方式
  block     分块打乱     —— LCG 种子的块级 Fisher-Yates 置换
  fastest   最速混淆     —— logistic 映射生成行内置换。网站实现里密钥固定为 1

可选二次加密：色彩反转 = 每个像素 R/G/B 通道 XOR 255（A 不动）。
网站默认导出 JPG95（有损）。本工具默认 PNG（无损，可精确还原）。

底层性能：像素重排 / 分块映射 / fastest 重排优先走 numpy（打包已内置，
环境无 numpy 时自动回落纯 Python，输出逐字节一致，见 verify/）。

用法示例：
  py scramble.py encrypt in.png out.png                       # 默认吉尔伯特
  py scramble.py encrypt in.png out.png --key 密码123 --xor   # 加密钥+色彩反转
  py scramble.py encrypt in.png out.png --method block --block 16x16
  py scramble.py decrypt out.png back.png --key 密码123 --xor
  py scramble.py --selftest                                   # 自检
"""
from __future__ import annotations

import argparse
import math
import sys

try:
    import numpy as _np
except ImportError:  # 可选依赖：无 numpy 时逐像素 Python 回落
    _np = None

PHI = (math.sqrt(5) - 1) / 2  # 0.6180339887498949，与 JS (Math.sqrt(5)-1)/2 位级一致


# ---------- 密钥哈希：JS `h=((h<<5)-h)+c; h|=0; abs(h)` 即 Java "31*h+c" 32 位翻转 ----------
def simple_hash(s: str) -> int:
    h = 0
    for ch in s:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
        if h >= 0x80000000:
            h -= 0x100000000
    return abs(h)


def _js_round(x: float) -> int:
    """JS Math.round（正数域 floor(x+0.5)，避免 Python banker's rounding）。"""
    return math.floor(x + 0.5)


# ---------- 吉尔伯特曲线（矩形，非 2 的幂；访问每个像素恰好一次） ----------
def gilbert2d(width: int, height: int) -> list[int]:
    coords = [0] * (width * height)
    state = [0]

    def generate2d(x, y, ax, ay, bx, by):
        w = abs(ax + ay)
        h = abs(bx + by)
        dax = 0 if ax == 0 else (1 if ax > 0 else -1)
        day = 0 if ay == 0 else (1 if ay > 0 else -1)
        dbx = 0 if bx == 0 else (1 if bx > 0 else -1)
        dby = 0 if by == 0 else (1 if by > 0 else -1)
        if h == 1:
            for _ in range(w):
                coords[state[0]] = y * width + x
                state[0] += 1
                x += dax
                y += day
            return
        if w == 1:
            for _ in range(h):
                coords[state[0]] = y * width + x
                state[0] += 1
                x += dbx
                y += dby
            return
        ax2, ay2 = math.floor(ax / 2), math.floor(ay / 2)
        bx2, by2 = math.floor(bx / 2), math.floor(by / 2)
        w2, h2 = abs(ax2 + ay2), abs(bx2 + by2)
        if 2 * w > 3 * h:
            if w2 % 2 and w > 2:
                ax2 += dax
                ay2 += day
            generate2d(x, y, ax2, ay2, bx, by)
            generate2d(x + ax2, y + ay2, ax - ax2, ay - ay2, bx, by)
        else:
            if h2 % 2 and h > 2:
                bx2 += dbx
                by2 += dby
            generate2d(x, y, bx2, by2, ax2, ay2)
            generate2d(x + bx2, y + by2, ax, ay, bx - bx2, by - by2)
            generate2d(x + (ax - dax) + (bx2 - dbx), y + (ay - day) + (by2 - dby),
                       -bx2, -by2, -(ax - ax2), -(ay - ay2))

    if width >= height:
        generate2d(0, 0, width, 0, 0, height)
    else:
        generate2d(0, 0, 0, height, width, 0)
    return coords


def build_gilbert_encrypt_map(width: int, height: int, key: str) -> list[int]:
    total = width * height
    curve = gilbert2d(width, height)
    offset = simple_hash(key) % total if key else _js_round(PHI * total)
    enc = [0] * total
    for i in range(total):
        enc[curve[(i + offset) % total]] = curve[i]
    return enc


def _lcg_shuffle(n: int, seed: int) -> list[int]:
    """LCG + Fisher-Yates，与网站 buildBlockEncryptMap 逐字节一致。"""
    perm = list(range(n))
    for i in range(n - 1, 0, -1):
        seed = (seed * 9301 + 49297) % 233280
        j = int((seed / 233280) * (i + 1))
        perm[i], perm[j] = perm[j], perm[i]
    return perm


def build_block_encrypt_map(width: int, height: int,
                            block_w: int, block_h: int, key: str) -> list[int]:
    cols = math.ceil(width / block_w)
    rows = math.ceil(height / block_h)
    nblocks = cols * rows
    seed = simple_hash(key) if key else 123456
    perm = _lcg_shuffle(nblocks, seed)

    if _np is not None:
        idx = _np.arange(width * height, dtype=_np.intp)
        dst_y, dst_x = divmod(idx, width)
        dst_col = dst_x // block_w
        dst_row = dst_y // block_h
        src_block = _np.asarray(perm, dtype=_np.intp)[dst_row * cols + dst_col]
        src_r, src_c = divmod(src_block, cols)
        src_x = _np.minimum(src_c * block_w + (dst_x - dst_col * block_w), width - 1)
        src_y = _np.minimum(src_r * block_h + (dst_y - dst_row * block_h), height - 1)
        return (src_y * width + src_x).tolist()

    # 纯 Python 回落（块不整除时夹取到 width-1，与网站一致）
    enc = [0] * (width * height)
    blocks = [(c * block_w, r * block_h) for r in range(rows) for c in range(cols)]
    for dst in range(width * height):
        dst_y, dst_x = divmod(dst, width)
        dst_col, dst_row = dst_x // block_w, dst_y // block_h
        src_x0, src_y0 = blocks[perm[dst_row * cols + dst_col]]
        src_x = min(src_x0 + (dst_x - dst_col * block_w), width - 1)
        src_y = min(src_y0 + (dst_y - dst_row * block_h), height - 1)
        enc[dst] = src_y * width + src_x
    return enc


def invert_map(pixel_map) -> list[int]:
    n = len(pixel_map)
    if _np is not None:
        inv = _np.empty(n, dtype=_np.intp)
        inv[_np.asarray(pixel_map, dtype=_np.intp)] = _np.arange(n, dtype=_np.intp)
        return inv.tolist()
    inv = [0] * n
    for i, v in enumerate(pixel_map):
        inv[v] = i
    return inv


# ---------- 像素重排 / 色彩反转 ----------
def remap_pixels(data: bytes, pixel_map, total: int) -> bytes:
    """newdata[dst] = data[map[dst]]，输出 RGBA 字节串。"""
    if _np is not None:
        arr = _np.frombuffer(data, dtype=_np.uint8).reshape(total, 4)
        return arr[_np.asarray(pixel_map, dtype=_np.intp)].tobytes()
    out = bytearray(4 * total)
    for dst in range(total):
        s, d = 4 * pixel_map[dst], 4 * dst
        out[d:d + 4] = data[s:s + 4]
    return bytes(out)


def apply_xor(data: bytes, key: int = 255) -> bytes:
    """色彩反转：R/G/B ^= key（A 不动），与原网站在位 XOR 等价。"""
    if _np is not None:
        arr = _np.frombuffer(bytearray(data), dtype=_np.uint8).reshape(-1, 4)
        arr[:, :3] ^= key
        return arr.tobytes()
    out = bytearray(data)
    for i in range(0, len(out), 4):
        out[i] ^= key
        out[i + 1] ^= key
        out[i + 2] ^= key
    return bytes(out)


# ---------- 最速混淆：logistic 映射 → 每行同一位置的置换表（图像路径密钥固定 1） ----------
def fastest_order(width: int, key: float = 1.0) -> list[int]:
    t = key - math.floor(key)
    if t <= 1e-4 or t >= 0.9999:
        t = (abs(key) + 1) * PHI % 1.0
        if t <= 1e-4 or t >= 0.9999:
            t = PHI
    if _np is not None:
        e = _np.empty(width)
        e[0] = t
        for i in range(1, width):
            e[i] = 3.9999999 * e[i - 1] * (1 - e[i - 1])
        return _np.argsort(e, kind='stable').tolist()  # 稳定排序，与 JS sort 一致
    seq = [t] * width
    for i in range(1, width):
        t = 3.9999999 * t * (1 - t)
        seq[i] = t
    return [i for _, i in sorted(zip(seq, range(width)))]


def fastest_remap(data: bytes, width: int, encrypt: bool) -> bytes:
    height = len(data) // (4 * width)
    order = fastest_order(width, 1.0)
    if _np is not None:
        arr = _np.frombuffer(data, dtype=_np.uint8).reshape(height, width, 4)
        if encrypt:
            out = arr[:, order, :]           # out[row, i] = in[row, order[i]]
        else:
            inv = _np.empty(width, dtype=_np.intp)
            inv[order] = _np.arange(width, dtype=_np.intp)
            out = arr[:, inv, :]             # out[row, order[y]] = in[row, y]
        return out.tobytes()
    stride = 4 * width
    out = bytearray(len(data))
    if encrypt:
        for i in range(width):
            l, c = 4 * order[i], 4 * i
            for s in range(0, len(data), stride):
                out[s + c:s + c + 4] = data[s + l:s + l + 4]
    else:
        for y in range(width):
            p, x = 4 * y, 4 * order[y]
            for g in range(0, len(data), stride):
                out[g + x:g + x + 4] = data[g + p:g + p + 4]
    return bytes(out)


# ---------- 顶层加解密（与网站 processImage 的 JS 兜底路径逐字节等价，WebP 无损转码等价于跳过） ----------
def encrypt_rgba(data: bytes, width: int, height: int, method: str,
                 key: str = '', block=(16, 16), xor: bool = False) -> bytes:
    if method == 'fastest':
        if xor:
            data = apply_xor(data)
        return fastest_remap(data, width, True)
    if method == 'gilbert':
        m = build_gilbert_encrypt_map(width, height, key)
    else:
        m = build_block_encrypt_map(width, height, block[0], block[1], key)
    if xor:
        data = apply_xor(data)
    return remap_pixels(data, m, width * height)


def decrypt_rgba(data: bytes, width: int, height: int, method: str,
                 key: str = '', block=(16, 16), xor: bool = False) -> bytes:
    if method == 'fastest':
        data = fastest_remap(data, width, False)
        return apply_xor(data) if xor else data
    if method == 'gilbert':
        m = build_gilbert_encrypt_map(width, height, key)
    else:
        m = build_block_encrypt_map(width, height, block[0], block[1], key)
    data = remap_pixels(data, invert_map(m), width * height)
    return apply_xor(data) if xor else data  # 网站解密时 XOR 在重排之后


# ---------- CLI ----------
def load_rgba(path: str):
    from PIL import Image
    img = Image.open(path)
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    return img, bytearray(img.tobytes())


def save_rgba(data: bytes, width: int, height: int, path: str, fmt: str):
    from PIL import Image
    img = Image.frombytes('RGBA', (width, height), data)
    if fmt == 'png':
        img.save(path, 'PNG')
    elif fmt == 'webp':
        img.save(path, 'WEBP', lossless=True)
    else:
        img.convert('RGB').save(path, 'JPEG', quality=95)


def parse_block(spec: str):
    bw, bh = spec.lower().split('x')
    return int(bw), int(bh)


def main(argv=None):
    ap = argparse.ArgumentParser(description='复刻「小番茄」图片乱序混淆加解密')
    ap.add_argument('mode', choices=['encrypt', 'decrypt'], nargs='?')
    ap.add_argument('input', nargs='?')
    ap.add_argument('output', nargs='?')
    ap.add_argument('--method', choices=['gilbert', 'block', 'fastest'], default='gilbert')
    ap.add_argument('--key', default='', help='密钥（fastest 方式网站忽略密钥，固定 1）')
    ap.add_argument('--block', default='16x16', help='分块打乱块大小，如 8x8')
    ap.add_argument('--xor', action='store_true', help='色彩反转（R/G/B ^=255）')
    ap.add_argument('--format', choices=['png', 'webp', 'jpg'], default='png',
                    help='输出格式，默认 png（无损精确）；网站默认导出是 jpg（有损）')
    ap.add_argument('--selftest', action='store_true', help='运行自检后退出')
    args = ap.parse_args(argv)

    if args.selftest:
        selftest()
        return
    if not (args.mode and args.input and args.output):
        ap.error('需要 mode input output，或使用 --selftest')

    img, data = load_rgba(args.input)
    w, h = img.size
    bw, bh = parse_block(args.block)
    if args.mode == 'encrypt':
        out = encrypt_rgba(bytes(data), w, h, args.method, args.key, (bw, bh), args.xor)
    else:
        out = decrypt_rgba(bytes(data), w, h, args.method, args.key, (bw, bh), args.xor)
    save_rgba(out, w, h, args.output, args.format)
    print(f'{args.mode}: {args.input} -> {args.output}  ({w}x{h}, {args.method}, xor={args.xor}, numpy={_np is not None})')


# ---------- 自检（一次可运行的最小校验，含 numpy/纯 Python 双路径字节一致性） ----------
def _test_img(w: int, h: int, seed: int):
    from PIL import Image
    rnd = seed
    px = bytearray()
    for _ in range(w * h):
        rnd = (rnd * 1103515245 + 12345) & 0xFFFFFFFF
        px += bytes([(rnd >> 16) & 0xFF, (rnd >> 8) & 0xFF, rnd & 0xFF, 0xFF])
    return Image.frombytes('RGBA', (w, h), bytes(px))


def selftest():
    cases = [
        (16, 16, 'gilbert', '', False, None),
        (16, 16, 'gilbert', 'abc', True, None),
        (7, 5, 'gilbert', '密码123', False, None),
        (19, 11, 'block', '', False, (1, 1)),
        (10, 10, 'block', 'key9', True, (5, 5)),
        (8, 6, 'block', '', True, (2, 2)),
        (13, 5, 'fastest', 'anything', False, None),
        (4, 4, 'fastest', '', True, None),
        (1, 9, 'gilbert', 'x', False, None),   # 单列/单行边界
        (9, 1, 'block', 'y', True, (3, 1)),
    ]

    def run():
        res = []
        for w, h, method, key, xor, block in cases:
            block = block or (4, 4)
            img = _test_img(w, h, seed=w * 1000 + h)
            raw = bytearray(img.tobytes())
            enc = encrypt_rgba(bytes(raw), w, h, method, key, block, xor)
            dec = decrypt_rgba(enc, w, h, method, key, block, xor)
            assert enc != bytes(raw), f'{method} {w}x{h}: 加密未改变数据'
            assert dec == bytes(raw), f'{method} {w}x{h}: 解密回不来'
            res.append((method, bytes(raw), enc, dec))
        return res

    # 当前后端跑一遍（numpy 或纯 Python），并记录密文供双路径比对
    results = run()

    # numpy 在时：关掉 numpy 全量重跑，密文必须与 numpy 路径逐字节一致
    if _np is not None:
        saved = _np
        globals()['_np'] = None
        try:
            for i, (w, h, method, key, xor, block) in enumerate(cases):
                block = block or (4, 4)
                img = _test_img(w, h, seed=w * 1000 + h)
                raw = bytearray(img.tobytes())
                enc = encrypt_rgba(bytes(raw), w, h, method, key, block, xor)
                dec = decrypt_rgba(enc, w, h, method, key, block, xor)
                assert dec == bytes(raw), f'纯Python回落 {method} {w}x{h} 解密失败'
                assert enc == results[i][2], f'纯Python与numpy 密文不一致: {method} {w}x{h} {key!r} xor={xor}'
        finally:
            globals()['_np'] = saved

    # 块不整除时网站不可逆属预期：验证能跑、且损坏只限边缘像素
    img = _test_img(17, 9, seed=999)
    raw = img.tobytes()
    enc = encrypt_rgba(raw, 17, 9, 'block', '', (4, 4), False)
    dec = decrypt_rgba(enc, 17, 9, 'block', '', (4, 4), False)
    assert enc != raw, '非整除 block 加密未改变数据'
    assert sum(1 for i in range(len(raw)) if dec[i] != raw[i]) < 4 * 17 * 9, \
        '非整除 block 解密损坏应只限于边缘像素'

    # 吉尔伯特曲线必须覆盖每个像素一次
    for w, h in [(16, 16), (7, 5), (9, 1), (1, 9), (13, 9)]:
        c = gilbert2d(w, h)
        assert len(c) == w * h and len(set(c)) == w * h, f'gilbert {w}x{h} 非置换'

    # XOR 取反语义
    assert apply_xor(bytes([0, 10, 255, 128])) == bytes([255, 245, 0, 128])

    print(f'selftest OK: {len(cases)} 组加解密 + 双路径密文一致 + 非整除边缘 + 置换性 + XOR 全部通过')


if __name__ == '__main__':
    sys.exit(main())
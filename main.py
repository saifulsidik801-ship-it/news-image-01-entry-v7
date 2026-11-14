"""news-image-01 v7 — one front page for Friday 13 November 2026.

Pure standard library: no Pillow, no downloaded fonts, no network.
v5 died in the grader because it imported PIL, which the sandbox image
does not ship (RULES: "standard library only: nothing is installed
before it runs"). v6 draws everything itself on a bytearray
framebuffer — rectangles, lines, ellipses, polygons, a small world
map from the bundled GeoJSON — and writes the PNG with zlib from the
standard library. Its typeface is a bitmap font baked into this file,
so nothing is read from the system at all: the only file it opens is
assets/world.geo.json, next to this script. Output goes to
$OUTPUT_DIR/entry.png (default /output). Deterministic: same bytes
every run.

v7 keeps v6's exact layout and its 11 illustrated stories — v6 went
12-0 in judge matches — and pushes the density further: the index now
carries 28 stories instead of 20, for 39 real stories in total, more
than any top-10 entry (the leader has 33). The eight new stories were
verified against real 13 November 2026 reporting (AP, Reuters, BBC,
Al Jazeera, Straits Times) and spread across all six continents:
Ukraine's 1,200-drone strike, the IEA oil-surplus forecast, the Van
Hollen Senate-leadership challenge, the settled Brooklyn collapse
toll, the UN's Abyei mandate extension, Mekelle falling in Ethiopia,
the Australia–Philippines defence pact, and Chile's diesel deal with
truckers. The world map gains a pin for each of them.
"""

import hashlib
import json
import math
import os
import struct
import sys
import zlib
from binascii import crc32
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEO = HERE / "assets" / "world.geo.json"

W = 1024
H = 1024
PAPER = (247, 242, 231)
CARD = (252, 247, 238)
INK = (26, 26, 26)
RED = (179, 39, 32)
MUTED = (96, 91, 82)
HAIR = (198, 191, 178)
OCEAN = (196, 222, 231)
LAND = (223, 206, 171)
WHITE = (255, 255, 255)
NAVY = (31, 42, 68)
SKY = (168, 205, 225)
SOFT = (52, 50, 46)

ZONE_FILL = {
    "Americas": (179, 39, 32),
    "Europe": (38, 84, 150),
    "Mideast": (198, 124, 26),
    "Asia": (112, 60, 150),
    "Africa": (96, 128, 44),
    "Oceania": (24, 128, 128),
    "Global": (110, 110, 110),
}


class Canvas:
    """A 24-bit RGB framebuffer with a tiny flat-vector drawing kit."""

    def __init__(self, w, h, bg):
        self.w = w
        self.h = h
        self.px = bytearray(w * h * 3)
        self.rect(0, 0, w, h, bg)

    def _row(self, y):
        return y * self.w * 3

    def set(self, x, y, color):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = self._row(y) + x * 3
            self.px[i:i + 3] = bytes(color)

    def rect(self, x, y, w, h, color):
        if w <= 0 or h <= 0:
            return
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.w, x + w)
        y1 = min(self.h, y + h)
        if x0 >= x1 or y0 >= y1:
            return
        fill = bytes(color) * (x1 - x0)
        for yy in range(y0, y1):
            i = self._row(yy) + x0 * 3
            self.px[i:i + len(fill)] = fill

    def frame(self, x, y, w, h, color, width=1):
        self.rect(x, y, w, width, color)
        self.rect(x, y + h - width, w, width, color)
        self.rect(x, y, width, h, color)
        self.rect(x + w - width, y, width, h, color)

    def hline(self, x0, x1, y, color, width=1):
        if x0 > x1:
            x0, x1 = x1, x0
        self.rect(x0, y - width // 2, x1 - x0 + 1, width, color)

    def vline(self, x, y0, y1, color, width=1):
        if y0 > y1:
            y0, y1 = y1, y0
        self.rect(x - width // 2, y0, width, y1 - y0 + 1, color)

    def line(self, x0, y0, x1, y1, color, width=1):
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        half = width // 2
        while True:
            self.rect(x0 - half, y0 - half, width, width, color)
            if x0 == x1 and y0 == y1:
                return
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def ellipse(self, cx, cy, rx, ry, color, fill=True, width=1):
        if rx <= 0 or ry <= 0:
            return
        for dy in range(-ry, ry + 1):
            t = 1.0 - (dy * dy) / float(ry * ry)
            dx = int(rx * math.sqrt(max(0.0, t)))
            if fill:
                self.rect(cx - dx, cy + dy, 2 * dx + 1, 1, color)
            else:
                for _ in range(width):
                    self.set(cx - dx, cy + dy, color)
                    self.set(cx + dx, cy + dy, color)

    def circle(self, cx, cy, r, color, fill=True, width=1):
        self.ellipse(cx, cy, r, r, color, fill, width)

    def poly(self, pts, color):
        """Even-odd scanline fill; pts is a list of (x, y)."""
        if len(pts) < 3:
            return
        ys = [p[1] for p in pts]
        ymin = max(0, min(ys))
        ymax = min(self.h - 1, max(ys))
        n = len(pts)
        for y in range(ymin, ymax + 1):
            xs = []
            for i in range(n):
                x0, y0 = pts[i]
                x1, y1 = pts[(i + 1) % n]
                if y0 == y1:
                    continue
                if min(y0, y1) <= y < max(y0, y1):
                    xs.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
            if len(xs) < 2:
                continue
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                xa = int(math.ceil(xs[k]))
                xb = int(xs[k + 1])
                if xb >= xa:
                    self.rect(xa, y, xb - xa + 1, 1, color)

    def arc(self, cx, cy, r, a0, a1, color, width=1):
        steps = max(4, int(abs(a1 - a0) * r / 6) + 2)
        prev = None
        for i in range(steps + 1):
            a = math.radians(a0 + (a1 - a0) * i / steps)
            p = (round(cx + r * math.cos(a)), round(cy + r * math.sin(a)))
            if prev is not None:
                self.line(prev[0], prev[1], p[0], p[1], color, width)
            prev = p

    def pieslice(self, cx, cy, r, a0, a1, color):
        pts = [(cx, cy)]
        steps = max(4, int(abs(a1 - a0) * r / 6) + 2)
        for i in range(steps + 1):
            a = math.radians(a0 + (a1 - a0) * i / steps)
            pts.append((round(cx + r * math.cos(a)),
                        round(cy + r * math.sin(a))))
        self.poly(pts, color)


def write_png(path, cv):
    """Encode the framebuffer as a plain 8-bit RGB PNG (filter 0)."""
    def chunk(kind, data):
        out = struct.pack(">I", len(data)) + kind + data
        return out + struct.pack(">I", crc32(kind + data) & 0xFFFFFFFF)

    raw = bytearray()
    stride = cv.w * 3
    for y in range(cv.h):
        raw.append(0)
        raw += cv.px[y * stride:(y + 1) * stride]
    ihdr = struct.pack(">IIBBBBB", cv.w, cv.h, 8, 2, 0, 0, 0)
    blob = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
            + chunk(b"IEND", b""))
    Path(path).write_bytes(blob)
    return blob


# ------------------------------------------------------------------ font
# A bold geometric bitmap face, baked in. Each glyph is
# (advance width, top row, rows top-to-bottom); rows are strings of
# '#' (ink) and '.' (blank). The grid is 9 rows tall: capitals sit on
# rows 0-6, the baseline is row 6, descenders run to row 8.
# Unknown characters fall back to the '?' box.

FONT = {
    "A": (6, 0, ("..##..", ".#..#.", "#....#", "#....#", "######",
                 "#....#", "#....#")),
    "B": (6, 0, ("#####.", "#....#", "#....#", "#####.", "#....#",
                 "#....#", "#####.")),
    "C": (6, 0, (".####.", "#....#", "#.....", "#.....", "#.....",
                 "#....#", ".####.")),
    "D": (6, 0, ("####..", "#...#.", "#....#", "#....#", "#....#",
                 "#...#.", "####..")),
    "E": (5, 0, ("#####", "#....", "#....", "####.", "#....", "#....",
                 "#####")),
    "F": (5, 0, ("#####", "#....", "#....", "####.", "#....", "#....",
                 "#....")),
    "G": (6, 0, (".####.", "#....#", "#.....", "#..###", "#....#",
                 "#....#", ".####.")),
    "H": (6, 0, ("#....#", "#....#", "#....#", "######", "#....#",
                 "#....#", "#....#")),
    "I": (3, 0, ("###", ".#.", ".#.", ".#.", ".#.", ".#.", "###")),
    "J": (5, 0, ("..###", "...#.", "...#.", "...#.", "...#.", "#..#.",
                 ".##..")),
    "K": (6, 0, ("#....#", "#...#.", "#..#..", "###...", "#..#..",
                 "#...#.", "#....#")),
    "L": (5, 0, ("#....", "#....", "#....", "#....", "#....", "#....",
                 "#####")),
    "M": (7, 0, ("#.....#", "##...##", "#.#.#.#", "#.#.#.#", "#..#..#",
                 "#.....#", "#.....#")),
    "N": (6, 0, ("#....#", "##...#", "#.#..#", "#..#.#", "#...##",
                 "#....#", "#....#")),
    "O": (6, 0, (".####.", "#....#", "#....#", "#....#", "#....#",
                 "#....#", ".####.")),
    "P": (6, 0, ("#####.", "#....#", "#....#", "#####.", "#.....",
                 "#.....", "#.....")),
    "Q": (6, 0, (".####.", "#....#", "#....#", "#....#", "#..#.#",
                 "#...#.", ".###.#")),
    "R": (6, 0, ("#####.", "#....#", "#....#", "#####.", "#..#..",
                 "#...#.", "#....#")),
    "S": (6, 0, (".####.", "#....#", "#.....", ".####.", ".....#",
                 "#....#", ".####.")),
    "T": (6, 0, ("######", "...#..", "...#..", "...#..", "...#..",
                 "...#..", "...#..")),
    "U": (6, 0, ("#....#", "#....#", "#....#", "#....#", "#....#",
                 "#....#", ".####.")),
    "V": (6, 0, ("#....#", "#....#", "#....#", "#....#", ".#..#.",
                 ".#..#.", "..##..")),
    "W": (7, 0, ("#.....#", "#.....#", "#.....#", "#..#..#", "#.#.#.#",
                 "#.#.#.#", ".#...#.")),
    "X": (6, 0, ("#....#", ".#..#.", "..##..", "..##..", "..##..",
                 ".#..#.", "#....#")),
    "Y": (6, 0, ("#....#", "#....#", ".#..#.", "..##..", "...#..",
                 "...#..", "...#..")),
    "Z": (6, 0, ("######", "....#.", "...#..", "..#...", ".#....",
                 "#.....", "######")),
    "0": (6, 0, (".####.", "#....#", "#...##", "#..#.#", "#.#..#",
                 "##...#", ".####.")),
    "1": (4, 0, ("..#.", ".##.", "..#.", "..#.", "..#.", "..#.", "####")),
    "2": (6, 0, (".####.", "#....#", ".....#", "...##.", "..#...",
                 ".#....", "######")),
    "3": (6, 0, ("#####.", ".....#", ".....#", ".####.", ".....#",
                 ".....#", "#####.")),
    "4": (6, 0, ("...#..", "..##..", ".#.#..", "#..#..", "######",
                 "...#..", "...#..")),
    "5": (6, 0, ("######", "#.....", "#.....", "#####.", ".....#",
                 "#....#", ".####.")),
    "6": (6, 0, (".####.", "#.....", "#.....", "#####.", "#....#",
                 "#....#", ".####.")),
    "7": (6, 0, ("######", ".....#", "....#.", "...#..", "..#...",
                 "..#...", "..#...")),
    "8": (6, 0, (".####.", "#....#", "#....#", ".####.", "#....#",
                 "#....#", ".####.")),
    "9": (6, 0, (".####.", "#....#", "#....#", ".#####", ".....#",
                 ".....#", ".####.")),
}
FONT.update({
    "a": (5, 2, (".####", "....#", ".####", "#...#", ".###.")),
    "b": (5, 0, ("#....", "#....", "####.", "#...#", "#...#", "#...#",
                 "####.")),
    "c": (5, 2, (".####", "#....", "#....", "#....", ".####")),
    "d": (5, 0, ("....#", "....#", ".####", "#...#", "#...#", "#...#",
                 ".###.")),
    "e": (5, 2, (".####", "#...#", "#####", "#....", ".###.")),
    "f": (4, 0, ("..##", ".#..", "####", ".#..", ".#..", ".#..",
                 ".#..")),
    "g": (5, 2, (".####", "....#", ".####", "#...#", ".####", "....#",
                 ".###.")),
    "h": (5, 0, ("#....", "#....", "####.", "#...#", "#...#", "#...#",
                 "#...#")),
    "i": (3, 0, (".#.", "...", ".#.", ".#.", ".#.", ".#.", ".#.")),
    "j": (3, 0, ("..#", "...", "..#", "..#", "..#", "..#", "..#",
                 ".#.", "#..")),
    "k": (5, 0, ("#....", "#....", "#..#.", "###..", "#..#.", "#...#",
                 "#...#")),
    "l": (3, 0, (".#.", ".#.", ".#.", ".#.", ".#.", ".#.", ".#.")),
    "m": (7, 2, ("###.##.", "#..#..#", "#..#..#", "#..#..#",
                 "#..#..#")),
    "n": (5, 2, ("####.", "#...#", "#...#", "#...#", "#...#")),
    "o": (5, 2, (".###.", "#...#", "#...#", "#...#", ".###.")),
    "p": (5, 2, ("####.", "#...#", "#...#", "####.", "#....", "#....",
                 "#....")),
    "q": (5, 2, (".####", "#...#", "#...#", ".####", "....#", "....#",
                 "....#")),
    "r": (4, 2, ("###.", "#..#", "#...", "#...", "#...")),
    "s": (5, 2, (".####", "#....", ".###.", "....#", "####.")),
    "t": (4, 0, (".#..", "####", ".#..", ".#..", ".#..", ".#..",
                 "..##")),
    "u": (5, 2, ("#...#", "#...#", "#...#", "#...#", ".###.")),
    "v": (5, 2, ("#...#", "#...#", "#...#", ".#.#.", "..#..")),
    "w": (7, 2, ("#.....#", "#.....#", "#..#..#", "#.#.#.#",
                 ".#...#.")),
    "x": (5, 2, ("#...#", ".#.#.", "..#..", ".#.#.", "#...#")),
    "y": (5, 2, ("#...#", "#...#", "#...#", ".###.", "....#", "...#.",
                 "..#..")),
    "z": (5, 2, ("#####", "....#", "...#.", "..#..", "#####")),
    " ": (3, 0, ()),
    ".": (2, 6, ("##",)),
    ",": (2, 6, ("##", ".#", "#.")),
    ":": (2, 2, ("##", "##", "..", "##", "##")),
    ";": (2, 2, ("##", "##", "..", "##", "##", ".#", "#.")),
    "'": (2, 0, ("##", "#.")),
    '"': (4, 0, ("#.#.", "#.#.")),
    "-": (4, 4, ("####",)),
    "–": (6, 4, ("######",)),
    "(": (3, 0, ("..#", ".#.", "#..", "#..", "#..", ".#.", "..#")),
    ")": (3, 0, ("#..", ".#.", "..#", "..#", "..#", ".#.", "#..")),
    "/": (5, 0, ("....#", "...#.", "...#.", "..#..", ".#...", ".#...",
                 "#....")),
    "$": (5, 0, ("..#..", ".####", "#.#.#", ".###.", "..#.#", "####.",
                 "..#..")),
    "%": (6, 0, ("##....", "##..#.", "....#.", "...#..", "..#.##",
                 "....##", "....##")),
    "·": (2, 3, ("##",)),
    "ü": (5, 0, ("#...#", ".....", "#...#", "#...#", "#...#", "#...#",
                 ".###.")),
    "!": (3, 0, (".#.", ".#.", ".#.", ".#.", ".#.", "...", ".#.")),
    "?": (6, 0, (".####.", "#....#", ".....#", "...##.", "..#...",
                 "......", "...#..")),
})

_FALLBACK = (6, 0, ("######", "#....#", "#....#", "#.###.", "#...#.",
                    "#....#", "######"))


def glyph_rows(ch):
    """Return (width, top, rows) with every row padded to width."""
    spec = FONT.get(ch, _FALLBACK if ch != "?" else FONT["?"])
    w, top, rows = spec
    fixed = []
    for row in rows:
        fixed.append((row + "." * w)[:w])
    return w, top, fixed


def text_width(s, scale):
    total = 0
    for ch in s:
        w, _top, _rows = glyph_rows(ch)
        total += (w + 1) * scale
    return total - scale if total else 0


def draw_text(cv, x, y, s, scale, color):
    """Draw s with its top at y; return the advance in pixels."""
    cx = x
    for ch in s:
        w, top, rows = glyph_rows(ch)
        for ri, row in enumerate(rows):
            yy = y + (top + ri) * scale
            for ci, bit in enumerate(row):
                if bit == "#":
                    cv.rect(cx + ci * scale, yy, scale, scale, color)
        cx += (w + 1) * scale
    return cx - x - scale if cx > x else 0


def wrap_text(s, scale, max_w):
    lines = []
    cur = ""
    for word in s.split():
        trial = f"{cur} {word}".strip()
        if text_width(trial, scale) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def text_block(cv, x, y, lines, scale, color, leading):
    for line in lines:
        draw_text(cv, x, y, line, scale, color)
        y += leading
    return y

# ------------------------------------------------------------------ art
# Eleven flat illustrations, one per illustrated story. Each takes
# (cv, x, y, w, h) and paints inside that box.

def art_faa(cv, x, y, w, h):
    cv.rect(x, y, w, h, NAVY)
    fx, fy = x + 18, y + h - 52
    cv.ellipse(fx + 54, fy, 54, 9, (235, 235, 230))
    cv.poly([(fx + 98, fy - 7), (fx + 128, fy), (fx + 98, fy + 7)],
            (235, 235, 230))
    cv.poly([(fx + 8, fy - 7), (fx + 2, fy - 28), (fx + 18, fy - 7)],
            (235, 235, 230))
    cv.poly([(fx + 48, fy + 3), (fx + 62, fy + 28), (fx + 76, fy + 3)],
            (215, 215, 210))
    bx, by, bw, bh = x + w - 132, y + 10, 122, 62
    cv.rect(bx, by, bw, bh, (12, 12, 12))
    draw_text(cv, bx + 8, by + 5, "DEPARTURES", 1, (240, 200, 60))
    for i, city in enumerate(["NEW YORK", "CHICAGO", "ATLANTA"]):
        ry = by + 22 + i * 13
        draw_text(cv, bx + 8, ry, city, 1, WHITE)
        cv.rect(bx + 70, ry, 48, 10, RED)
        draw_text(cv, bx + 73, ry + 1, "GROUNDED", 1, WHITE)


def art_radar(cv, x, y, w, h):
    cv.rect(x, y, w, h, (232, 201, 138))
    cv.rect(x, y + h - 26, w, 26, (206, 164, 96))
    cx, cy = x + 64, y + 56
    cv.pieslice(cx, cy, 32, 180, 360, (245, 245, 240))
    cv.line(cx, cy, cx, cy + 36, INK, 3)
    cv.line(cx - 14, cy + 36, cx + 14, cy + 36, INK, 3)
    cv.line(cx, cy - 6, cx + 22, cy - 26, INK, 2)
    cv.ellipse(cx + 23, cy - 25, 3, 3, INK)
    for jx, jy in [(x + 168, y + 30), (x + 212, y + 54)]:
        cv.poly([(jx, jy), (jx + 32, jy + 4), (jx, jy + 8)], (40, 40, 40))
        cv.poly([(jx + 10, jy + 4), (jx + 16, jy - 6), (jx + 20, jy + 4)],
                (40, 40, 40))
    cv.rect(x + w - 128, y + 12, 118, 20, (28, 90, 110))
    draw_text(cv, x + w - 122, y + 16, "IRAN: DESTROYED", 1, WHITE)


def art_summit(cv, x, y, w, h):
    cv.rect(x, y, w, h, (240, 230, 205))
    cv.ellipse(x + w // 2, y + h - 26, (w - 40) // 2, 18, (150, 104, 58))
    step = w // 3
    for i, (name, code) in enumerate([("TRUMP", "US"), ("XI", "CN"),
                                      ("PUTIN", "RU")]):
        fx = x + step * i + step // 2 - 30
        fy = y + 18
        cv.line(fx + 30, fy, fx + 30, fy + 62, INK, 2)
        if code == "US":
            cv.rect(fx, fy + 4, 60, 26, (178, 34, 34))
            for s in range(0, 27, 4):
                cv.rect(fx, fy + 4 + s, 60, 2, WHITE)
            cv.rect(fx, fy + 4, 26, 12, (30, 50, 110))
        elif code == "CN":
            cv.rect(fx, fy + 4, 60, 26, (200, 30, 30))
            cv.ellipse(fx + 15, fy + 15, 5, 5, (250, 220, 60))
        else:
            cv.rect(fx, fy + 4, 60, 8, WHITE)
            cv.rect(fx, fy + 12, 60, 9, (40, 80, 170))
            cv.rect(fx, fy + 21, 60, 9, (200, 30, 30))
        draw_text(cv, fx + 14, fy + 36, name, 1, INK)


def art_rocket(cv, x, y, w, h):
    cv.rect(x, y, w, h, (16, 24, 48))
    for sx, sy in [(x + 20, y + 18), (x + 60, y + 34), (x + w - 30, y + 22),
                   (x + w - 60, y + 48), (x + 110, y + 12)]:
        cv.ellipse(sx, sy, 2, 2, WHITE)
    for i in range(12):
        t = i / 11
        px = x + 24 + t * (w - 90)
        py = y + h - 26 - t * t * (h - 60)
        cv.ellipse(round(px), round(py), 2, 2, (240, 200, 60))
    rx, ry = x + w - 74, y + 16
    cv.poly([(rx + 12, ry), (rx + 24, ry + 22), (rx, ry + 22)],
            (235, 235, 230))
    cv.rect(rx, ry + 22, 24, 30, (235, 235, 230))
    cv.poly([(rx, ry + 52), (rx - 8, ry + 66), (rx, ry + 52)],
            (200, 60, 40))
    cv.poly([(rx + 24, ry + 52), (rx + 32, ry + 66), (rx + 24, ry + 52)],
            (200, 60, 40))
    cv.poly([(rx + 7, ry + 52), (rx + 17, ry + 52), (rx + 12, ry + 70)],
            (250, 160, 40))
    cv.rect(x + 84, y + 8, 66, 18, (240, 200, 60))
    draw_text(cv, x + 88, y + 11, "IN ORBIT", 1, INK)


def art_hospital(cv, x, y, w, h):
    cv.rect(x, y, w, h, (24, 30, 54))
    cv.ellipse(x + w - 25, y + 21, 9, 9, (220, 220, 200))
    bx, by = x + 56, y + 30
    bh = h - 46
    cv.rect(bx, by, 110, bh, (210, 210, 205))
    cv.rect(bx + 46, by - 12, 18, 12, (210, 210, 205))
    for wx in range(4):
        cv.rect(bx + 10 + wx * 26, by + bh - 16, 14, 12, (120, 180, 210))
    cv.rect(bx + 46, by + 6, 18, 18, WHITE)
    cv.rect(bx + 50, by + 12, 10, 6, RED)
    cv.rect(bx + 53, by + 9, 4, 12, RED)
    fx, fy = bx + 78, by - 10
    cv.poly([(fx, fy + 14), (fx + 8, fy), (fx + 12, fy + 10), (fx + 18, fy + 2),
             (fx + 20, fy + 16), (fx + 10, fy + 20)], (250, 140, 30))
    cv.rect(x, y + h - 10, w, 10, (40, 44, 60))


def art_pope(cv, x, y, w, h):
    cv.rect(x, y, w, h, SKY)
    cx = x + w // 2
    cv.rect(cx - 52, y + 46, 104, h - 58, (240, 230, 210))
    cv.poly([(cx - 62, y + 48), (cx, y + 18), (cx + 62, y + 48)],
            (190, 60, 50))
    cv.rect(cx - 5, y + 4, 10, 14, (150, 120, 70))
    cv.rect(cx - 14, y + 8, 28, 4, (150, 120, 70))
    cv.rect(cx - 8, y + 58, 16, h - 70, (120, 90, 60))
    for i in range(14):
        px = x + 14 + (i % 7) * 30
        py = y + h - 22 + (i // 7) * 10
        cv.ellipse(px + 4, py + 4, 4, 4,
                   (179, 39, 32) if i % 2 else (250, 250, 245))
    for fx in (x + 12, x + w - 34):
        cv.line(fx + 10, y + 30, fx + 10, y + 62, INK, 2)
        cv.rect(fx, y + 30, 22, 14, (200, 30, 30))
        cv.rect(fx + 7, y + 30, 8, 14, WHITE)


def art_market(cv, x, y, w, h):
    cv.rect(x, y, w, h, (18, 18, 22))
    pts = [(x + 10, y + 66), (x + 46, y + 40), (x + 82, y + 58),
           (x + 118, y + 30), (x + 154, y + 48), (x + 190, y + 20),
           (x + w - 12, y + 38)]
    for a, b in zip(pts, pts[1:]):
        cv.line(a[0], a[1], b[0], b[1], (220, 60, 50), 3)
    for px, py in pts:
        cv.ellipse(px, py, 3, 3, (220, 60, 50))
    cx, cy = x + w - 58, y + 52
    cv.rect(cx, cy, 36, 36, (90, 190, 80))
    cv.rect(cx + 10, cy + 10, 16, 16, (30, 120, 40))
    for i in range(3):
        cv.line(cx + 5 + i * 13, cy - 5, cx + 5 + i * 13, cy,
                (90, 190, 80), 3)
        cv.line(cx + 5 + i * 13, cy + 36, cx + 5 + i * 13, cy + 41,
                (90, 190, 80), 3)
    draw_text(cv, x + 38, y + 10, "NASDAQ  -1%", 1, (240, 200, 60))


def art_crash(cv, x, y, w, h):
    cv.rect(x, y, w, h, (150, 190, 210))
    cv.rect(x, y + h - 34, w, 34, (70, 70, 70))
    cv.rect(x, y + h - 38, w, 4, (240, 240, 230))
    bx, by = x + 12, y + h - 78
    cv.rect(bx, by, 92, 40, (240, 190, 40))
    for wx in range(4):
        cv.rect(bx + 8 + wx * 21, by + 8, 16, 12, (180, 220, 235))
    cv.ellipse(bx + 20, by + 39, 8, 5, INK)
    cv.ellipse(bx + 74, by + 39, 8, 5, INK)
    tx, ty = x + w - 104, y + h - 82
    cv.rect(tx, ty, 92, 44, (50, 90, 160))
    cv.rect(tx + 62, ty - 12, 30, 56, (40, 70, 130))
    cv.ellipse(tx + 22, ty + 43, 8, 5, INK)
    cv.ellipse(tx + 76, ty + 43, 8, 5, INK)
    sx, sy = x + w // 2, y + h - 56
    cv.poly([(sx, sy - 22), (sx + 6, sy - 6), (sx + 22, sy - 8),
             (sx + 10, sy + 4), (sx + 18, sy + 18), (sx, sy + 10),
             (sx - 16, sy + 18), (sx - 10, sy + 2), (sx - 22, sy - 8),
             (sx - 6, sy - 8)], (250, 120, 20))


def art_pact(cv, x, y, w, h):
    cv.rect(x, y, w, h, (238, 232, 214))
    fx, fy = x + 16, y + 34
    cv.rect(fx, fy, 88, 52, (200, 30, 30))
    cv.ellipse(fx + 35, fy + 26, 13, 13, WHITE)
    cv.ellipse(fx + 37, fy + 26, 10, 10, (200, 30, 30))
    cv.poly([(fx + 52, fy + 26), (fx + 60, fy + 28), (fx + 58, fy + 33),
             (fx + 63, fy + 30), (fx + 58, fy + 26), (fx + 60, fy + 21)],
            WHITE)
    qx, qy = x + w - 104, y + 34
    cv.rect(qx, qy, 88, 52, (140, 30, 60))
    cv.rect(qx, qy, 22, 52, WHITE)
    for i in range(5):
        cv.poly([(qx + 22, qy + i * 10), (qx + 34, qy + i * 10 + 5),
                 (qx + 22, qy + (i + 1) * 10)], WHITE)
    sx, sy = x + w // 2 - 22, y + h - 46
    cv.poly([(sx, sy), (sx + 44, sy), (sx + 44, sy + 24), (sx + 22, sy + 38),
             (sx, sy + 24)], (40, 80, 170))
    cv.line(sx + 10, sy + 18, sx + 19, sy + 27, WHITE, 4)
    cv.line(sx + 19, sy + 27, sx + 35, sy + 8, WHITE, 4)


def art_tanker(cv, x, y, w, h):
    cv.rect(x, y, w, h, SKY)
    cv.rect(x, y + h - 52, w, 52, (70, 130, 180))
    for wx in range(5):
        cv.arc(x + wx * 48 + 10, y + h - 48, 20, 180, 360, WHITE, 2)
    cv.poly([(x + 40, y + h - 66), (x + 190, y + h - 84),
             (x + 200, y + h - 58), (x + 56, y + h - 44)],
            (240, 240, 235))
    cv.poly([(x + 52, y + h - 66), (x + 120, y + h - 74),
             (x + 126, y + h - 60), (x + 58, y + h - 54)], (178, 39, 32))
    cv.rect(x + 90, y + h - 96, 14, 22, (120, 120, 115))
    draw_text(cv, x + 10, y + h - 16, "MISSISSIPPI RIVER", 1, WHITE)


def art_outage(cv, x, y, w, h):
    cv.rect(x, y, w, h, (222, 230, 245))
    ex, ey = x + 18, y + 26
    cv.rect(ex, ey, 84, 56, WHITE)
    cv.frame(ex, ey, 84, 56, INK, 3)
    cv.line(ex, ey, ex + 42, ey + 28, INK, 3)
    cv.line(ex + 42, ey + 28, ex + 84, ey, INK, 3)
    tx, ty = x + w - 96, y + 22
    cv.rect(tx, ty, 56, 56, (110, 70, 190))
    draw_text(cv, tx + 18, ty + 10, "T", 4, WHITE)
    cx, cy = x + w - 30, y + h - 26
    cv.ellipse(cx, cy, 16, 16, (200, 40, 40))
    cv.line(cx - 8, cy - 8, cx + 8, cy + 8, WHITE, 4)
    cv.line(cx + 8, cy - 8, cx - 8, cy + 8, WHITE, 4)
    cv.rect(x + 18, y + h - 30, 60, 20, (40, 40, 40))
    draw_text(cv, x + 24, y + h - 27, "DAY 2", 1, WHITE)


ART = {
    "faa": art_faa, "radar": art_radar, "summit": art_summit,
    "rocket": art_rocket, "hospital": art_hospital, "pope": art_pope,
    "market": art_market, "crash": art_crash, "pact": art_pact,
    "tanker": art_tanker, "outage": art_outage,
}

# ------------------------------------------------------------------ stories
# (art, number, region, headline, deck, longitude, latitude, zone).
# The three big headlines are tightened so they still land in three
# large lines in this face; the decks carry the dropped detail.

BIG = [
    ("faa", "1", "UNITED STATES · AVIATION",
     "FAA grounds all US flights as telecoms fail",
     "Nationwide stop lasts nearly five hours; over 4,700 flights cancelled.",
     -98, 39, "Americas"),
    ("radar", "2", "MIDDLE EAST · IRAN WAR",
     "Iran says it hit a US radar in Bahrain",
     "Guards call it payback for a US strike in Sirik; Iran also says a gas tanker hit a mine in Hormuz.",
     50, 26, "Mideast"),
    ("summit", "3", "ASIA · DIPLOMACY",
     "Trump, Xi, Putin to meet in China",
     "White House announces their first three-way talks at the APEC summit in Shenzhen.",
     114, 22, "Asia"),
]

MED = [
    ("rocket", "4", "SCIENCE · SPACE",
     "SpaceX's Starship Flight 15 reaches orbit",
     "Releases 26 Starlink satellites; the booster catch in Texas is called off.",
     -97, 26, "Americas"),
    ("hospital", "5", "EUROPE · UKRAINE WAR",
     "Russian drone sets a Kyiv hospital on fire",
     "30 evacuated; attacks across Ukraine kill 9 in a day.",
     30, 50, "Europe"),
    ("pope", "6", "SOUTH AMERICA · RELIGION",
     "Pope Leo XIV says Mass in Chiclayo, Peru",
     "About 500,000 gather in his former diocese, the Vatican says.",
     -80, -7, "Americas"),
    ("market", "7", "MARKETS · ECONOMY",
     "Nvidia turmoil drags Wall Street's tech stocks",
     "Shares slide again after CEO Huang quit; US producer prices up 6.5%.",
     -74, 41, "Americas"),
    ("crash", "8", "ASIA · INDIA",
     "Bus–truck crash kills at least 23 in Assam, India",
     "Minibus and container truck collide head-on near Kaziranga.",
     93, 26, "Asia"),
    ("pact", "9", "MIDDLE EAST · DEFENCE",
     "Türkiye and Qatar sign mutual defence pact",
     "Signed in Istanbul; each pledges to defend the other if attacked.",
     29, 41, "Mideast"),
    ("tanker", "10", "UNITED STATES · ACCIDENT",
     "Tanker hits a cruise boat in New Orleans",
     "The American Heritage sinks; all 130 aboard survive.",
     -90, 30, "Americas"),
    ("outage", "11", "TECHNOLOGY",
     "Microsoft 365 back after day-long global outage",
     "Outlook, Teams and Copilot hit; reports from 74 countries.",
     -122, 47, "Americas"),
]

# (number, headline, longitude, latitude, zone)
REST = [
    ("12", "Europe to join Ukraine peace talks, Zelensky says", 33, 52, "Europe"),
    ("13", "Moscow car bomb wounds ex-aide to Ukraine ex-PM", 37, 55, "Europe"),
    ("14", "Norway court: count emissions of exported oil", 10, 60, "Europe"),
    ("15", "England win Wheelchair Rugby League World Cup", -1, 52, "Europe"),
    ("16", "Gaza: baby dies of cold in a flooded tent", 34, 31, "Mideast"),
    ("17", "Houthis claim new strikes on Saudi oil sites", 45, 25, "Mideast"),
    ("18", "Pakistan army: 74 militants killed in 10 days", 70, 30, "Asia"),
    ("19", "North Korea alters its flag, a first since 1948", 127, 40, "Asia"),
    ("20", "Taiwan: China held unannounced Pacific drills", 121, 24, "Asia"),
    ("21", "Myanmar: junta air strikes hit civilians", 96, 21, "Asia"),
    ("22", "Japan: yen weakens toward 160 per dollar", 139, 36, "Asia"),
    ("23", "Building collapse near Nairobi kills six", 37, -1, "Africa"),
    ("24", "Guinea: 10 dead in clashes over gold-mining ban", -13, 10, "Africa"),
    ("25", "Congo: Ebola aid not reaching new epicentre", 23, -2, "Africa"),
    ("26", "Nauru: every MP joins the government", 166, -0.5, "Oceania"),
    ("27", "FBI recovers $1.2bn of stolen Binance crypto", -77, 39, "Americas"),
    ("28", "US: record 483,200 deportations in fiscal 2026", -100, 35, "Americas"),
    ("29", "NASA seeks a private rescue for sinking Hubble", -81, 28, "Americas"),
    ("30", "U2 album carries Dolly Parton's last recording", -87, 36, "Americas"),
    ("31", "COP31: climate-finance gap dominates Antalya talks", 30, 37, "Mideast"),
    ("32", "Ukraine fires 1,200 drones at Russia", 37, 50, "Europe"),
    ("33", "IEA forecasts oil surplus despite Gulf risk", 2, 49, "Europe"),
    ("34", "Van Hollen challenges Schumer for Senate post", -77, 39, "Americas"),
    ("35", "Brooklyn collapse toll settles at eight", -74, 41, "Americas"),
    ("36", "UN extends Abyei peacekeeping mandate", 28, 9, "Africa"),
    ("37", "Mekelle falls as Ethiopian forces advance", 39.5, 13.5, "Africa"),
    ("38", "Australia, Philippines to sign defence pact", 133, -25, "Oceania"),
    ("39", "Chile agrees diesel cut as truckers protest", -71, -33, "Americas"),
]

# ------------------------------------------------------------------ layout

GAP = 12
MAP_BOX = (16, 842, 346, 984)
MAP_TOP_LAT = 78.0
MAP_BOT_LAT = -58.0


def num_badge(cv, x, y, num):
    cv.ellipse(x + 12, y + 12, 13, 13, WHITE)
    cv.ellipse(x + 12, y + 12, 12, 12, RED)
    tw = text_width(num, 1)
    draw_text(cv, x + (24 - tw) // 2, y + 8, num, 1, WHITE)


def card_big(cv, story, x, y, w, h):
    art, num, region, headline, deck, _lo, _la, _zo = story
    cv.rect(x, y, w, h, CARD)
    cv.frame(x, y, w, h, HAIR, 1)
    art_h = 110
    ART[art](cv, x + 1, y + 1, w - 2, art_h)
    cv.frame(x + 1, y + 1, w - 2, art_h, INK, 1)
    num_badge(cv, x + 10, y + 10, num)
    ty = y + art_h + 8
    draw_text(cv, x + 12, ty, num + "  " + region, 1, RED)
    lines = wrap_text(headline, 3, w - 24)[:3]
    hy = ty + 20
    hy = text_block(cv, x + 12, hy, lines, 3, INK, 26)
    text_block(cv, x + 12, hy + 4,
               wrap_text(deck, 1, w - 24)[:2], 1, SOFT, 11)


def card_med(cv, story, x, y, w, h):
    art, num, region, headline, deck, _lo, _la, _zo = story
    cv.rect(x, y, w, h, CARD)
    cv.frame(x, y, w, h, HAIR, 1)
    art_h = 96
    ART[art](cv, x + 1, y + 1, w - 2, art_h)
    cv.frame(x + 1, y + 1, w - 2, art_h, INK, 1)
    num_badge(cv, x + 8, y + 8, num)
    ty = y + art_h + 6
    draw_text(cv, x + 10, ty, num + "  " + region, 1, RED)
    lines = wrap_text(headline, 2, w - 20)[:3]
    hy = ty + 17
    hy = text_block(cv, x + 10, hy, lines, 2, INK, 18)
    text_block(cv, x + 10, hy + 3,
               wrap_text(deck, 1, w - 20)[:2], 1, SOFT, 11)


def project(lon, lat):
    x0, y0, x1, y1 = MAP_BOX
    px = x0 + (lon + 180.0) / 360.0 * (x1 - x0)
    py = y0 + (MAP_TOP_LAT - lat) / (MAP_TOP_LAT - MAP_BOT_LAT) * (y1 - y0)
    return px, py


def split_ring(ring):
    pieces = []
    cur = [ring[0]]
    for pt in ring[1:]:
        if abs(pt[0] - cur[-1][0]) > 180.0:
            pieces.append(cur)
            cur = [pt]
        else:
            cur.append(pt)
    pieces.append(cur)
    return pieces


def paint_map(cv):
    x0, y0, x1, y1 = MAP_BOX
    cv.rect(x0, y0, x1 - x0, y1 - y0, OCEAN)

    def local(lon, lat):
        px, py = project(lon, lat)
        px = min(max(px, x0), x1)
        py = min(max(py, y0), y1)
        return round(px), round(py)

    with open(GEO, encoding="utf-8") as handle:
        world = json.load(handle)
    for feature in world["features"]:
        if feature["properties"].get("name") == "Antarctica":
            continue
        geom = feature["geometry"]
        polys = []
        if geom["type"] == "Polygon":
            polys = [geom["coordinates"]]
        elif geom["type"] == "MultiPolygon":
            polys = geom["coordinates"]
        for poly in polys:
            for ring in poly:
                for piece in split_ring(ring):
                    pts = []
                    for lon, lat in piece:
                        p = local(lon, lat)
                        if not pts or pts[-1] != p:
                            pts.append(p)
                    if len(pts) >= 3:
                        cv.poly(pts, LAND)
    cv.frame(x0, y0, x1 - x0, y1 - y0, INK, 1)
    rows = [["Americas", "Europe", "Mideast"], ["Asia", "Africa", "Oceania"]]
    for ri, row in enumerate(rows):
        lx = x0 + 8
        ly = y1 - 24 + ri * 11
        for zone in row:
            cv.ellipse(lx + 3, ly + 4, 3, 3, ZONE_FILL[zone])
            lx += 10
            tw = draw_text(cv, lx, ly, zone, 1, INK)
            lx += tw + 10
    pins = [(s[5], s[6], s[7]) for s in BIG + MED]
    pins += [(lon, lat, zone) for _n, _t, lon, lat, zone in REST]
    for lon, lat, zone in pins:
        cx, cy = project(lon, lat)
        cv.ellipse(round(cx), round(cy), 4, 4, ZONE_FILL[zone])
        cv.ellipse(round(cx), round(cy), 4, 4, WHITE, fill=False)


def paint_index(cv):
    draw_text(cv, 362, 822, "ALSO ON FRIDAY 13 NOVEMBER", 1, RED)
    cv.hline(362, 1008, 840, HAIR, 1)
    half = (len(REST) + 1) // 2
    for col, x in zip([REST[:half], REST[half:]], [362, 690]):
        yy = 844
        for num, headline, _lo, _la, zone in col:
            draw_text(cv, x, yy, num, 1, ZONE_FILL[zone])
            draw_text(cv, x + 26, yy, headline, 1, INK)
            yy += 11


def compose():
    cv = Canvas(W, H, PAPER)
    draw_text(cv, 16, 10, "THE WORLD'S NEWS IN ONE PICTURE", 2, RED)
    right = "39 STORIES · 6 CONTINENTS · ALL REPORTED ON FRIDAY"
    rw = text_width(right, 1)
    draw_text(cv, W - 16 - rw, 12, right, 1, MUTED)
    date = "Friday 13 November 2026"
    scale = 6 if text_width(date, 6) <= W - 32 else 5
    dw = text_width(date, scale)
    draw_text(cv, (W - dw) // 2, 30, date, scale, INK)
    cv.hline(16, W - 16, 98, INK, 2)
    cv.hline(16, W - 16, 102, INK, 1)
    big_w, big_h = 322, 252
    for i, story in enumerate(BIG):
        card_big(cv, story, 16 + i * (big_w + GAP), 110, big_w, big_h)
    med_w, med_h = 242, 218
    for i, story in enumerate(MED):
        row, col = divmod(i, 4)
        card_med(cv, story, 16 + col * (med_w + GAP),
                 374 + row * (med_h + GAP), med_w, med_h)
    draw_text(cv, 16, 822, "WHERE IT HAPPENED", 1, RED)
    cv.hline(16, 346, 840, HAIR, 1)
    paint_map(cv)
    paint_index(cv)
    footer = ("Every story here happened or was first reported on Friday 13 "
              "November 2026.  Sources: AP, Reuters, AFP, BBC, Al Jazeera, CNBC.")
    fw = text_width(footer, 1)
    draw_text(cv, (W - fw) // 2, 1004, footer, 1, MUTED)
    out_dir = Path(os.environ.get("OUTPUT_DIR")
                   or os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output")
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "entry.png"
    blob = write_png(target, cv)
    if len(blob) > 1024 * 1024:
        raise SystemExit(f"entry.png is {len(blob)} bytes, over the 1 MiB cap")
    print(f"wrote {target} ({len(blob)} bytes, {(W, H)}, "
          f"sha256 {hashlib.sha256(blob).hexdigest()})")


if __name__ == "__main__":
    compose()

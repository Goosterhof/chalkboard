"""The chalk itself — board textures, grainy strokes, wobbly hand-drawn lines.

Everything draws onto per-colour grayscale masks first; compositing applies
chalk grain (noise-modulated alpha) so strokes skip and breathe like real
chalk instead of vector-perfect ink. render.py owns layout; this module owns
the physics of chalk on slate.
"""

import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def _noise_field(w, h, scale, rng):
    """Smooth noise in [0,1] — a coarse random grid upsampled bicubically."""
    gw, gh = max(2, w // scale), max(2, h // scale)
    grid = rng.random((gh, gw)).astype(np.float32)
    img = Image.fromarray((grid * 255).astype(np.uint8), "L").resize((w, h), Image.BICUBIC)
    return np.asarray(img, np.float32) / 255.0


def make_grain(w, h, seed=7):
    """Chalk grain field in [0,1]: fine speckle + low-frequency pressure drift."""
    rng = np.random.default_rng(seed)
    fine = rng.random((h, w)).astype(np.float32)
    mid = _noise_field(w, h, 6, rng)
    low = _noise_field(w, h, 90, rng)
    g = 0.45 * fine + 0.30 * mid + 0.25 * low
    g = (g - g.min()) / (g.max() - g.min() + 1e-6)
    return g


def make_board(w, h, base=(24, 24, 27), seed=None, smudges=10, ghost_lines=8):
    """Black slate: mottled base, eraser smudge streaks, ghost scribbles, vignette.

    Seed defaults to random so every rechalking cycle leaves slightly different
    eraser history on the board — the surface itself says "rewritten".
    """
    if seed is None:
        seed = random.randrange(1 << 30)
    rng = np.random.default_rng(seed)
    pyrng = random.Random(seed)

    base_arr = np.zeros((h, w, 3), np.float32)
    base_arr[:] = base
    base_arr += ((_noise_field(w, h, 140, rng) - 0.5) * 16)[..., None]
    base_arr += rng.normal(0, 3.2, (h, w, 1)).astype(np.float32)
    board = Image.fromarray(np.clip(base_arr, 0, 255).astype(np.uint8), "RGB")

    # eraser smudges: soft rotated streaks of chalk residue
    residue = Image.new("L", (w, h), 0)
    rd = ImageDraw.Draw(residue)
    for _ in range(smudges):
        cx, cy = pyrng.uniform(0, w), pyrng.uniform(0, h)
        sw, sh = pyrng.uniform(w * 0.10, w * 0.32), pyrng.uniform(40, 130)
        ang = pyrng.uniform(-28, 28)
        streak = Image.new("L", (int(sw), int(sh)), 0)
        ImageDraw.Draw(streak).ellipse([0, 0, sw, sh], fill=pyrng.randint(14, 30))
        streak = streak.rotate(ang, expand=True)
        residue.paste(streak, (int(cx - sw / 2), int(cy - sh / 2)), streak)
    # a few wide arc swipes — the classic eraser gesture
    for _ in range(3):
        cx, cy = pyrng.uniform(w * 0.15, w * 0.85), pyrng.uniform(h * 0.2, h * 0.9)
        r = pyrng.uniform(200, 520)
        a0 = pyrng.uniform(160, 200)
        rd.arc([cx - r, cy - r * 0.45, cx + r, cy + r * 0.45], a0, a0 + pyrng.uniform(60, 130),
               fill=18, width=pyrng.randint(40, 90))
    residue = residue.filter(ImageFilter.GaussianBlur(26))
    board = Image.composite(Image.new("RGB", (w, h), (215, 215, 208)), board, residue)

    # ghost of the last chalking — faint illegible scribble lines
    ghost = Image.new("L", (w, h), 0)
    gd = ImageDraw.Draw(ghost)
    for _ in range(ghost_lines):
        y = pyrng.uniform(h * 0.1, h * 0.95)
        x0 = pyrng.uniform(0, w * 0.5)
        length = pyrng.uniform(w * 0.1, w * 0.4)
        pts = []
        x = x0
        while x < x0 + length:
            pts.append((x, y + pyrng.uniform(-6, 6)))
            x += 22
        if len(pts) > 1:
            gd.line(pts, fill=26, width=7)
    ghost = ghost.filter(ImageFilter.GaussianBlur(6))
    board = Image.composite(Image.new("RGB", (w, h), (225, 225, 218)), board, ghost)

    # vignette
    vig = Image.new("L", (w, h), 0)
    ImageDraw.Draw(vig).ellipse([-w * 0.25, -h * 0.25, w * 1.25, h * 1.25], fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(220))
    dark = np.asarray(board, np.float32) * (0.82 + 0.18 * (np.asarray(vig, np.float32)[..., None] / 255.0))
    return Image.fromarray(np.clip(dark, 0, 255).astype(np.uint8), "RGB")


class ChalkLayer:
    """Grayscale stroke accumulator for one chalk colour."""

    def __init__(self, w, h, seed=3):
        self.w, self.h = w, h
        self.mask = Image.new("L", (w, h), 0)
        self.draw = ImageDraw.Draw(self.mask)
        self.rng = random.Random(seed)

    # -- text ---------------------------------------------------------------
    def text(self, xy, s, font, alpha=255, double_strike=True):
        self.draw.text(xy, s, font=font, fill=alpha)
        if double_strike:
            self.draw.text((xy[0] + 1, xy[1]), s, font=font, fill=int(alpha * 0.5))

    def text_len(self, s, font):
        return self.draw.textlength(s, font=font)

    def truncate(self, s, font, max_width):
        """Pixel-accurate truncation with an ellipsis."""
        if self.text_len(s, font) <= max_width:
            return s
        lo, hi = 0, len(s)
        while lo < hi:
            mid = (lo + hi) // 2
            if self.text_len(s[:mid] + "…", font) <= max_width:
                lo = mid + 1
            else:
                hi = mid
        return s[: max(lo - 1, 0)] + "…"

    def truncate_words(self, s, font, max_width):
        """Like truncate, but cuts at the last whole word — "fix: corr…" says
        nothing, "fix: correct…" says something."""
        cut = self.truncate(s, font, max_width)
        if cut == s:
            return s
        body = cut[:-1].rstrip()
        if " " in body:
            body = body.rsplit(" ", 1)[0].rstrip("—-·,:;")
        return body.rstrip() + "…"

    # -- wobbly geometry ----------------------------------------------------
    def _wobble(self, pts, wobble=2.2, step=16):
        """Subdivide a polyline and push points around like a hand would."""
        out = []
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            seg = math.hypot(x1 - x0, y1 - y0)
            n = max(2, int(seg / step))
            drift = 0.0
            for i in range(n + 1):
                t = i / n
                drift = drift * 0.6 + self.rng.uniform(-wobble, wobble) * 0.7
                nx, ny = -(y1 - y0) / (seg + 1e-6), (x1 - x0) / (seg + 1e-6)
                out.append((x0 + (x1 - x0) * t + nx * drift, y0 + (y1 - y0) * t + ny * drift))
        return out

    def line(self, pts, width=4, wobble=2.2, alpha=255, passes=2):
        wpts = self._wobble(pts, wobble)
        self.draw.line(wpts, fill=alpha, width=width, joint="curve")
        for _ in range(passes - 1):
            off = (self.rng.uniform(-1.5, 1.5), self.rng.uniform(-1.5, 1.5))
            shifted = [(x + off[0], y + off[1]) for x, y in wpts]
            self.draw.line(shifted, fill=int(alpha * 0.45), width=max(1, width - 2), joint="curve")

    def rect(self, box, width=4, wobble=2.5, alpha=255):
        x0, y0, x1, y1 = box
        for a, b in [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)),
                     ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]:
            # overshoot corners slightly — hands do
            dx, dy = b[0] - a[0], b[1] - a[1]
            aa = (a[0] - dx * 0.012, a[1] - dy * 0.012)
            bb = (b[0] + dx * 0.012, b[1] + dy * 0.012)
            self.line([aa, bb], width=width, wobble=wobble, alpha=alpha)

    def circle_scribble(self, box, laps=2, width=3, alpha=255):
        """A hand looping around something, `laps` times with overshoot. Each
        lap's centre drifts a little — that drift, not the radius jitter, is
        what makes it read as a scribble instead of an ellipse. On this board
        a circle has exactly one meaning: *this one is waiting on you*."""
        x0, y0, x1, y1 = box
        rx, ry = (x1 - x0) / 2, (y1 - y0) / 2
        cx, cy = x0 + rx, y0 + ry
        pts = []
        start = self.rng.uniform(0, math.tau)
        total = math.tau * laps + math.radians(25 * laps)  # ~25° overshoot per lap
        steps = max(12, int(total / math.radians(12)))
        ox = oy = 0.0
        for i in range(steps + 1):
            a = start + total * i / steps
            if i % max(1, steps // laps) == 0:  # new lap, new centre drift
                ox, oy = self.rng.uniform(-2.5, 2.5), self.rng.uniform(-2.5, 2.5)
            wob = 1 + self.rng.uniform(-0.03, 0.03)
            pts.append((cx + ox + math.cos(a) * rx * wob, cy + oy + math.sin(a) * ry * wob))
        self.line(pts, width=width, wobble=1.0, alpha=alpha, passes=2)

    def underline(self, x0, x1, y, width=5, alpha=255, double=True):
        self.line([(x0, y), (x1, y)], width=width, wobble=2.8, alpha=alpha)
        if double:
            self.line([(x0 + self.rng.uniform(4, 18), y + 9), (x1 - self.rng.uniform(4, 18), y + 9)],
                      width=max(2, width - 2), wobble=2.4, alpha=int(alpha * 0.8))

    def tick(self, x, y, size=32, width=5):
        """Hand-drawn check mark (the fonts carry no dingbats)."""
        s = size / 32
        self.line([(x, y + 18 * s), (x + 11 * s, y + 30 * s), (x + 32 * s, y)], width=width, wobble=1.2)

    def cross(self, x, y, size=28, width=5):
        s = size / 28
        self.line([(x, y), (x + 26 * s, y + 28 * s)], width=width, wobble=1.2)
        self.line([(x + 26 * s, y), (x, y + 28 * s)], width=width, wobble=1.2)

    def tilde(self, x, y, size=30, width=5):
        """Hand-drawn ~ for pending/unknown check state."""
        s = size / 30
        self.line([(x, y + 8 * s), (x + 10 * s, y), (x + 20 * s, y + 8 * s), (x + 30 * s, y)],
                  width=width, wobble=1.0)

    def sparkline(self, values, box, width=4, alpha=255, dot=True):
        x0, y0, x1, y1 = box
        vmax = max(max(values), 1)
        n = len(values)
        pts = []
        for i, v in enumerate(values):
            px = x0 + (x1 - x0) * (i / max(n - 1, 1))
            py = y1 - (y1 - y0) * (v / vmax)
            pts.append((px, py))
        self.line(pts, width=width, wobble=1.6, alpha=alpha, passes=2)
        if dot:
            lx, ly = pts[-1]
            r = width + 2
            self.draw.ellipse([lx - r, ly - r, lx + r, ly + r], fill=alpha)

    def stock_bar(self, box, frac, width=3, hatch_layer=None):
        """Hand-drawn stock gauge: wobbly outline, diagonal chalk hatching up
        to `frac`. Pass hatch_layer to hatch in a different colour than the
        outline (the pantry hatches rose when stock runs low)."""
        x0, y0, x1, y1 = box
        self.rect([x0, y0, x1, y1], width=width, wobble=1.6)
        fill = (hatch_layer or self)
        fill_w = (x1 - x0) * min(max(frac, 0.0), 1.0)
        h = y1 - y0
        x = x0 + 5
        while x < x0 + fill_w - 3:
            fill.line([(x, y1 - 3), (x + h * 0.55, y0 + 3)], width=width, wobble=0.8, passes=1)
            x += 13

    def dotted_leader(self, x0, x1, y, alpha=200, gap=14, r=2):
        x = x0
        while x < x1:
            jy = y + self.rng.uniform(-1.5, 1.5)
            self.draw.ellipse([x - r, jy - r, x + r, jy + r], fill=alpha)
            x += gap

    # -- compositing --------------------------------------------------------
    def composite(self, board, tint, grain, strength=1.0, blur=0.7):
        mask = self.mask.filter(ImageFilter.GaussianBlur(blur))
        m = np.asarray(mask, np.float32) / 255.0
        alpha = np.clip(m * (0.55 + 0.45 * grain) * strength, 0, 1)
        colour = np.zeros((self.h, self.w, 3), np.float32)
        colour[:] = tint
        out = np.asarray(board, np.float32) * (1 - alpha[..., None]) + colour * alpha[..., None]
        return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")


def add_dust(board, seed=None, specks=1000):
    """Faint chalk dust hanging on the surface."""
    rng = random.Random(seed)
    arr = np.asarray(board, np.float32).copy()
    h, w = arr.shape[:2]
    for _ in range(specks):
        x, y = rng.randrange(w), rng.randrange(h)
        arr[y, x] = np.clip(arr[y, x] + rng.uniform(8, 30), 0, 255)
    return Image.fromarray(arr.astype(np.uint8), "RGB")

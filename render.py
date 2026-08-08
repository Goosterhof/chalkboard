"""Chalkboard rendering — the menu board.

A café blackboard: black slate, tall Amatic SC caps, centered composition,
dotted leaders running out to ages like menu prices, chalk frame, per-repo
commit sparklines under THE REGULARS. Layout is designed in 2560×1440 units
and scaled to the actual primary screen. chalk.py owns the chalk physics;
this module owns the composition.
"""

import ctypes
import logging
from pathlib import Path

from PIL import ImageFont

from chalk import ChalkLayer, add_dust, make_board, make_grain

BASE_DIR = Path(__file__).resolve().parent

WHITE = (236, 234, 226)
YELLOW = (240, 210, 130)
ROSE = (236, 172, 168)
MINT = (168, 224, 196)
DIM = (172, 174, 168)

MAX_PRS_PER_SECTION = 3
DESIGN_H = 1440.0


def get_primary_screen_size(config):
    try:
        user32 = ctypes.windll.user32
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    except AttributeError:  # not Windows — bench previews render at a fixed size
        w, h = config.get("preview_size", [2560, 1440])
        logging.info("No Windows display API here — rendering at %dx%d for preview.", w, h)
        return w, h


def load_font(font_dir, name, size):
    try:
        return ImageFont.truetype(str(font_dir / f"{name}.ttf"), size)
    except OSError:
        logging.warning("Font %s not found under %s — falling back to PIL default.", name, font_dir)
        return ImageFont.load_default()


def render_dashboard(data, config, output_path):
    width, height = get_primary_screen_size(config)
    s = height / DESIGN_H  # scale factor for fonts and vertical rhythm

    font_dir = BASE_DIR / config.get("font_dir", "fonts")
    title_f = load_font(font_dir, "amatic-sc-700", int(160 * s))
    sub_f = load_font(font_dir, "amatic-sc-400", int(54 * s))
    head_f = load_font(font_dir, "amatic-sc-700", int(76 * s))
    body_f = load_font(font_dir, "amatic-sc-700", int(52 * s))
    script_f = load_font(font_dir, "caveat-500", int(36 * s))

    board = make_board(width, height)
    grain = make_grain(width, height)

    Lw = ChalkLayer(width, height, seed=2)   # white — the workhorse chalk
    Ly = ChalkLayer(width, height, seed=3)   # yellow — headings, sparklines
    Lr = ChalkLayer(width, height, seed=4)   # rose — the review side, failures
    Lm = ChalkLayer(width, height, seed=5)   # mint — passing checks
    Ld = ChalkLayer(width, height, seed=6)   # dim — annotations, leaders

    cx = width // 2

    def centered(layer, y, text, f, alpha=255):
        w_ = layer.text_len(text, f)
        layer.text((cx - w_ / 2, y), text, f, alpha=alpha)
        return w_

    # ------------------------------------------------------------- frame
    Lw.rect([56 * s, 56 * s, width - 56 * s, height - 56 * s], width=max(3, int(5 * s)), wobble=3.0, alpha=190)
    Lw.rect([76 * s, 76 * s, width - 76 * s, height - 76 * s], width=max(2, int(3 * s)), wobble=2.6, alpha=150)

    # ------------------------------------------------------------- title
    tw = centered(Lw, 96 * s, "THE CHALKBOARD", title_f)
    for sx in (cx - tw / 2 - 90 * s, cx + tw / 2 + 50 * s):
        star_y = 210 * s
        Ly.line([(sx, star_y - 26 * s), (sx + 40 * s, star_y + 26 * s)], width=max(2, int(4 * s)), wobble=1.5)
        Ly.line([(sx + 40 * s, star_y - 26 * s), (sx, star_y + 26 * s)], width=max(2, int(4 * s)), wobble=1.5)
        Ly.line([(sx + 20 * s, star_y - 34 * s), (sx + 20 * s, star_y + 34 * s)], width=max(2, int(4 * s)), wobble=1.5)
    centered(Ly, 268 * s, f"~  DAILY SPECIALS  ·  {data['stamp']}  ~", sub_f)

    # ------------------------------------------------------- PR columns
    col_lx = int(190 * s)
    col_rx = width // 2 + int(110 * s)
    col_w = width // 2 - int(300 * s)
    row_h = int(116 * s)
    mark_w = int(56 * s)

    def menu_row(x, y, title_text, sub_text, age):
        title_max = col_w - mark_w - Ld.text_len(age, body_f) - 160 * s
        title_text = Lw.truncate(title_text.upper(), body_f, title_max)
        Lw.text((x + mark_w, y), title_text, body_f)
        t_w = Lw.text_len(title_text, body_f)
        age_w = Ld.text_len(age, body_f)
        Ld.dotted_leader(x + mark_w + t_w + 24 * s, x + col_w - age_w - 30 * s, y + 40 * s, gap=14 * s, r=2 * s)
        Ld.text((x + col_w - age_w, y), age, body_f)
        Ld.text((x + mark_w + 6 * s, y + 58 * s), sub_text, script_f)

    def overflow_note(x, y, hidden):
        if hidden > 0:
            Ld.text((x + mark_w, y), f"…and {hidden} more on the specials board", script_f)

    # left: authored PRs, with check-status chalk marks
    y = int(420 * s)
    Ly.text((col_lx, y - 60 * s), "FRESH FROM THE BENCH", head_f)
    Ly.underline(col_lx, col_lx + 560 * s, y + 34 * s, width=max(2, int(4 * s)), double=False)
    y += int(74 * s)
    for pr in data["my_prs"][:MAX_PRS_PER_SECTION]:
        checks = pr.get("checks", "none")
        if checks == "green":
            Lm.tick(col_lx, y + 10 * s, size=32 * s, width=max(3, int(5 * s)))
        elif checks == "red":
            Lr.cross(col_lx, y + 8 * s, size=28 * s, width=max(3, int(5 * s)))
        elif checks == "pending":
            Ly.tilde(col_lx, y + 20 * s, size=30 * s, width=max(3, int(5 * s)))
        sub = f"{pr['repo']} #{pr['number']}" + (f" — {pr['review']}" if pr.get("review") else "")
        menu_row(col_lx, y, pr["title"], sub, pr["age"])
        y += row_h
    overflow_note(col_lx, y, len(data["my_prs"]) - MAX_PRS_PER_SECTION)

    # right: review requests
    y = int(420 * s)
    Lr.text((col_rx, y - 60 * s), "WAITING ON YOUR EYES", head_f)
    Lr.underline(col_rx, col_rx + 560 * s, y + 34 * s, width=max(2, int(4 * s)), double=False)
    y += int(74 * s)
    for pr in data["review_prs"][:MAX_PRS_PER_SECTION]:
        sub = f"{pr['repo']} #{pr['number']} — {pr['author']}"
        menu_row(col_rx, y, pr["title"], sub, pr["age"])
        y += row_h
    overflow_note(col_rx, y, len(data["review_prs"]) - MAX_PRS_PER_SECTION)

    # ------------------------------------------------------ the regulars
    div_y = 904 * s
    Lw.line([(cx - 430 * s, div_y), (cx + 430 * s, div_y)], width=max(2, int(4 * s)), wobble=2.2, alpha=200)
    Lw.line([(cx - 310 * s, div_y + 12 * s), (cx + 310 * s, div_y + 12 * s)], width=max(2, int(3 * s)), wobble=2.0, alpha=150)
    centered(Ly, 928 * s, "THE REGULARS", head_f)

    repos = list(data["activity"].keys())
    if repos:
        slot_w = (width - int(360 * s)) // len(repos)
        y0 = int(1040 * s)
        for i, repo in enumerate(repos):
            x0 = int(180 * s) + i * slot_w + int(30 * s)
            acts = data["activity"][repo] or [0]
            Lw.text((x0, y0), repo.upper(), body_f)
            Ly.sparkline(acts, [x0 + 4 * s, y0 + 84 * s, x0 + slot_w - 90 * s, y0 + 168 * s], width=max(3, int(4 * s)))
            note = f"{sum(acts[-7:])} this week"
            last = data["last_commit"].get(repo)
            if last:
                note = Ld.truncate(f"{note} — {last['message']}", script_f, slot_w - 110 * s)
            Ld.text((x0 + 4 * s, y0 + 192 * s), note, script_f)

    # ------------------------------- footer rail: chef's note + refresh
    footer_parts = []
    kendo = data.get("kendo")
    if kendo:
        if kendo.get("plate") is not None:
            footer_parts.append(f"CHEF'S NOTE: {kendo['plate']} ON YOUR PLATE")
        if kendo.get("sprint") and kendo.get("total"):
            footer_parts.append(f"SPRINT {kendo['sprint']} — {kendo.get('served', 0)}/{kendo['total']} SERVED")
    refresh = config.get("refresh_minutes", 10)
    footer_parts.append(f"ERASED & RECHALKED EVERY {refresh} MINUTES")
    centered(Ld, height - 138 * s, "·  " + "  ·  ".join(footer_parts) + "  ·", sub_f)

    # --------------------------------------------------------- composite
    out = board
    for layer, tint in [(Ld, DIM), (Lw, WHITE), (Ly, YELLOW), (Lr, ROSE), (Lm, MINT)]:
        out = layer.composite(out, tint, grain)
    out = add_dust(out)
    out.save(output_path, "PNG")

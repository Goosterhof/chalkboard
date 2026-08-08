"""Chalkboard rendering — the menu board.

A café blackboard: black slate, tall Amatic SC caps, centered composition,
dotted leaders running out to ages like menu prices, chalk frame, per-repo
commit sparklines under THE REGULARS. Layout is designed in 2560×1440 units
and scaled to the actual primary screen. chalk.py owns the chalk physics;
this module owns the composition.
"""

import ctypes
import logging
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

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
        elif checks == "unknown":  # the board admits what it couldn't read
            Ld.text((col_lx + 8 * s, y), "?", body_f)
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

    # --------------------------------------- the regulars + the pantry
    div_y = 904 * s
    Lw.line([(cx - 430 * s, div_y), (cx + 430 * s, div_y)], width=max(2, int(4 * s)), wobble=2.2, alpha=200)
    Lw.line([(cx - 310 * s, div_y + 12 * s), (cx + 310 * s, div_y + 12 * s)], width=max(2, int(3 * s)), wobble=2.0, alpha=150)

    pantry = data.get("pantry")
    reg_x0 = int(180 * s)
    reg_x1 = width - int(840 * s) if pantry else width - int(180 * s)

    def zone_heading(layer, x0, x1, text):
        w_ = layer.text_len(text, head_f)
        layer.text(((x0 + x1) / 2 - w_ / 2, 928 * s), text, head_f)

    zone_heading(Ly, reg_x0, reg_x1, "THE REGULARS")

    repos = list(data["activity"].keys())
    if repos:
        slot_w = (reg_x1 - reg_x0) // len(repos)
        y0 = int(1040 * s)
        for i, repo in enumerate(repos):
            x0 = reg_x0 + i * slot_w + int(30 * s)
            acts = data["activity"][repo] or [0]
            Lw.text((x0, y0), repo.upper(), body_f)
            Ly.sparkline(acts, [x0 + 4 * s, y0 + 84 * s, x0 + slot_w - 90 * s, y0 + 168 * s], width=max(3, int(4 * s)))
            # "318/wk — fix: correct timezone…", word-boundary truncated; the
            # message tail rides along only when at least one whole word of it
            # fits (chaos #00110 D1: a fixed threshold quietly ate the tail on
            # every resolution once the pantry took its share of the width)
            note = f"{sum(acts[-7:])}/wk"
            last = data["last_commit"].get(repo)
            if last:
                fitted = Ld.truncate_words(f"{note} — {last['message']}", script_f, slot_w - 60 * s)
                if len(fitted) >= len(note) + 6:
                    note = fitted
            Ld.text((x0 + 4 * s, y0 + 192 * s), note, script_f)

    if pantry:
        pan_x0, pan_x1 = width - int(780 * s), width - int(180 * s)
        zone_heading(Lm, pan_x0, pan_x1, "THE PANTRY")

        def shelf(y, label, value, frac=None):
            Lw.text((pan_x0, y), label, body_f)
            l_w = Lw.text_len(label, body_f)
            v_w = Ld.text_len(value, script_f)
            Ld.dotted_leader(pan_x0 + l_w + 20 * s, pan_x1 - v_w - 24 * s, y + 34 * s, gap=14 * s, r=2 * s)
            Ld.text((pan_x1 - v_w, y + 10 * s), value, script_f)
            if frac is not None:
                # stock below 15% (or a shelf over 85% full) hatches rose
                hatch = Lr if frac > 0.85 else Ly
                Lw.stock_bar([pan_x0, y + 58 * s, pan_x1, y + 74 * s], frac,
                             width=max(2, int(3 * s)), hatch_layer=hatch)
                return y + 74 * s
            return y + 50 * s

        y = int(996 * s)
        bottom = shelf(y, "MEMORY", f"{pantry['mem_used_gb']:.1f} / {pantry['mem_total_gb']:.0f} GB",
                       pantry["mem_frac"])
        y += int(88 * s)
        for disk in pantry["disks"][:2]:
            bottom = shelf(y, disk["label"].upper(), f"{disk['free_gb']:.0f} GB FREE", disk["used_frac"])
            y += int(88 * s)
        bottom = shelf(y - int(16 * s), "STOVE ON", pantry["uptime"])
        # separator between the regulars and the pantry, cut to content height
        # — a degraded pantry (fewer shelves) no longer hangs a rail into void
        Lw.line([(width - int(810 * s), 950 * s), (width - int(810 * s), min(bottom + 14 * s, 1270 * s))],
                width=max(2, int(3 * s)), wobble=2.4, alpha=150)

    # ------------------------------- footer rail: earned facts first,
    # the cron interval rides last (chaos #00110 D6: the one permanent
    # sentence on the board should be something the board earned)
    footer_parts = []
    if data["review_prs"]:
        footer_parts.append(f"LONGEST ON THE PASS: {data['review_prs'][0]['age'].upper()}")
    week_total = sum(sum((acts or [0])[-7:]) for acts in data["activity"].values())
    if week_total:
        footer_parts.append(f"{week_total} SERVED THIS WEEK")
    kendo = data.get("kendo")
    if kendo:
        if kendo.get("plate") is not None:
            footer_parts.append(f"CHEF'S NOTE: {kendo['plate']} ON YOUR PLATE")
        if kendo.get("sprint") and kendo.get("total"):
            footer_parts.append(f"SPRINT {kendo['sprint']} — {kendo.get('served', 0)}/{kendo['total']} SERVED")
    refresh = config.get("refresh_minutes", 10)
    footer_parts.append(f"RECHALKED EVERY {refresh} MIN")
    centered(Ld, height - 138 * s, "·  " + "  ·  ".join(footer_parts) + "  ·", sub_f)

    # --------------------------------------------------------- composite
    out = board
    for layer, tint in [(Ld, DIM), (Lw, WHITE), (Ly, YELLOW), (Lr, ROSE), (Lm, MINT)]:
        out = layer.composite(out, tint, grain)
    out = add_dust(out)
    out.save(output_path, "PNG")


def chalk_service_pause(output_path, config, last_stamp, pauses, reason="GH WENT QUIET"):
    """Chaos #00110 D3: a failed cycle must never leave a confidently wrong
    timestamp on the wall. Re-chalks the subtitle line of the LAST board as a
    service-pause notice — `~ SERVICE PAUSED · LAST CHALKED 14:12 ·
    GH WENT QUIET ~` — and lets an eraser smudge grow over the specials the
    longer the silence runs. Touches no healthy-cycle code path; returns
    False (caller keeps the old board untouched) if there is no board yet."""
    try:
        board = Image.open(output_path).convert("RGB")
    except (FileNotFoundError, OSError) as exc:
        logging.warning("No previous board to mark as paused: %s", exc)
        return False

    w, h = board.size
    s = h / DESIGN_H
    rng = random.Random(pauses)

    # wipe the subtitle band back to slate before rewriting — repeated
    # pauses re-enter here, and stacking light smudges would bleach the
    # notice into an unreadable white blob (the erased patch must stay
    # chalkable)
    patch = Image.new("L", (w, h), 0)
    ImageDraw.Draw(patch).ellipse([w / 2 - 780 * s, 228 * s, w / 2 + 780 * s, 354 * s], fill=210)
    patch = patch.filter(ImageFilter.GaussianBlur(18))
    board = Image.composite(Image.new("RGB", (w, h), (30, 30, 33)), board, patch)

    # one faint eraser streak per silent cycle over the specials — the fog
    # grows by accumulation across cycles, never by per-call opacity
    residue = Image.new("L", (w, h), 0)
    rd = ImageDraw.Draw(residue)
    rd.ellipse([w / 2 - 700 * s, 240 * s, w / 2 + 700 * s, 340 * s], fill=22)
    growth = min(pauses, 12)
    rx, ry = (260 + growth * 60) * s, (80 + growth * 18) * s
    cx_, cy_ = w * 0.30 + rng.uniform(-80, 80) * s, 560 * s + rng.uniform(-60, 60) * s
    rd.ellipse([cx_ - rx, cy_ - ry, cx_ + rx, cy_ + ry], fill=22)
    residue = residue.filter(ImageFilter.GaussianBlur(24))
    board = Image.composite(Image.new("RGB", (w, h), (208, 208, 201)), board, residue)

    notice = ChalkLayer(w, h, seed=pauses + 1)
    font_dir = BASE_DIR / config.get("font_dir", "fonts")
    sub_f = load_font(font_dir, "amatic-sc-400", int(54 * s))
    line = f"~  SERVICE PAUSED · LAST CHALKED {last_stamp} · {reason.upper()}  ~"
    lw_ = notice.text_len(line, sub_f)
    notice.text((w / 2 - lw_ / 2, 268 * s), line, sub_f)
    board = notice.composite(board, ROSE, make_grain(w, h, seed=pauses + 3))

    board.save(output_path, "PNG")
    return True

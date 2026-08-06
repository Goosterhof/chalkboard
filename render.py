"""Chalkboard rendering — draws the dark dashboard panel with Pillow."""

import ctypes
import logging

from PIL import Image, ImageDraw, ImageFont

BG = (18, 20, 24)
ACCENT = (94, 234, 212)
TEXT = (226, 232, 240)
DIM_TEXT = (140, 148, 160)

MARGIN = 64
LINE_H_BODY = 34
LINE_H_COMMIT = 30
MAX_PRS_PER_SECTION = 8
MAX_COMMITS_PER_REPO = 4


def get_primary_screen_size():
    user32 = ctypes.windll.user32
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def load_font(font_path, size):
    try:
        return ImageFont.truetype(font_path, size)
    except OSError:
        logging.warning("Font not found at %s — falling back to PIL default.", font_path)
        return ImageFont.load_default()


def truncate(draw, text, font, max_width):
    if draw.textlength(text, font=font) <= max_width:
        return text
    ellipsis = "…"
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi) // 2
        candidate = text[:mid] + ellipsis
        if draw.textlength(candidate, font=font) <= max_width:
            lo = mid + 1
        else:
            hi = mid
    return text[: max(lo - 1, 0)] + ellipsis


def draw_pr_section(draw, heading, prs, x, y, col_width, header_font, body_font, dim_font):
    draw.text((x, y), heading, font=header_font, fill=ACCENT)
    cursor_y = y + 40
    if not prs:
        draw.text((x, cursor_y), "— nothing open —", font=dim_font, fill=DIM_TEXT)
        return cursor_y + LINE_H_BODY
    for pr in prs[:MAX_PRS_PER_SECTION]:
        repo_name = pr.get("repository", {}).get("name", "?")
        title = pr.get("title", "")
        label = truncate(draw, f"{repo_name}: {title}", body_font, col_width)
        draw.text((x, cursor_y), label, font=body_font, fill=TEXT)
        cursor_y += LINE_H_BODY
    return cursor_y


def draw_commit_section(draw, commits_by_repo, x, y, width, max_y, header_font, body_font, dim_font):
    draw.text((x, y), "RECENT COMMITS", font=header_font, fill=ACCENT)
    cursor_y = y + 40
    dropped_repos = []
    for repo_name, commits in commits_by_repo.items():
        if cursor_y > max_y - LINE_H_COMMIT:
            dropped_repos.append(repo_name)
            continue
        draw.text((x, cursor_y), repo_name, font=body_font, fill=ACCENT)
        cursor_y += LINE_H_COMMIT
        if not commits:
            draw.text((x + 24, cursor_y), "— no recent commits —", font=dim_font, fill=DIM_TEXT)
            cursor_y += LINE_H_COMMIT
            continue
        for commit in commits[:MAX_COMMITS_PER_REPO]:
            if cursor_y > max_y - LINE_H_COMMIT:
                break
            sha = (commit.get("sha") or "")[:7]
            message = (commit.get("message") or "").splitlines()[0] if commit.get("message") else ""
            author = commit.get("author") or ""
            line = truncate(draw, f"{sha}  {message}  — {author}", dim_font, width - 24)
            draw.text((x + 24, cursor_y), line, font=dim_font, fill=TEXT)
            cursor_y += LINE_H_COMMIT
        cursor_y += 8
    if dropped_repos and cursor_y <= max_y - LINE_H_COMMIT:
        draw.text(
            (x, cursor_y),
            f"…and {len(dropped_repos)} more repo(s) — see gh directly",
            font=dim_font,
            fill=DIM_TEXT,
        )


def render_dashboard(data, config, output_path):
    width, height = get_primary_screen_size()
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    font_path = config.get("font_path", "")
    title_font = load_font(font_path, 42)
    header_font = load_font(font_path, 26)
    body_font = load_font(font_path, 20)
    dim_font = load_font(font_path, 16)

    draw.text((MARGIN, MARGIN), "CHALKBOARD", font=title_font, fill=ACCENT)
    stamp = f"last chalked {data['fetched_at']}"
    stamp_w = draw.textlength(stamp, font=dim_font)
    draw.text((width - MARGIN - stamp_w, MARGIN + 14), stamp, font=dim_font, fill=DIM_TEXT)

    top = MARGIN + 90
    col_gap = 48
    col_width = (width - MARGIN * 2 - col_gap) // 2
    left_x = MARGIN
    right_x = MARGIN + col_width + col_gap

    left_bottom = draw_pr_section(
        draw, "OPEN — AUTHORED BY YOU", data["my_prs"], left_x, top, col_width, header_font, body_font, dim_font
    )
    right_bottom = draw_pr_section(
        draw, "AWAITING YOUR REVIEW", data["review_prs"], right_x, top, col_width, header_font, body_font, dim_font
    )

    commits_top = max(left_bottom, right_bottom) + 56
    footer_clearance = 44  # keeps the last commit line from colliding with the footer stamp
    draw_commit_section(
        draw,
        data["commits"],
        MARGIN,
        commits_top,
        width - MARGIN * 2,
        height - MARGIN - footer_clearance,
        header_font,
        body_font,
        dim_font,
    )

    footer = f"chalkboard · refreshes every {config.get('refresh_minutes', 10)}m"
    draw.text((MARGIN, height - MARGIN + 8), footer, font=dim_font, fill=DIM_TEXT)

    img.save(output_path, "PNG")

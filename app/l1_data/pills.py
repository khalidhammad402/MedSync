"""Pill pictures drawn in code. Never real product photos."""
from __future__ import annotations

import hashlib

COLOR_HEX = {
    "white": "#fbfbf7", "yellow": "#f6d84c", "orange": "#f29a3f", "pink": "#f5a8c2",
    "red": "#d8524e", "brown": "#a9764f", "green": "#7dc17f", "blue": "#5a9bd8",
    "purple": "#9d80cc", "grey": "#b9bfc7",
}
STROKE_HEX = {
    "white": "#8e99a6", "yellow": "#b3952a", "orange": "#b06a1f", "pink": "#b86a86",
    "red": "#96302d", "brown": "#6f4a30", "green": "#4c8a4e", "blue": "#2f6aa3",
    "purple": "#66499a", "grey": "#7b828c",
}


def scale_for(size_mm: float) -> float:
    return 0.55 + (max(5.0, min(15.0, size_mm)) - 5.0) * 0.045


def geometry(shape: str, size_mm: float) -> tuple[float, float]:
    """Half-width and half-height of the pill in a 120 x 120 box."""
    s = scale_for(size_mm)
    if shape == "round":
        return 46 * s, 46 * s
    if shape == "oval":
        return 56 * s, 34 * s
    if shape == "shield":
        return 42 * s, 48 * s
    return 57 * s, 23 * s  # oblong, capsule


def _outline(shape: str, w: float, h: float) -> str:
    cx = cy = 60
    if shape == "round":
        return f'<circle cx="{cx}" cy="{cy}" r="{w:.1f}"/>'
    if shape == "oval":
        return f'<ellipse cx="{cx}" cy="{cy}" rx="{w:.1f}" ry="{h:.1f}"/>'
    if shape == "shield":
        return (f'<path d="M{cx - w:.1f},{cy - h:.1f} L{cx + w:.1f},{cy - h:.1f} '
                f'L{cx + w:.1f},{cy + h * 0.15:.1f} Q{cx + w:.1f},{cy + h * 0.75:.1f} {cx},{cy + h:.1f} '
                f'Q{cx - w:.1f},{cy + h * 0.75:.1f} {cx - w:.1f},{cy + h * 0.15:.1f} Z" stroke-linejoin="round"/>')
    return f'<rect x="{cx - w:.1f}" y="{cy - h:.1f}" width="{2 * w:.1f}" height="{2 * h:.1f}" rx="{h:.1f}"/>'


def pill_svg(color: str, shape: str, size_mm: float, score_line: str = "none",
             imprint: str = "", divisible_parts: int = 1, half: bool = False) -> str:
    fill = COLOR_HEX.get(color, "#dddddd")
    stroke = STROKE_HEX.get(color, "#777777")
    w, h = geometry(shape, size_mm)
    uid = hashlib.md5(f"{color}{shape}{size_mm}{score_line}{imprint}{divisible_parts}{half}".encode()).hexdigest()[:8]
    outline = _outline(shape, w, h)
    clip = f' clip-path="url(#h{uid})"' if half else ""
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" class="pill" role="img" '
        f'aria-label="{color} {shape} tablet">',
        f'<defs><radialGradient id="g{uid}" cx="35%" cy="30%" r="75%">'
        f'<stop offset="0" stop-color="#ffffff" stop-opacity="0.85"/>'
        f'<stop offset="0.45" stop-color="#ffffff" stop-opacity="0"/>'
        f'<stop offset="1" stop-color="#000000" stop-opacity="0.16"/></radialGradient>'
        f'<clipPath id="c{uid}">{outline}</clipPath>'
        f'<clipPath id="h{uid}"><rect x="0" y="0" width="59" height="120"/></clipPath></defs>',
        f'<g{clip}>',
        f'<g fill="{fill}" stroke="{stroke}" stroke-width="2.5">{outline}</g>',
    ]
    if shape == "capsule":
        parts.append(f'<rect x="60" y="0" width="60" height="120" fill="{stroke}" opacity="0.35" clip-path="url(#c{uid})"/>')
        parts.append(f'<line x1="60" y1="{60 - h:.1f}" x2="60" y2="{60 + h:.1f}" stroke="{stroke}" stroke-width="1.5"/>')
    parts.append(f'<g fill="url(#g{uid})">{outline}</g>')
    vertical = shape in ("oval", "oblong")
    has_line = score_line != "none" and shape != "capsule"
    if has_line:
        width = 3 if score_line == "functional" else 1.6
        reach = 1.0 if score_line == "functional" else 0.62
        if vertical:
            parts.append(f'<line x1="60" y1="{60 - h * reach:.1f}" x2="60" y2="{60 + h * reach:.1f}" '
                         f'stroke="{stroke}" stroke-width="{width}" stroke-linecap="round" clip-path="url(#c{uid})"/>')
        else:
            parts.append(f'<line x1="{60 - w * reach:.1f}" y1="60" x2="{60 + w * reach:.1f}" y2="60" '
                         f'stroke="{stroke}" stroke-width="{width}" stroke-linecap="round" clip-path="url(#c{uid})"/>')
            if divisible_parts == 4:
                parts.append(f'<line x1="60" y1="{60 - h:.1f}" x2="60" y2="{60 + h:.1f}" stroke="{stroke}" '
                             f'stroke-width="{width}" clip-path="url(#c{uid})"/>')
    if imprint and not (has_line and divisible_parts == 4):
        room = w * (0.8 if vertical and has_line else 1.5)
        size = max(8.0, min(h * 0.62, room / max(len(imprint), 2) * 1.5))
        x, y = 60.0, 60.0
        if has_line and vertical:
            x = 60 - w * 0.5
        elif has_line:
            y = 60 - h * 0.45
            size = min(size, h * 0.48)
        parts.append(f'<text x="{x:.1f}" y="{y:.1f}" font-family="Arial, Helvetica, sans-serif" font-size="{size:.1f}" '
                     f'font-weight="700" fill="{stroke}" text-anchor="middle" dominant-baseline="central">{imprint}</text>')
    parts.append("</g></svg>")
    return "".join(parts)

#!/usr/bin/env python3
"""Regenerate the README badge pills (readme-assets/badge-*.svg).

Usage: python3 tools/gen_badges.py <release-tag> <total-downloads> <stars>
No dependencies, standard library only.
"""
import sys
from pathlib import Path

ICONS = {
    "release": '<path d="M20.6 13.4l-7.2 7.2a2 2 0 0 1-2.8 0L2 12V2h10l8.6 8.6a2 2 0 0 1 0 2.8z"/><circle cx="7" cy="7" r="1.2"/>',
    "downloads": '<path d="M12 3v12m0 0l-5-5m5 5l5-5M4 21h16"/>',
    "stars": '<path d="M12 2l3.1 6.3 6.9 1-5 4.9 1.2 6.9L12 17.8 5.8 21.1 7 14.2 2 9.3l6.9-1z"/>',
}
CW = 6.6 + 1  # approx monospace char width incl. letter spacing


def pill(key, label, value):
    lw = len(label) * CW
    vw = len(value) * (CW + 0.4)
    x_lab = 10 + 14 + 6
    x_div = x_lab + lw + 8
    x_val = x_div + 1 + 8
    w = round(x_val + vw + 12)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="24" viewBox="0 0 {w} 24" role="img" aria-label="{label.title()}: {value}"><title>{label.title()}: {value}</title>
<rect x="0.75" y="0.75" width="{w-1.5}" height="22.5" rx="11.25" fill="#000" stroke="#000" stroke-width="1.5"/>
<g transform="translate(10 5) scale(0.58)" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">{ICONS[key]}</g>
<g font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,'DejaVu Sans Mono',monospace" font-size="11" letter-spacing="0.8" fill="#fff">
<text x="{x_lab}" y="15.5">{label}</text>
<rect x="{x_div}" y="6" width="1" height="12" fill="#555"/>
<text x="{x_val}" y="15.5" font-weight="700">{value}</text></g></svg>'''


def main():
    tag, downloads, stars = sys.argv[1:4]
    out = Path(__file__).resolve().parent.parent / "readme-assets"
    out.mkdir(exist_ok=True)
    for key, label, value in (
        ("release", "RELEASE", tag),
        ("downloads", "DOWNLOADS", downloads),
        ("stars", "STARS", stars),
    ):
        (out / f"badge-{key}.svg").write_text(pill(key, label, value))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Render animated, GitHub README-safe SVG cards from profile.json and contributions.json.

Run `python build_cards.py --refresh-data` to update contribution history and cards.
Set STATIC=1 (or pass --static) to emit the final, motionless frame for screenshots.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CARDS = ROOT / "cards"
DATA = ROOT / "data" / "contributions.json"
PROFILE = ROOT / "profile.json"
CACHE = ROOT / ".cache" / "fonts"
USER_AGENT = "animated-profile-readme/1.0 (+https://github.com/thearnavjain)"
GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 .,;:!?+-–—_()[]{}'\"/@#%&*<>|·→↗×"
FONT_URLS = {
    "InstrumentSerif-Regular.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/instrumentserif/InstrumentSerif-Regular.ttf",
    "Inter.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/inter/Inter[opsz,wght].ttf",
    "IBMPlexMono.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/ibmplexmono/IBMPlexMono-Regular.ttf",
}


def request(url: str, *, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def refresh_contributions(profile: dict[str, Any]) -> dict[str, Any]:
    """Read GitHub's public contribution calendar without a token or third-party API."""
    login = profile["login"]
    page = request(f"https://github.com/users/{login}/contributions").decode("utf-8", "replace")
    days: dict[str, int] = {}
    cell = re.compile(r'<td\b(?=[^>]*\bdata-date="(\d{4}-\d{2}-\d{2})")[^>]*\bid="([^"]+)"[^>]*>', re.I)
    tips = re.compile(r'<tool-tip\b[^>]*\bfor="([^"]+)"[^>]*>(.*?)</tool-tip>', re.I | re.S)
    counts: dict[str, int] = {}
    for target, label in tips.findall(page):
        text = re.sub(r"<[^>]+>", "", label)
        text = html.unescape(text)
        match = re.search(r"([\d,]+) contribution", text)
        counts[target] = int(match.group(1).replace(",", "")) if match else 0
    for date, target in cell.findall(page):
        days[date] = counts.get(target, 0)
    if len(days) < 300:
        raise RuntimeError(f"GitHub returned only {len(days)} contribution days for @{login}; refusing to overwrite data.")
    today = dt.date.today()
    first = today - dt.timedelta(days=364)
    trimmed = {d.isoformat(): days.get(d.isoformat(), 0) for d in (first + dt.timedelta(days=i) for i in range(365))}
    result = {"login": login, "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "days": trimmed}
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def subset_font(name: str, url: str) -> str:
    CACHE.mkdir(parents=True, exist_ok=True)
    src = CACHE / name
    glyph_hash = hashlib.sha256(GLYPHS.encode("utf-8")).hexdigest()[:8]
    out = CACHE / (Path(name).stem + f"-{glyph_hash}.woff")
    if not src.exists():
        src.write_bytes(request(url))
    if not out.exists() or out.stat().st_mtime < src.stat().st_mtime:
        executable = shutil.which("pyftsubset")
        command = ([executable] if executable else [sys.executable, "-m", "fontTools.subset"])
        command += [str(src), f"--output-file={out}", "--flavor=woff", f"--text={GLYPHS}", "--layout-features=*", "--glyph-names"]
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
    return "data:font/woff;base64," + base64.b64encode(out.read_bytes()).decode("ascii")


def fonts_css() -> str:
    urls = {"InstrumentSerif-Regular.ttf": FONT_URLS["InstrumentSerif-Regular.ttf"], "Inter.ttf": FONT_URLS["Inter.ttf"], "IBMPlexMono.ttf": FONT_URLS["IBMPlexMono.ttf"]}
    faces = []
    for filename, url in urls.items():
        family = {"InstrumentSerif-Regular.ttf": "Instrument Serif", "Inter.ttf": "Inter", "IBMPlexMono.ttf": "IBM Plex Mono"}[filename]
        uri = subset_font(filename, url)
        weight = "100 900" if family == "Inter" else "400"
        faces.append(f"@font-face{{font-family:'{family}';src:url('{uri}') format('woff');font-weight:{weight};font-style:normal;font-display:swap}}")
    return "".join(faces)


def common_style(font_css: str, delay: float, static: bool) -> str:
    motion = "" if static else f".enter{{animation:rise .8s cubic-bezier(.2,.75,.25,1) {delay:.2f}s both}} .draw{{animation:draw 1s ease {delay + .35:.2f}s both}} .pulse{{animation:pulse 3.6s ease-in-out {delay + .8:.2f}s infinite}}"
    static_css = ".static .enter,.static .draw,.static .pulse{animation:none!important;opacity:1!important;stroke-dashoffset:0!important}.static .motion{display:none!important}"
    return f"""<style>{font_css}
:root{{--paper:#f4f4f9;--ink:#252227;--muted:#4c5573;--faint:#7a4e42;--accent:#895a4e;--line:#2522271c;--sans:'Inter',Arial,sans-serif;--serif:'Instrument Serif',Georgia,serif;--mono:'IBM Plex Mono',monospace}}
*{{box-sizing:border-box}}text{{fill:var(--ink)}}.muted{{fill:var(--muted)}}.faint{{fill:var(--faint)}}.serif{{font-family:var(--serif)}}.sans{{font-family:var(--sans)}}.mono{{font-family:var(--mono)}}
.card{{fill:var(--paper);stroke:var(--line);stroke-width:1}}.accent{{fill:var(--accent)}}.rule{{stroke:var(--line);stroke-width:1}}.enter{{opacity:1}}@keyframes rise{{from{{opacity:0}}to{{opacity:1}}}}@keyframes draw{{from{{stroke-dashoffset:1200}}to{{stroke-dashoffset:0}}}}@keyframes pulse{{0%,100%{{opacity:.58}}50%{{opacity:1}}}}
{motion}{static_css}
@media(prefers-reduced-motion:reduce){{*,*::before,*::after{{animation:none!important;transition:none!important;opacity:1!important;stroke-dashoffset:0!important}}.motion{{display:none!important}}}}
</style>"""


def svg(width: int, height: int, contents: str, css: str, static: bool) -> str:
    cl = ' class="static"' if static else ""
    return f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{width}" height="{height}" viewBox="0 0 {width} {height}"{cl} role="img">{css}<rect width="100%" height="100%" rx="22" class="card"/><g>{contents}</g></svg>\n'


def write_card(name: str, width: int, height: int, contents: str, css: str, static: bool) -> None:
    CARDS.mkdir(parents=True, exist_ok=True)
    (CARDS / name).write_text(svg(width, height, contents, css, static), encoding="utf-8")


def image_data(url: str) -> tuple[str, str]:
    data = request(url)
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif data.startswith((b"GIF87a", b"GIF89a")):
        mime = "image/gif"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        raise ValueError("Portrait URL did not return a supported image")
    return mime, base64.b64encode(data).decode("ascii")


def hero(profile: dict[str, Any], css: str, static: bool) -> None:
    name = escape(profile["name"])
    one_liner = escape(profile["tagline"])
    login = escape(profile["login"])
    location = escape(profile.get("location", ""))
    portrait = ""
    portrait_url = profile.get("portrait")
    if portrait_url:
        try:
            mime, data = image_data(portrait_url)
            portrait = f'<clipPath id="portrait-clip"><circle cx="824" cy="112" r="46"/></clipPath><image class="enter" href="data:{mime};base64,{data}" x="778" y="66" width="92" height="92" preserveAspectRatio="xMidYMid slice" clip-path="url(#portrait-clip)"/><circle cx="824" cy="112" r="47" fill="none" stroke="var(--accent)" stroke-width="2"/>'
        except (urllib.error.URLError, ValueError):
            portrait = ""
    smil = "" if static else '<animate attributeName="opacity" values=".45;1;.45" dur="4s" repeatCount="indefinite" class="motion"/>'
    education = escape(profile.get("education", "").upper())
    interests = escape(profile.get("interests", "").upper())
    content = f'''<g class="enter"><text x="46" y="42" class="mono faint" font-size="12" letter-spacing="2">{login.upper()} / PROFILE</text><text x="46" y="116" class="serif" font-size="58">{name}</text><text x="48" y="153" class="sans muted" font-size="16">{one_liner}</text><text x="48" y="198" class="mono faint" font-size="11" letter-spacing="1.2">{education}  ·  {location.upper()}</text><path d="M48 222H852" class="rule"/><circle cx="48" cy="258" r="4" class="accent pulse">{smil}</circle><text x="62" y="262" class="mono muted" font-size="11">{interests}</text>{portrait}</g>'''
    write_card("hero.svg", 900, 286, content, css, static)


def stats_and_months(data: dict[str, Any]) -> tuple[list[tuple[str, int]], int, int, str]:
    days = {dt.date.fromisoformat(key): int(value) for key, value in data.get("days", {}).items()}
    today = dt.date.today()
    month_keys = []
    y, m = today.year, today.month
    for _ in range(12):
        month_keys.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    month_keys.reverse()
    months = [(dt.date(y, m, 1).strftime("%b").upper(), sum(n for d, n in days.items() if d.year == y and d.month == m)) for y, m in month_keys]
    active = sum(1 for value in days.values() if value > 0)
    busiest_date, busiest_count = max(days.items(), key=lambda pair: (pair[1], pair[0]), default=(today, 0))
    cursor = today if days.get(today, 0) else today - dt.timedelta(days=1)
    streak = 0
    while days.get(cursor, 0) > 0:
        streak += 1
        cursor -= dt.timedelta(days=1)
    busy = busiest_date.strftime("%b %-d") if os.name != "nt" else busiest_date.strftime("%b %#d")
    return months, streak, active, f"{busy} · {busiest_count}"


def contribution_chart(data: dict[str, Any], css: str, static: bool) -> None:
    months, streak, active, busiest = stats_and_months(data)
    values = [n for _, n in months]
    maxv = max(values, default=1) or 1
    bar_w, gap, x0, base = 47, 17, 50, 244
    bars = []
    labels = []
    for i, (label, value) in enumerate(months):
        h = 102 * value / maxv if value else 2
        x = x0 + i * (bar_w + gap)
        bars.append(f'<rect x="{x}" y="{base-h:.1f}" width="{bar_w}" height="{h:.1f}" rx="5" fill="var(--accent)" opacity="{.34 + .66*(i+1)/12:.2f}" class="enter"/>')
        labels.append(f'<text x="{x+bar_w/2}" y="267" class="mono faint" font-size="9" text-anchor="middle">{label}</text>')
    maxlabel = max(values, default=0)
    metrics = [(str(streak), "DAY STREAK"), (str(active), "ACTIVE DAYS"), (busiest, "BUSIEST DAY")]
    metric_svg = "".join(f'<g class="enter" transform="translate({50+i*253},0)"><text x="0" y="64" class="serif" font-size="28">{escape(value)}</text><text x="0" y="83" class="mono faint" font-size="9" letter-spacing="1">{label}</text></g>' for i, (value, label) in enumerate(metrics))
    content = f'''<text x="40" y="36" class="mono faint" font-size="10" letter-spacing="1.6">CONTRIBUTION RHYTHM / LAST 12 MONTHS</text><text x="40" y="118" class="serif" font-size="31">A year of showing up.</text>{metric_svg}<path d="M40 137H860" class="rule"/><line x1="40" y1="{base}" x2="860" y2="{base}" class="rule"/>{''.join(bars)}{''.join(labels)}<text x="40" y="291" class="mono faint" font-size="9">{maxlabel:,} CONTRIBUTIONS IN A BUSIEST MONTH</text>'''
    write_card("contributions-monthly.svg", 900, 310, content, css, static)


def repo_cards(profile: dict[str, Any], css: str, static: bool, delay_start: float) -> list[str]:
    outputs = []
    for stale in CARDS.glob("repo-*.svg"):
        stale.unlink()
    for i, repo in enumerate(profile.get("featured_repos", [])):
        name = escape(repo["name"])
        description = escape(repo["description"])
        language = escape(repo.get("language", "Open source"))
        meta = escape(repo.get("meta", "FEATURED REPOSITORY"))
        local_css = common_style(font_css, delay_start + i * .28, static)
        content = f'''<g class="enter"><text x="40" y="40" class="mono faint" font-size="10" letter-spacing="1.5">{meta}</text><text x="40" y="97" class="serif" font-size="39">{name}</text><text x="40" y="132" class="sans muted" font-size="14">{description}</text><path d="M40 159H860" class="rule"/><text x="40" y="193" class="mono muted" font-size="10">{language.upper()}</text><text x="860" y="193" class="mono" text-anchor="end" font-size="11" fill="var(--accent)">EXPLORE PROJECT ↗</text></g>'''
        filename = f"repo-{i+1:02d}-{re.sub(r'[^a-z0-9]+','-',repo['name'].lower()).strip('-')}.svg"
        write_card(filename, 900, 220, content, local_css, static)
        outputs.append(f"cards/{filename}")
    return outputs


def contribution_graph(data: dict[str, Any], profile: dict[str, Any], css: str, static: bool) -> None:
    raw = [(dt.date.fromisoformat(key), int(value)) for key, value in data.get("days", {}).items()]
    if not raw:
        raw = [(dt.date.today() - dt.timedelta(days=364-i), 0) for i in range(365)]
    raw.sort()
    start = raw[0][0]
    start -= dt.timedelta(days=start.weekday() + 1 if start.weekday() < 6 else 0)
    values = dict(raw)
    maxv = max(values.values(), default=0)
    counts = sorted(v for v in values.values() if v > 0)
    q1 = counts[max(0, len(counts)//3)] if counts else 1
    q2 = counts[max(0, 2*len(counts)//3)] if counts else 2
    levels = ["#e7e5e5", "#d7bdb7", "#bd958b", "#a87367", "#895a4e"]
    x0, y0, cell, gap = 48, 84, 10, 4
    cells = []
    for week in range(53):
        for dow in range(7):
            day = start + dt.timedelta(days=week*7+dow)
            if day not in values:
                continue
            n = values[day]
            level = 0 if n == 0 else 1 if n <= q1 else 2 if n <= q2 else 3 if n < maxv else 4
            d = x0 + week*(cell+gap)
            yy = y0 + dow*(cell+gap)
            cells.append(f'<rect x="{d}" y="{yy}" width="{cell}" height="{cell}" rx="2" fill="{levels[level]}" class="enter" style="animation-delay:{4+week*.012:.2f}s"><title>{day.isoformat()}: {n} contributions</title></rect>')
    total = sum(values.values())
    months_labels = []
    current = None
    for week in range(53):
        day = start + dt.timedelta(days=week*7)
        key = (day.year, day.month)
        if key != current:
            months_labels.append(f'<text x="{x0+week*(cell+gap)}" y="67" class="mono faint" font-size="9">{day.strftime("%b").upper()}</text>')
            current = key
    days_labels = "".join(f'<text x="39" y="{y0+day*(cell+gap)+8}" class="mono faint" font-size="8" text-anchor="end">{("M","W","F")[day//2] if day in (1,3,5) else ""}</text>' for day in range(7))
    content = f'''<text x="40" y="35" class="mono faint" font-size="10" letter-spacing="1.5">THE LONG VIEW / DAILY PRACTICE</text><text x="40" y="58" class="serif" font-size="26">{total:,} contributions in the last year</text>{''.join(months_labels)}{days_labels}{''.join(cells)}<text x="40" y="202" class="mono muted" font-size="9">LESS</text>{''.join(f'<rect x="{75+i*15}" y="193" width="10" height="10" rx="2" fill="{color}"/>' for i, color in enumerate(levels))}<text x="159" y="202" class="mono muted" font-size="9">MORE</text><text x="860" y="202" class="mono faint" text-anchor="end" font-size="9">{escape(profile['brand_color'].upper())} / {escape(data.get('updated_at','')[:10])}</text>'''
    write_card("contributions-graph.svg", 900, 224, content, css, static)


def readme(profile: dict[str, Any], repo_paths: list[str]) -> str:
    repo_tags = "\n".join(f'<a href="{escape(repo["url"])}"><img src="{path}" width="100%" alt="{escape(repo["name"])} repository card" /></a>' for path, repo in zip(repo_paths, profile.get("featured_repos", [])))
    return f'''<!-- Generated by build_cards.py. Edit profile.json; cards are refreshed daily. -->
<p align="center"><img src="cards/hero.svg" width="100%" alt="{escape(profile['name'])} — animated introduction" /></p>

<p align="center"><img src="cards/contributions-monthly.svg" width="100%" alt="Monthly contributions, current streak, active days, and busiest day" /></p>

{repo_tags}

<p align="center"><img src="cards/contributions-graph.svg" width="100%" alt="Contribution graph in my brand colour" /></p>
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-data", action="store_true", help="Fetch the current public GitHub contribution calendar before rendering")
    parser.add_argument("--static", action="store_true", help="Render the final screenshot frame without motion")
    args = parser.parse_args()
    static = args.static or os.environ.get("STATIC") == "1"
    profile = load_json(PROFILE, {})
    data = refresh_contributions(profile) if args.refresh_data else load_json(DATA, {"login": profile.get("login"), "days": {}})
    global font_css
    font_css = fonts_css()
    base_delay = 0.15
    css = common_style(font_css, base_delay, static)
    hero(profile, css, static)
    contribution_chart(data, common_style(font_css, 1.7, static), static)
    repo_paths = repo_cards(profile, css, static, 2.3)
    contribution_graph(data, profile, common_style(font_css, 3.8 + len(repo_paths)*.28, static), static)
    for tile in CARDS.glob("tile-*.svg"):
        tile.unlink()
    (ROOT / "README.md").write_text(readme(profile, repo_paths), encoding="utf-8")
    mode = "static" if static else "animated"
    print(f"Rendered {3 + len(repo_paths)} SVG cards ({mode}) into {CARDS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Rebuild the inline CSS of the self-contained landing page.

landing.html carries two generated <style> blocks:
  <style id="tw">    - Tailwind utilities compiled from landing.build.css
  <style id="fonts"> - Inter + JetBrains Mono variable fonts as data URIs

This script recompiles the Tailwind CSS with the frontend's toolchain (offline,
no CDN) and re-embeds the woff2 subsets from docs/fonts/, splicing both blocks
in place. Run after editing landing.html classes or landing.build.css:

    uv run python scripts/build_landing_css.py
"""
from __future__ import annotations

import base64
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LANDING = ROOT / "landing.html"
BUILD_CSS = ROOT / "landing.build.css"
FONTS = [
    # (family, weight range, repo woff2, unicode-range of the Google latin subset)
    ("Inter", "400 900", ROOT / "docs/fonts/inter-var-latin.woff2",
     "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, "
     "U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD"),
    ("JetBrains Mono", "400 700", ROOT / "docs/fonts/jetbrains-mono-var-latin.woff2",
     "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, "
     "U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD"),
]


def compile_tailwind() -> str:
    """Run the Tailwind v4 CLI from frontend/ (where tailwindcss is installed)."""
    npx = shutil.which("npx")
    if not npx:
        sys.exit("npx not found - need the frontend toolchain to compile Tailwind")
    # The CLI resolves @import "tailwindcss" relative to the input file, so the
    # input must live inside frontend/; rewrite @source to still point at landing.html.
    src = BUILD_CSS.read_text(encoding="utf-8").replace('@source "./landing.html"',
                                                        '@source "../landing.html"')
    frontend = ROOT / "frontend"
    with tempfile.NamedTemporaryFile("w", suffix=".css", dir=frontend, delete=False,
                                     encoding="utf-8") as f:
        f.write(src)
        tmp_in = Path(f.name)
    tmp_out = tmp_in.with_suffix(".out.css")
    try:
        subprocess.run([npx, "-y", "@tailwindcss/cli", "-i", tmp_in.name,
                        "-o", str(tmp_out), "--minify"], cwd=frontend, check=True)
        return tmp_out.read_text(encoding="utf-8").strip()
    finally:
        tmp_in.unlink(missing_ok=True)
        tmp_out.unlink(missing_ok=True)


def font_faces() -> str:
    out = []
    for family, weights, woff2, unicode_range in FONTS:
        b64 = base64.b64encode(woff2.read_bytes()).decode()
        out.append(
            f'@font-face{{font-family:"{family}";font-style:normal;font-weight:{weights};'
            f"font-display:swap;src:url(data:font/woff2;base64,{b64}) format(\"woff2\");"
            f"unicode-range:{unicode_range}}}"
        )
    return "".join(out)


def splice(html: str, style_id: str, css: str) -> str:
    pattern = re.compile(rf'(<style id="{style_id}">).*?(</style>)', re.DOTALL)
    if not pattern.search(html):
        sys.exit(f'landing.html is missing <style id="{style_id}">')
    return pattern.sub(lambda m: m.group(1) + css + m.group(2), html)


def main() -> None:
    html = LANDING.read_text(encoding="utf-8")
    html = splice(html, "tw", compile_tailwind())
    html = splice(html, "fonts", font_faces())
    LANDING.write_text(html, encoding="utf-8")
    size_kb = LANDING.stat().st_size / 1024
    print(f"landing.html rebuilt self-contained: {size_kb:.0f} KB")


if __name__ == "__main__":
    main()

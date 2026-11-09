"""README の画像を作り直す。

  python scripts/render_assets.py

docs/assets/src/frames.html の各 .frame を PNG（2倍解像度）で docs/assets/ に書き出す。
デモの中身は docs/assets/data/*.json（omoshiro-reply が実際に出力した結果）から差し込む。
必要: pip install playwright && playwright install chromium
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from omoshiro.prompts import TECH_BY_NAME  # noqa: E402

SRC = ROOT / "docs/assets/src/frames.html"
DATA = ROOT / "docs/assets/data"
OUT = ROOT / "docs/assets"
FRAMES = ["hero", "demo-grok", "demo-robot", "demo-fiction", "how", "definition", "results", "rate"]

ICONS = ('<div class="acts"><svg viewBox="0 0 24 24"><path d="M4 5h16v11H9l-5 4z"/></svg>'
         '<svg viewBox="0 0 24 24"><path d="M7 7h11l-3-3M17 17H6l3 3"/></svg>'
         '<svg viewBox="0 0 24 24"><path d="M12 20s-7-4.5-7-10a4 4 0 0 1 7-2.5A4 4 0 0 1 19 10c0 5.5-7 10-7 10z"/></svg>'
         '<svg viewBox="0 0 24 24"><path d="M6 4h12v16l-6-4-6 4z"/></svg></div>')


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def label(tech: str) -> str:
    return TECH_BY_NAME.get(tech, {}).get("label", tech)


def fiction_blocks(d: dict) -> dict[str, str]:
    rows = []
    for i, r in enumerate(d["top"], 1):
        win = " win" if i == 1 else ""
        tag = f'<span class="label om">1位 · {esc(label(r["technique"]))}</span>' if i == 1 else \
              f'<span class="label ai">{i}位 · {esc(label(r["technique"]))}</span>'
        rows.append(f'<div class="post{win}">{tag}<div class="av me">チ</div><div>'
                    f'<div class="who"><b>チャエン</b><span class="badge-v"></span><span>@masahirochaen</span></div>'
                    f'<div class="repto">返信先: <em>架空太郎</em></div>'
                    f'<div class="txt{" big" if i == 1 else ""}">{esc(r["text"])}</div>{ICONS if i == 1 else ""}</div></div>')
    obvious = "<br>".join(f"<s>{esc(o)}</s>" for o in d["obvious"][:5])
    c = d["counts"]
    counts = (f'<b>{c["generated"]}案</b>を出して、AI臭・長文・ベタに似た案を機械で<b>{c["dropped"]}案</b>捨て、'
              f'残り{c["kept"]}案を審査員2人が採点。上位<b>{d["finalists"]}案</b>を総当たりで比べ、'
              f'構成作家役が削ってから順位を確定した。')
    return {"<!--FICTION_REPLIES-->": "".join(rows), "<!--FICTION_OBVIOUS-->": obvious,
            "<!--FICTION_COUNTS-->": counts}


def rate_rows(d: dict) -> str:
    reps = sorted(d["replies"], key=lambda r: -r["score"])
    out = []
    for i, r in enumerate(reps, 1):
        cls = " top" if i <= 3 else (" worst" if r["ai_likelihood"] >= 50 else "")
        chip = ""
        if i == 1:
            chip = '<span class="chip g">最高点</span>'
        elif r["ai_likelihood"] >= 50:
            chip = '<span class="chip r">AIっぽい</span>'
        out.append(
            f'<div class="rrow{cls}"><div class="rank">{i}</div><div class="av">?</div>'
            f'<div class="t">{esc(r["text"])}{chip}</div><div class="meters">'
            f'<div class="meter">笑う確率<div class="tr"><div class="f laugh" style="width:{r["laugh"]:.0f}%"></div></div>'
            f'<span class="v">{r["laugh"]:.0f}%</span></div>'
            f'<div class="meter">AIっぽさ<div class="tr"><div class="f ai" style="width:{r["ai_likelihood"]:.0f}%"></div></div>'
            f'<span class="v">{r["ai_likelihood"]:.0f}%</span></div></div></div>')
    return "".join(out)


def main() -> None:
    from playwright.sync_api import sync_playwright

    page_html = SRC.read_text()
    subs = fiction_blocks(json.loads((DATA / "demo-fiction.json").read_text()))
    subs["<!--RATE_ROWS-->"] = rate_rows(json.loads((DATA / "rate-demo.json").read_text()))
    for k, v in subs.items():
        page_html = page_html.replace(k, v)
    built = SRC.with_name("_built.html")
    built.write_text(page_html)
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(device_scale_factor=2, viewport={"width": 1400, "height": 1000})
            pg.goto(built.as_uri())
            pg.wait_for_timeout(300)
            for name in FRAMES:
                pg.locator(f"#{name}").screenshot(path=str(OUT / f"{name}.png"))
                print("書き出し:", OUT / f"{name}.png")
            b.close()
    finally:
        built.unlink(missing_ok=True)


if __name__ == "__main__":
    main()

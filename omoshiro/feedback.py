"""本人が選んだ・捨てた案の記録（審査の手本になる）。

「AIに選ばせて終わりにしない。選ぶ人の好みを仕組みに溜める」の実装。
記録は prefs/feedback.jsonl（Git に入れない）。
"""
from __future__ import annotations

import json
import time

from .paths import HOME

PREFS = HOME / "prefs" / "feedback.jsonl"


def record(post_text: str, chosen: list[str], rejected: list[str], note: str = "") -> None:
    PREFS.parent.mkdir(parents=True, exist_ok=True)
    with open(PREFS, "a") as f:
        f.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "post": post_text[:300],
                            "chosen": chosen, "rejected": rejected, "note": note},
                           ensure_ascii=False) + "\n")


def load(limit: int = 12) -> list[dict]:
    if not PREFS.exists():
        return []
    rows = [json.loads(l) for l in PREFS.read_text().splitlines() if l.strip()]
    return rows[-limit:]


def block(limit: int = 12) -> str:
    """プロンプトに差し込む「この人の好み」"""
    rows = load(limit)
    if not rows:
        return ""
    lines = ["", "■ リプを書く本人の好み（過去に本人が選んだ案と捨てた案。これに合わせて判断する）"]
    for r in rows:
        lines.append(f"投稿: {r['post'][:80]}")
        for c in r["chosen"]:
            lines.append(f"  ○ 採用: {c}")
        for c in r["rejected"]:
            lines.append(f"  × 没: {c}")
        if r.get("note"):
            lines.append(f"  本人のメモ: {r['note']}")
    return "\n".join(lines) + "\n"

"""結果の表示（画面・Markdown）"""
from __future__ import annotations

from .prompts import AXES, AXES_JA, TECH_BY_NAME


def _tech(name: str) -> str:
    t = TECH_BY_NAME.get(name)
    return t["label"] if t else name


def _axes(ax: dict) -> str:
    return " ".join(f"{AXES_JA[a]}{ax.get(a, 0):.0f}" for a in AXES)


def reply_console(res: dict) -> str:
    lines = ["■ リプ案（総当たりの勝ち数順・投稿はしていません）"]
    for i, c in enumerate(res["ranking"], 1):
        mark = "（磨いた版）" if c.get("original") else ""
        lines.append(f"{i}. {c['text']}{mark}")
        lines.append(f"   型: {_tech(c['technique'])} / 勝ち {c['wins']:.1f} / 点 {c['score']:.1f} / 笑う確率 {c['laugh']:.0f}%")
    k = res.get("judge_consistency")
    if k is not None:
        lines.append(f"\n審査の安定度（順番を入れ替えても同じ判定だった割合）: {k:.0%}")
    c = res["counts"]
    lines.append(f"出した案 {c['generated']} → 機械で捨てた {c['dropped']} → 採点 {c['kept']}")
    return "\n".join(lines)


def reply_md(res: dict) -> str:
    p = res["post"]
    an = res["analysis"]
    out = [f"# リプ案: {p['id']}", "", f"投稿者: @{p['author']}", "", "```", p["text"], "```", ""]
    if p.get("quoted_text"):
        out += ["引用元:", "", "```", p["quoted_text"], "```", ""]
    out += ["## 最終候補（投稿はしていません）", "", "| # | リプ | 型 | 勝ち | 点 | 笑う確率 | 内訳 |",
            "|---|---|---|---|---|---|---|"]
    for i, c in enumerate(res["ranking"], 1):
        t = c["text"].replace("|", "｜").replace("\n", " ")
        if c.get("original"):
            t += f"<br>（元: {c['original']}）"
        out.append(f"| {i} | {t} | {_tech(c['technique'])} | {c['wins']:.1f} | {c['score']:.1f} | "
                   f"{c['laugh']:.0f}% | {_axes(c['axes'])} |")
    out += ["", "### 審査員の講評", ""]
    for i, c in enumerate(res["ranking"], 1):
        out.append(f"{i}. {c['text']}")
        for cm in c["comments"]:
            out.append(f"   - {cm}")
    out += ["", "## 読解", "", "### ベタ予測（避けた領域）", ""] + [f"- {o}" for o in an.get("obvious", [])]
    out += ["", "### ツッコミどころ", ""] + [
        f"- {h['detail']} — ずれ: {h['gap']} / 別の読み: {h['other_script']}" for h in an.get("hooks", [])]
    out += ["", "### 地雷", ""] + [f"- {x}" for x in an.get("landmines", [])]
    if res.get("punchup"):
        out += ["", "## 磨き（一騎打ちで勝ったときだけ採用）", "", "| 前 | 後 | 後の勝率 | 採用 |", "|---|---|---|---|"]
        for t in res["punchup"]:
            out.append(f"| {t['before']} | {t['after']} | {t.get('after_wins', '-')} | {'○' if t.get('adopted') else '×'} |")
    out += ["", "## 惜しかった案", ""] + [f"- {c['text']}（{_tech(c['technique'])}・点 {c['score']:.1f}）"
                                          for c in res.get("others", [])]
    out += ["", "## 機械で捨てた案", ""] + [f"- {c['text']} — {c['dropped']}" for c in res.get("dropped", [])]
    k = res.get("judge_consistency")
    out += ["", f"審査の安定度: {k:.0%}" if k is not None else ""]
    return "\n".join(out) + "\n"


def rate_console(res: dict) -> str:
    lines = ["■ 付いたリプの面白さランキング"]
    for i, r in enumerate(res["replies"], 1):
        lines.append(f"{i:2d}. 点 {r['score']:4.1f} | 笑 {r['laugh']:3.0f}% | AIっぽさ {r['ai_likelihood']:3.0f}% | "
                     f"♥{r['likes']} | {r['text'][:60].replace(chr(10), ' ')}")
    s = res.get("spearman_vs_likes")
    lines.append(f"\n点数といいね数の順位相関: {s if s is not None else '計算できず（いいねに差がない）'}")
    return "\n".join(lines)


def rate_md(res: dict) -> str:
    p = res["post"]
    out = [f"# リプ採点: {p['id']}", "", "```", p["text"], "```", "",
           "| # | リプ | 点 | 笑う確率 | AIっぽさ | 種類 | いいね | 講評 |", "|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(res["replies"], 1):
        t = r["text"].replace("|", "｜").replace("\n", " ")
        out.append(f"| {i} | {t} | {r['score']:.1f} | {r['laugh']:.0f}% | {r['ai_likelihood']:.0f}% | {r['kind']} | "
                   f"{r['likes']} | {' / '.join(r['comments'])[:160]} |")
    ai = [r for r in res["replies"] if r["ai_likelihood"] >= 60]
    out += ["", f"AIっぽさ60%以上: {len(ai)} / {len(res['replies'])} 件",
            f"点数といいね数の順位相関: {res.get('spearman_vs_likes')}"]
    return "\n".join(out) + "\n"


def bench_summary(rows: list[dict]) -> str:
    agg = {}
    for r in rows:
        for k, v in r["win_rate"].items():
            if v is not None:
                agg.setdefault(k, []).append(v)
    lines = ["■ 比較の結果（総当たりの平均勝率）"]
    for k, v in sorted(agg.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
        lines.append(f"  {k:12s} {sum(v) / len(v):.0%}（{len(v)} 投稿）")
    return "\n".join(lines)


def bench_md(rows: list[dict]) -> str:
    out = ["# 比較: この仕組み vs ふつうのAIリプ vs 人間で一番いいねのリプ", "", bench_summary(rows), ""]
    for r in rows:
        out += [f"## {r['post_id']}", "", "```", r["post_text"], "```", "", "| 出どころ | リプ | 勝率 |", "|---|---|---|"]
        for k, v in r["entries"].items():
            out.append(f"| {k} | {v.replace('|', '｜')} | {r['win_rate'].get(k)} |")
        out.append("")
    return "\n".join(out) + "\n"

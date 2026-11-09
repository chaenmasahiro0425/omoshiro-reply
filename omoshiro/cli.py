"""omoshiro — Xの面白いリプを作る・付いたリプの面白さを採点する。投稿はしない。

  python -m omoshiro reply <投稿URL|ID> [--persona chaen]   リプ案を作る
  python -m omoshiro reply --text "投稿本文"                 APIなしで本文から作る
  python -m omoshiro rate  <投稿URL|ID>                       付いたリプを採点する
  python -m omoshiro bench <投稿URL|ID> ...                   ふつうのAIリプ・人間・この仕組みを比べる
  python -m omoshiro pick  <runディレクトリ> --ok 1,3 --ng 2   本人の好みを記録する
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import feedback, pipeline, report
from .llm import backend_name
from .xapi import Post, get_post, get_replies, parse_id

from .paths import HOME, PERSONAS

RUNS = HOME / "runs"


def load_persona(name: str) -> str:
    p = Path(name)
    if not p.exists():
        p = PERSONAS / f"{name}.md"
    if not p.exists():
        sys.exit(f"ペルソナが見つかりません: {name}（personas/ に .md を置く）")
    return p.read_text()


def _post_from_args(a) -> tuple[Post, list[Post]]:
    if a.text:
        quoted = a.quoted or ""
        return Post(id="text", text=a.text, author=a.author or "", quoted_text=quoted), []
    post = get_post(parse_id(a.target))
    existing = []
    if not a.no_replies:
        try:
            existing = get_replies(post.conversation_id or post.id, limit=a.replies,
                                   exclude_author=post.author, target_id=post.id)
        except Exception as e:
            print(f"  ⚠️ 既存リプは取れませんでした（続行）: {e}")
    return post, existing


def _run_dir(kind: str, post_id: str) -> Path:
    d = RUNS / f"{time.strftime('%Y%m%d-%H%M%S')}_{kind}_{post_id}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cmd_reply(a) -> None:
    persona = load_persona(a.persona)
    post, existing = _post_from_args(a)
    print(f"投稿 {post.id}（@{post.author}）既存リプ {len(existing)} 件 / 呼び出し: {backend_name()}")
    res = pipeline.make_replies(post, persona, existing, n_per=a.n, finalists=a.finalists, polish=a.polish)
    res["persona"] = a.persona
    d = _run_dir("reply", post.id)
    (d / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=2))
    md = report.reply_md(res)
    (d / "result.md").write_text(md)
    print("\n" + report.reply_console(res))
    print(f"\n保存: {d}/result.md")
    print("気に入った案を記録すると次回から審査に効きます:")
    print(f"  python -m omoshiro pick {d} --ok 1 --ng 3")


def cmd_rate(a) -> None:
    a.text = None
    post = get_post(parse_id(a.target))
    replies = get_replies(post.conversation_id or post.id, limit=a.replies, exclude_author=post.author,
                          target_id=post.id)
    if not replies:
        sys.exit("採点するリプがありません（検索APIは直近7日ぶんだけ）")
    print(f"投稿 {post.id}（@{post.author}）のリプ {len(replies)} 件を採点 / 呼び出し: {backend_name()}")
    res = pipeline.rate_replies(post, replies)
    d = _run_dir("rate", post.id)
    (d / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=2))
    (d / "result.md").write_text(report.rate_md(res))
    print("\n" + report.rate_console(res))
    print(f"\n保存: {d}/result.md")


def cmd_bench(a) -> None:
    persona = load_persona(a.persona)
    out = []
    for t in a.targets:
        post = get_post(parse_id(t))
        existing = get_replies(post.conversation_id or post.id, limit=a.replies, exclude_author=post.author,
                               target_id=post.id)
        print(f"\n=== {post.id} @{post.author}: {post.text[:50]}")
        made = pipeline.make_replies(post, persona, existing, n_per=a.n, quiet=True)
        best = made["ranking"][0]["text"]
        base = pipeline.baseline_reply(post)
        humans = sorted([e for e in existing if e.text], key=lambda e: e.likes, reverse=True)
        entries = {"omoshiro": best, "baseline_ai": base}
        if humans:
            entries["human_top"] = humans[0].text
        h2h = pipeline.head_to_head(post, entries)
        h2h["post_id"], h2h["post_text"] = post.id, post.text[:200]
        h2h["human_top_likes"] = humans[0].likes if humans else None
        out.append(h2h)
        for k, v in entries.items():
            print(f"  {k:12s} 勝率 {h2h['win_rate'].get(k)} | {v}")
    d = _run_dir("bench", str(len(out)))
    (d / "result.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    (d / "result.md").write_text(report.bench_md(out))
    print("\n" + report.bench_summary(out))
    print(f"\n保存: {d}/result.md")


def cmd_pick(a) -> None:
    res = json.loads((Path(a.run) / "result.json").read_text())
    ranking = res["ranking"]

    def nums(s):
        out = []
        for x in (s or "").split(","):
            x = x.strip()
            if not x:
                continue
            if not x.isdigit() or not 1 <= int(x) <= len(ranking):
                sys.exit(f"番号は 1〜{len(ranking)} で指定してください: {x}")
            if int(x) not in out:
                out.append(int(x))
        return out

    ok_n, ng_n = nums(a.ok), nums(a.ng)
    if set(ok_n) & set(ng_n):
        sys.exit(f"同じ番号を採用と没の両方に入れています: {sorted(set(ok_n) & set(ng_n))}")
    if not ok_n and not ng_n:
        sys.exit("--ok か --ng で番号を指定してください")
    ok = [ranking[i - 1]["text"] for i in ok_n]
    ng = [ranking[i - 1]["text"] for i in ng_n]
    feedback.record(res["post"]["text"], ok, ng, a.note or "")
    print(f"記録しました（採用 {len(ok)} / 没 {len(ng)}）→ {feedback.PREFS}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="omoshiro", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("reply", help="リプ案を作る")
    r.add_argument("target", nargs="?", help="投稿URLかID")
    r.add_argument("--text", help="APIを使わず投稿本文を直接渡す")
    r.add_argument("--quoted", help="--text と一緒に、引用元の本文")
    r.add_argument("--author", help="--text と一緒に、投稿者名")
    r.add_argument("--persona", default="chaen")
    r.add_argument("--n", type=int, default=3, help="型ごとの案数（既定3 → 12型で36案）")
    r.add_argument("--finalists", type=int, default=8)
    r.add_argument("--polish", type=int, default=4)
    r.add_argument("--replies", type=int, default=20, help="参考にする既存リプの件数")
    r.add_argument("--no-replies", action="store_true")
    r.set_defaults(fn=cmd_reply)

    s = sub.add_parser("rate", help="付いたリプを採点する")
    s.add_argument("target")
    s.add_argument("--replies", type=int, default=20)
    s.set_defaults(fn=cmd_rate)

    b = sub.add_parser("bench", help="ふつうのAIリプ・人間・この仕組みを比べる")
    b.add_argument("targets", nargs="+")
    b.add_argument("--persona", default="chaen")
    b.add_argument("--n", type=int, default=3)
    b.add_argument("--replies", type=int, default=20)
    b.set_defaults(fn=cmd_bench)

    k = sub.add_parser("pick", help="気に入った案・没の案を記録する")
    k.add_argument("run")
    k.add_argument("--ok", default="")
    k.add_argument("--ng", default="")
    k.add_argument("--note")
    k.set_defaults(fn=cmd_pick)

    a = ap.parse_args(argv)
    if a.cmd == "reply" and not (a.target or a.text):
        ap.error("投稿URL/ID か --text を渡してください")
    a.fn(a)


if __name__ == "__main__":
    main()

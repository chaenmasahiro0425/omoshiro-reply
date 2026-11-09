"""面白いリプを作る工程と、付いたリプを採点する工程。

工程（docs/omoshiro-definition.md の4章）:
  1. 読む   analyze()      ベタ予測・ツッコミどころ・地雷
  2. 出す   generate()     12の型 × n案を3並列で
  3. 捨てる prune()        重複・ベタ似・AI臭・長すぎを機械で落とす
  4. 選ぶ   score() → tournament()   別系統の審査員2人で採点 → 並び順を入れ替えた総当たり
  5. 削る   punchup()      作家役が削り、一騎打ちで勝ったときだけ差し替え
"""
from __future__ import annotations

import itertools
import math
import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, asdict

from . import prompts as P
from .aismell import smell, similarity
from .feedback import block as feedback_block
from .llm import call_json
from .xapi import Post

JUDGES = ["x_humor_judge", "x_humor_judge_b"]
# 比較（bench）専用。選定に関わった審査員で比べると自分の選んだ案を褒めるので、別系統に判定させる
REFEREES = ["x_humor_referee"]

# 総合点の重み（掛け算型。docs の5章）
WEIGHTS = {"surprise": 0.25, "landing": 0.20, "specificity": 0.20,
           "persona": 0.15, "brevity": 0.10, "harmless": 0.10}


@dataclass
class Cand:
    id: str
    text: str
    technique: str = ""
    gap: str = ""
    smell: float = 0.0
    smell_reasons: list = field(default_factory=list)
    axes: dict = field(default_factory=dict)
    laugh: float = 0.0
    comments: list = field(default_factory=list)
    score: float = 0.0
    wins: float = 0.0
    invented: float = 0.0       # 事実を作っていると判定した審査員の割合
    original: str = ""          # 磨く前の文（磨いて差し替えた時だけ）
    dropped: str = ""           # 落とされた理由


def _log(msg: str, quiet: bool) -> None:
    if not quiet:
        print(msg, flush=True)


def _existing_block(existing: list[Post], n: int = 12) -> str:
    if not existing:
        return "（なし）"
    return "\n".join(f"・{e.text[:100]}" for e in existing[:n])


def _parallel(fns):
    with ThreadPoolExecutor(max_workers=len(fns)) as ex:
        futs = [ex.submit(f) for f in fns]
        out = []
        for f in futs:
            try:
                out.append(f.result())
            except Exception as e:   # 1本落ちても残りで続ける
                print(f"  ⚠️ 並列呼び出しの1本が失敗: {type(e).__name__}: {str(e)[:160]}", flush=True)
                out.append(None)
        return out


# ── 1. 読む ─────────────────────────────────────────────
def analyze(post: Post, existing: list[Post]) -> dict:
    prompt = P.ANALYZE.format(definition=P.DEFINITION, post=post.context_block(),
                              existing=_existing_block(existing))
    return call_json("x_humor_analyze", prompt, P.ANALYZE_SCHEMA, temperature=0.4)


def _hooks_block(an: dict) -> str:
    best = {b["hook_index"] for b in an.get("best_angles", [])}
    lines = []
    for i, h in enumerate(an.get("hooks", [])):
        star = "★" if i in best or (i + 1) in best else "・"
        lines.append(f"{star}{h['detail']} — ずれ: {h['gap']} / 別の読み: {h['other_script']}")
    return "\n".join(lines)


# ── 2. 出す ─────────────────────────────────────────────
def is_self_reply(post: Post, persona: str) -> bool:
    return bool(post.author) and f"@{post.author.lower()}" in persona.lower()


def generate(post: Post, persona: str, an: dict, existing: list[Post], n_per: int = 3,
             groups: int = 3) -> list[Cand]:
    names = [t["name"] for t in P.TECHNIQUES]
    random.shuffle(names)
    chunks = [names[i::groups] for i in range(groups)]
    fb = feedback_block()

    def one(chunk):
        prompt = P.GENERATE.format(
            definition=P.DEFINITION, ai_smell=P.AI_SMELL_RULES, safety=P.SAFETY_RULES,
            post=post.context_block(), persona=persona, hooks=_hooks_block(an),
            shared="\n".join(f"・{s}" for s in an.get("shared_context", [])),
            obvious="\n".join(f"・{o}" for o in an.get("obvious", [])),
            existing=_existing_block(existing), techniques=P.technique_block(chunk), n=n_per,
            feedback=fb, self_mode=P.SELF_MODE if is_self_reply(post, persona) else "")
        return call_json("x_humor_generate", prompt, P.GENERATE_SCHEMA, temperature=1.0)

    cands = []
    for res in _parallel([lambda c=c: one(c) for c in chunks]):
        for c in (res or {}).get("candidates", []):
            t = c["text"].strip().strip("「」")
            if t:
                cands.append(Cand(id="", text=t, technique=c.get("technique", ""), gap=c.get("gap", "")))
    for i, c in enumerate(cands):
        c.id = f"c{i + 1:02d}"
    return cands


# ── 3. 捨てる ───────────────────────────────────────────
def prune(cands: list[Cand], an: dict, post: Post, existing: list[Post],
          max_smell: float = 4.0, max_len: int = 100) -> tuple[list[Cand], list[Cand]]:
    keep, drop = [], []
    obvious = an.get("obvious", []) + [e.text for e in existing]
    source = post.text + "\n" + post.quoted_text
    for c in cands:
        sm = smell(c.text, source)
        c.smell, c.smell_reasons = sm["score"], sm["reasons"]
        if len(c.text) > max_len:
            c.dropped = f"長すぎ（{len(c.text)}字）"
        elif c.smell >= max_smell:
            c.dropped = "AI臭: " + "・".join(c.smell_reasons)
        elif obvious and max(similarity(c.text, o) for o in obvious) > 0.45:
            c.dropped = "ベタ予測か既存リプに似ている"
        elif any(similarity(c.text, k.text) > 0.5 for k in keep):
            c.dropped = "他の案と重複"
        (drop if c.dropped else keep).append(c)
    return keep, drop


# ── 4. 選ぶ ─────────────────────────────────────────────
def overall(axes: dict, laugh: float, smell_score: float) -> float:
    """掛け算型の総合点（0〜10）"""
    if not axes:
        return 0.0
    g = math.exp(sum(w * math.log(max(axes.get(a, 0), 0.5) / 10) for a, w in WEIGHTS.items())) * 10
    s = 0.6 * g + 0.4 * (laugh / 10) - 0.4 * smell_score
    if axes.get("harmless", 10) < 5:
        s -= 5
    return round(s, 2)


def _cands_block(cands: list[Cand]) -> str:
    order = cands[:]
    random.shuffle(order)            # 審査員ごとに順番を変える（位置の偏りを散らす）
    return "\n".join(f"{c.id}: {c.text}" for c in order)


def score(post: Post, persona: str, cands: list[Cand], an: dict) -> None:
    fb = feedback_block()

    def one(task):
        who = persona + (P.SELF_MODE if is_self_reply(post, persona) else "")
        prompt = P.JUDGE.format(definition=P.DEFINITION, post=post.context_block(), persona=who,
                                obvious="\n".join(f"・{o}" for o in an.get("obvious", [])[:6]),
                                feedback=fb, candidates=_cands_block(cands))
        return call_json(task, prompt, P.JUDGE_SCHEMA, temperature=0.2)

    by_id = {c.id: c for c in cands}
    sums = {c.id: {a: [] for a in P.AXES} | {"laugh": [], "invented": []} for c in cands}
    for task, res in zip(JUDGES, _parallel([lambda t=t: one(t) for t in JUDGES])):
        for s in (res or {}).get("scores", []):
            if s["id"] not in sums:
                continue
            for a in P.AXES:
                sums[s["id"]][a].append(float(s[a]))
            sums[s["id"]]["laugh"].append(float(s["laugh"]))
            sums[s["id"]]["invented"].append(1.0 if s.get("invented") else 0.0)
            by_id[s["id"]].comments.append(f"{task.replace('x_humor_', '')}: {s['comment']}")
    for cid, d in sums.items():
        c = by_id[cid]
        c.axes = {a: round(sum(d[a]) / len(d[a]), 2) for a in P.AXES if d[a]}
        c.laugh = round(sum(d["laugh"]) / len(d["laugh"]), 1) if d["laugh"] else 0
        c.invented = round(sum(d["invented"]) / len(d["invented"]), 2) if d["invented"] else 0
        c.score = round(overall(c.axes, c.laugh, c.smell) - 3 * c.invented, 2)


def pick_finalists(cands: list[Cand], k: int, max_per_technique: int = 2, sim_penalty: float = 6.0) -> list[Cand]:
    """点が高い順に、似た案・同じ型ばかりにならないよう選ぶ（MMR）。
    1位の案と同じネタの言い換えが決勝を埋めると、別角度の当たりが総当たりに出られない"""
    pool = sorted(cands, key=lambda c: c.score, reverse=True)
    chosen: list[Cand] = []
    while pool and len(chosen) < k:
        def mmr(c):
            sim = max((similarity(c.text, x.text, 2) for x in chosen), default=0.0)
            same = sum(1 for x in chosen if x.technique == c.technique)
            return c.score - sim_penalty * sim - (99 if same >= max_per_technique else 0)
        best = max(pool, key=mmr)
        chosen.append(best)
        pool.remove(best)
    return chosen


def _pairwise(post: Post, pairs: list[tuple[Cand, Cand]], judges=JUDGES) -> list[dict]:
    """各組を両審査員 × 両順で判定。戻り値は [{a, b, a_wins(0〜1)}]（a視点の勝率）"""
    fb = feedback_block()

    def one(task, swap):
        lines, key = [], {}
        for i, (a, b) in enumerate(pairs):
            x, y = (b, a) if swap else (a, b)
            pid = f"p{i + 1:02d}"
            key[pid] = (i, swap)
            lines.append(f"{pid}\n  A: {x.text}\n  B: {y.text}")
        prompt = P.PAIRWISE.format(definition=P.DEFINITION, feedback=fb, post=post.context_block(),
                                   pairs="\n".join(lines))
        res = call_json(task, prompt, P.PAIRWISE_SCHEMA, temperature=0.2)
        return key, res

    jobs = [(t, s) for t in judges for s in (False, True)]
    tallies = [[0.0, 0] for _ in pairs]
    agree = {}
    for (task, swap), out in zip(jobs, _parallel([lambda t=t, s=s: one(t, s) for t, s in jobs])):
        if not out:
            continue
        key, res = out
        for r in res.get("results", []):
            if r["pair"] not in key:
                continue
            i, sw = key[r["pair"]]
            w = r["winner"]
            a_win = 0.5 if w == "draw" else (1.0 if (w == "A") != sw else 0.0)
            tallies[i][0] += a_win
            tallies[i][1] += 1
            agree.setdefault((task, i), []).append(a_win)
    out = []
    for (a, b), (s, n) in zip(pairs, tallies):
        out.append({"a": a, "b": b, "a_wins": s / n if n else 0.5, "votes": n})
    # 同じ審査員が順番を入れ替えても同じ判定をした割合（位置の偏りの目安）
    pairs_seen = [v for v in agree.values() if len(v) == 2]
    consistency = (sum(1 for v in pairs_seen if v[0] == v[1]) / len(pairs_seen)) if pairs_seen else None
    return out, consistency


def tournament(post: Post, cands: list[Cand]) -> float | None:
    pairs = list(itertools.combinations(cands, 2))
    results, consistency = _pairwise(post, pairs)
    for c in cands:
        c.wins = 0.0
    for r in results:
        r["a"].wins += r["a_wins"]
        r["b"].wins += 1 - r["a_wins"]
    cands.sort(key=lambda c: (c.wins, c.score), reverse=True)
    return consistency


# ── 5. 削る ─────────────────────────────────────────────
def punchup(post: Post, persona: str, cands: list[Cand]) -> list[dict]:
    prompt = P.PUNCHUP.format(definition=P.DEFINITION, ai_smell=P.AI_SMELL_RULES, post=post.context_block(),
                              persona=persona, candidates="\n".join(f"{c.id}: {c.text}" for c in cands))
    res = call_json("x_humor_punchup", prompt, P.PUNCHUP_SCHEMA, temperature=0.5)
    by_id = {c.id: c for c in cands}
    trials = []
    pairs = []
    for r in res.get("revised", []):
        c = by_id.get(r["id"])
        new = r["text"].strip().strip("「」")
        if c and new and new != c.text:
            pairs.append((Cand(id=c.id + "r", text=new), c))
            trials.append({"id": c.id, "before": c.text, "after": new, "change": r.get("change", "")})
    if not pairs:
        return trials
    results, _ = _pairwise(post, pairs)
    for t, r in zip(trials, results):
        t["after_wins"] = round(r["a_wins"], 2)
        if r["a_wins"] > 0.5:               # 磨いた版がはっきり勝った時だけ差し替える
            c = by_id[t["id"]]
            c.original, c.text = c.text, t["after"]
            t["adopted"] = True
        else:
            t["adopted"] = False
    return trials


# ── 全体 ────────────────────────────────────────────────
def make_replies(post: Post, persona: str, existing: list[Post] | None = None, n_per: int = 3,
                 finalists: int = 8, polish: int = 4, quiet: bool = False) -> dict:
    existing = existing or []
    _log("1/5 投稿を読んでいます（ベタ予測・ツッコミどころ）", quiet)
    an = analyze(post, existing)
    _log(f"   ベタ予測 {len(an.get('obvious', []))} 個 / ツッコミどころ {len(an.get('hooks', []))} 個", quiet)

    _log("2/5 12の型でリプ案を出しています", quiet)
    cands = generate(post, persona, an, existing, n_per=n_per)
    keep, drop = prune(cands, an, post, existing)
    _log(f"   {len(cands)} 案 → 機械で {len(drop)} 案を捨てて {len(keep)} 案", quiet)
    if not keep:
        raise RuntimeError("全案が落ちました。--n を増やすか、投稿を変えてください")

    _log("3/5 審査員2人で採点しています", quiet)
    score(post, persona, keep, an)
    keep.sort(key=lambda c: c.score, reverse=True)
    final = pick_finalists(keep, finalists)
    others = [c for c in keep if c not in final]

    _log(f"4/5 上位 {len(final)} 案で総当たり（順番を入れ替えて2回ずつ）", quiet)
    consistency = tournament(post, final)

    _log(f"5/5 上位 {min(polish, len(final))} 案を磨いて一騎打ち", quiet)
    trials = punchup(post, persona, final[:polish]) if polish else []

    return {
        "post": asdict(post),
        "analysis": an,
        "ranking": [asdict(c) for c in final],
        "others": [asdict(c) for c in others],
        "self_reply": is_self_reply(post, persona),
        "dropped": [asdict(c) for c in drop],
        "punchup": trials,
        "judge_consistency": consistency,
        "counts": {"generated": len(cands), "kept": len(keep), "dropped": len(drop)},
    }


# ── 付いたリプを採点する ────────────────────────────────
def rate_replies(post: Post, replies: list[Post]) -> dict:
    cands = [Cand(id=f"r{i + 1:02d}", text=r.text) for i, r in enumerate(replies)]
    src = post.text + "\n" + post.quoted_text

    def one(task):
        prompt = P.RATE.format(definition=P.DEFINITION, post=post.context_block(),
                               candidates=_cands_block(cands))
        return call_json(task, prompt, P.RATE_SCHEMA, temperature=0.2)

    agg = {c.id: {"axes": {a: [] for a in P.AXES}, "laugh": [], "ai": [], "kind": [], "comment": []}
           for c in cands}
    for task, res in zip(JUDGES, _parallel([lambda t=t: one(t) for t in JUDGES])):
        for s in (res or {}).get("scores", []):
            if s["id"] not in agg:
                continue
            g = agg[s["id"]]
            for a in P.AXES:
                g["axes"][a].append(float(s[a]))
            g["laugh"].append(float(s["laugh"]))
            g["ai"].append(float(s["ai_likelihood"]))
            g["kind"].append(s["kind"])
            g["comment"].append(s["comment"])
    rows = []
    for c, r in zip(cands, replies):
        g = agg[c.id]
        axes = {a: round(sum(v) / len(v), 2) for a, v in g["axes"].items() if v}
        laugh = sum(g["laugh"]) / len(g["laugh"]) if g["laugh"] else 0
        sm = smell(c.text, src)
        ai_llm = sum(g["ai"]) / len(g["ai"]) if g["ai"] else 0
        rows.append({
            "id": c.id, "author": r.author, "text": r.text, "likes": r.likes,
            "axes": axes, "laugh": round(laugh, 1),
            "score": overall(axes, laugh, sm["score"]),
            "ai_likelihood": round(0.7 * ai_llm + 30 * sm["score"] / 10, 1),
            "smell": sm["score"], "smell_reasons": sm["reasons"],
            "kind": max(set(g["kind"]), key=g["kind"].count) if g["kind"] else "",
            "comments": g["comment"],
        })
    rows.sort(key=lambda r: r["score"], reverse=True)
    return {"post": asdict(post), "replies": rows, "spearman_vs_likes": spearman(
        [r["score"] for r in rows], [r["likes"] for r in rows])}


def spearman(x: list[float], y: list[float]) -> float | None:
    n = len(x)
    if n < 4 or len(set(y)) < 2:
        return None

    def rank(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r

    rx, ry = rank(x), rank(y)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    vy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return round(cov / (vx * vy), 3) if vx and vy else None


# ── 比較（ふつうのAIリプ vs この仕組み vs 人間） ─────────
def baseline_reply(post: Post) -> str:
    res = call_json("x_humor_generate", P.BASELINE.format(post=post.context_block()),
                    P.BASELINE_SCHEMA, temperature=0.7)
    return res["text"].strip()


def head_to_head(post: Post, entries: dict[str, str], judges=None) -> dict:
    """{名前: リプ} を総当たりで比べ、名前ごとの勝率を返す（既定は選定に関わらない審査員）"""
    from .llm import has_task
    judges = judges or [t for t in REFEREES if has_task(t)] or JUDGES
    cands = [Cand(id=k, text=v) for k, v in entries.items() if v]
    pairs = list(itertools.combinations(cands, 2))
    results, consistency = _pairwise(post, pairs, judges=judges)
    wins = {c.id: 0.0 for c in cands}
    games = {c.id: 0 for c in cands}
    detail = []
    for r in results:
        wins[r["a"].id] += r["a_wins"]
        wins[r["b"].id] += 1 - r["a_wins"]
        games[r["a"].id] += 1
        games[r["b"].id] += 1
        detail.append({"a": r["a"].id, "b": r["b"].id, "a_win_rate": round(r["a_wins"], 2)})
    return {"win_rate": {k: round(wins[k] / games[k], 2) if games[k] else None for k in wins},
            "pairs": detail, "judge_consistency": consistency, "entries": entries, "judges": judges}

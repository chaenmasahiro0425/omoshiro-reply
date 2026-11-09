"""AI臭の検知（ルールベース）。

LLMの審査員は「整った文」を高く付けがちなので、AIリプに典型的な言い回しは
モデルに頼らず機械で減点する。パターンは 2026-11-08 に実際のリプ欄で観察したものから作った。
"""
from __future__ import annotations

import re
import unicodedata

# (正規表現, 減点, 理由)
PATTERNS: list[tuple[str, float, str]] = [
    (r"(素晴らしい|興味深い|印象的|心強い|勉強になります|参考になります|ありがたい話|胸が熱く)", 2.0, "定型の褒め言葉"),
    (r"(まさに|さすが|なるほど[っ！!]*$)", 1.0, "定型の相づち"),
    (r"(が|は)(大事|重要|鍵|ポイント|肝)(です|だと|ですよね|になり)", 2.0, "一般論で締める"),
    (r"(安心材料|納得感|表裏一体|本質的|示唆)", 1.5, "評論家の語彙"),
    (r"(私|僕|自分|うち)も.{8,}(ています|てます|しています)", 1.5, "取って付けた自分語り"),
    (r"(かもしれません|と感じています|気がしてます|と思います)[。]?$", 1.0, "ぼかした締め"),
    (r"(ほど|につれて).{2,20}(ほど|なる)", 1.0, "〜ほど〜という一般論"),
    (r"という(割り切り|判断|設計|方針|姿勢)が", 1.5, "投稿の言い直し"),
    (r"ですね[！!。]?(\s|$)", 0.7, "〜ですね"),
    (r"#\S+", 1.5, "ハッシュタグ"),
    (r"[！!]{2,}", 0.5, "！の重ね"),
]

EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def char_ngrams(s: str, n: int = 3) -> set[str]:
    s = re.sub(r"\s+", "", unicodedata.normalize("NFKC", s))
    return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}


def similarity(a: str, b: str, n: int = 3) -> float:
    """文字3-gramのJaccard係数（0〜1）"""
    A, B = char_ngrams(a, n), char_ngrams(b, n)
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def overlap_with_source(reply: str, source: str, n: int = 4) -> float:
    """リプの文字4-gramのうち、元投稿にも出てくる割合（＝要約の言い直し度）"""
    R = char_ngrams(reply, n)
    if not R:
        return 0.0
    return len(R & char_ngrams(source, n)) / len(R)


def smell(reply: str, source: str = "") -> dict:
    """AI臭スコア（0=人間っぽい〜10=AIそのもの）と理由"""
    score, reasons = 0.0, []
    for pat, w, why in PATTERNS:
        hits = re.findall(pat, reply)
        if hits:
            score += w * min(len(hits), 2)
            reasons.append(why)
    emojis = len(EMOJI_RE.findall(reply))
    if emojis >= 2:
        score += 1.0 * (emojis - 1)
        reasons.append(f"絵文字{emojis}個")
    n = len(reply)
    if n > 80:
        score += min(3.0, (n - 80) / 40)
        reasons.append(f"長い（{n}字）")
    if reply.count("。") >= 3:
        score += 1.0
        reasons.append("文が3つ以上")
    if source:
        ov = overlap_with_source(reply, source)
        if ov > 0.35:
            score += 3.0 * ov
            reasons.append(f"投稿の言い直し（重なり{ov:.0%}）")
    return {"score": round(min(score, 10.0), 2), "reasons": reasons}

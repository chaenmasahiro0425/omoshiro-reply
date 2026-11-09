"""X の読み取り専用ラッパー（xurl を使う）。

このモジュールは GET しかしない。投稿・リプ・いいね等の書き込みは、
コードのどこからも呼べないように `_get()` で弾く（tests/test_no_write.py が検査する）。
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from urllib.parse import quote

TWEET_FIELDS = "text,note_tweet,author_id,conversation_id,created_at,public_metrics,referenced_tweets,lang"
USER_FIELDS = "username,name,description"


@dataclass
class Post:
    id: str
    text: str
    author: str = ""            # @なしのユーザー名
    author_name: str = ""
    author_bio: str = ""
    likes: int = 0
    replies: int = 0
    conversation_id: str = ""
    quoted_text: str = ""       # 引用している投稿の本文
    quoted_author: str = ""
    reply_to_text: str = ""     # リプ先の本文
    extra: dict = field(default_factory=dict)

    def context_block(self) -> str:
        lines = [f"投稿者: @{self.author}（{self.author_name}）" if self.author else "投稿者: 不明"]
        if self.author_bio:
            lines.append(f"投稿者のプロフィール: {self.author_bio[:120]}")
        if self.reply_to_text:
            lines.append(f"この投稿はリプライ。リプ先の本文:\n{self.reply_to_text}")
        lines.append(f"本文:\n{self.text}")
        if self.quoted_text:
            lines.append(f"引用している投稿（@{self.quoted_author}）:\n{self.quoted_text}")
        return "\n".join(lines)


class XReadError(RuntimeError):
    pass


def parse_id(s: str) -> str:
    m = re.search(r"status(?:es)?/(\d+)", s)
    if m:
        return m.group(1)
    if re.fullmatch(r"\d{5,25}", s.strip()):
        return s.strip()
    raise ValueError(f"投稿のURLかIDを渡してください: {s}")


def _get(path: str, app_auth: bool = False) -> dict:
    if not path.startswith(("/2/tweets", "/2/users")):
        raise XReadError(f"投稿とユーザーの読み取り以外は使いません: {path}")
    exe = shutil.which("xurl")
    if not exe:
        raise XReadError("xurl が見つかりません（https://github.com/xdevplatform/xurl）")
    cmd = [exe] + (["--auth", "app"] if app_auth else []) + [path]   # -X は付けない＝必ず GET
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    out = r.stdout
    i = out.find("{")                      # 手前に注意書きを出すラッパーがあっても読めるように
    if i < 0:
        raise XReadError(f"X API の応答が読めません: {(r.stderr or out)[:200]}")
    data = json.loads(out[i:])
    if "data" not in data and data.get("status") in (401, 403, 429):
        raise XReadError(f"X API エラー {data.get('status')}: {data.get('detail') or data.get('title')}")
    return data


def _text(t: dict) -> str:
    return (t.get("note_tweet") or {}).get("text") or t.get("text", "")


def get_post(post_id: str) -> Post:
    d = _get(f"/2/tweets/{post_id}?tweet.fields={TWEET_FIELDS}"
             f"&expansions=author_id,referenced_tweets.id,referenced_tweets.id.author_id"
             f"&user.fields={USER_FIELDS}")
    if "data" not in d:
        raise XReadError(f"投稿が取れません: {d.get('errors') or d}")
    t = d["data"]
    inc = d.get("includes", {})
    users = {u["id"]: u for u in inc.get("users", [])}
    tweets = {x["id"]: x for x in inc.get("tweets", [])}
    u = users.get(t.get("author_id"), {})
    p = Post(id=t["id"], text=_text(t), author=u.get("username", ""), author_name=u.get("name", ""),
             author_bio=u.get("description", ""), likes=t["public_metrics"]["like_count"],
             replies=t["public_metrics"]["reply_count"], conversation_id=t.get("conversation_id", t["id"]))
    for ref in t.get("referenced_tweets", []):
        rt = tweets.get(ref["id"])
        if not rt:
            continue
        ru = users.get(rt.get("author_id"), {})
        if ref["type"] == "quoted":
            p.quoted_text, p.quoted_author = _text(rt), ru.get("username", "")
        elif ref["type"] == "replied_to":
            p.reply_to_text = _text(rt)
    return p


def get_replies(conversation_id: str, limit: int = 20, exclude_author: str = "",
                target_id: str = "") -> list[Post]:
    """会話についたリプ（直近7日・1ページ最大100件）。検索APIはアプリ認証で叩く。
    target_id を渡すと、その投稿への直接のリプだけに絞る（別の枝・リプへのリプを混ぜない）"""
    q = f"conversation_id:{conversation_id} is:reply"
    if exclude_author:
        q += f" -from:{exclude_author}"
    d = _get(f"/2/tweets/search/recent?query={quote(q)}&max_results={max(10, min(limit * 2, 100))}"
             f"&tweet.fields={TWEET_FIELDS}&expansions=author_id&user.fields={USER_FIELDS}", app_auth=True)
    users = {u["id"]: u for u in d.get("includes", {}).get("users", [])}
    out = []
    rows = d.get("data", [])
    if target_id:
        rows = [t for t in rows if any(r["type"] == "replied_to" and r["id"] == target_id
                                       for r in t.get("referenced_tweets", []))]
    for t in rows[:limit]:
        u = users.get(t.get("author_id"), {})
        txt = re.sub(r"^(@\w+\s+)+", "", _text(t)).strip()   # 先頭の @宛先 を外す
        out.append(Post(id=t["id"], text=txt, author=u.get("username", ""), author_name=u.get("name", ""),
                        author_bio=u.get("description", ""), likes=t["public_metrics"]["like_count"],
                        replies=t["public_metrics"]["reply_count"], conversation_id=t.get("conversation_id", "")))
    return out


def get_user_posts(username: str, limit: int = 20, replies_only: bool = False) -> list[Post]:
    me = _get(f"/2/users/by/username/{username}?user.fields={USER_FIELDS}")
    uid = me["data"]["id"]
    excl = "retweets" if replies_only else "retweets,replies"
    d = _get(f"/2/users/{uid}/tweets?max_results={max(5, min(limit, 100))}&exclude={excl}"
             f"&tweet.fields={TWEET_FIELDS}")
    out = []
    for t in d.get("data", []):
        is_reply = any(r["type"] == "replied_to" for r in t.get("referenced_tweets", []))
        if replies_only and not is_reply:
            continue
        out.append(Post(id=t["id"], text=_text(t), author=username, likes=t["public_metrics"]["like_count"],
                        replies=t["public_metrics"]["reply_count"], conversation_id=t.get("conversation_id", "")))
    return out[:limit]

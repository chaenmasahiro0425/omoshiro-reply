from omoshiro.aismell import smell, similarity, overlap_with_source

AI_LIKE = [
    "「必要なら他社モデルを契約すればいい」という割り切りが印象的です。企業側は用途ごとにモデルを使い分ける前提なので、Claudeは文章やコード、業務の自動化に集中する方針なのかもしれません。",
    "忘れる・途中で詰まる弱点への改善、しかも無料で全員に開放なのがすごいです🔥 心強いです✨😊",
    "ローカルフォルダまで触れるようにしつつ、承認は自分のMacからだけ、という設計が大事だと思います。",
]
HUMAN_LIKE = ["お前じゃい！", "AIのリプライに手動で返してしまった時の虚しさ半端ないです", "間違いない。"]


def test_ai_like_scores_higher_than_human_like():
    ai = min(smell(t)["score"] for t in AI_LIKE)
    human = max(smell(t)["score"] for t in HUMAN_LIKE)
    assert ai > human


def test_short_tsukkomi_is_clean():
    assert smell("お前じゃい！")["score"] < 1


def test_restating_the_post_is_flagged():
    post = "Grok Bot強化週間。アプリ繋ぎまくる＋Claude Code連携もしたのでかなり便利になった。"
    r = smell("アプリ繋ぎまくる＋Claude Code連携もしたのでかなり便利になったのすごいですね", post)
    assert any("言い直し" in x for x in r["reasons"])
    assert overlap_with_source("全然関係ない話", post) < 0.2


def test_similarity_bounds():
    assert similarity("同じ文です", "同じ文です") == 1.0
    assert similarity("あいうえお", "かきくけこ") == 0.0

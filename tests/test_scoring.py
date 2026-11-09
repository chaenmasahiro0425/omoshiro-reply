from omoshiro.pipeline import overall, spearman, Cand, prune
from omoshiro.xapi import Post

FULL = {"surprise": 8, "landing": 8, "specificity": 8, "persona": 8, "brevity": 8, "harmless": 9}


def test_one_zero_axis_sinks_the_total():
    low = dict(FULL, specificity=0)
    assert overall(low, 50, 0) < overall(FULL, 50, 0) - 2


def test_harmful_is_penalized_hard():
    assert overall(dict(FULL, harmless=2), 90, 0) < overall(dict(FULL, surprise=4), 40, 0)


def test_smell_lowers_score():
    assert overall(FULL, 50, 5) < overall(FULL, 50, 0)


def test_spearman():
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
    assert spearman([1, 2, 3, 4], [0, 0, 0, 0]) is None


def test_prune_drops_obvious_and_duplicates():
    post = Post(id="1", text="新モデルが出た")
    an = {"obvious": ["新モデルすごいですね！早速試してみます"]}
    cands = [Cand(id="c1", text="新モデルすごいですね！早速試してみます"),
             Cand(id="c2", text="ワイの脳はまだ旧モデルで動いてる"),
             Cand(id="c3", text="ワイの脳はまだ旧モデルで動いてる。"),
             Cand(id="c4", text="あ" * 120)]
    keep, drop = prune(cands, an, post, [])
    assert [c.id for c in keep] == ["c2"]
    assert len(drop) == 3


def test_finalists_are_diverse():
    from omoshiro.pipeline import pick_finalists
    cs = [Cand(id="a", text="Macに繋がれてるのワイの方やん", technique="zurashi", score=8),
          Cand(id="b", text="Macに繋がれてるのはワイの方やった", technique="mitate", score=7.9),
          Cand(id="c", text="看板はGrok、厨房はClaude Codeの町中華", technique="mitate", score=7.0)]
    got = [c.id for c in pick_finalists(cs, 2)]
    assert got == ["a", "c"]


def test_self_reply_detection():
    from omoshiro.pipeline import is_self_reply
    assert is_self_reply(Post(id="1", text="x", author="masahirochaen"), "チャエン（@masahirochaen）")
    assert not is_self_reply(Post(id="1", text="x", author="usutaku_channel"), "チャエン（@masahirochaen）")

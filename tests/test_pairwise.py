"""総当たりの集計（swap の符号・欠票の扱い）と、LLM呼び出しでツールが全部切れていることの検査"""
import json
import subprocess

from omoshiro import llm, pipeline
from omoshiro.pipeline import Cand
from omoshiro.xapi import Post

POST = Post(id="1", text="テスト投稿")


def _fake(answers):
    """answers[(task, swap)] = 'A'|'B'|'draw'|None(失敗)"""
    def call_json(task, prompt, schema, temperature=0.7):
        swap = "A: 二番" in prompt          # 1組目の A に二番が来ていれば入れ替え版
        w = answers[(task, swap)]
        if w is None:
            raise RuntimeError("落ちた")
        return {"results": [{"pair": "p01", "winner": w, "why": ""}]}
    return call_json


def _run(monkeypatch, answers, judges=("j1",)):
    monkeypatch.setattr(pipeline, "call_json", _fake(answers))
    a, b = Cand(id="a", text="一番"), Cand(id="b", text="二番")
    res, cons = pipeline._pairwise(POST, [(a, b)], judges=list(judges))
    return res[0]["a_wins"], cons


def test_consistent_win(monkeypatch):
    # 通常順で A（＝一番）、入れ替え版で B（＝一番）→ 一番の完勝
    assert _run(monkeypatch, {("j1", False): "A", ("j1", True): "B"}) == (1.0, 1.0)


def test_position_bias_becomes_draw(monkeypatch):
    # どちらの順でも「A」＝位置で選んでいる → 50% と不一致
    assert _run(monkeypatch, {("j1", False): "A", ("j1", True): "A"}) == (0.5, 0.0)


def test_one_side_missing_is_not_counted(monkeypatch):
    rate, cons = _run(monkeypatch, {("j1", False): "A", ("j1", True): None})
    assert rate is None and cons is None


def test_other_judge_still_counts(monkeypatch):
    rate, _ = _run(monkeypatch, {("j1", False): "A", ("j1", True): None,
                                 ("j2", False): "B", ("j2", True): "A"}, judges=("j1", "j2"))
    assert rate == 0.0      # j1 は片側欠けで捨てられ、j2 の「二番の完勝」だけが残る


def test_claude_call_disables_all_tools(monkeypatch):
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, json.dumps({"structured_output": {"ok": 1}}), "")

    monkeypatch.setattr(llm.subprocess, "run", fake_run)
    monkeypatch.setattr(llm.shutil, "which", lambda x: "/usr/bin/claude")
    assert llm._claude_json("x", "p", {"type": "object"}) == {"ok": 1}
    cmd = seen["cmd"]
    assert cmd[cmd.index("--tools") + 1] == ""

"""このツールは X に一切書き込まない。コード上で書き込みの道が無いことを検査する"""
import re
from pathlib import Path

import pytest

from omoshiro import xapi

SRC = Path(__file__).resolve().parent.parent / "omoshiro"
WRITE_WORDS = r"""["'](post|reply|quote|like|repost|follow|dm|delete|media)["']"""


def test_only_xapi_calls_xurl():
    for f in SRC.glob("*.py"):
        if f.name != "xapi.py":
            assert 'which("xurl")' not in f.read_text(), f"{f.name} が xurl を直接呼んでいる"


def test_xapi_has_no_write_path():
    text = (SRC / "xapi.py").read_text()
    assert not re.search(r"""["']-X["']""", text), "-X（メソッド指定）がある"
    for line in text.splitlines():
        if "cmd" in line:
            assert not re.search(WRITE_WORDS, line), line


def test_get_refuses_non_read_paths():
    with pytest.raises(xapi.XReadError):
        xapi._get("/2/dm_conversations")
    with pytest.raises(xapi.XReadError):
        xapi._get("post")


def test_parse_id():
    assert xapi.parse_id("https://x.com/a/status/2119488747293266272?s=20") == "2119488747293266272"
    assert xapi.parse_id("2119488747293266272") == "2119488747293266272"

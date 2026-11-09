"""置き場所。

- ペルソナと既定設定はパッケージに同梱（pip install しても動く）
- 実行結果（runs/）と好みの記録（prefs/）は書き込める場所に置く:
  OMOSHIRO_HOME があればそこ、リポジトリから動かしているならリポジトリ直下、それ以外は ~/.omoshiro
"""
from __future__ import annotations

import os
from pathlib import Path

PKG = Path(__file__).resolve().parent
PERSONAS = PKG / "personas"
_REPO = PKG.parent

if os.environ.get("OMOSHIRO_HOME"):
    HOME = Path(os.environ["OMOSHIRO_HOME"]).expanduser()
elif (_REPO / ".git").exists():
    HOME = _REPO
else:
    HOME = Path.home() / ".omoshiro"

CONFIG = Path(os.environ.get("OMOSHIRO_CONFIG") or (HOME / "config.toml" if (HOME / "config.toml").exists()
                                                    else PKG / "config.toml"))

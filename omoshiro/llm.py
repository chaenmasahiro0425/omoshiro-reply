"""LLM 呼び出し層。

- 手元に ai-router（~/dev/tools/ai-router）があれば、その台帳（models.toml）の工程名で呼ぶ
- 無ければ `claude -p`（Claude Code のサブスク枠）で呼ぶ。モデル名は config.toml に置く

どちらも「JSON Schema を渡して構造化JSONを返す」だけの1関数に揃えてある。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from .paths import CONFIG

_AIROUTER = None


def _airouter():
    """ai-router を探して import する。無ければ False"""
    global _AIROUTER
    if _AIROUTER is not None:
        return _AIROUTER
    if os.environ.get("OMOSHIRO_BACKEND") == "claude":
        _AIROUTER = False
        return _AIROUTER
    cand = os.environ.get("AIROUTER_HOME") or os.path.expanduser("~/dev/tools/ai-router")
    if Path(cand, "airouter").is_dir():
        sys.path.insert(0, cand)
        try:
            import airouter  # noqa: F401
            from airouter import tasks as _tasks
            if "x_humor_generate" in _tasks():
                _AIROUTER = airouter
                return _AIROUTER
        except Exception:
            pass
    _AIROUTER = False
    return _AIROUTER


def _config() -> dict:
    if CONFIG.exists():
        with open(CONFIG, "rb") as f:
            return tomllib.load(f)
    return {}


SYSTEM = ("あなたは日本語のお笑いの構成作家です。指示された JSON だけを返します。"
          "前置きや説明文は書きません。")


def _claude_json(task: str, prompt: str, schema: dict, model: str | None = None,
                 effort: str | None = None) -> dict:
    cfg = _config().get("standalone", {})
    model = model or (cfg.get("models", {}) or {}).get(task) or cfg.get("model")
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError("claude CLI が見つかりません。Claude Code を入れるか ai-router を用意してください")
    env = {k: v for k, v in os.environ.items()
           if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL")}
    if not env.get("USER"):
        import getpass
        env["USER"] = getpass.getuser()
    cmd = [exe, "-p", "--output-format", "json",
           "--json-schema", json.dumps(schema, ensure_ascii=False),
           "--system-prompt", SYSTEM,
           "--setting-sources", "",
           "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
           "--disable-slash-commands", "--no-session-persistence",
           "--tools", ""]                     # 組み込みツールを全部切る（純テキスト。何も実行させない）
    if model:
        cmd[2:2] = ["--model", model]
    if effort:
        cmd[2:2] = ["--effort", effort]
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, env=env, timeout=900, cwd="/tmp")
    try:
        out = json.loads(r.stdout)
    except Exception:
        raise RuntimeError(f"claude -p が失敗しました(rc={r.returncode}): {(r.stderr or r.stdout)[:300]}")
    if out.get("is_error") or r.returncode != 0:
        # 利用上限（429）やログイン切れは result に人間向けの理由が入る
        raise RuntimeError(f"claude -p 失敗: {str(out.get('result') or out.get('subtype'))[:200]}")
    if isinstance(out.get("structured_output"), (dict, list)):
        return out["structured_output"]
    text = out.get("result") or ""
    return json.loads(text[text.find("{"): text.rfind("}") + 1])


def call_json(task: str, prompt: str, schema: dict, temperature: float = 0.7) -> dict:
    """工程名・プロンプト・スキーマを渡して dict を返す"""
    ar = _airouter()
    if ar:
        spec = ar.route(task)
        if spec.provider == "claude_code":
            # ai-router の claude_code はキーチェーンの長期トークンを差し込む。そのアカウントが
            # 上限に達していても、いまログインしている Claude Code は動くことがあるので先にそちらで呼ぶ。
            # 落ちたら台帳の alt（別系統）へ回す
            try:
                return _claude_json(task, prompt, schema, model=spec.model, effort=spec.effort)
            except Exception as e:
                alt = ar.route(task, alt=True)
                print(f"  ⚠️ {task}: Claude で失敗したので {alt.provider}:{alt.model} へ: {str(e)[:120]}", flush=True)
                data = ar.text_json(task, prompt, schema, temperature=temperature, verbose=False, fallback=False) \
                    if alt.provider == "claude_code" else _ar_run(alt, prompt, schema, temperature)
                if isinstance(data, dict):
                    data.pop("__usage__", None)
                return data
        data = ar.text_json(task, prompt, schema, temperature=temperature, verbose=False)
        if isinstance(data, dict):
            data.pop("__usage__", None)
        return data
    return _claude_json(task, prompt, schema)


def backend_name() -> str:
    return "ai-router" if _airouter() else "claude -p"


def _ar_run(spec, prompt: str, schema: dict, temperature: float) -> dict:
    from airouter.call import _run
    return _run(spec, prompt, schema, temperature, False)


def has_task(task: str) -> bool:
    """その工程が使えるか（ai-router なら台帳にあるか。claude -p 単体なら常に使える）"""
    ar = _airouter()
    if ar:
        return task in ar.tasks()
    return True


def resolved_models(task_list: list[str]) -> dict[str, str]:
    """工程 → 実際に使う provider:model（独立した審査かどうかの判定と記録に使う）"""
    ar = _airouter()
    out = {}
    for t in task_list:
        if ar:
            try:
                sp = ar.route(t)
                out[t] = f"{sp.provider}:{sp.model}"
            except KeyError:
                continue
        else:
            cfg = _config().get("standalone", {})
            out[t] = "claude:" + ((cfg.get("models", {}) or {}).get(t) or cfg.get("model") or "default")
    return out

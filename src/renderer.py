"""会議準備チェックリスト 描画（spec §5/§7・AC-16）.

md / html / json / csv の4フォーマットを PrepResult から生成する。
  - 時刻・乱数を混ぜない（決定論 §8）。now()/today() 禁止。
  - BOM はここでは付けない（utf-8-sig は cli の責務・§7）。
  - envelope は別担当（envelope.py）。本モジュールは import も参照もしない。
  - 判定を再計算しない（PrepResult を描画するだけ）。

確定IF（cli が依存）: render_md / render_html / render_json / render_csv / render

由来: C3 escalation-skill/src/renderer.py 同型・prep checklist 構造。
"""

from __future__ import annotations

import csv as _csv
import html as _html
import io
import json

from .prep import PrepResult
from . import config as _cfg

# ---------------------------------------------------------------------------
# CSV 固定列（spec §7・AC-15/16・9列・順序固定）
# ---------------------------------------------------------------------------
_CSV_HEADER = [
    "プロジェクト",
    "区分",
    "状態",
    "項目",
    "担当",
    "期日",
    "関連タスク",
    "関連工程",
    "根拠セル参照",
]


def _none_to_empty(v: object) -> str:
    """None / 空値を空文字に変換。"""
    if v is None:
        return ""
    return str(v)


def _evidence_refs(evidence: list) -> str:
    """evidence（CellRef dataclass または dict）から ref を '; ' 連結する。"""
    parts: list[str] = []
    for e in evidence:
        ref = e.render() if hasattr(e, "render") else e.get("ref", "")
        if ref:
            parts.append(ref)
    return "; ".join(parts)


def _related_tasks_str(item) -> str:
    """related_tasks を ',' 連結。空は空文字。"""
    return ",".join(item.related_tasks) if item.related_tasks else ""


def _related_phases_str(item) -> str:
    """related_phases を ',' 連結。None/空は空文字。"""
    if not item.related_phases:
        return ""
    return ",".join(item.related_phases)


def _status_label(status: str) -> str:
    """status -> 日本語ラベル（config.STATUS_LABELS）。未知は status そのまま。"""
    return _cfg.STATUS_LABELS.get(status, status)


def _kind_label(kind: str) -> str:
    """kind -> 日本語ラベル（config.KIND_LABELS）。未知は kind そのまま。"""
    return _cfg.KIND_LABELS.get(kind, kind)


# ---------------------------------------------------------------------------
# md — AC-16
# ---------------------------------------------------------------------------

def render_md(r: PrepResult, *, project_name: "str | None" = None) -> str:
    """会議準備チェックリストを Markdown で返す（AC-16）.

    見出しに「会議準備チェックリスト」を含む・headline・as_of・各項目（区分/状態/項目/
    担当/期日/関連工程）と evidence の ref（'!'含む）・recommended_actions・overdue_note。
    """
    pn = project_name or ""
    out: list[str] = []

    title = "# 会議準備チェックリスト" + (f"（{pn}）" if pn else "")
    out.append(title)
    out.append("")

    out.append("## 概要")
    out.append("")
    out.append(f"- **headline**: {r.headline}")
    out.append(f"- **as_of**: {r.as_of}（{r.as_of_week}）")
    out.append(f"- **horizon_days**: {r.horizon_days}")
    out.append(f"- **meeting_scope**: {r.meeting_scope}")
    out.append("")

    out.append("## チェックリスト")
    out.append("")
    if not r.checklist:
        out.append("（対応項目なし）")
        out.append("")
    else:
        for idx, it in enumerate(r.checklist, 1):
            out.append(f"### {idx}. [{_kind_label(it.kind)}/{_status_label(it.status)}] {it.title}")
            out.append("")
            out.append(f"- **区分**: {it.kind}（{_kind_label(it.kind)}）")
            out.append(f"- **状態**: {it.status}（{_status_label(it.status)}）")
            if it.owner:
                out.append(f"- **担当**: {it.owner}")
            if it.due:
                out.append(f"- **期日**: {it.due}")
            if it.related_tasks:
                out.append(f"- **関連タスク**: {', '.join(it.related_tasks)}")
            if it.related_phases is not None:
                phases = ", ".join(it.related_phases) if it.related_phases else "（なし）"
                out.append(f"- **関連工程**: {phases}")
            if it.evidence:
                out.append("")
                out.append("**根拠セル参照**")
                out.append("")
                for ev in it.evidence:
                    ref = ev.render() if hasattr(ev, "render") else ev.get("ref", "")
                    out.append(f"- {ref}")
            out.append("")

    if r.recommended_actions:
        out.append("## 推奨アクション")
        out.append("")
        for idx, act in enumerate(r.recommended_actions, 1):
            out.append(f"{idx}. {act}")
        out.append("")

    out.append("## サマリー")
    out.append("")
    s = r.summary
    bys = s.get("by_status", {})
    out.append(f"- 対応項目合計: {s.get('item_count', 0)}")
    out.append(f"- 期限経過(overdue): {bys.get('overdue', 0)}")
    out.append(f"- 期限間近(due_soon): {bys.get('due_soon', 0)}")
    out.append(f"- 未確認(pending): {bys.get('pending', 0)}")
    out.append("")
    if r.overdue_note:
        out.append(f"> {r.overdue_note}")
        out.append("")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# html — AC-16
# ---------------------------------------------------------------------------

def render_html(r: PrepResult, *, project_name: "str | None" = None) -> str:
    """会議準備チェックリストを HTML で返す（AC-16）。evidence の ref（'!'含む）を含む。"""
    pn = project_name or ""
    title_text = "会議準備チェックリスト" + (f"（{pn}）" if pn else "")

    css = """<style>
.prep-checklist{font-family:sans-serif;font-size:14px}
.prep-checklist h1,.prep-checklist h2,.prep-checklist h3{margin:0.8em 0 0.4em}
.prep-checklist ul{margin:0.3em 0;padding-left:1.5em}
.prep-checklist li{margin-bottom:0.2em}
.status-overdue{color:#c00;font-weight:bold}
.status-due_soon{color:#996600;font-weight:bold}
.status-pending{color:#333}
.status-info{color:#06c}
.evidence-block{background:#f5f5f5;border-left:3px solid #ccc;padding:4px 8px;margin:4px 0}
</style>"""

    parts: list[str] = ['<div class="prep-checklist">']
    parts.append(css)
    parts.append(f"<h1>{_html.escape(title_text)}</h1>")

    parts.append("<h2>概要</h2><ul>")
    parts.append(f"<li><strong>headline</strong>: {_html.escape(r.headline)}</li>")
    parts.append(f"<li><strong>as_of</strong>: {_html.escape(r.as_of)}（{_html.escape(r.as_of_week)}）</li>")
    parts.append(f"<li><strong>horizon_days</strong>: {_html.escape(str(r.horizon_days))}</li>")
    parts.append(f"<li><strong>meeting_scope</strong>: {_html.escape(r.meeting_scope)}</li>")
    parts.append("</ul>")

    parts.append("<h2>チェックリスト</h2>")
    if not r.checklist:
        parts.append("<p>（対応項目なし）</p>")
    else:
        for idx, it in enumerate(r.checklist, 1):
            heading = f"{idx}. [{_html.escape(_kind_label(it.kind))}/{_html.escape(_status_label(it.status))}] {_html.escape(it.title)}"
            parts.append(f"<h3>{heading}</h3><ul>")
            parts.append(f"<li><strong>区分</strong>: {_html.escape(it.kind)}（{_html.escape(_kind_label(it.kind))}）</li>")
            parts.append(
                f'<li><strong>状態</strong>: <span class="status-{_html.escape(it.status)}">'
                f"{_html.escape(it.status)}（{_html.escape(_status_label(it.status))}）</span></li>"
            )
            if it.owner:
                parts.append(f"<li><strong>担当</strong>: {_html.escape(it.owner)}</li>")
            if it.due:
                parts.append(f"<li><strong>期日</strong>: {_html.escape(it.due)}</li>")
            if it.related_tasks:
                parts.append(f"<li><strong>関連タスク</strong>: {_html.escape(', '.join(it.related_tasks))}</li>")
            if it.related_phases is not None:
                phases = ", ".join(it.related_phases) if it.related_phases else "（なし）"
                parts.append(f"<li><strong>関連工程</strong>: {_html.escape(phases)}</li>")
            parts.append("</ul>")
            if it.evidence:
                parts.append('<div class="evidence-block"><strong>根拠セル参照</strong><ul>')
                for ev in it.evidence:
                    ref = ev.render() if hasattr(ev, "render") else ev.get("ref", "")
                    parts.append(f"<li>{_html.escape(ref)}</li>")
                parts.append("</ul></div>")

    if r.recommended_actions:
        parts.append("<h2>推奨アクション</h2><ol>")
        for act in r.recommended_actions:
            parts.append(f"<li>{_html.escape(act)}</li>")
        parts.append("</ol>")

    parts.append("<h2>サマリー</h2><ul>")
    s = r.summary
    bys = s.get("by_status", {})
    parts.append(f"<li>対応項目合計: {_html.escape(str(s.get('item_count', 0)))}</li>")
    parts.append(f"<li>期限経過(overdue): {_html.escape(str(bys.get('overdue', 0)))}</li>")
    parts.append(f"<li>期限間近(due_soon): {_html.escape(str(bys.get('due_soon', 0)))}</li>")
    parts.append(f"<li>未確認(pending): {_html.escape(str(bys.get('pending', 0)))}</li>")
    parts.append("</ul>")
    if r.overdue_note:
        parts.append(f"<p><em>{_html.escape(r.overdue_note)}</em></p>")

    parts.append("</div>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# json — AC-16（envelope とは別の素 json）
# ---------------------------------------------------------------------------

def render_json(r: PrepResult, *, project_name: "str | None" = None) -> str:
    """会議準備チェックリストを機械可読 JSON で返す（AC-16）.

    checklist/summary/recommended_actions/headline/overdue_note を含む。
    evidence は各 CellRef.render() を ref キーに展開。envelope を参照せず PrepResult から独立構築。
    """
    def _ev_to_dict(ev) -> dict:
        if hasattr(ev, "render"):
            return {
                "sheet": ev.sheet,
                "column": ev.column,
                "row": ev.row,
                "value": ev.value.isoformat() if hasattr(ev.value, "isoformat") else ev.value,
                "note": ev.note,
                "ref": ev.render(),
            }
        return dict(ev)

    def _item_to_dict(it) -> dict:
        d: dict = {
            "kind": it.kind,
            "status": it.status,
            "title": it.title,
            "owner": it.owner,
            "due": it.due,
            "related_tasks": list(it.related_tasks),
            "evidence": [_ev_to_dict(e) for e in it.evidence],
        }
        if it.related_phases is not None:
            d["related_phases"] = list(it.related_phases)
        return d

    result_dict = {
        "project_name": project_name or "",
        "as_of": r.as_of,
        "as_of_week": r.as_of_week,
        "horizon_days": r.horizon_days,
        "meeting_scope": r.meeting_scope,
        "headline": r.headline,
        "checklist": [_item_to_dict(it) for it in r.checklist],
        "summary": {
            "item_count": r.summary["item_count"],
            "by_status": dict(r.summary["by_status"]),
            "by_kind": dict(r.summary["by_kind"]),
        },
        "overdue_note": r.overdue_note,
        "recommended_actions": list(r.recommended_actions),
    }
    return json.dumps(result_dict, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# csv — §7・AC-15/16（BOM を付けない＝cli 責務）
# ---------------------------------------------------------------------------

def render_csv(r: PrepResult, *, project_name: "str | None" = None) -> str:
    """1チェック項目=1行 tidy CSV を返す（§7・AC-15/16）.

    固定9列（この順）: プロジェクト, 区分, 状態, 項目, 担当, 期日, 関連タスク, 関連工程, 根拠セル参照。
    - 項目0件は header 1行のみ。
    - 全行フィールド数=9。BOM はここでは付けない（cli 責務）。
    - csv.writer + io.StringIO + lineterminator="\\n" + QUOTE_MINIMAL で決定論。
    """
    pn = project_name or ""
    buf = io.StringIO()
    writer = _csv.writer(buf, lineterminator="\n", quoting=_csv.QUOTE_MINIMAL)
    writer.writerow(_CSV_HEADER)

    for it in r.checklist:
        writer.writerow([
            pn,
            _none_to_empty(it.kind),
            _none_to_empty(it.status),
            _none_to_empty(it.title),
            _none_to_empty(it.owner),
            _none_to_empty(it.due),
            _related_tasks_str(it),
            _related_phases_str(it),
            _evidence_refs(it.evidence),
        ])

    return buf.getvalue()


# ---------------------------------------------------------------------------
# ディスパッチャ
# ---------------------------------------------------------------------------

def render(r: PrepResult, fmt: str, *, project_name: "str | None" = None) -> str:
    """fmt in {"md","html","json","csv"} を各関数にディスパッチする（未知は ValueError）."""
    _dispatch = {
        "md": render_md,
        "html": render_html,
        "json": render_json,
        "csv": render_csv,
    }
    if fmt not in _dispatch:
        raise ValueError(f"未知のフォーマット: {fmt!r}。有効値: {sorted(_dispatch)}")
    return _dispatch[fmt](r, project_name=project_name)

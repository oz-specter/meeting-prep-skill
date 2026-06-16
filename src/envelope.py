"""共通エンベロープ（会議事前準備スキル）— A1 互換 schema 1.1・ui_type=prep_checklist.

D1 report-skill / C3 escalation-skill の envelope.py 同型。
設計: claude-std concept/13（統合ダッシュボードのアーキテクチャ）。
意図: ダッシュボードは payload の中身ではなく `ui_type` で分岐する（有限UI型語彙）。
      ui_type="prep_checklist"（確定UI型9種目）の新タイルとして A1 と同一トップレベルキー集合を保つ。

エンベロープ構造（schema 1.1・トップレベル10キー）:
    {schema_version, skill_id, ui_type, ui_type_label,
     title, generated_at, status, notice, meta, payload}

- `status`: "ok" | "degraded" | "error"（degraded=必須列/シート欠落で手当て提案のみ）。
- `payload`: spec §5 キー dict。build_prep() の PrepResult を dict 化（呼び出し側変更から隔離）。
- `notice`: prep_result.notice（dict|None）または degraded 時 {sheet, missing_columns, suggestion}。
- `generated_at`: now().isoformat(timespec="seconds")（出力スタンプ専用・payload/meta に時刻を入れない＝決定論 §6）。

複製元: C3 escalation-skill/src/envelope.py（同型構造）。確定IF: prep.PrepResult / model.MissingColumnReport。
"""

from __future__ import annotations

import datetime as _dt
import json

from .prep import PrepResult
from .model import MissingColumnReport

SCHEMA_VERSION = "1.1"
SKILL_ID = "meeting-prep-skill"
UI_TYPE = "prep_checklist"
UI_TYPE_LABEL = "準備チェックリスト（会議事前準備）"

STATUS_OK = "ok"
STATUS_DEGRADED = "degraded"
STATUS_ERROR = "error"


def _now() -> str:
    """generated_at 専用。分析値（payload/meta）には使わない（決定論 spec §6）."""
    return _dt.datetime.now().isoformat(timespec="seconds")


def _cellref_to_dict(ref) -> dict:
    """CellRef -> evidence 6キー dict（手組み禁止・render() 経由）.

    6キー固定: sheet / column / row / value / note / ref。
    value は JSON 安全化（date/datetime は isoformat、他はそのまま）。
    """
    if isinstance(ref.value, (_dt.date, _dt.datetime)):
        safe_value = ref.value.isoformat()
    else:
        safe_value = ref.value
    return {
        "sheet": ref.sheet,
        "column": ref.column,
        "row": ref.row,
        "value": safe_value,
        "note": ref.note,
        "ref": ref.render(),
    }


def _prep_to_payload(r: PrepResult) -> dict:
    """PrepResult -> payload dict（spec §5 形）。シリアライズのみ・再計算なし."""
    return {
        "as_of": r.as_of,
        "as_of_week": r.as_of_week,
        "horizon_days": r.horizon_days,
        "meeting_scope": r.meeting_scope,
        "headline": r.headline,
        "checklist": [
            {
                "kind": it.kind,
                "status": it.status,
                "title": it.title,
                "owner": it.owner,
                "due": it.due,
                "related_tasks": list(it.related_tasks),
                "evidence": [_cellref_to_dict(e) for e in it.evidence],
                **({"related_phases": list(it.related_phases)}
                   if it.related_phases is not None else {}),
            }
            for it in r.checklist
        ],
        "summary": {
            "item_count": r.summary["item_count"],
            "by_status": dict(r.summary["by_status"]),
            "by_kind": dict(r.summary["by_kind"]),
        },
        "overdue_note": r.overdue_note,
        "recommended_actions": list(r.recommended_actions),
    }


def build_envelope(
    prep_result: PrepResult,
    *,
    title: str,
    project_type: "str | None" = None,
    project_name: "str | None" = None,
    status: str = STATUS_OK,
    notice: str = "__USE_RESULT__",
) -> dict:
    """PrepResult を共通エンベロープに包む（正常系）.

    Args:
        prep_result: prep.build_prep() の返り値（PrepResult）。
        title: レポートタイトル。
        project_type: 案件タイプ（既定 None・spec §5 で project_type=None）。
        project_name: プロジェクト名（ダッシュボード統合の grouping キー）。非Null推奨。
        status: "ok" / "degraded" / "error"。
        notice: 省略時（"__USE_RESULT__"）は prep_result.notice をそのまま使う。
    """
    resolved_notice = prep_result.notice if notice == "__USE_RESULT__" else notice
    by_status = prep_result.summary["by_status"]

    return {
        "schema_version": SCHEMA_VERSION,
        "skill_id": SKILL_ID,
        "ui_type": UI_TYPE,
        "ui_type_label": UI_TYPE_LABEL,
        "title": title,
        "generated_at": _now(),
        "status": status,
        "notice": resolved_notice,
        "meta": {
            "project_name": project_name,
            "project_type": project_type,
            "item_count": prep_result.summary["item_count"],
            "overdue_count": by_status.get("overdue", 0),
            "due_soon_count": by_status.get("due_soon", 0),
            "as_of": prep_result.as_of,
            "as_of_week": prep_result.as_of_week,
            "unit": "件",
        },
        "payload": _prep_to_payload(prep_result),
    }


def from_missing_report(
    report: MissingColumnReport,
    *,
    title: "str | None" = None,
    project_type: "str | None" = None,
    project_name: "str | None" = None,
) -> dict:
    """必須列／シート欠落時の縮退エンベロープ（A1 同型・status=degraded）.

    「Excelを直せ」ではなく「これがあればここまで出せます」を返す（既存資産AIラッピング）。
    notice スキーマ（A1 同型）: {sheet, missing_columns, suggestion}。
    payload は空形（spec §5 キーを保ち全 0/空）。meta カウント全0・as_of None。
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "skill_id": SKILL_ID,
        "ui_type": UI_TYPE,
        "ui_type_label": UI_TYPE_LABEL,
        "title": title or "入力の確認が必要です",
        "generated_at": _now(),
        "status": STATUS_DEGRADED,
        "notice": {
            "sheet": report.sheet,
            "missing_columns": list(report.missing_columns),
            "suggestion": report.suggestion,
        },
        "meta": {
            "project_name": project_name,
            "project_type": project_type,
            "item_count": 0,
            "overdue_count": 0,
            "due_soon_count": 0,
            "as_of": None,
            "as_of_week": None,
            "unit": "件",
        },
        "payload": {
            "as_of": None,
            "as_of_week": None,
            "horizon_days": None,
            "meeting_scope": "all",
            "headline": "",
            "checklist": [],
            "summary": {
                "item_count": 0,
                "by_status": {"overdue": 0, "due_soon": 0, "pending": 0, "info": 0},
                "by_kind": {},
            },
            "overdue_note": "",
            "recommended_actions": [],
        },
    }


def dumps(envelope: dict) -> str:
    """エンベロープ dict を JSON 文字列に変換（ensure_ascii=False・indent=2）."""
    return json.dumps(envelope, ensure_ascii=False, indent=2)

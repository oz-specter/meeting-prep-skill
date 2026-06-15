"""ISO週ユーティリティ（D3 meeting-prep-skill 用・D1 report-skill/src/workcal.py の逐語複製）.

由来: D1 report-skill/src/workcal.py（＝B1 progress-skill/src/workcal.py の逐語複製）。
営業日・祝日（jpholiday）・稼働曜日まわりは持ち込まない。
今日/now() の取得なし。完全決定論。コードは改変しない（由来コメントのみ）。

確定IF（後段 prep が依存）:
  iso_week_label(d)         : date -> "YYYY-Www"
  week_start(label)         : "YYYY-Www" -> date | None （形式不正・範囲外は None）
  week_sequence(first, last): 連続ISO週ラベル列（両端含む）。不正・first>last は []
"""

from __future__ import annotations

import datetime as _dt
import re

_LABEL_RE = re.compile(r"^(\d{4})-W(\d{2})$")


def iso_week_label(d: _dt.date) -> str:
    """date -> "YYYY-Www"（ISO週・ゼロ埋め2桁）.

    例: date(2026, 6, 1) -> "2026-W23"
        date(2026, 8, 17) -> "2026-W34"
    """
    iso = d.isocalendar()
    year = iso[0]
    week = iso[1]
    return f"{year}-W{week:02d}"


def week_start(label: str) -> _dt.date | None:
    """"YYYY-Www" -> その週の月曜日。形式不正・範囲外は None（例外を投げない）.

    例: "2026-W23" -> date(2026, 6, 1)
        "2026-W34" -> date(2026, 8, 17)
        "bad"      -> None
        "2026-W60" -> None（範囲外）
    """
    m = _LABEL_RE.match(label)
    if m is None:
        return None
    year = int(m.group(1))
    week = int(m.group(2))
    try:
        return _dt.date.fromisocalendar(year, week, 1)
    except ValueError:
        # 週番号が範囲外（例: W00, W60）
        return None


def week_sequence(first_label: str, last_label: str) -> list[str]:
    """両端含む連続ISO週ラベル列。年跨ぎ対応。

    どちらかパース不能、または first > last の場合は []。

    例: week_sequence("2026-W52", "2027-W02")
        -> ["2026-W52", "2026-W53", "2027-W01", "2027-W02"]
        week_sequence("2026-W23", "2026-W34")  # 長さ 12
        -> ["2026-W23", ..., "2026-W34"]
    """
    first = week_start(first_label)
    last = week_start(last_label)
    if first is None or last is None:
        return []
    if first > last:
        return []

    result: list[str] = []
    current = first
    one_week = _dt.timedelta(weeks=1)
    while current <= last:
        result.append(iso_week_label(current))
        current += one_week
    return result

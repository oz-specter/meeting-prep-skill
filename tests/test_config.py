"""tests/test_config.py — config.py の単体テスト（D1複製の議事録部＋D3固有）."""

from __future__ import annotations

import re

import pytest

from src import config


class TestMinutesSchema:
    def test_required_columns(self):
        assert config.MINUTES_REQUIRED_COLUMNS == ["日付", "会議体", "決定事項"]

    def test_optional_columns(self):
        assert config.MINUTES_OPTIONAL_COLUMNS == [
            "出席", "宿題_内容", "宿題_担当", "宿題_期限", "関連タスク", "関連要件",
        ]

    def test_sheet_alias_self_contained(self):
        assert config.MINUTES_SHEET_ALIASES["議事録"][0] == "議事録"

    def test_alias_keys_cover_required_and_optional(self):
        keys = set(config.MINUTES_COLUMN_ALIASES.keys())
        assert set(config.MINUTES_REQUIRED_COLUMNS) <= keys
        assert set(config.MINUTES_OPTIONAL_COLUMNS) <= keys

    @pytest.mark.parametrize("raw,expected", [
        ("日付", "日付"),
        ("会議日", "日付"),
        ("会議体", "会議体"),
        ("決定", "決定事項"),
        ("宿題", "宿題_内容"),
        ("担当", "宿題_担当"),
        ("期限", "宿題_期限"),
        ("タスクID", "関連タスク"),
        ("要件", "関連要件"),
    ])
    def test_normalize_minutes_column_aliases(self, raw, expected):
        assert config.normalize_minutes_column(raw) == expected

    def test_normalize_strips_and_case_insensitive(self):
        assert config.normalize_minutes_column("  ToDo  ") == "宿題_内容"

    def test_normalize_unknown_returns_none(self):
        assert config.normalize_minutes_column("未知の列") is None

    def test_normalize_non_string_returns_none(self):
        assert config.normalize_minutes_column(None) is None
        assert config.normalize_minutes_column(123) is None

    def test_stale_minutes_days(self):
        assert config.STALE_MINUTES_DAYS == 30


class TestD3Status:
    def test_horizon_days(self):
        assert config.HORIZON_DAYS == 14

    def test_status_labels_keys(self):
        assert set(config.STATUS_LABELS.keys()) == {"overdue", "due_soon", "pending", "info"}

    def test_status_order_keys_match_labels(self):
        assert set(config.STATUS_ORDER.keys()) == set(config.STATUS_LABELS.keys())

    def test_status_order_priority(self):
        o = config.STATUS_ORDER
        assert o["overdue"] < o["due_soon"] < o["pending"] < o["info"]

    def test_status_order_unique(self):
        vals = list(config.STATUS_ORDER.values())
        assert len(vals) == len(set(vals))

    def test_kind_labels_keys(self):
        assert set(config.KIND_LABELS.keys()) == {
            "carryover_action", "decision_followup", "upcoming_task", "freshness",
        }


class TestDecisionRefPattern:
    def test_matches_rk(self):
        assert re.search(config.DECISION_REF_PATTERN, "Gap対応はアドオン合意範囲に限定(RK-05)")

    def test_matches_r(self):
        assert re.search(config.DECISION_REF_PATTERN, "要件R-01〜R-10を全件承認")

    def test_findall_multiple(self):
        m = re.findall(config.DECISION_REF_PATTERN, "(R-02)仕様の確定期限を設定(RK-12)")
        assert set(m) == {"R-02", "RK-12"}

    def test_no_match_plain_text(self):
        assert re.search(config.DECISION_REF_PATTERN, "体制とスケジュールを承認") is None


class TestTemplates:
    def test_headline_format_fields(self):
        s = config.HEADLINE_FORMAT.format(item_count=11, overdue=5, due_soon=1)
        assert "11" in s and "5" in s and "1" in s

    def test_headline_empty_is_str(self):
        assert isinstance(config.HEADLINE_FORMAT_EMPTY, str) and config.HEADLINE_FORMAT_EMPTY

    def test_recommended_action_templates_keys(self):
        assert set(config.RECOMMENDED_ACTION_TEMPLATES.keys()) == {
            "overdue", "upcoming", "decision", "freshness",
        }

    def test_recommended_upcoming_uses_horizon(self):
        s = config.RECOMMENDED_ACTION_TEMPLATES["upcoming"].format(horizon=14, n=13)
        assert "14" in s and "13" in s

    def test_overdue_note_text(self):
        assert "完了状態" in config.OVERDUE_NOTE

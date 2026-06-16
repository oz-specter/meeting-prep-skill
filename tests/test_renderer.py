"""tests/test_renderer.py — render_md/html/json/csv/render（AC-16）.

各format生成・evidence ref・CSV9列/BOMなし（cli責務）・0件header1行・未知fmt ValueError。
"""

from __future__ import annotations

import csv as _csv
import io
import json

import pytest

from src.minutes_reader import read_minutes
from src.wbs_reader import read_wbs
from src.prep import build_prep
from src import renderer as rnd


@pytest.fixture
def result_wbs(minutes_sample_path, wbs_sample_path):
    reg = read_minutes(str(minutes_sample_path))
    wv = read_wbs(str(wbs_sample_path))
    return build_prep(reg, wbs_view=wv)


class TestMd:
    def test_title_and_headline(self, result_wbs):
        md = rnd.render_md(result_wbs, project_name="P")
        assert "会議準備チェックリスト" in md
        assert result_wbs.headline in md

    def test_contains_cellref(self, result_wbs):
        md = rnd.render_md(result_wbs)
        assert "!" in md


class TestHtml:
    def test_title_and_cellref(self, result_wbs):
        h = rnd.render_html(result_wbs, project_name="P")
        assert "会議準備チェックリスト" in h
        assert "!" in h


class TestJson:
    def test_parseable_with_evidence(self, result_wbs):
        d = json.loads(rnd.render_json(result_wbs, project_name="P"))
        assert d["as_of"] == result_wbs.as_of
        assert len(d["checklist"]) == result_wbs.summary["item_count"]
        ev = d["checklist"][0]["evidence"][0]
        assert "!" in ev["ref"]

    def test_non_ascii_preserved(self, result_wbs):
        s = rnd.render_json(result_wbs)
        assert "\\u" not in s


class TestCsv:
    def test_header_9_cols(self, result_wbs):
        out = rnd.render_csv(result_wbs, project_name="P")
        rows = list(_csv.reader(io.StringIO(out)))
        assert rows[0] == [
            "プロジェクト", "区分", "状態", "項目", "担当", "期日",
            "関連タスク", "関連工程", "根拠セル参照",
        ]

    def test_all_rows_9_cols_one_per_item(self, result_wbs):
        out = rnd.render_csv(result_wbs, project_name="P")
        rows = list(_csv.reader(io.StringIO(out)))
        assert all(len(r) == 9 for r in rows)
        assert len(rows) == result_wbs.summary["item_count"] + 1

    def test_no_bom_in_renderer(self, result_wbs):
        out = rnd.render_csv(result_wbs)
        assert not out.startswith("﻿")

    def test_zero_items_header_only(self, minutes_sample_path):
        reg = read_minutes(str(minutes_sample_path))
        r = build_prep(reg, meeting_type="__存在しない会議体__")
        out = rnd.render_csv(r, project_name="P")
        rows = list(_csv.reader(io.StringIO(out)))
        assert len(rows) == 1


class TestDispatch:
    def test_render_dispatches(self, result_wbs):
        for fmt in ("md", "html", "json", "csv"):
            assert rnd.render(result_wbs, fmt)

    def test_unknown_format_raises(self, result_wbs):
        with pytest.raises(ValueError):
            rnd.render(result_wbs, "pdf")

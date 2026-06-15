"""tests/test_workcal.py — workcal.py の単体テスト（D1逐語複製）.

確定IF: iso_week_label / week_start / week_sequence
年跨ぎテスト期待値の根拠: date(2026,12,28).isocalendar() => week=53。
"""

import datetime
import pytest

from src.workcal import iso_week_label, week_start, week_sequence


class TestIsoWeekLabel:
    def test_sample_first_week(self):
        assert iso_week_label(datetime.date(2026, 6, 1)) == "2026-W23"

    def test_sample_last_week(self):
        assert iso_week_label(datetime.date(2026, 8, 17)) == "2026-W34"

    def test_d3_as_of_week(self):
        """D3 既定 as_of=2026-07-10 -> "2026-W28"（specs §10 A-2）."""
        assert iso_week_label(datetime.date(2026, 7, 10)) == "2026-W28"

    def test_week_number_zero_padded(self):
        assert iso_week_label(datetime.date(2026, 1, 5)) == "2026-W02"

    def test_year_boundary_dec_28(self):
        assert iso_week_label(datetime.date(2026, 12, 28)) == "2026-W53"

    def test_year_boundary_jan_1_belongs_to_prev(self):
        assert iso_week_label(datetime.date(2027, 1, 1)) == "2026-W53"

    def test_year_boundary_jan_4_2027(self):
        assert iso_week_label(datetime.date(2027, 1, 4)) == "2027-W01"

    def test_returns_string(self):
        assert isinstance(iso_week_label(datetime.date(2026, 6, 1)), str)


class TestWeekStart:
    def test_sample_w23(self):
        assert week_start("2026-W23") == datetime.date(2026, 6, 1)

    def test_sample_w34(self):
        assert week_start("2026-W34") == datetime.date(2026, 8, 17)

    def test_d3_w28(self):
        """2026-W28 -> date(2026, 7, 6)（D3 as_of週の月曜）."""
        assert week_start("2026-W28") == datetime.date(2026, 7, 6)

    def test_result_is_monday_w23(self):
        result = week_start("2026-W23")
        assert result is not None
        assert result.weekday() == 0

    def test_result_is_monday_w34(self):
        result = week_start("2026-W34")
        assert result is not None
        assert result.weekday() == 0

    def test_invalid_format_bad(self):
        assert week_start("bad") is None

    def test_invalid_format_empty(self):
        assert week_start("") is None

    def test_invalid_format_no_hyphen(self):
        assert week_start("2026W23") is None

    def test_invalid_format_lowercase_w(self):
        assert week_start("2026-w23") is None

    def test_out_of_range_w60(self):
        assert week_start("2026-W60") is None

    def test_out_of_range_w00(self):
        assert week_start("2026-W00") is None

    def test_year_boundary_w53(self):
        result = week_start("2026-W53")
        assert result == datetime.date(2026, 12, 28)
        assert result.weekday() == 0

    def test_year_2027_w01(self):
        result = week_start("2027-W01")
        assert result == datetime.date(2027, 1, 4)
        assert result.weekday() == 0


class TestRoundTrip:
    @pytest.mark.parametrize("d", [
        datetime.date(2026, 1, 1),
        datetime.date(2026, 12, 31),
        datetime.date(2026, 6, 1),
        datetime.date(2026, 7, 10),
        datetime.date(2026, 8, 17),
        datetime.date(2027, 1, 1),
    ])
    def test_week_start_le_d(self, d):
        label = iso_week_label(d)
        ws = week_start(label)
        assert ws is not None
        assert ws <= d

    @pytest.mark.parametrize("d", [
        datetime.date(2026, 1, 1),
        datetime.date(2026, 12, 31),
        datetime.date(2026, 6, 1),
        datetime.date(2026, 7, 10),
        datetime.date(2026, 8, 17),
        datetime.date(2027, 1, 1),
    ])
    def test_round_trip_label(self, d):
        label = iso_week_label(d)
        ws = week_start(label)
        assert ws is not None
        assert iso_week_label(ws) == label

    @pytest.mark.parametrize("d", [
        datetime.date(2026, 1, 1),
        datetime.date(2026, 12, 31),
    ])
    def test_week_start_is_monday(self, d):
        ws = week_start(iso_week_label(d))
        assert ws is not None
        assert ws.weekday() == 0


class TestWeekSequence:
    def test_sample_w23_to_w34_length(self):
        seq = week_sequence("2026-W23", "2026-W34")
        assert len(seq) == 12

    def test_sample_w23_to_w34_first_last(self):
        seq = week_sequence("2026-W23", "2026-W34")
        assert seq[0] == "2026-W23"
        assert seq[-1] == "2026-W34"

    def test_year_crossing_sequence(self):
        seq = week_sequence("2026-W52", "2027-W02")
        assert seq == ["2026-W52", "2026-W53", "2027-W01", "2027-W02"]

    def test_year_crossing_length(self):
        seq = week_sequence("2026-W52", "2027-W02")
        assert len(seq) == 4

    def test_year_crossing_first_last(self):
        seq = week_sequence("2026-W52", "2027-W02")
        assert seq[0] == "2026-W52"
        assert seq[-1] == "2027-W02"

    def test_year_crossing_all_parseable(self):
        seq = week_sequence("2026-W52", "2027-W02")
        for label in seq:
            assert week_start(label) is not None, f"{label} should be parseable"

    def test_year_crossing_adjacent_diff_7days(self):
        seq = week_sequence("2026-W52", "2027-W02")
        for i in range(len(seq) - 1):
            ws_curr = week_start(seq[i])
            ws_next = week_start(seq[i + 1])
            assert ws_next is not None
            assert ws_curr is not None
            assert (ws_next - ws_curr).days == 7

    def test_single_week(self):
        seq = week_sequence("2026-W23", "2026-W23")
        assert seq == ["2026-W23"]

    def test_first_greater_than_last(self):
        assert week_sequence("2026-W34", "2026-W23") == []

    def test_invalid_first(self):
        assert week_sequence("bad", "2026-W30") == []

    def test_invalid_last(self):
        assert week_sequence("2026-W23", "bad") == []

    def test_both_invalid(self):
        assert week_sequence("bad", "worse") == []

    def test_returns_list(self):
        assert isinstance(week_sequence("2026-W23", "2026-W25"), list)

    def test_all_elements_are_strings(self):
        seq = week_sequence("2026-W23", "2026-W25")
        for label in seq:
            assert isinstance(label, str)

    def test_adjacent_diff_7days_within_year(self):
        seq = week_sequence("2026-W23", "2026-W26")
        for i in range(len(seq) - 1):
            ws_curr = week_start(seq[i])
            ws_next = week_start(seq[i + 1])
            assert ws_next is not None and ws_curr is not None
            assert (ws_next - ws_curr).days == 7

    def test_w53_is_included_in_crossing(self):
        seq = week_sequence("2026-W52", "2027-W02")
        assert "2026-W53" in seq

    def test_w54_does_not_exist(self):
        assert week_start("2026-W54") is None

"""pytest 共通設定 — サンプル資材へのパス定義＋e2eアンカー凍結（資材は複製しない）.

レイアウト（01_PoC と 02_Skill はプロジェクト直下で同階層）:
  <root>/01_PoC/議事録サンプル_人事給与SaaS導入_v1.xlsx     <- 議事録サンプル正本
  <root>/01_PoC/WBSサンプル_人事給与SaaS導入_v1.xlsx        <- WBSサンプル正本
  <root>/02_Skill/meeting-prep-skill/tests/conftest.py      <- このファイル

このファイルから 01_PoC までは parents[3]（= <root>）。**cwd には依存しない**。
parents[3] を第一候補に、見つからなければ上方向に `01_PoC` を探索。
環境変数 `MEETING_PREP_SAMPLES_DIR` があれば最優先で上書き（CI 等で別配置のとき用）。

パターン由来: D1 report-skill/tests/conftest.py。
実測定数は specs/meeting-prep.md §10（e2eアンカー・PM実測 2026-06-14・スポンサー独立再現一致）。
**テストは数値をハードコードせずこの fixture を使う**（確定リファレンス運用・関所１固定条件）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# src/ を import path に追加（src.model 等を読めるように）。
_SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SKILL_ROOT))


def _resolve_samples_dir() -> Path:
    """サンプル正本ディレクトリ 01_PoC を解決する（cwd 非依存）."""
    env = os.environ.get("MEETING_PREP_SAMPLES_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    primary = here.parents[3] / "01_PoC"   # <root>/01_PoC
    if primary.exists():
        return primary
    for parent in here.parents:            # フォールバック: 上方向探索
        candidate = parent / "01_PoC"
        if candidate.exists():
            return candidate
    return primary  # 見つからなくても primary を返す（fixture 側で skip 表示）


SAMPLES_DIR = _resolve_samples_dir()
MINUTES_SAMPLE = SAMPLES_DIR / "議事録サンプル_人事給与SaaS導入_v1.xlsx"
WBS_SAMPLE = SAMPLES_DIR / "WBSサンプル_人事給与SaaS導入_v1.xlsx"

# ─── e2eアンカー凍結値（specs §10・PM実測 2026-06-14・独立再現一致・一字一句この値で）───
SAMPLE_MEETING_COUNT = 6              # 議事録の会議数
SAMPLE_AS_OF = "2026-07-10"          # 既定 as_of = 議事録の最新会議日（D3規約・D1のmax方式と別）
SAMPLE_ASOF_WEEK = "2026-W28"        # as_of の ISO週
SAMPLE_HORIZON_DAYS = 14             # due_soon 窓の既定地平線
SAMPLE_CARRYOVER_OVERDUE = 5         # carryover_action のうち overdue
SAMPLE_CARRYOVER_DUE_SOON = 1        # carryover_action のうち due_soon
SAMPLE_CARRYOVER_PENDING = 0         # carryover_action のうち pending
SAMPLE_CARRYOVER_TOTAL = 6           # carryover_action 合計（宿題非空の全件）
SAMPLE_DECISION_FOLLOWUP = 5         # decision_followup（RK-/R- 参照を含む決定）
SAMPLE_WBS_TASK_COUNT = 81           # WBS 総タスク数
SAMPLE_UPCOMING_TASK = 13            # --wbs時 horizon窓内に開始or終了のタスク
SAMPLE_ITEM_COUNT_NO_WBS = 11        # item_count（WBS無）= carryover6 + decision5 + freshness0
SAMPLE_ITEM_COUNT_WITH_WBS = 24      # item_count（WBS有）= 11 + upcoming13


@pytest.fixture
def minutes_sample_path() -> Path:
    """議事録 基準サンプル（6会議）."""
    if not MINUTES_SAMPLE.exists():
        pytest.skip(f"議事録サンプル未配置: {MINUTES_SAMPLE}（MEETING_PREP_SAMPLES_DIR で上書き可）")
    return MINUTES_SAMPLE


@pytest.fixture
def wbs_sample_path() -> Path:
    """WBS 基準サンプル（任意連携・81タスク）."""
    if not WBS_SAMPLE.exists():
        pytest.skip(f"WBSサンプル未配置: {WBS_SAMPLE}（MEETING_PREP_SAMPLES_DIR で上書き可）")
    return WBS_SAMPLE


@pytest.fixture
def sample_meeting_count() -> int:
    return SAMPLE_MEETING_COUNT


@pytest.fixture
def sample_as_of() -> str:
    return SAMPLE_AS_OF


@pytest.fixture
def sample_asof_week() -> str:
    return SAMPLE_ASOF_WEEK


@pytest.fixture
def sample_horizon_days() -> int:
    return SAMPLE_HORIZON_DAYS


@pytest.fixture
def sample_carryover_overdue() -> int:
    return SAMPLE_CARRYOVER_OVERDUE


@pytest.fixture
def sample_carryover_due_soon() -> int:
    return SAMPLE_CARRYOVER_DUE_SOON


@pytest.fixture
def sample_carryover_pending() -> int:
    return SAMPLE_CARRYOVER_PENDING


@pytest.fixture
def sample_carryover_total() -> int:
    return SAMPLE_CARRYOVER_TOTAL


@pytest.fixture
def sample_action_count() -> int:
    """宿題（＝carryover_action）件数。test_minutes_reader 用（＝SAMPLE_CARRYOVER_TOTAL）。"""
    return SAMPLE_CARRYOVER_TOTAL


@pytest.fixture
def sample_decision_followup() -> int:
    return SAMPLE_DECISION_FOLLOWUP


@pytest.fixture
def sample_wbs_task_count() -> int:
    return SAMPLE_WBS_TASK_COUNT


@pytest.fixture
def sample_upcoming_task() -> int:
    return SAMPLE_UPCOMING_TASK


@pytest.fixture
def sample_item_count_no_wbs() -> int:
    return SAMPLE_ITEM_COUNT_NO_WBS


@pytest.fixture
def sample_item_count_with_wbs() -> int:
    return SAMPLE_ITEM_COUNT_WITH_WBS

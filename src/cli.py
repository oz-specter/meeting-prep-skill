"""単一エントリ — 会議事前準備スキル（spec §7）.

C3 escalation-skill/src/cli.py 同型構造（D1 report-skill 由来）。
now() はファイル名スタンプ専用。分析パスには使わない（決定論 §8）。

CLI（spec §7）:
  python src/cli.py --minutes <議事録.xlsx> [--wbs <WBS.xlsx>]
                    --out _output/ --format md|html|json|csv|envelope
                    [--project-name 名] [--as-of YYYY-MM-DD] [--horizon-days 14]
                    [--meeting-type 会議体] [--stale-days 30]
exit: 0=正常 / 2=必須列欠落 / その他=異常（全スキル共通）。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from src.minutes_reader import read_minutes
    from src.wbs_reader import read_wbs
    from src.model import MissingColumnReport
    from src.prep import build_prep
    from src import envelope as envmod
    from src.renderer import render
else:
    from .minutes_reader import read_minutes
    from .wbs_reader import read_wbs
    from .model import MissingColumnReport
    from .prep import build_prep
    from . import envelope as envmod
    from .renderer import render

_REPORT = "会議準備チェックリスト"
_EXT = {"md": ".md", "html": ".html", "json": ".json", "csv": ".csv", "envelope": ".envelope.json"}


def _read_or_missing(path: str, reader, sheet_label: str):
    """ファイル無し → MissingColumnReport（AC-14「ファイル無し」も欠落として扱う）."""
    if not Path(path).exists():
        return MissingColumnReport(
            sheet=sheet_label,
            missing_columns=[],
            suggestion=f"ファイルが見つかりません: {path}",
        )
    return reader(path)


def _write_history(out_dir, stamp, fmt, out_filename, project_name,
                   overdue_count, item_count, status):
    """history.jsonl に1行追記（OSError は握りつぶし）."""
    hist = out_dir / "history.jsonl"
    try:
        with hist.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "stamp": stamp,
                "format": fmt,
                "out": out_filename,
                "project_name": project_name,
                "overdue_count": overdue_count,
                "item_count": item_count,
                "status": status,
            }, ensure_ascii=False) + "\n")
    except OSError:
        pass


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="会議事前準備スキル")
    p.add_argument("--minutes", required=True)
    p.add_argument("--wbs", default=None)
    p.add_argument("--out", required=True)
    p.add_argument("--format", choices=["md", "html", "json", "csv", "envelope"],
                   default="md", dest="format")
    p.add_argument("--project-name", dest="project_name", default=None)
    p.add_argument("--as-of", dest="as_of", default=None)
    p.add_argument("--horizon-days", dest="horizon_days", type=int, default=None)
    p.add_argument("--meeting-type", dest="meeting_type", default=None)
    p.add_argument("--stale-days", dest="stale_days", type=int, default=None)
    args = p.parse_args(argv)

    resolved_name = args.project_name or Path(args.minutes).stem
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    minutes = _read_or_missing(args.minutes, read_minutes, "議事録")

    if isinstance(minutes, MissingColumnReport):
        if args.format == "envelope":
            env = envmod.from_missing_report(
                minutes,
                title=f"入力の確認：{minutes.sheet}",
                project_name=resolved_name,
            )
            out_path = out_dir / f"{_REPORT}_{stamp}.envelope.json"
            out_path.write_text(envmod.dumps(env), encoding="utf-8")
            _write_history(out_dir, stamp, args.format, out_path.name,
                           resolved_name, 0, 0, "degraded")
            print(f"縮退エンベロープを出力しました: {out_path}", file=sys.stderr)
            return 0
        print("【入力エラー：必須入力の欠落】", file=sys.stderr)
        print(f"  対象: {minutes.sheet}", file=sys.stderr)
        if minutes.missing_columns:
            print(f"  欠落列: {minutes.missing_columns}", file=sys.stderr)
        print(f"  手当て提案: {minutes.suggestion}", file=sys.stderr)
        return 2

    # WBS（任意）
    wbs_view = None
    if args.wbs:
        wbs_view = read_wbs(args.wbs)
        if wbs_view is None:
            print(
                f"【警告】WBS を読めませんでした（シート/列欠落の可能性）。WBS連携なしで続行します: {args.wbs}",
                file=sys.stderr,
            )

    try:
        prep_result = build_prep(
            minutes,
            wbs_view=wbs_view,
            as_of=args.as_of,
            horizon_days=args.horizon_days,
            stale_days=args.stale_days,
            meeting_type=args.meeting_type,
        )
    except ValueError as e:
        print(f"【入力エラー】{e}", file=sys.stderr)
        return 2

    fmt = args.format
    overdue_count = prep_result.summary["by_status"].get("overdue", 0)
    item_count = prep_result.summary["item_count"]

    if fmt == "envelope":
        env = envmod.build_envelope(
            prep_result,
            title=f"{_REPORT}（{resolved_name}）",
            project_name=resolved_name,
            project_type=None,
        )
        out_path = out_dir / f"{_REPORT}_{stamp}.envelope.json"
        out_path.write_text(envmod.dumps(env), encoding="utf-8")
        _write_history(out_dir, stamp, fmt, out_path.name,
                       resolved_name, overdue_count, item_count,
                       env.get("status", "ok"))
    else:
        text = render(prep_result, fmt, project_name=resolved_name)
        out_path = out_dir / f"{_REPORT}_{stamp}{_EXT[fmt]}"
        enc = "utf-8-sig" if fmt == "csv" else "utf-8"   # CSV の BOM は cli 責務（§7）
        out_path.write_text(text, encoding=enc)
        _write_history(out_dir, stamp, fmt, out_path.name,
                       resolved_name, overdue_count, item_count, "ok")

    print(f"{_REPORT}を出力しました: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

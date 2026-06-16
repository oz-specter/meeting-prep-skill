"""CI境界再現スクリプト — CLI実走でe2eアンカー＋契約境界を独立再現する（D3 meeting-prep-skill）.

ゲート自動化B案（concept/17）。pytestとは独立に、配布物の境界（src/cli.py）だけを叩いて検証する:

  1. e2eアンカー（§10・conftest 凍結値と同値・PM実測2026-06-14独立再現一致）
     既定 as_of（議事録最新会議日）で:
       meta: item_count(WBS有)=24 / overdue_count=5 / due_soon_count=14
             as_of=2026-07-10 / as_of_week=2026-W28
       by_kind: carryover_action=6 / decision_followup=5 / upcoming_task=13
       WBS無: item_count=11（S-1差分=upcoming13）
       enrich: carryover/decision 全11件に related_phases（工程突合）
       headline: "次回までに要対応 24件" を含む
  2. 封筒トップレベル10キー（A1互換）・ui_type=prep_checklist・skill_id=meeting-prep-skill
  3. CSV: UTF-8 BOM（cli責務）＋ヘッダー9列
  4. 決定論: 2回実行で generated_at を除き同一
  5. 入力非汚染: 実行前後でサンプルファイルの sha256 不変
  6. 境界（meeting_scope）: --meeting-type 指定で carryover/decision は部分集合・upcoming は全件（§15）

テンプレート由来: C3 escalation-skill/scripts/ci_boundary_check.py。
サンプル位置は環境変数 MEETING_PREP_SAMPLES_DIR（CI=repo同梱 samples/）。
未設定時は repo直下 samples/ を解決する。終了コード 0=全PASS / 1=FAIL。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# --- アンカー定数（tests/conftest.py §10 と同値・一字一句この値で） ---
ANCHOR = {
    "as_of": "2026-07-10",
    "as_of_week": "2026-W28",
    "item_count_with_wbs": 24,
    "item_count_no_wbs": 11,
    "overdue_count": 5,
    "due_soon_count_with_wbs": 14,
    "carryover": 6,
    "decision": 5,
    "upcoming": 13,
    "cd_with_phases": 11,            # carryover+decision 全件が工程突合済
    "headline_substr": "次回までに要対応 24件",
}

ENVELOPE_KEYS = {
    "schema_version", "skill_id", "ui_type", "ui_type_label", "title",
    "generated_at", "status", "notice", "meta", "payload",
}

CSV_HEADER = "プロジェクト,区分,状態,項目,担当,期日,関連タスク,関連工程,根拠セル参照"

_failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        _failures.append(name)


def resolve_samples() -> Path:
    env = os.environ.get("MEETING_PREP_SAMPLES_DIR")
    if env:
        return Path(env)
    local = REPO / "samples"
    if local.exists():
        return local
    sys.exit("サンプルディレクトリ未解決（MEETING_PREP_SAMPLES_DIR を設定してください）")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_cli(minutes: Path, out_dir: Path, fmt: str,
            wbs: "Path | None" = None, extra_args: "list[str] | None" = None) -> Path:
    cmd = [
        sys.executable, "-X", "utf8", str(REPO / "src" / "cli.py"),
        "--minutes", str(minutes),
        "--out", str(out_dir),
        "--format", fmt,
    ]
    if wbs is not None:
        cmd += ["--wbs", str(wbs)]
    if extra_args:
        cmd += extra_args
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr)
        sys.exit(f"CLI実行失敗 (--format {fmt}): exit={r.returncode}")
    ext = ".envelope.json" if fmt == "envelope" else f".{fmt}"
    files = sorted(p for p in out_dir.glob("*") if p.name.endswith(ext))
    if len(files) != 1:
        sys.exit(f"出力ファイル({ext})が1つでない: {[p.name for p in out_dir.glob('*')]}")
    return files[0]


def strip_generated_at(env: dict) -> dict:
    d = json.loads(json.dumps(env, ensure_ascii=False))
    d.pop("generated_at", None)
    return d


def main() -> int:
    samples = resolve_samples()
    minutes = samples / "議事録サンプル_人事給与SaaS導入_v1.xlsx"
    wbs = samples / "WBSサンプル_人事給与SaaS導入_v1.xlsx"
    for p in (minutes, wbs):
        if not p.exists():
            sys.exit(f"サンプル未配置: {p}")

    before = {p.name: sha256(p) for p in (minutes, wbs)}

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # --- envelope（WBS有）2回 + CSV + WBS無 + meeting-type ---
        env_path1 = run_cli(minutes, tmp / "run1", "envelope", wbs=wbs)
        env_path2 = run_cli(minutes, tmp / "run2", "envelope", wbs=wbs)
        csv_path = run_cli(minutes, tmp / "csv", "csv", wbs=wbs)
        env_nowbs = run_cli(minutes, tmp / "nowbs", "envelope")

        env1 = json.loads(env_path1.read_text(encoding="utf-8"))
        env2 = json.loads(env_path2.read_text(encoding="utf-8"))
        envn = json.loads(env_nowbs.read_text(encoding="utf-8"))

        # 2. 封筒契約
        check("封筒トップレベル10キー(A1互換)",
              set(env1.keys()) == ENVELOPE_KEYS, f"keys={sorted(env1.keys())}")
        check("ui_type=prep_checklist", env1.get("ui_type") == "prep_checklist",
              str(env1.get("ui_type")))
        check("skill_id=meeting-prep-skill", env1.get("skill_id") == "meeting-prep-skill",
              str(env1.get("skill_id")))

        # 1. e2eアンカー — meta
        meta = env1.get("meta", {})
        check("アンカー: meta.item_count(WBS有)=24",
              meta.get("item_count") == ANCHOR["item_count_with_wbs"], str(meta.get("item_count")))
        check("アンカー: meta.overdue_count=5",
              meta.get("overdue_count") == ANCHOR["overdue_count"], str(meta.get("overdue_count")))
        check("アンカー: meta.due_soon_count=14",
              meta.get("due_soon_count") == ANCHOR["due_soon_count_with_wbs"], str(meta.get("due_soon_count")))
        check("アンカー: meta.as_of=2026-07-10",
              meta.get("as_of") == ANCHOR["as_of"], str(meta.get("as_of")))
        check("アンカー: meta.as_of_week=2026-W28",
              meta.get("as_of_week") == ANCHOR["as_of_week"], str(meta.get("as_of_week")))

        # 1. e2eアンカー — by_kind
        payload = env1.get("payload", {})
        by_kind = payload.get("summary", {}).get("by_kind", {})
        check("アンカー: carryover_action=6",
              by_kind.get("carryover_action") == ANCHOR["carryover"], str(by_kind.get("carryover_action")))
        check("アンカー: decision_followup=5",
              by_kind.get("decision_followup") == ANCHOR["decision"], str(by_kind.get("decision_followup")))
        check("アンカー: upcoming_task=13",
              by_kind.get("upcoming_task") == ANCHOR["upcoming"], str(by_kind.get("upcoming_task")))

        # 1. e2eアンカー — WBS無 item_count（S-1差分）
        check("アンカー: item_count(WBS無)=11",
              envn.get("meta", {}).get("item_count") == ANCHOR["item_count_no_wbs"],
              str(envn.get("meta", {}).get("item_count")))

        # 1. enrich — carryover/decision 全件に related_phases
        cd = [i for i in payload.get("checklist", [])
              if i.get("kind") in ("carryover_action", "decision_followup")]
        cd_with = [i for i in cd if i.get("related_phases")]
        check("アンカー: carryover/decision 全件に related_phases",
              len(cd) == ANCHOR["cd_with_phases"] and len(cd_with) == ANCHOR["cd_with_phases"],
              f"cd={len(cd)} with_phases={len(cd_with)}")

        # 1. headline
        check("アンカー: headline に '次回までに要対応 24件'",
              ANCHOR["headline_substr"] in payload.get("headline", ""),
              repr(payload.get("headline", "")))

        # evidence: 全 checklist 項目に ref（'!' 含む）
        all_ev_ok = all(
            it.get("evidence") and all("!" in e.get("ref", "") for e in it["evidence"])
            for it in payload.get("checklist", [])
        )
        check("契約: 全項目 evidence に CellRef ref（'!'含む）", all_ev_ok)

        # 3. CSV: BOM + 9列ヘッダー
        raw = csv_path.read_bytes()
        check("CSV: UTF-8 BOM(cli責務)", raw[:3] == b"\xef\xbb\xbf")
        first_line = raw.decode("utf-8-sig").splitlines()[0]
        check("CSV: ヘッダー9列", first_line == CSV_HEADER, first_line)

        # 4. 決定論
        check("決定論: 2回実行で同一（generated_at除く）",
              strip_generated_at(env1) == strip_generated_at(env2))

        # 6. 境界（meeting_scope）: --meeting-type で carryover/decision 部分集合・upcoming 全件
        all_cd_titles = {(i["kind"], i["title"]) for i in cd}
        up_all = by_kind.get("upcoming_task", 0)
        env_scope_path = run_cli(
            minutes, tmp / "scope", "envelope", wbs=wbs,
            extra_args=["--meeting-type", "週次定例"],
        )
        env_scope = json.loads(env_scope_path.read_text(encoding="utf-8"))
        spl = env_scope.get("payload", {})
        scope_cd = {(i["kind"], i["title"]) for i in spl.get("checklist", [])
                    if i.get("kind") in ("carryover_action", "decision_followup")}
        scope_up = spl.get("summary", {}).get("by_kind", {}).get("upcoming_task", 0)
        check("境界: --meeting-type で carryover/decision 部分集合",
              scope_cd <= all_cd_titles and len(scope_cd) < len(all_cd_titles),
              f"scope={len(scope_cd)} all={len(all_cd_titles)}")
        check("境界: --meeting-type でも upcoming_task は全件",
              scope_up == up_all, f"scope={scope_up} all={up_all}")
        check("境界: meeting_scope フィールド反映",
              spl.get("meeting_scope") == "週次定例", str(spl.get("meeting_scope")))

    # 5. 入力非汚染
    after = {p.name: sha256(p) for p in (minutes, wbs)}
    check("入力非汚染: サンプルsha256不変", before == after)

    print()
    if _failures:
        print(f"NG: {len(_failures)}件失敗 -> {_failures}")
        return 1
    print("OK: 境界再現 全PASS（e2eアンカー・封筒10キー・CSV BOM/9列・決定論・非汚染・meeting_scope）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

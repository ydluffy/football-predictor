from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import sleep

from config.settings import get_settings
from research_director.director import Gate, ResearchDirector
from research_director.model_registry import get_current_production_model, load_registry
from research_director.scheduler import ResearchScheduler
from research_director.data_preflight import preflight_real_data


def _fmt_model_line(m) -> str:
    if not m:
        return "(none)"
    return " | ".join(
        [
            f"model_id={m.model_id}",
            f"model_type={m.model_type}",
            f"feature_version={m.feature_version}",
            f"calibration_method={m.calibration_method}",
            f"status={m.status}",
            f"artifact_path={m.artifact_path}",
        ]
    )


def _print_registry_summary(*, max_candidates: int = 5) -> None:
    prod = get_current_production_model()
    reg = load_registry()
    print("registry.production:")
    print(_fmt_model_line(prod))
    print("registry.candidates_recent:")
    recent = list(reg.candidate_models)[-int(max_candidates) :]
    if not recent:
        print("(none)")
        return
    for m in reversed(recent):
        print(_fmt_model_line(m))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scheduler", choices=["true", "false"], default="false")
    parser.add_argument("--scheduler-config", default="")
    parser.add_argument("--show-registry", choices=["true", "false"], default="false")
    parser.add_argument("--registry-limit", type=int, default=5)
    parser.add_argument("--workflow", choices=["daily_prediction", "post_match_learning", "candidate_model_upgrade", "candidate_upgrade"], default="")
    parser.add_argument("--model-type", choices=["logit", "lightgbm", "stacking", "stacking_oof"], default="logit")
    parser.add_argument("--feature-version", choices=["v1", "v2", "v3"], default="v3")
    parser.add_argument("--calibration", choices=["none", "sigmoid", "isotonic"], default="none")
    parser.add_argument("--use-verifier", choices=["true", "false"], default="false")
    parser.add_argument("--data-mode", choices=["mock", "real"], default="mock")
    parser.add_argument("--allow-high-risk", choices=["true", "false"], default="false")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--resume", choices=["true", "false"], default="false")
    parser.add_argument("--max-retries", type=int, default=0)
    parser.add_argument("--today-matches-path", default="")
    parser.add_argument("--matches-path", default="")
    parser.add_argument("--raw-matches-csv", default="")
    parser.add_argument("--mapping-path", default="")
    parser.add_argument("--mapping-spec-json", default="")
    args = parser.parse_args()

    if args.scheduler == "false" and not args.workflow and args.show_registry == "false":
        raise SystemExit("--scheduler false 时必须提供 --workflow")

    gate = Gate(allow_high_risk=args.allow_high_risk == "true")
    director = ResearchDirector(gate=gate)
    s = get_settings()

    if args.scheduler == "true":
        cfg = args.scheduler_config or str(s.research_scheduler_config_path)
        scheduler = ResearchScheduler.load_from_config(cfg)
        print("registered_jobs=" + json.dumps(scheduler.list_jobs(), ensure_ascii=False, indent=2))
        try:
            while True:
                _ = scheduler.run_pending(director=director)
                sleep(1)
        except KeyboardInterrupt:
            return

    if args.show_registry == "true" and not args.workflow:
        _print_registry_summary(max_candidates=int(args.registry_limit))
        return

    wf = args.workflow
    if wf == "candidate_upgrade":
        wf = "candidate_model_upgrade"

    ctx = {
        "model_type": args.model_type,
        "feature_version": args.feature_version,
        "calibration": args.calibration,
        "use_verifier": args.use_verifier == "true",
        "max_retries": int(args.max_retries),
        "data_mode": args.data_mode,
    }
    if args.today_matches_path:
        ctx["today_matches_path"] = args.today_matches_path
    if args.matches_path:
        ctx["matches_path"] = args.matches_path
    if args.raw_matches_csv:
        ctx["raw_matches_csv"] = args.raw_matches_csv
    if args.mapping_path:
        ctx["mapping_path"] = args.mapping_path
    if args.mapping_spec_json:
        ctx["mapping_spec"] = json.loads(Path(args.mapping_spec_json).read_text(encoding="utf-8"))

    if args.data_mode == "real":
        if "raw_matches_csv" not in ctx:
            default_raw = s.data_ingest_input_default_path
            if default_raw.exists():
                ctx["raw_matches_csv"] = str(default_raw)
        if "mapping_path" not in ctx:
            if args.feature_version == "v1":
                default_mapping = s.data_mappings_dir / "example_mapping_minimal.json"
            elif args.feature_version == "v2":
                default_mapping = s.data_mappings_dir / "example_mapping_v2.json"
            else:
                default_mapping = s.data_mappings_dir / "example_mapping_v3.json"
            if default_mapping.exists():
                ctx["mapping_path"] = str(default_mapping)

        raw_p = ctx.get("raw_matches_csv")
        map_p = ctx.get("mapping_path")
        print(f"raw_matches_csv={raw_p}")
        print(f"mapping_path={map_p}")
        if raw_p and map_p:
            pre = preflight_real_data(raw_matches_csv=str(raw_p), mapping_path=str(map_p), feature_version=str(ctx.get('feature_version') or 'v3'))
            print(f"preflight_status={pre.status}")
            print("preflight_reasons=" + json.dumps(pre.reasons, ensure_ascii=False))
        else:
            print("preflight_status=review_required")
            print("preflight_reasons=" + json.dumps(["raw_or_mapping_missing"], ensure_ascii=False))

    result = director.run(wf, context=ctx, run_id=args.run_id or None, resume=args.resume == "true")

    run_id = str(result.get("run_id") or "")
    run_dir = str(result.get("run_dir") or "")
    print(f"run_id={run_id}")
    print(f"run_dir={run_dir}")
    print(f"status={result.get('status')}")

    if result.get("decision") is not None:
        d = result.get("decision")
        print("decision=" + json.dumps(d, ensure_ascii=False))
        if isinstance(d, dict) and isinstance(d.get("gate_reasons"), list):
            print("gate_reasons=" + json.dumps(d.get("gate_reasons"), ensure_ascii=False))

    print("key_artifacts:")
    print(str(Path(run_dir) / "run_manifest.json"))
    print(str(s.research_execution_history_path))
    print(str(s.research_latest_execution_summary_path))
    print(str(s.artifacts_research_reports_dir))

    for a in result.get("artifacts") or []:
        if isinstance(a, dict) and a.get("path"):
            print(str(a.get("path")))

    if args.data_mode == "real":
        steps_m = None
        if isinstance(result.get("metrics"), dict):
            steps_m = result["metrics"].get("steps") if isinstance(result["metrics"].get("steps"), dict) else None
        data_m = steps_m.get("data") if isinstance(steps_m, dict) and isinstance(steps_m.get("data"), dict) else {}
        print("standardized_data_path=" + str(data_m.get("standardized_data_path") or ""))
        print("validation_path=" + str(data_m.get("validation_path") or ""))
        print("missing_report_path=" + str(data_m.get("missing_report_path") or ""))

    if args.show_registry == "true":
        _print_registry_summary(max_candidates=int(args.registry_limit))


if __name__ == "__main__":
    main()

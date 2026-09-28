from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping

from .client import (
    ProviderConfig,
    ProviderError,
    build_request_payload,
    call_provider,
    extract_normalized_response,
    usage_metrics,
)
from .contract import ContractError, build_analysis_context, load_json, validate_analysis


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURE = PROJECT_ROOT / "config/analysis/inputs/w0-construction-set.v1.json"
DEFAULT_SCHEMA = PROJECT_ROOT / "config/analysis/analysis-response.schema.v1.json"
DEFAULT_PROMPT = PROJECT_ROOT / "config/analysis/prompts/construction-analysis.v1.md"
RUNS_DIR = PROJECT_ROOT / "artifacts/w0-runs"
LIVE_FIXTURES_DIR = PROJECT_ROOT / "config/analysis/fixtures/live"


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _request_manifest(
    context: Mapping[str, Any], config: ProviderConfig, prompt: str, schema: Mapping[str, Any]
) -> Dict[str, Any]:
    return {
        "provider": config.provider,
        "endpoint": config.endpoint,
        "model": config.model,
        "api_style": config.api_style,
        "fixture_version": context["fixture_version"],
        "contract_version": context["contract_version"],
        "prompt_version": context["prompt_version"],
        "catalog_version": context["catalog_version"],
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "schema_sha256": hashlib.sha256(
            json.dumps(schema, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "image_processing": {
            "format": "jpeg",
            "max_edge": config.image_max_edge,
            "quality": config.image_jpeg_quality,
        },
        "images": [
            {
                "image_id": image["image_id"],
                "camera_id": image["camera_id"],
                "path": image["path"],
                "sha256": image["sha256"],
            }
            for image in context["images"]
        ],
    }


def _dry_run_summary(context: Mapping[str, Any], config: ProviderConfig) -> Dict[str, Any]:
    return {
        "status": "ready",
        "provider": config.provider,
        "endpoint": config.endpoint,
        "model": config.model,
        "api_style": config.api_style,
        "cameras": len(context["cameras"]),
        "images": len(context["images"]),
        "plan_items": len(context["plan_items"]),
        "image_bytes": sum(Path(item["absolute_path"]).stat().st_size for item in context["images"]),
        "image_processing": {
            "format": "jpeg",
            "max_edge": config.image_max_edge,
            "quality": config.image_jpeg_quality,
        },
        "has_api_key": bool(config.api_key),
    }


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run or validate the StroyKontrol W0 analysis contract")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs without calling the provider")
    parser.add_argument("--validate-response", type=Path, help="Validate a normalized response JSON and exit")
    parser.add_argument(
        "--promote-fixture",
        metavar="NAME",
        help="After a successful live run, copy the normalized response and metrics to fixtures/live/NAME.*.json",
    )
    return parser


def main(argv: Any = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        fixture = load_json(args.fixture)
        context = build_analysis_context(fixture, PROJECT_ROOT)
        schema = load_json(args.schema)
        prompt = args.prompt.read_text(encoding="utf-8")
        config = ProviderConfig.from_environment()

        if args.validate_response:
            validate_analysis(load_json(args.validate_response), context)
            print(json.dumps({"status": "valid", "response": str(args.validate_response)}, ensure_ascii=False))
            return 0

        if args.dry_run:
            print(json.dumps(_dry_run_summary(context, config), ensure_ascii=False, indent=2))
            return 0

        if not config.api_key:
            raise ProviderError("AI_API_KEY is empty; live W0 run was not attempted")

        payload = build_request_payload(config, context, schema, prompt)
        run_dir = RUNS_DIR / _timestamp()
        run_dir.mkdir(parents=True, exist_ok=False)
        _write_json(run_dir / "request-manifest.json", _request_manifest(context, config, prompt, schema))

        try:
            raw, headers, duration_ms = call_provider(config, payload)
            _write_json(run_dir / "raw-response.json", raw)
            normalized = extract_normalized_response(raw, config.api_style)
            validate_analysis(normalized, context)
            _write_json(run_dir / "normalized-response.json", normalized)
            request_id = headers.get("x-request-id") or str(raw.get("id", ""))
            metrics = usage_metrics(raw, config, duration_ms, request_id)
            _write_json(run_dir / "metrics.json", metrics)
        except (ContractError, ProviderError) as exc:
            _write_json(
                run_dir / "failure.json",
                {"status": "failed", "error_type": type(exc).__name__, "message": str(exc)},
            )
            raise

        if args.promote_fixture:
            LIVE_FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(
                run_dir / "normalized-response.json",
                LIVE_FIXTURES_DIR / f"{args.promote_fixture}.response.json",
            )
            shutil.copy2(run_dir / "metrics.json", LIVE_FIXTURES_DIR / f"{args.promote_fixture}.metrics.json")

        print(
            json.dumps(
                {"status": "completed", "run_dir": str(run_dir), "metrics": metrics},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except (ContractError, ProviderError, OSError, ValueError) as exc:
        print(f"W0 analysis failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

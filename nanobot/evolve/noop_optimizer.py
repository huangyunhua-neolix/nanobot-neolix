from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from nanobot.evolve.optimizer.schemas import OptimizerInput, OptimizerResult

_NO_IMPROVEMENT_MESSAGE = "No optimizer configured; deterministic no-op fallback used."


def build_result(payload: OptimizerInput) -> OptimizerResult:
    return OptimizerResult(
        optimizer_name="nanobot-noop-optimizer",
        optimizer_version="1",
        seed=payload.seed,
        candidates=[],
        tool_metadata_candidates=[],
        prompt_template_candidates=[],
        error={"code": "no_improvement", "message": _NO_IMPROVEMENT_MESSAGE},
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic no-op optimizer for nanobot evolve.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    try:
        payload = OptimizerInput.model_validate_json(Path(args.input).read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        print(f"noop optimizer: invalid input: {exc}", file=sys.stderr)
        return 2

    result = build_result(payload)
    Path(args.output).write_text(result.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

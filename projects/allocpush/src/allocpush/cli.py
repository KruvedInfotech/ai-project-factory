"""Command line for AllocPush."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .model import Wave
from .policies import GRADE_WEIGHT, GRADES, POLICIES, policies_payload
from .push import plan
from .report import text_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="allocpush",
        description="Push DC inventory to stores by need, grade, and case pack.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    push_cmd = sub.add_parser("push", help="Allocate a wave JSON file")
    push_cmd.add_argument("path", type=Path)
    push_cmd.add_argument("--json", action="store_true", help="Print machine-readable result")

    sub.add_parser("policies", help="List allocation policies and store-grade weights")

    serve = sub.add_parser("serve", help="Open the local allocation desk")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8795)

    args = parser.parse_args(argv)

    if args.command == "policies":
        _print_policies()
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    try:
        payload = json.loads(args.path.read_text(encoding="utf-8"))
        result = plan(Wave.from_dict(payload))
    except (OSError, ValueError, KeyError, json.JSONDecodeError, TypeError) as exc:
        sys.stderr.write(f"allocpush: {exc}\n")
        return 1
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.all_filled else 2


def _print_policies() -> None:
    body = policies_payload()
    print("Policies")
    for key, name in POLICIES.items():
        mark = " (default)" if key == body["default_policy"] else ""
        print(f"  {key:<12} {name}{mark}")
    print("Store grades (fair-share weights)")
    for grade in GRADES:
        print(f"  {grade}  ×{GRADE_WEIGHT[grade]}")
    print(body["rule"])

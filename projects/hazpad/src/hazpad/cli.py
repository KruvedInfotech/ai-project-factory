"""Command line for HazPad."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .matrix import CLASS_NAMES, CLASSES, CODE_NAMES, classes_payload, lookup
from .model import Shipment
from .place import plan
from .report import text_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="hazpad",
        description="Segregate hazmat lots on a warehouse pad or trailer.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="Assign lots from a shipment JSON file")
    check.add_argument("path", type=Path)
    check.add_argument("--json", action="store_true", help="Print machine-readable result")

    sub.add_parser("classes", help="List hazard classes and the mixing grid")

    serve = sub.add_parser("serve", help="Open the local segregation desk")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8796)

    args = parser.parse_args(argv)

    if args.command == "classes":
        _print_classes()
        return 0

    if args.command == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    try:
        payload = json.loads(args.path.read_text(encoding="utf-8"))
        result = plan(Shipment.from_dict(payload))
    except (OSError, ValueError, KeyError, json.JSONDecodeError, TypeError) as exc:
        sys.stderr.write(f"hazpad: {exc}\n")
        return 1
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text_report(result))
    return 0 if result.all_fit else 2


def _print_classes() -> None:
    body = classes_payload()
    print("Hazard classes")
    for key in CLASSES:
        print(f"  {key:<5} {CLASS_NAMES[key]}")
    print("Codes")
    for key, name in CODE_NAMES.items():
        print(f"  {key}  {name}")
    print("Mixing grid")
    header = "     " + " ".join(f"{key:>4}" for key in CLASSES)
    print(header)
    for row in CLASSES:
        cells = " ".join(f"{lookup(row, col):>4}" for col in CLASSES)
        print(f"  {row:<3} {cells}")
    print(body["rule"])

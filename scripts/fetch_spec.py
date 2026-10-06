"""Generate src/kestra_mcp/openapi/kestra.generated.json from Kestra's own OpenAPI spec.

Downloads the OpenAPI 3 spec Kestra publishes in its client-sdk repo
(https://github.com/kestra-io/client-sdk). It covers both editions: operations only available in
Enterprise carry `x-kestra: {edition: ee}`, which the server uses to filter them out for OSS.
The spec is kept as-is apart from the YAML -> JSON conversion.

Reports which operations were added, removed, or moved against the currently shipped spec.
Exit code is 1 with --check when upstream has changed.

Usage:
    uv run python scripts/fetch_spec.py                 # regenerate the shipped spec
    uv run python scripts/fetch_spec.py --check         # only report; don't write anything
    uv run python scripts/fetch_spec.py --url URL       # use another spec, e.g. your own instance
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

import yaml

SOURCE_URL = "https://raw.githubusercontent.com/kestra-io/client-sdk/main/kestra-ee.yml"
OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent / "src" / "kestra_mcp" / "openapi" / "kestra.generated.json"
)


def operations(spec: dict) -> dict[str, tuple[str, str]]:
    """operationId -> (METHOD, path)"""
    return {
        op["operationId"]: (method.upper(), path)
        for path, methods in spec.get("paths", {}).items()
        for method, op in methods.items()
        if isinstance(op, dict) and "operationId" in op
    }


def report_changes(old: dict, new: dict) -> bool:
    """Print what changed between the shipped and the upstream spec; return whether anything did."""
    old_ops, new_ops = operations(old), operations(new)
    if not old_ops:
        print(f"  No shipped spec yet; {len(new_ops)} operations upstream.", file=sys.stderr)
        return True
    added = sorted(new_ops.keys() - old_ops.keys())
    removed = sorted(old_ops.keys() - new_ops.keys())
    moved = sorted(k for k in old_ops.keys() & new_ops.keys() if old_ops[k] != new_ops[k])

    for label, names, ops in (("Added", added, new_ops), ("Removed", removed, old_ops)):
        for name in names:
            print(f"  {label}: {name} ({' '.join(ops[name])})", file=sys.stderr)
    for name in moved:
        print(f"  Moved: {name} ({' '.join(old_ops[name])} -> {' '.join(new_ops[name])})", file=sys.stderr)

    if added or removed or moved:
        return True
    if old != new:
        print("  Same operations; schemas or descriptions changed.", file=sys.stderr)
        return True
    print("  No changes against the shipped spec.", file=sys.stderr)
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="only report changes, write nothing")
    parser.add_argument("--url", default=SOURCE_URL, help=f"spec to download (default: {SOURCE_URL})")
    args = parser.parse_args()

    print(f"Downloading {args.url} ...", file=sys.stderr)
    with urllib.request.urlopen(args.url) as resp:  # noqa: S310 - user-chosen spec URL
        spec = yaml.safe_load(resp.read())

    print("\nChanges against the shipped spec:", file=sys.stderr)
    old_spec = json.loads(OUTPUT_PATH.read_text()) if OUTPUT_PATH.exists() else {}
    changed = report_changes(old_spec, spec)

    if args.check:
        sys.exit(1 if changed else 0)
    if changed:
        OUTPUT_PATH.write_text(json.dumps(spec, indent=1))
        print(f"\nWrote {OUTPUT_PATH} - {len(operations(spec))} operations.", file=sys.stderr)


if __name__ == "__main__":
    main()

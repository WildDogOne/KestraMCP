"""Dev helper: build the server and print the tools it exposes, without calling Kestra.

Respects KESTRA_EDITION / KESTRA_TOOLSETS / KESTRA_READ_ONLY, so it also shows what a given filter
leaves enabled.

Usage:
    KESTRA_URL=http://localhost:8080 uv run python scripts/list_tools.py
"""

import asyncio
import collections

from kestra_mcp.server import build_server


async def main() -> None:
    tools = await build_server().list_tools()
    counts = collections.Counter()
    for tool in tools:
        print(f"{tool.name} [{', '.join(sorted(tool.tags))}]")
        counts.update(t for t in tool.tags if t not in ("read", "write"))
    print(f"\nTotal tools: {len(tools)}")
    for toolset, n in sorted(counts.items()):
        print(f"  {toolset}: {n}")


if __name__ == "__main__":
    asyncio.run(main())

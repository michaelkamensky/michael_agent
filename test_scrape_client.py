#!/usr/bin/env python3
import argparse
import asyncio
import json

from fastmcp import Client


async def main() -> int:
    parser = argparse.ArgumentParser(description="Test MCP scrape_url_text tool.")
    parser.add_argument("url", help="URL to scrape (http/https).")
    parser.add_argument(
        "--endpoint",
        default="http://localhost:8000/mcp",
        help="MCP server endpoint (default: http://localhost:8000/mcp)",
    )
    args = parser.parse_args()

    async with Client(args.endpoint) as mcp_client:
        result = await mcp_client.call_tool("scrape_url_text", {"url": args.url})
        payload = result.data if hasattr(result, "data") else result
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

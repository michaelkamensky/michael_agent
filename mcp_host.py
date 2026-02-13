#!/usr/bin/python
import asyncio
from pathlib import Path
import subprocess
import sys

from fastmcp import Client

async def main():
    source_path = input("Source filename (e.g. He He.txt): ").strip()
    find_text = input("Find text: ").strip()
    replace_text = input("Replace text: ").strip()
    output_pdf_path = input("Output PDF filename (e.g. He He.pdf): ").strip() or "He He.pdf"
    reference_pdf = (
        input("Reference PDF filename (default: Michael Engineering Resume.pdf): ")
        .strip()
        .strip("'\"")
        or "Michael Engineering Resume.pdf"
    )

    # 1. Connect to the remote MCP Server
    async with Client("http://localhost:8000/mcp") as mcp_client:
        output_source_path = f"{Path(source_path).stem}_modified.txt"

        # 2. Read source text
        read_result = await mcp_client.call_tool("read_text_source", {"path": source_path})
        source_text = read_result.data if hasattr(read_result, "data") else read_result

        # 3. Replace text
        updated_text = source_text.replace(find_text, replace_text)

        # 4. Write updated source
        write_result = await mcp_client.call_tool(
            "write_text_source",
            {"path": output_source_path, "text": updated_text},
        )
        print(f"Server result: {write_result}")

        # 5. Render PDF using reference layout
        script_path = Path("/home/mike/projects/michael_agent/format_from_reference.py")
        result = subprocess.run(
            [sys.executable, str(script_path)],
            input=f"{output_source_path}\n{output_pdf_path}\n{reference_pdf}\n",
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        if result.stdout.strip():
            print(result.stdout.strip())

        # 6. Delete modified source after rendering
        output_text_path = Path("/home/mike/projects/michael_agent/sources") / output_source_path
        try:
            output_text_path.unlink()
            print(f"Deleted temporary source: {output_text_path}")
        except FileNotFoundError:
            print(f"Temporary source not found: {output_text_path}")

if __name__ == "__main__":
    asyncio.run(main())

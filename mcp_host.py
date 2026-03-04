#!/usr/bin/python
import asyncio
from pathlib import Path
import subprocess
import sys

import ollama
from fastmcp import Client

async def main():
    source_path = input("Source filename (e.g. He He.txt): ").strip()
    target_url = input("Target URL to analyze: ").strip()
    output_pdf_path = input("Output PDF filename (e.g. He He.pdf): ").strip() or "He He.pdf"
    reference_pdf = (
        input("Reference PDF filename (default: Michael Engineering Resume.pdf): ")
        .strip()
        .strip("'\"")
        or "Michael Engineering Resume.pdf"
    )

    # Normalize source path to the sources folder when given a bare filename.
    source_path_obj = Path(source_path)
    if not source_path_obj.is_absolute():
        parts = source_path_obj.parts
        if parts[:1] != ("sources",) and parts[:2] != (".", "sources"):
            source_path = str(Path("") / source_path_obj)

    # 1. Connect to the remote MCP Server
    async with Client("http://localhost:8000/mcp") as mcp_client:
        output_source_path = f"{Path(source_path).stem}_modified.txt"

        # 2. Get available tools from the server
        tools = await mcp_client.list_tools()
        allowed_tool_names = {t.name for t in tools}
        ollama_tools = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.inputSchema,
                },
            }
            for t in tools
        ]

        # 3. Ask the LLM to perform the substitution using MCP tools
        user_prompt = (
            "You are an assistant that must use MCP tools to complete the task.\n"
            "Goal: Update the resume text to better match the vocabulary, keywords, and requirements "
            "from the job description at the target URL.\n\n"
            "Steps:\n"
            "1) Use `fetch_html` or `fetch_dom_text` to gather the job description text from the URL.\n"
            "2) Use `read_text_source` to read the resume text from the input file.\n"
            "3) Use `read_text_source` to read the experience file at './experience/experience.txt' "
            "and use it as the source of truth for relevant experience details.\n"
            "4) Update the resume to incorporate relevant keywords and phrases from the job description, "
            "without fabricating experience. Keep tone professional and concise.\n"
            "5) Write the updated resume to the output file using `write_text_source`.\n\n"
            f"Target URL: {target_url}\n"
            f"Input file: {source_path}\n"
            "Experience file: ./experience/experience.txt\n"
            f"Output file: {output_source_path}\n\n"
            "When you have completed the task, reply with the single word 'done'."
        )
        messages = [{"role": "user", "content": user_prompt}]

        response = ollama.chat(
            model="gpt-oss:120b",
            messages=messages,
            tools=ollama_tools,
        )

        # 4. Handle tool calls (loop to allow multiple tool steps)
        while True:
            message = response.get("message", {})
            content = (message.get("content") or "").strip().lower()
            if "done" in content:
                break

            if not message.get("tool_calls"):
                messages.append(
                    {"role": "user", "content": "If the task is complete, reply with 'done'."}
                )
                response = ollama.chat(
                    model="gpt-oss:120b",
                    messages=messages,
                    tools=ollama_tools,
                )
                continue

            for call in response["message"]["tool_calls"]:
                tool_name = call["function"]["name"]
                arguments = call["function"]["arguments"]
                if tool_name not in allowed_tool_names:
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"Tool '{tool_name}' is not available. "
                                f"Choose one of: {', '.join(sorted(allowed_tool_names))}."
                            ),
                        }
                    )
                    response = ollama.chat(
                        model="gpt-oss:120b",
                        messages=messages,
                        tools=ollama_tools,
                    )
                    break

                print(f"Agent is calling remote tool: {tool_name} with {arguments}")
                result = await mcp_client.call_tool(tool_name, arguments)
                tool_output = result.data if hasattr(result, "data") else result
                messages.append({"role": "tool", "name": tool_name, "content": str(tool_output)})
            else:
                response = ollama.chat(
                    model="gpt-oss:120b",
                    messages=messages,
                    tools=ollama_tools,
                )
                continue

            continue

        # 5. Debug: keep the modified text source and skip PDF rendering
        print(f"Debug output written to sources/{output_source_path}")

        # 6. Leave the modified source in place for debugging
        output_text_path = Path("/home/mike/projects/michael_agent/sources") / output_source_path
        if output_text_path.exists():
            print(f"Debug file retained: {output_text_path}")
        else:
            print(f"Debug file not found: {output_text_path}")

if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/python
import asyncio
from pathlib import Path
import re
import subprocess
import sys

import ollama
from fastmcp import Client

async def main():
    source_path = input("Source filename (e.g. He He.tex or He He.txt): ").strip() or "resume.tex"
    target_url = input("Target URL to analyze: ").strip()
    company_name = input("Company name (for output folder and filenames): ").strip()

    # Normalize source path to the sources folder when given a bare filename.
    source_path_obj = Path(source_path)
    if not source_path_obj.is_absolute():
        parts = source_path_obj.parts
        if parts[:1] != ("sources",) and parts[:2] != (".", "sources"):
            source_path = str(Path("") / source_path_obj)

    # 1. Connect to the remote MCP Server
    async with Client("http://localhost:8000/mcp") as mcp_client:
        output_source_path = f"{Path(source_path).stem}_modified.tex"
        output_cover_letter_path = f"{Path(source_path).stem}_cover_letter.tex"

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
            "Goal: Update the resume text and create a tailored cover letter to better match the vocabulary, "
            "keywords, and requirements from the job description at the target URL.\n\n"
            "Steps:\n"
            "1) Use `fetch_html` or `fetch_dom_text` to gather the job description text from the URL.\n"
            "2) Use `read_text_source` to read the resume LaTeX from the input file.\n"
            "3) Use `read_text_source` to read the experience file at './experience/experience.txt' "
            "and use it as the source of truth for relevant experience details.\n"
            "4) Update the resume to incorporate relevant keywords and phrases from the job description, "
            "without fabricating experience. Keep tone professional and concise.\n"
            "5) Write the updated resume to the output resume file using `write_text_source`.\n"
            "6) Write a tailored cover letter (LaTeX) to the output cover letter file using `write_text_source` the letter should be three paragraphs long explaining in detail why I am a good fit for this position and for the company.\n"
            "You must call `write_text_source` exactly once for each output file (resume, cover letter) before replying 'done'.\n\n"
            f"Target URL: {target_url}\n"
            f"Input file: {source_path}\n"
            "Experience file: ./experience/experience.txt\n"
            f"Output resume file: {output_source_path}\n"
            f"Output cover letter file: {output_cover_letter_path}\n\n"
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

        # 5. Build output paths from the user-provided company name
        company_name_value = company_name.strip()

        def _sanitize_filename(name: str) -> str:
            cleaned = re.sub(r"[^\w\s.-]", "", name.strip())
            cleaned = re.sub(r"\s+", "_", cleaned).strip("_")
            return cleaned or "company"

        company_slug = _sanitize_filename(company_name_value)

        # Create / reuse a company-named directory under pdfs.
        pdfs_dir = Path("/home/mike/projects/michael_agent/pdfs")
        create_dir_result = await mcp_client.call_tool(
            "create_company_pdf_dir",
            {"company_name": company_name_value or company_slug},
        )
        create_dir_output = create_dir_result.data if hasattr(create_dir_result, "data") else create_dir_result
        print(create_dir_output)
        pdfs_dir = pdfs_dir / (company_name_value or company_slug)

        output_pdf_path = f"{company_slug}_michaelk_resume.pdf"
        cover_letter_pdf_path = f"{company_slug}_michaelk_CV.pdf"

        # 6. Ensure output LaTeX exists, then render to PDF
        print(f"Modified LaTeX written to sources/{output_source_path}")

        output_tex_path = Path("/home/mike/projects/michael_agent/sources") / output_source_path
        if not output_tex_path.exists():
            # Fallback: if the model didn't write output, copy the input as a baseline.
            input_tex_path = Path("/home/mike/projects/michael_agent/sources") / Path(source_path).name
            if input_tex_path.exists():
                output_tex_path.write_text(input_tex_path.read_text(encoding="utf-8"), encoding="utf-8")
                print(f"Fallback: copied input LaTeX to {output_tex_path}")

        if output_tex_path.exists():
            # Copy LaTeX alongside the PDF output for convenience.
            latex_copy_name = Path(output_pdf_path).with_suffix(".tex").name
            latex_copy_path = pdfs_dir / latex_copy_name
            pdfs_dir.mkdir(parents=True, exist_ok=True)
            latex_copy_path.write_text(output_tex_path.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"Copied LaTeX to {latex_copy_path}")

            render_result = await mcp_client.call_tool(
                "render_pdf_from_latex",
                {"path": str(output_tex_path), "output_path": str(pdfs_dir / output_pdf_path)},
            )
            render_output = render_result.data if hasattr(render_result, "data") else render_result
            print(render_output)
        else:
            print(f"LaTeX output not found: {output_tex_path}")

        # 6. Ensure cover letter LaTeX exists, then render to PDF
        print(f"Cover letter LaTeX written to sources/{output_cover_letter_path}")

        cover_tex_path = Path("/home/mike/projects/michael_agent/sources") / output_cover_letter_path
        if not cover_tex_path.exists():
            # Fallback: create a minimal cover letter template if the model didn't write output.
            minimal_cover = (
                "\\documentclass[11pt]{letter}\n"
                "\\usepackage[margin=1in]{geometry}\n"
                "\\begin{document}\n"
                "\\begin{letter}{Hiring Manager}\n"
                "\\opening{Dear Hiring Manager,}\n"
                "I am excited to apply for this role. Please find my resume attached.\n"
                "\\closing{Sincerely,}\n"
                "\\end{letter}\n"
                "\\end{document}\n"
            )
            cover_tex_path.write_text(minimal_cover, encoding="utf-8")
            print(f"Fallback: wrote minimal cover letter to {cover_tex_path}")

        if cover_tex_path.exists():
            # Copy cover letter LaTeX alongside the PDF output for convenience.
            cover_latex_copy_name = Path(cover_letter_pdf_path).with_suffix(".tex").name
            cover_latex_copy_path = pdfs_dir / cover_latex_copy_name
            pdfs_dir.mkdir(parents=True, exist_ok=True)
            cover_latex_copy_path.write_text(cover_tex_path.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"Copied cover letter LaTeX to {cover_latex_copy_path}")

            render_cover_result = await mcp_client.call_tool(
                "render_pdf_from_latex",
                {"path": str(cover_tex_path), "output_path": str(pdfs_dir / cover_letter_pdf_path)},
            )
            render_cover_output = (
                render_cover_result.data if hasattr(render_cover_result, "data") else render_cover_result
            )
            print(render_cover_output)
        else:
            print(f"Cover letter LaTeX output not found: {cover_tex_path}")

        # 7. Leave the modified source in place for debugging
        output_text_path = Path("/home/mike/projects/michael_agent/sources") / output_source_path
        if output_text_path.exists():
            print(f"Debug file retained: {output_text_path}")
        else:
            print(f"Debug file not found: {output_text_path}")

if __name__ == "__main__":
    asyncio.run(main())

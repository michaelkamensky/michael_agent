#!/usr/bin/python
import asyncio
import ollama
from fastmcp import Client

async def main():
    # 1. Connect to the remote MCP Server
    async with Client("http://localhost:8000/mcp") as mcp_client:
        
        # 2. Get available tools from the server
        tools = await mcp_client.list_tools()
        
        # Convert MCP tools to Ollama-compatible tool format
        ollama_tools = [
            {
                'type': 'function',
                'function': {
                    'name': t.name,
                    'description': t.description,
                    'parameters': t.inputSchema,
                },
            } for t in tools
        ]

        for t in tools:
            print(f"name = {t.name}, description = {t.description}")
            print(f"parameters = {t.inputSchema}")

        # 3. Ask Ollama a question that requires the tool
        user_prompt = "What is 15784 multiplied by 739?"
        response = ollama.chat(
            model='gpt-oss:120b', # Ensure this model supports tool calling
            messages=[{'role': 'user', 'content': user_prompt}],
            tools=ollama_tools,
        )

        # 4. Handle the Tool Call (if Ollama decides to use one)
        if response.get('message', {}).get('tool_calls'):
            for call in response['message']['tool_calls']:
                tool_name = call['function']['name']
                arguments = call['function']['arguments']
                
                print(f"Agent is calling remote tool: {tool_name} with {arguments}")
                
                # Execute the tool on the remote MCP Server
                result = await mcp_client.call_tool(tool_name, arguments)
                print(f"Server result: {result}")

if __name__ == "__main__":
    asyncio.run(main())

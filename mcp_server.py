#!/usr/bin/python

from fastmcp import FastMCP

mcp = FastMCP("MathServer")

@mcp.tool()
def multiply_numbers(a: int, b: int) -> int:
    """Multiplies two numbers together."""
    return a * b

if __name__ == "__main__":
    # Start the server on a specific port using HTTP transport
    mcp.run(transport="http", host="0.0.0.0", port=8000)

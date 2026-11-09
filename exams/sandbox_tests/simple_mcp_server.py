#!/usr/bin/env python3
# ABOUTME: Simple MCP test server providing add, multiply, echo tools for sandbox integration tests.
# ABOUTME: Supports both stdio and HTTP (streamable-http) transports via FastMCP.
"""Simple MCP server for testing sandbox integration.

Supports both HTTP and stdio modes using FastMCP for proper protocol compliance.

HTTP mode (streamable HTTP transport):
    python simple_mcp_server.py --http --port 8080

Stdio mode (Content-Length framing):
    python simple_mcp_server.py --stdio
"""
import argparse
import sys

from mcp.server.fastmcp import FastMCP


def build_server(host: str = "localhost", port: int = 8080) -> FastMCP:
    """Create the MCP server with tools registered."""
    mcp = FastMCP("test-mcp-server", host=host, port=port)

    @mcp.tool()
    def add(a: int, b: int) -> str:
        """Add two numbers."""
        return str(a + b)

    @mcp.tool()
    def multiply(a: int, b: int) -> str:
        """Multiply two numbers."""
        return str(a * b)

    @mcp.tool()
    def echo(message: str) -> str:
        """Echo a message back."""
        return f"Echo: {message}"

    return mcp


def main():
    parser = argparse.ArgumentParser(description="Simple MCP server for testing")
    parser.add_argument("--http", action="store_true", help="Run HTTP/SSE server")
    parser.add_argument("--stdio", action="store_true", help="Run stdio server")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port (default: 8080)")

    args = parser.parse_args()

    if args.http:
        mcp = build_server(host="localhost", port=args.port)
        mcp.run(transport="streamable-http")
    elif args.stdio:
        mcp = build_server()
        mcp.run(transport="stdio")
    else:
        print("Specify --http or --stdio")
        sys.exit(1)


if __name__ == "__main__":
    main()

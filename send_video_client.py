"""
Video MCP Client
================
Sends a video file to a VideoReceiverMCP server.

Supports both transports:
  stdio (local)   - connects to a local server process via stdin/stdout
  http  (network) - connects to a remote server via HTTP (Streamable-HTTP MCP)

Usage:
  # Local (stdio)
  python send_video_client.py myvideo.mp4

  # Remote server
  python send_video_client.py myvideo.mp4 --url http://localhost:8000/mcp
  python send_video_client.py myvideo.mp4 --url https://your-server.onrender.com/mcp
"""

import asyncio
import base64
import sys
import os
import argparse
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# ── helpers ──────────────────────────────────────────────────────────────────

def encode_video(path: str) -> tuple[str, str, int]:
    """Return (base64_string, filename, byte_count)."""
    with open(path, "rb") as f:
        raw = f.read()
    return base64.b64encode(raw).decode("utf-8"), os.path.basename(path), len(raw)


async def call_tools(session: ClientSession, video_path: str):
    """Initialize session, send video, list videos."""
    await session.initialize()

    tools = await session.list_tools()
    print(f"[client] Available tools: {[t.name for t in tools.tools]}")

    b64, filename, nbytes = encode_video(video_path)
    print(f"[client] Sending '{filename}'  ({nbytes / 1024:.2f} KB -> {len(b64)} B base64)")

    result = await session.call_tool(
        "receive_video",
        arguments={
            "video_base64": b64,
            "filename": filename,
            "description": f"Sent from {video_path}",
        },
    )
    print("\n--- Server response (receive_video) ---")
    for c in result.content:
        print(c.text)

    list_result = await session.call_tool("list_received_videos", arguments={})
    print("\n--- Server response (list_received_videos) ---")
    for c in list_result.content:
        print(c.text)


# ── transports ───────────────────────────────────────────────────────────────

async def send_via_stdio(video_path: str):
    """Connect to a local server via stdio."""
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[os.path.join(os.path.dirname(__file__), "video_mcp_server.py")],
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await call_tools(session, video_path)


async def send_via_http(video_path: str, url: str):
    """Connect to a remote server via Streamable HTTP."""
    try:
        from mcp.client.streamable_http import streamablehttp_client
    except ImportError:
        print("ERROR: mcp streamable_http client not available. Update mcp package.")
        sys.exit(1)

    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await call_tools(session, video_path)


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Send a video to a VideoReceiverMCP server")
    parser.add_argument("video", help="Path to the video file to send")
    parser.add_argument(
        "--url",
        default=None,
        help="MCP server URL for HTTP transport, e.g. http://localhost:8000/mcp",
    )
    args = parser.parse_args()

    if not os.path.exists(args.video):
        print(f"ERROR: File not found: {args.video}")
        sys.exit(1)

    if args.url:
        print(f"[client] Transport: HTTP -> {args.url}")
        asyncio.run(send_via_http(args.video, args.url))
    else:
        print("[client] Transport: stdio (local)")
        asyncio.run(send_via_stdio(args.video))


if __name__ == "__main__":
    main()

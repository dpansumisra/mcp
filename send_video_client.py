"""
Video MCP Client
================
Sends a video file to a VideoReceiverMCP server, or calls any specific tool.

Supports both transports:
  stdio (local)   - connects to a local server process via stdin/stdout
  http  (network) - connects to a remote server via HTTP (Streamable-HTTP MCP)

Usage:
  # Upload a video (default)
  python send_video_client.py test_video.mp4 --url https://your-server.onrender.com/mcp

  # List all videos
  python send_video_client.py --url https://your-server.onrender.com/mcp --tool list

  # Delete a specific video
  python send_video_client.py --url https://your-server.onrender.com/mcp --tool delete --filename clip.mp4

  # List available tools
  python send_video_client.py --url https://your-server.onrender.com/mcp --tool tools
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


def print_result(tool_name: str, result):
    print(f"\n--- Server response ({tool_name}) ---")
    for c in result.content:
        print(c.text)


async def run_tool(session: ClientSession, args):
    """Dispatch to the correct tool based on --tool argument."""
    await session.initialize()

    tool = args.tool

    # ── tools: list available MCP tools ──────────────────────────────────────
    if tool == "tools":
        tools = await session.list_tools()
        print("[client] Available tools:")
        for t in tools.tools:
            print(f"  • {t.name} — {t.description or '(no description)'}")

    # ── list: list all stored videos ─────────────────────────────────────────
    elif tool == "list":
        result = await session.call_tool("list_received_videos", arguments={})
        print_result("list_received_videos", result)

    # ── delete: delete a specific video ──────────────────────────────────────
    elif tool == "delete":
        if not args.filename:
            print("ERROR: --filename is required for --tool delete")
            print("  Example: --tool delete --filename clip.mp4")
            sys.exit(1)
        result = await session.call_tool(
            "delete_video",
            arguments={"filename": args.filename},
        )
        print_result("delete_video", result)

    # ── download: fetch a video from the server and save locally ──────────────
    elif tool == "download":
        import json
        if not args.filename:
            print("ERROR: --filename is required for --tool download")
            print("  Example: --tool download --filename clip.mp4")
            sys.exit(1)
        print(f"[client] Requesting download of '{args.filename}' from server...")
        result = await session.call_tool(
            "download_video",
            arguments={"filename": args.filename},
        )
        raw_text = result.content[0].text
        if raw_text.startswith("ERROR:"):
            print(f"\n--- Server response (download_video) ---\n{raw_text}")
            return
        data = json.loads(raw_text)
        video_bytes = base64.b64decode(data["video_base64"])
        # Save to current directory (or use --output path if provided)
        out_path = args.output or data["filename"]
        with open(out_path, "wb") as f:
            f.write(video_bytes)
        size_kb = len(video_bytes) / 1024
        print(f"\n[client] Downloaded '{data['filename']}' ({size_kb:.2f} KB)")
        print(f"[client] Saved to: {os.path.abspath(out_path)}")

    # ── upload (default): send a video file ──────────────────────────────────
    elif tool == "upload":
        if not args.video:
            print("ERROR: a video file path is required for --tool upload")
            print("  Example: python send_video_client.py myvideo.mp4 --url ...")
            sys.exit(1)
        if not os.path.exists(args.video):
            print(f"ERROR: File not found: {args.video}")
            sys.exit(1)

        b64, filename, nbytes = encode_video(args.video)
        print(f"[client] Sending '{filename}'  ({nbytes / 1024:.2f} KB -> {len(b64)} B base64)")

        result = await session.call_tool(
            "receive_video",
            arguments={
                "video_base64": b64,
                "filename": args.filename or filename,
                "description": args.description or f"Sent from {args.video}",
            },
        )
        print_result("receive_video", result)

        # Also list after upload
        list_result = await session.call_tool("list_received_videos", arguments={})
        print_result("list_received_videos", list_result)

    else:
        print(f"ERROR: Unknown tool '{tool}'. Valid options: upload, list, delete, download, tools")
        sys.exit(1)


# ── transports ───────────────────────────────────────────────────────────────

async def run_via_stdio(args):
    """Connect to a local server via stdio."""
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[os.path.join(os.path.dirname(__file__), "video_mcp_server.py")],
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await run_tool(session, args)


async def run_via_http(args):
    """Connect to a remote server via Streamable HTTP.

    Retries automatically on ConnectError — Render free tier can take up to
    60 seconds to wake from sleep.
    """
    try:
        from mcp.client.streamable_http import streamablehttp_client
    except ImportError:
        print("ERROR: mcp streamable_http client not available. Update mcp package.")
        sys.exit(1)

    import httpx

    def http1_client_factory(**kwargs) -> httpx.AsyncClient:
        """Force HTTP/1.1 — HTTP/2 connection coalescing causes 421 on Render."""
        kwargs.pop("http2", None)
        return httpx.AsyncClient(http2=False, **kwargs)

    max_retries = 5
    retry_delays = [5, 10, 15, 20, 30]  # seconds between attempts

    for attempt in range(1, max_retries + 1):
        try:
            async with streamablehttp_client(args.url, httpx_client_factory=http1_client_factory) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await run_tool(session, args)
            return  # success — exit the retry loop
        except* (httpx.ConnectError, httpx.RemoteProtocolError) as eg:
            delay = retry_delays[attempt - 1]
            if attempt < max_retries:
                print(f"\n[client] Server not reachable (attempt {attempt}/{max_retries}). "
                      f"Server may be waking from sleep — retrying in {delay}s...")
                await asyncio.sleep(delay)
            else:
                print(f"\n[client] Could not connect after {max_retries} attempts.")
                print("[client] The server may be down. Check https://dashboard.render.com")
                raise


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="VideoReceiverMCP client — upload, list, or delete videos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Upload a video:
    python send_video_client.py test_video.mp4 --url https://mcp-rgi7.onrender.com/mcp

  List stored videos:
    python send_video_client.py --url https://mcp-rgi7.onrender.com/mcp --tool list

  Delete a video:
    python send_video_client.py --url https://mcp-rgi7.onrender.com/mcp --tool delete --filename test_video.mp4

  Show available MCP tools:
    python send_video_client.py --url https://mcp-rgi7.onrender.com/mcp --tool tools
        """,
    )
    parser.add_argument(
        "video",
        nargs="?",
        default=None,
        help="Path to video file (required for upload, optional otherwise)",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="MCP server URL, e.g. https://mcp-rgi7.onrender.com/mcp (omit for local stdio)",
    )
    parser.add_argument(
        "--tool",
        default="upload",
        choices=["upload", "list", "delete", "download", "tools"],
        help="Which tool to call: upload (default), list, delete, download, tools",
    )
    parser.add_argument(
        "--filename",
        default=None,
        help="Target filename on the server (used with --tool delete, or to rename on upload)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Local path to save a downloaded video (used with --tool download)",
    )
    parser.add_argument(
        "--description",
        default=None,
        help="Description for the uploaded video (optional, used with --tool upload)",
    )
    args = parser.parse_args()

    # For upload, video positional arg is required
    if args.tool == "upload" and not args.video:
        parser.error("A video file path is required when using --tool upload (the default).\n"
                     "  Example: python send_video_client.py myvideo.mp4 --url ...")

    if args.url:
        print(f"[client] Transport: HTTP -> {args.url}  |  tool: {args.tool}")
        asyncio.run(run_via_http(args))
    else:
        print(f"[client] Transport: stdio (local)  |  tool: {args.tool}")
        asyncio.run(run_via_stdio(args))


if __name__ == "__main__":
    main()

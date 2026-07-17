"""
Video MCP Server
================
Supports two transports:

  stdio  (default) - for local use with Claude Desktop / Cursor
  http             - for network deployment (Render, Railway, etc.)

Usage:
  python video_mcp_server.py           # stdio mode
  python video_mcp_server.py --http    # HTTP / Streamable-HTTP mode (port 8000)
"""

import base64
import os
import sys
from datetime import datetime

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Server init
# ---------------------------------------------------------------------------
mcp = FastMCP(name="VideoReceiverMCP")

# Where received videos are saved
SAVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "received_videos")
os.makedirs(SAVE_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def receive_video(
    video_base64: str,
    filename: str = "",
    description: str = "",
) -> str:
    """
    Receives a Base64-encoded video file and saves it to disk.

    Args:
        video_base64:  The video file encoded as a Base64 string.
        filename:      Optional filename (e.g. 'clip.mp4').
                       A timestamped name is auto-generated if omitted.
        description:   Optional human-readable label for this video.

    Returns:
        Status message with saved path and file size.
    """
    try:
        video_bytes = base64.b64decode(video_base64)
    except Exception as exc:
        return f"ERROR: Failed to decode Base64 data: {exc}"

    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"video_{timestamp}.mp4"

    filename = os.path.basename(filename)           # prevent path traversal
    save_path = os.path.join(SAVE_DIR, filename)

    try:
        with open(save_path, "wb") as f:
            f.write(video_bytes)
    except OSError as exc:
        return f"ERROR: Failed to save video: {exc}"

    size_kb = len(video_bytes) / 1024
    desc_line = f"\n   Description : {description}" if description else ""

    return (
        f"Video received and saved!\n"
        f"   File  : {save_path}\n"
        f"   Size  : {size_kb:.2f} KB ({len(video_bytes)} bytes)"
        f"{desc_line}"
    )


@mcp.tool()
def list_received_videos() -> str:
    """
    Lists all videos that have been saved by this server.

    Returns:
        A formatted list of filenames and sizes.
    """
    try:
        files = sorted(os.listdir(SAVE_DIR))
    except OSError as exc:
        return f"ERROR: Could not read save directory: {exc}"

    if not files:
        return "No videos received yet."

    lines = [f"Received videos ({len(files)}) -> {SAVE_DIR}\n"]
    for fname in files:
        fpath = os.path.join(SAVE_DIR, fname)
        try:
            size_kb = os.path.getsize(fpath) / 1024
            lines.append(f"  {fname}  ({size_kb:.2f} KB)")
        except OSError:
            lines.append(f"  {fname}  (size unknown)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# ASGI app — exported so Render can run:
#   uvicorn video_mcp_server:app --host 0.0.0.0 --port $PORT
# ---------------------------------------------------------------------------
app = mcp.streamable_http_app()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    use_http = "--http" in sys.argv
    port = int(os.environ.get("PORT", 8000))

    if use_http:
        import uvicorn
        print(f"[VideoReceiverMCP] Starting HTTP server on port {port} ...")
        print(f"[VideoReceiverMCP] MCP endpoint: http://0.0.0.0:{port}/mcp")
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=port,
            proxy_headers=True,      # trust Render/Railway SSL-terminating proxy
            forwarded_allow_ips="*", # fixes 421 Misdirected Request
        )
    else:
        # Default: stdio for Claude Desktop / Cursor / local agents
        mcp.run(transport="stdio")

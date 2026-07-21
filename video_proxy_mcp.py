"""
Video Proxy MCP  (local)
========================
Runs on your machine via stdio so VS Code / Antigravity IDE / GitHub Copilot can reach it.

It bridges to the remote MCP deployed on Render, handling all the
Base64 encode/decode automatically so the AI just uses plain file paths.

Architecture
------------
  AI Agent (Antigravity / Copilot)
       │  (stdio)
       ▼
  video_proxy_mcp.py   <- THIS FILE  (runs locally)
       |
       +-- reads  C:\\Videos\\movie.mp4
       +-- Base64-encodes it
       +-- calls  receive_video()
       v
  https://mcp-rgi7.onrender.com/mcp   (remote MCP on Render)
       |
       v
  saves file on server disk

Usage
-----
  python video_proxy_mcp.py

mcp.json (works for VS Code AND Antigravity IDE)
------------------------------------------------
  {
    "servers": {
      "video-proxy": {
        "command": "python",
        "args": ["d:/workspace/mcp/video_proxy_mcp.py"]
      }
    }
  }
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# URL of the remote MCP server deployed on Render
REMOTE_URL = "https://mcp-rgi7.onrender.com/mcp"

# HTTP timeout (seconds) — large files can take a while to upload
UPLOAD_TIMEOUT = 300   # 5 minutes
DOWNLOAD_TIMEOUT = 300

# ---------------------------------------------------------------------------
# Local proxy server
# ---------------------------------------------------------------------------

mcp = FastMCP("Video Proxy")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _call_remote(tool_name: str, arguments: dict) -> str:
    """
    Open a fresh Streamable-HTTP session to the remote MCP,
    call one tool, and return its text content as a string.
    """
    timeout = UPLOAD_TIMEOUT if "video_base64" in arguments else DOWNLOAD_TIMEOUT

    async with streamablehttp_client(
        REMOTE_URL,
        timeout=timeout,  # plain seconds (int/float); httpx.Timeout not accepted here
    ) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)

    # result.content is a list of TextContent / BlobContent objects
    if not result.content:
        return "(no response from remote server)"

    # Concatenate all text parts
    parts: list[str] = []
    for item in result.content:
        if hasattr(item, "text"):
            parts.append(item.text)
        else:
            parts.append(str(item))

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Tools exposed to the AI agent
# ---------------------------------------------------------------------------

@mcp.tool()
async def upload_video(path: str, description: str = "") -> str:
    """
    Upload a local video file to the remote MCP server.

    Args:
        path:        Absolute path to the local video file.
                     Examples: C:\\Users\\You\\Videos\\movie.mp4
                               D:\\clips\\demo.mp4
        description: Optional human-readable label stored with the video.

    Returns:
        Status message from the remote server (saved path + file size).
    """
    p = Path(path)

    if not p.exists():
        return f"ERROR: File not found - {path}"

    if not p.is_file():
        return f"ERROR: Path is not a file - {path}"

    size_mb = p.stat().st_size / (1024 * 1024)
    print(f"[proxy] Reading {p.name} ({size_mb:.2f} MB) ...")

    # Read and encode
    raw = p.read_bytes()
    encoded = base64.b64encode(raw).decode("utf-8")

    print(f"[proxy] Uploading to {REMOTE_URL} ...")

    result = await _call_remote(
        "receive_video",
        {
            "video_base64": encoded,
            "filename": p.name,
            "description": description,
        },
    )

    return result


@mcp.tool()
async def download_video(filename: str, output_path: str) -> str:
    """
    Download a video from the remote MCP server and save it locally.

    Args:
        filename:    Name of the video on the remote server (e.g. 'clip.mp4').
        output_path: Absolute local path where the file should be saved.
                     Example: C:\\Users\\You\\Downloads\\clip.mp4

    Returns:
        Confirmation message with the saved path and file size.
    """
    print(f"[proxy] Downloading '{filename}' from {REMOTE_URL} ...")

    raw_response = await _call_remote(
        "download_video",
        {"filename": filename},
    )

    # The remote tool returns a JSON string
    if raw_response.startswith("ERROR"):
        return raw_response

    try:
        obj = json.loads(raw_response)
    except json.JSONDecodeError:
        return f"ERROR: Unexpected response from remote server:\n{raw_response}"

    video_base64 = obj.get("video_base64")
    if not video_base64:
        return f"ERROR: Remote response missing 'video_base64' key.\nResponse: {raw_response}"

    video_bytes = base64.b64decode(video_base64)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(video_bytes)

    size_kb = len(video_bytes) / 1024
    return (
        f"Download complete!\n"
        f"   File : {out.resolve()}\n"
        f"   Size : {size_kb:.2f} KB ({len(video_bytes)} bytes)"
    )


@mcp.tool()
async def list_videos() -> str:
    """
    List all videos stored on the remote MCP server.

    Returns:
        Formatted list of filenames and their sizes.
    """
    return await _call_remote("list_received_videos", {})


@mcp.tool()
async def delete_video(filename: str) -> str:
    """
    Delete a video from the remote MCP server.

    Args:
        filename: Name of the video to delete (e.g. 'clip.mp4').

    Returns:
        Confirmation message or error.
    """
    return await _call_remote("delete_video", {"filename": filename})


# ---------------------------------------------------------------------------
# Entry point — stdio transport for VS Code / Antigravity IDE / Copilot
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")

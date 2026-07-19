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
import html
from datetime import datetime

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles
from starlette.responses import HTMLResponse

# ---------------------------------------------------------------------------
# Server init
# ---------------------------------------------------------------------------
# Disable DNS Rebinding protection so Render domain is allowed
mcp = FastMCP(
    name="VideoReceiverMCP",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False
    )
)

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


@mcp.tool()
def delete_video(filename: str) -> str:
    """
    Deletes a received video from the server.

    Args:
        filename: The filename of the video to delete (e.g., 'clip.mp4').

    Returns:
        Status message confirming deletion or error.
    """
    filename = os.path.basename(filename)  # prevent path traversal
    file_path = os.path.join(SAVE_DIR, filename)

    if not os.path.exists(file_path):
        return f"ERROR: Video file '{filename}' not found."

    try:
        os.remove(file_path)
        return f"Successfully deleted video '{filename}'."
    except OSError as exc:
        return f"ERROR: Failed to delete video: {exc}"



# ---------------------------------------------------------------------------
# ASGI app — exported so Render can run:
#   uvicorn video_mcp_server:app --host 0.0.0.0 --port $PORT
# ---------------------------------------------------------------------------

async def homepage(request):
    try:
        files = sorted(os.listdir(SAVE_DIR))
    except Exception:
        files = []

    video_items = ""
    if not files:
        video_items = '<div class="no-videos">No videos received yet. Use the receive_video tool to upload!</div>'
    else:
        for fname in files:
            fpath = os.path.join(SAVE_DIR, fname)
            size_kb = os.path.getsize(fpath) / 1024
            time_str = datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%Y-%m-%d %H:%M:%S")
            video_items += f"""
            <div class="video-card" onclick="playVideo('/videos/{html.escape(fname)}', '{html.escape(fname)}')">
                <div class="video-icon">🎬</div>
                <div class="video-info">
                    <div class="video-name">{html.escape(fname)}</div>
                    <div class="video-meta">{size_kb:.2f} KB &bull; {time_str}</div>
                </div>
            </div>
            """

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Video MCP Gallery</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #0b0f19;
            --panel: rgba(255, 255, 255, 0.03);
            --border: rgba(255, 255, 255, 0.08);
            --text: #f3f4f6;
            --text-secondary: #9ca3af;
            --accent: #6366f1;
            --accent-hover: #4f46e5;
        }}
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Plus Jakarta Sans', sans-serif;
        }}
        body {{
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 2rem 1rem;
            overflow-x: hidden;
        }}
        .container {{
            width: 100%;
            max-width: 1200px;
            display: grid;
            grid-template-columns: 1fr;
            gap: 2rem;
        }}
        @media(min-width: 768px) {{
            .container {{
                grid-template-columns: 350px 1fr;
            }}
        }}
        header {{
            grid-column: 1 / -1;
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--border);
        }}
        h1 {{
            font-size: 1.75rem;
            font-weight: 700;
            background: linear-gradient(135deg, #a5b4fc, #6366f1);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .badge {{
            background: rgba(99, 102, 241, 0.15);
            color: #a5b4fc;
            padding: 0.35rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.85rem;
            font-weight: 600;
            border: 1px solid rgba(99, 102, 241, 0.3);
        }}
        .sidebar {{
            display: flex;
            flex-direction: column;
            gap: 1rem;
            max-height: 70vh;
            overflow-y: auto;
            padding-right: 0.5rem;
        }}
        .sidebar::-webkit-scrollbar {{
            width: 6px;
        }}
        .sidebar::-webkit-scrollbar-thumb {{
            background: var(--border);
            border-radius: 4px;
        }}
        .video-card {{
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1rem;
            display: flex;
            align-items: center;
            gap: 1rem;
            cursor: pointer;
            transition: all 0.2s ease;
        }}
        .video-card:hover {{
            background: rgba(255, 255, 255, 0.07);
            border-color: var(--accent);
            transform: translateY(-2px);
        }}
        .video-icon {{
            font-size: 1.5rem;
            background: rgba(255, 255, 255, 0.05);
            padding: 0.5rem;
            border-radius: 8px;
        }}
        .video-info {{
            flex: 1;
            min-width: 0;
        }}
        .video-name {{
            font-weight: 600;
            font-size: 0.95rem;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .video-meta {{
            font-size: 0.8rem;
            color: var(--text-secondary);
            margin-top: 0.25rem;
        }}
        .main-content {{
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 1.5rem;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 450px;
            backdrop-filter: blur(10px);
        }}
        .player-container {{
            width: 100%;
            display: none;
            flex-direction: column;
            gap: 1rem;
        }}
        video {{
            width: 100%;
            border-radius: 12px;
            background: #000;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.5);
            border: 1px solid var(--border);
        }}
        .player-title {{
            font-size: 1.2rem;
            font-weight: 600;
        }}
        .no-videos {{
            color: var(--text-secondary);
            text-align: center;
            font-size: 0.95rem;
        }}
        .placeholder-text {{
            font-size: 1.1rem;
            color: var(--text-secondary);
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Video MCP Gallery</h1>
            <span class="badge">Active endpoint: /mcp</span>
        </header>
        
        <div class="sidebar">
            {video_items}
        </div>
        
        <div class="main-content" id="main-content">
            <div class="placeholder-text" id="placeholder">
                🎬 Select a video from the sidebar to play it here.
            </div>
            <div class="player-container" id="player-container">
                <div class="player-title" id="player-title">Video Player</div>
                <video id="video-player" controls autoplay></video>
            </div>
        </div>
    </div>

    <script>
        function playVideo(url, name) {{
            document.getElementById('placeholder').style.display = 'none';
            const container = document.getElementById('player-container');
            container.style.display = 'flex';
            
            const player = document.getElementById('video-player');
            player.src = url;
            player.load();
            
            document.getElementById('player-title').innerText = name;
        }}
    </script>
</body>
</html>
"""
    return HTMLResponse(html_content)


# Build the ASGI app by composing MCP app + gallery + static files
_mcp_asgi = mcp.streamable_http_app()

app = Starlette(
    routes=[
        Route("/", homepage),
        Mount("/videos", StaticFiles(directory=SAVE_DIR), name="videos"),
        Mount("/", _mcp_asgi),  # MCP handles /mcp endpoint
    ]
)


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

# setup.ps1 - Run this once to set up the virtual environment
Write-Host "Setting up VideoReceiverMCP..." -ForegroundColor Cyan

# Create venv if missing
if (-not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv venv
}

# Install dependencies
Write-Host "Installing dependencies..." -ForegroundColor Yellow
& .\venv\Scripts\pip install -r requirements.txt

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Run locally (stdio - for Claude Desktop / Cursor):" -ForegroundColor Cyan
Write-Host "  .\venv\Scripts\python video_mcp_server.py"
Write-Host ""
Write-Host "Run locally (HTTP - to test network mode):" -ForegroundColor Cyan
Write-Host "  .\venv\Scripts\python video_mcp_server.py --http"
Write-Host ""
Write-Host "Send a test video (stdio):" -ForegroundColor Cyan
Write-Host "  .\venv\Scripts\python send_video_client.py path\to\video.mp4"
Write-Host ""
Write-Host "Send a test video (HTTP to local server):" -ForegroundColor Cyan
Write-Host "  .\venv\Scripts\python send_video_client.py path\to\video.mp4 --url http://localhost:8000/mcp"

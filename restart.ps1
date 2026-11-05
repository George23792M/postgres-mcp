# Restart postgres-mcp
Write-Host "Stopping postgres-mcp application..." -ForegroundColor Yellow

# Fixed: Moved ErrorAction to Get-Process so it doesn't crash when Python is already stopped
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force

Start-Sleep -Seconds 2

Write-Host "Starting postgres-mcp application..." -ForegroundColor Green

uv run main.py

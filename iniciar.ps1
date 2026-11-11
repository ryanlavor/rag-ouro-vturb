# Sobe o chat em http://127.0.0.1:8765 (só nesta máquina) e abre o navegador.
$uv = "$env:LOCALAPPDATA\com.LangflowDesktop\uv\uv.exe"
if (Get-Command uv -ErrorAction SilentlyContinue) { $uv = "uv" }
Set-Location "$PSScriptRoot\backend"
$env:HF_HUB_OFFLINE = "1"
Start-Process "http://127.0.0.1:8765"
& $uv run uvicorn app:app --host 127.0.0.1 --port 8765

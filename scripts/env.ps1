# Kundali development environment variables
# Dot-source this file:  . .\scripts\env.ps1

$env:UV_CACHE_DIR="D:\DevCache\uv\cache"
$env:UV_PYTHON_INSTALL_DIR="D:\DevCache\uv\python"
$env:UV_TOOL_DIR="D:\DevCache\uv\tools"
$env:UV_PYTHON_BIN_DIR="D:\DevCache\uv\bin"
$env:PIP_CACHE_DIR="D:\DevCache\pip"
$env:npm_config_cache="D:\DevCache\npm\cache"
$env:npm_config_prefix="D:\DevCache\npm\global"
$env:COREPACK_HOME="D:\DevCache\corepack"
$env:TEMP="D:\DevCache\tmp"
$env:TMP="D:\DevCache\tmp"
$env:HF_HOME="D:\DevCache\huggingface"
$env:TORCH_HOME="D:\DevCache\torch"
$env:XDG_CACHE_HOME="D:\DevCache\xdg"
$env:NEXT_TELEMETRY_DISABLED="1"

Write-Host "Kundali env loaded - all caches on D:\DevCache" -ForegroundColor Green

# verify_env.ps1 — Verify that all environment variables point to D:\DevCache
$vars = @(
    "UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR", "UV_TOOL_DIR", "UV_PYTHON_BIN_DIR",
    "PIP_CACHE_DIR", "npm_config_cache", "npm_config_prefix", "COREPACK_HOME",
    "TEMP", "TMP", "HF_HOME", "TORCH_HOME", "XDG_CACHE_HOME"
)
$ok = $true
foreach ($v in $vars) {
    $val = [Environment]::GetEnvironmentVariable($v, "Process")
    if (-not $val -or -not $val.StartsWith("D:\")) {
        Write-Host "FAIL: $v = $val" -ForegroundColor Red
        $ok = $false
    } else {
        Write-Host "OK:   $v = $val" -ForegroundColor Green
    }
}
if ($ok) { Write-Host "`nAll environment variables OK." -ForegroundColor Green }
else { Write-Host "`nSome variables are missing or not on D:!" -ForegroundColor Red }

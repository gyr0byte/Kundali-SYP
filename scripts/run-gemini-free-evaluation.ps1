# Run explicitly from Windows PowerShell as the Windows user who stored the DPAPI key.
[CmdletBinding()]
param(
    [switch]$AuthorizeHosted,
    [switch]$ConfirmFreeTier,
    [Parameter(Mandatory)][ValidatePattern('\A[0-9a-f]{64}\z')][string]$ApprovedDatasetSha256,
    [Parameter(Mandatory)][string]$Output
)

$ErrorActionPreference = 'Stop'
$secure = $null
$buffer = [IntPtr]::Zero
$start = $null
$child = $null
$childExit = 1
$phase = 'checking evaluation arguments and setup'
try {
    if (-not $AuthorizeHosted -or -not $ConfirmFreeTier) { throw 'Authorization required' }
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Windows required' }
    . (Join-Path $PSScriptRoot 'env.ps1')
    $backend = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\backend'))
    if ($backend -notlike 'D:\*') { throw 'Backend must be on D:' }
    $outputPath = [IO.Path]::GetFullPath($Output)
    if ($outputPath -notlike 'D:\*.json' -or $outputPath.Contains('"') -or
        (Test-Path -LiteralPath $outputPath) -or
        -not (Test-Path -LiteralPath (Split-Path -Parent $outputPath) -PathType Container)) {
        throw 'A new D: JSON output file is required'
    }

    $fixture = Join-Path $backend 'tests\fixtures\multilingual-retrieval-v1.json'
    $pinned = '7f35fe79f71e8f9c07f757a5f3523f7cfd8632e688405df3724c9e2303d10b66'
    if ($ApprovedDatasetSha256 -ne $pinned -or (Get-FileHash -LiteralPath $fixture).Hash -ne $pinned) {
        throw 'Reviewed fixture checksum mismatch'
    }

    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = Join-Path $backend '.venv\Scripts\python.exe'
    $start.WorkingDirectory = $backend
    $start.UseShellExecute = $false
    $start.Arguments = '-B -m app.ai.evaluate_retrieval --provider developer --authorize-hosted ' +
        '--confirm-free-tier --max-attempts 44 --max-spend-microusd 0 --price-per-1000-microusd 0 ' +
        "--approved-dataset-sha256 $pinned --output `"$outputPath`""
    $start.EnvironmentVariables.Remove('KUNDALI_VERTEX_ACCESS_TOKEN')
    $start.EnvironmentVariables['PYTHONDONTWRITEBYTECODE'] = '1'
    $phase = 'reading the encrypted Gemini credential file'
    $encrypted = [IO.File]::ReadAllText('D:\DevSecrets\Kundali\gemini-api-key.dpapi').TrimEnd()
    $phase = 'decrypting the Gemini credential with Windows DPAPI'
    $secure = ConvertTo-SecureString -String $encrypted
    $buffer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($buffer)
    $phase = 'validating the decrypted Gemini credential format'
    if ($key -cnotmatch '\A(?:AIza[A-Za-z0-9_-]{35}|AQ\.[A-Za-z0-9_-]{17,253})\z') {
        throw 'Invalid credential format'
    }

    $phase = 'running the evaluation child process'
    $start.EnvironmentVariables['KUNDALI_GEMINI_API_KEY'] = $key
    try {
        $child = [Diagnostics.Process]::Start($start)
    } finally {
        $start.EnvironmentVariables.Remove('KUNDALI_GEMINI_API_KEY')
        $key = $null
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($buffer)
        $buffer = [IntPtr]::Zero
        $secure.Dispose()
        $secure = $null
    }
    $child.WaitForExit()
    $childExit = $child.ExitCode
} catch {
    throw "Gemini evaluation stopped while $phase."
} finally {
    $key = $null
    if ($buffer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($buffer) }
    if ($null -ne $secure) { $secure.Dispose() }
    if ($null -ne $child) { $child.Dispose() }
}
exit $childExit

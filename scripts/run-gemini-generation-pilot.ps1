# Run from Windows PowerShell as the Windows account that stored the DPAPI key.
[CmdletBinding()]
param(
    [switch]$AuthorizeHosted,
    [switch]$ConfirmFreeTier,
    [Parameter(Mandatory)][ValidatePattern('\A[0-9a-f]{64}\z')][string]$ApprovedFixtureSha256,
    [ValidateRange(1, 20)][int]$MaxHttpAttempts = 8,
    [Parameter(Mandatory)][string]$Output
)

$ErrorActionPreference = 'Stop'
$secure = $null
$buffer = [IntPtr]::Zero
$child = $null
$childExit = 1
$phase = 'checking hosted authorization and pilot setup'
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

    $fixture = Join-Path $backend 'tests\fixtures\synthetic-generation-v1.json'
    $pinned = 'b76b874f899151f2b03812b050ed9e7380e7f14f76ee53f4688d55785565c3db'
    if ($ApprovedFixtureSha256 -ne $pinned -or (Get-FileHash -LiteralPath $fixture).Hash -ne $pinned) {
        throw 'Reviewed fixture checksum mismatch'
    }
    $python = Join-Path $backend '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Python venv unavailable' }

    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = $python
    $start.WorkingDirectory = $backend
    $start.UseShellExecute = $false
    $start.Arguments = '-B -m app.ai.evaluate_generation --authorize-hosted --confirm-free-tier ' +
        "--approved-fixture-sha256 $pinned --max-http-attempts $MaxHttpAttempts --output `"$outputPath`""
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

    $phase = 'running the synthetic generation pilot child process'
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
    throw "Gemini generation pilot stopped while $phase."
} finally {
    $key = $null
    if ($buffer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($buffer) }
    if ($null -ne $secure) { $secure.Dispose() }
    if ($null -ne $child) { $child.Dispose() }
}
exit $childExit

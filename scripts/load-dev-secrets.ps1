# Dot-source this file in a dedicated Windows PowerShell backend session.
& {
    param($scriptRoot, $secretDirectory, $caFile)

    $ErrorActionPreference = 'Stop'
    $files = [ordered]@{
        DATABASE_URL = 'runtime-db.dpapi'
        JWT_SECRET = 'jwt-secret.dpapi'
        ENCRYPTION_KEY = 'encryption-key.dpapi'
    }
    $values = @{}
    $ca = $null
    $phase = 'checking the Windows runtime and CA bundle'
    $applying = $false

    try {
        if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Windows required' }
        $ca = Get-Item -LiteralPath $caFile
        if ($ca.PSIsContainer -or $ca.Length -le 0 -or $ca.FullName -notlike 'D:\*') {
            throw 'Invalid CA file'
        }

        foreach ($entry in $files.GetEnumerator()) {
            $phase = "loading $($entry.Key)"
            $encrypted = [IO.File]::ReadAllText((Join-Path $secretDirectory $entry.Value)).TrimEnd()
            if ([string]::IsNullOrWhiteSpace($encrypted)) { throw 'Empty credential file' }

            $secure = $null
            $buffer = [IntPtr]::Zero
            try {
                $secure = ConvertTo-SecureString -String $encrypted
                $buffer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
                $values[$entry.Key] = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($buffer)
                if ([string]::IsNullOrWhiteSpace($values[$entry.Key]) -or
                    $values[$entry.Key].Length -gt 8192 -or
                    $values[$entry.Key] -match '[\x00-\x1f\x7f]') {
                    throw 'Invalid credential value'
                }
            } finally {
                if ($buffer -ne [IntPtr]::Zero) {
                    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($buffer)
                }
                if ($null -ne $secure) { $secure.Dispose() }
            }
        }

        $phase = 'validating the direct restricted runtime database URL'
        $runtimeUrl = '\Apostgresql(?:\+psycopg)?://kundali_dev_app:(?:[A-Za-z0-9._~-]|%[0-9A-Fa-f]{2})+@'
        $runtimeUrl += '(?![a-z0-9-]+-pooler\.)[a-z0-9-]+(?:\.[a-z0-9-]+)*\.neon\.tech(?::5432)?/'
        $runtimeUrl += '(?!kundali_test_)[A-Za-z0-9_-]+(?:\?(?:sslmode=verify-full(?:&channel_binding=require)?|channel_binding=require(?:&sslmode=verify-full)?))?\z'
        if ($values.DATABASE_URL -cnotmatch $runtimeUrl) { throw 'Runtime URL required' }

        $phase = 'validating the JWT signing secret'
        if ($values.JWT_SECRET.Trim().Length -lt 32) { throw 'Invalid JWT signing secret' }

        $phase = 'validating the Fernet key'
        if ($values.ENCRYPTION_KEY -cnotmatch '\A[A-Za-z0-9_-]{43}=\z') { throw 'Invalid Fernet key' }

        $phase = 'loading the D: development environment'
        . (Join-Path $scriptRoot 'env.ps1')

        $phase = 'setting the runtime process environment'
        $applying = $true
        $remove = @(
            'ADMIN_PASSWORD', 'ADMIN_DATABASE_URL', 'DATABASE_ADMIN_URL', 'KUNDALI_ADMIN_DATABASE_URL',
            'MIGRATION_DATABASE_URL', 'DATABASE_MIGRATION_URL', 'KUNDALI_MIGRATION_DATABASE_URL',
            'KUNDALI_DB_MIGRATION_TARGET', 'TEST_DATABASE_URL', 'KUNDALI_TEST_DATABASE_URL',
            'KUNDALI_TEST_DATABASE_TARGET', 'KUNDALI_RUN_POSTGRES_TESTS',
            'PGSERVICE', 'PGSERVICEFILE', 'PGHOSTADDR', 'PGPASSWORD', 'PGPASSFILE',
            'PGUSER', 'PGDATABASE', 'PGHOST', 'PGPORT', 'PGOPTIONS'
        )
        foreach ($name in $remove) {
            [Environment]::SetEnvironmentVariable($name, $null, 'Process')
        }
        $values.ENVIRONMENT = 'dev'
        $values.KUNDALI_DB_CA_FILE = $ca.FullName
        foreach ($entry in $values.GetEnumerator()) {
            [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, 'Process')
        }
    } catch {
        if ($applying) {
            foreach ($name in @($files.Keys) + @('ENVIRONMENT', 'KUNDALI_DB_CA_FILE')) {
                [Environment]::SetEnvironmentVariable($name, $null, 'Process')
            }
        }
        throw "Kundali development startup stopped while $phase. Do not start the backend from this shell."
    } finally {
        $values.Clear()
        $entry = $null
    }
} $PSScriptRoot 'D:\DevSecrets\Kundali' 'D:\DevCache\Certificates\cacert.pem'

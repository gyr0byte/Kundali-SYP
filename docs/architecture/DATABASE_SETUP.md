# PostgreSQL setup on Windows

Run FastAPI and Next.js natively on Windows. From the repository root, dot-source `. .\scripts\env.ps1` before invoking the existing virtual environment. Keep the environment, dependencies, certificates, caches, temporary files and generated artifacts on D:. Managed PostgreSQL is preferred. Use the direct Neon development endpoint. Native PostgreSQL is an alternative when it meets the same verification requirements.

## Verified development database

Manual verification covered Neon Singapore PostgreSQL 16.16 over a direct connection with certificate and hostname verification and required channel binding. Migrations `0001` through `0003` were applied, pgvector is installed, and effective grants were verified for the dedicated migration and restricted runtime roles. All 38 focused offline tests and all four live PostgreSQL integration tests passed.

The restricted runtime role passed the application settings and SQLAlchemy engine smoke test. The developer verified DPAPI credential storage and loading in a fresh PowerShell session, plus validation of the stable JWT and Fernet keys. FastAPI startup, health, registration, login, authenticated profile listing, creation, retrieval and deletion passed. Reading the deleted profile returned HTTP 404. PostgreSQL persisted `auth:register`, `profile:create` and `profile:delete` audit events.

Transaction hardening passed 103 focused offline tests and all nine cases in a separate disposable PostgreSQL concurrency suite (66.50 seconds, exit code 0). Live checks covered duplicate refresh consumption and family revocation, refresh racing with logout and password reset, last-active-admin protection, overlapping approval and activation changes, and rollback when an audit write fails. Alembic compatibility, pgvector and encrypted profile CRUD passed again. No new migration was required. Ruff, formatting, mypy and whitespace checks passed. The known Starlette/httpx deprecation warning remains.

Existing access JWTs can remain valid until expiry. Strict reuse detection can revoke a token family after a legitimate duplicate refresh request. Direct SQL writers can bypass application locks. Full browser-to-database verification and a portable, secure Fernet recovery backup remain pending. The migration role retains elevated development-only privileges. The disposable concurrency database retains its migrated schema and synthetic test data. The earlier integration database and synthetic development account also remain in place.

| Role | Purpose and grants |
|---|---|
| `neondb_owner` | Original Neon administrator. Use for role and database administration only. |
| `kundali_dev_migrator` | Owns the six application tables and `alembic_version` on development. Use for Alembic DDL only. |
| `kundali_dev_app` | CRUD on `users`, `refresh_tokens`, `password_reset_tokens`, `astrologer_profiles`, and `birth_profiles`. SELECT and INSERT on `audit_logs`. SELECT only on `alembic_version`. No database CREATE, schema CREATE, or `neon_superuser` membership. |

## Private PowerShell configuration

Load these values into the current PowerShell process from an approved secret store. Start tooling from that same shell. Keep values out of shell history, transcripts, command-line arguments, IDE logs, machine-wide environment variables and real `.env` files.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Direct approved development endpoint. Use `postgresql://` or `postgresql+psycopg://`. Omit TLS parameters or set `sslmode=verify-full&channel_binding=require`. The shared policy enforces both. A provider URI with `sslmode=require` needs to be corrected privately. |
| `KUNDALI_DB_CA_FILE` | Absolute path on D: to a trusted PEM CA bundle. Use an approved source and verify provenance. Use the server's DNS hostname for hostname verification. |
| `KUNDALI_DB_MIGRATION_TARGET` | Independently confirm the approved target in the provider console, in `hostname:port/database` form. Do not derive this confirmation from the connection string. |
| `JWT_SECRET` | Stable development-only signing secret from at least 32 cryptographically random bytes. Use a separate production secret. Rotation invalidates existing access tokens. |
| `ENCRYPTION_KEY` | Development-only Fernet key generated once with `Fernet.generate_key()`. Keep it stable and back it up securely. Rotation requires planned re-encryption of existing ciphertext. |

The client requires certificate and hostname verification, SCRAM channel binding and a five-second connection timeout. The explicit PEM bundle avoids relying on Windows system trust discovery. Client TLS is inspected through Psycopg.

### Load runtime credentials with DPAPI

In a dedicated Windows PowerShell backend shell, run from the repository root:

```powershell
. .\scripts\load-dev-secrets.ps1
Set-Location .\backend
.\.venv\Scripts\python.exe -B -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The loader uses the current Windows account's DPAPI context to open `runtime-db.dpapi`, `jwt-secret.dpapi`, and `encryption-key.dpapi` in `D:\DevSecrets\Kundali`. It uses `D:\DevCache\Certificates\cacert.pem`, selects `ENVIRONMENT=dev`, and rejects DSNs that do not identify the restricted runtime role on a direct Neon hostname. Confirm separately that the stored DSN targets the development branch. On success it replaces the process credentials and clears the known administrator, migration, test, and libpq routing overrides. On validation failure it leaves the existing environment intact. Stop if the loader reports an error. Close the dedicated shell after use because the backend and its children inherit plaintext environment values.

The DPAPI files are account-bound local copies. Keep a separate secure, recoverable backup of the original stable Fernet key. Replacing it without re-encrypting existing rows makes birth profiles unreadable. Do not use the runtime loader for migration or test credentials.

### Initialize a passwordless Neon role

Neon documents plaintext input for SQL password changes over a verified connection and rejects precomputed SCRAM verifiers, including clients that submit a verifier through `\password`. Console reset may fail when the SQL-created role has never had a password. For an authorized initialization, use the administrative role on the development branch to set a disposable password on the existing role, require commit acknowledgement, then promptly rotate the disposable password through the Console. Keep the final runtime credential out of SQL. A password literal may appear in provider-side logs. If initialization or commit fails, report only the operation stage and SQLSTATE and reconcile the result before retrying. [Neon role management](https://neon.com/docs/manage/roles#manage-roles-with-sql)

## Migrations and readiness

Offline SQL preview works without secrets. Run from `backend`:

```powershell
.\.venv\Scripts\python.exe -B -m alembic upgrade head --sql
```

Only run live commands when explicitly authorized. Verify branch and database in the provider console. Use a development-only migration role with DDL and extension privileges and no production access. Use a narrower role for application runtime. From the repository root, run the read-only checker:

```powershell
.\backend\.venv\Scripts\python.exe -B .\scripts\check_db.py
```

Exit codes are `0` for ready, `1` for reachable with incomplete schema or extension, `2` for invalid configuration, and `3` for connectivity or inspection failure. The checker needs no JWT or Fernet key.

Readiness requires revision `0007_knowledge_embeddings` and installed pgvector.
The checker reports recognized earlier revisions by name. For example,
`0006_knowledge_corpus` and `0005_resolved_bs_profiles` are recognized and
return exit code `1`.

To apply migrations, run the Alembic command above from `backend` without `--sql`, then rerun the checker. Revision `0003_enable_pgvector` creates the PostgreSQL extension `vector` if absent. Availability and permission to install are separate. Downgrade retains the extension because it may predate the migration or be shared.

The migrator needs `USAGE` and `CREATE` on the target schema and ownership, directly or through an approved owner role, of objects that it alters or drops. Database-wide CREATE and broader role memberships are unnecessary for ordinary table migrations. Check extension-specific grants separately when a future migration installs or updates an extension. Explicitly grant the runtime role the intended access to newly created objects from the owning role and verify the effective grants. Keep DDL with the migrator and preserve audit append-only and migration-history read-only access. Alembic currently emits a generic sanitized error on live failure. A future improvement is to report the operation stage and allowlisted SQLSTATE without exception text, query parameters, or connection details.

### BS profile migration

Revision `0005_resolved_bs_profiles` replaces the check constraint on
`birth_profiles` so a BS profile can store its encrypted Gregorian date. AD
profiles still require an encrypted Gregorian date. The migrator needs
ownership of `birth_profiles`. Existing runtime grants cover the change.
Legacy pending BS rows stay pending until their owner successfully saves them.
The migration does not backfill rows or rewrite snapshots. Downgrade refuses
to restore the old constraint while resolved BS rows exist.

The populated PostgreSQL migration regression passed in 10.51 seconds. It
verified that upgrading from `0004` preserves encrypted AD and unresolved BS
profiles, their revisions, and the existing AD snapshot. The new constraint
accepted a resolved BS profile and rejected invalid calendar states.
Development migration `0005` and the readiness checker both exited 0.
The checker confirmed verified TLS, revision `0005`, and installed pgvector.

Live Playwright verification used the restricted development runtime role
with English at 1440 × 900 and Nepali at 375 × 812. Registration, login,
profile creation, Nepali digit input, server conversion, date validation,
editing, recalculation, and deletion passed. Equivalent AD and BS inputs
produced identical chart facts and fingerprints with distinct snapshot UUIDs.
Editing invalidated the active result and retained its historical snapshot.
Both profiles were deleted and all three snapshot URLs returned HTTP 404.
The browser reported zero uncaught JavaScript errors, network failures, or
horizontal overflow.

Two synthetic development accounts remain. The browser smoke test did not
independently query the resulting audit entries. Mobile planetary labels
still need more spacing in crowded chart cells. Live verification covers
the workflows and viewport sizes above.

### Chart snapshot migration and grants

Revision `0004_chart_snapshots` adds a profile revision counter and the `chart_snapshots` table. Existing profiles start at revision `1`. The migrator needs ownership of `public.birth_profiles` and `CREATE` on the target schema. After the migration, the table owner grants the development runtime role the following privileges:

```sql
GRANT SELECT, INSERT ON TABLE public.chart_snapshots TO kundali_dev_app;
```

The existing `birth_profiles` grants cover revision reads, row locks and edits. The development runtime role was verified to have `SELECT` and `INSERT` on `chart_snapshots`, with `UPDATE`, `DELETE` and `TRUNCATE` denied. The foreign key cascades from profile deletion without a separate runtime grant on snapshots. Downgrading `0004` drops all stored snapshots and their facts.

Development migration `0004` applied successfully, the database checker returned exit code 0, and backend startup passed using the existing DPAPI loader. All 48 focused offline tests and all 12 disposable PostgreSQL integration tests passed. The live suite took 88.41 seconds and exited 0, covering concurrent duplicate saves, profile edits and deletions. Ruff lint and formatting, mypy, offline Alembic SQL generation and whitespace checks passed.

The live HTTP smoke test authenticated a synthetic account with the restricted runtime role and verified profile creation (`201`), chart calculation (`200`), the snapshot `Location` header, and snapshot retrieval (`200`). The stored result matched the calculated chart, including verified metadata and fact units. Recalculation reused the same snapshot. Cross-user access returned `404`, and parent deletion (`204`) made the snapshot return `404`. Full browser-to-database verification and portable Fernet recovery backup remain pending. Disposable test databases and synthetic development accounts remain in place.

## Disposable integration tests

In a separate private PowerShell process, supply `KUNDALI_TEST_DATABASE_URL`, `KUNDALI_DB_CA_FILE`, and an independently confirmed `KUNDALI_TEST_DATABASE_TARGET` in `hostname:port/database` form. Use an empty database named `kundali_test_*` on a development-only endpoint, with credentials restricted to that test target. Leave normal development and production credentials out of the test shell. Set `KUNDALI_RUN_POSTGRES_TESTS=1` only after confirming that the target is disposable.

From `backend`:

```powershell
.\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider tests/integration/test_postgresql.py
```

The harness rejects URL/target mismatches and non-test names before connecting. It checks database identity, role, default schema and catalog emptiness before applying migrations. It leaves the migrated database with synthetic test data in place for authorized disposal. Use a fresh database per run. Standard offline suites retain their SQLite fixtures.

## Manual runtime API smoke test

Start the backend as shown above. Use a second PowerShell shell for HTTP requests so it needs no database credentials. Run only on the development branch with synthetic data. The commands retain the bearer token in memory and print status codes only.

```powershell
$base = 'http://127.0.0.1:8000'
$health = Invoke-WebRequest -UseBasicParsing "$base/health"
$health.StatusCode                             # 200
($health.Content | ConvertFrom-Json).status    # ok

$account = @{
    email = "smoke-$([guid]::NewGuid().ToString('N'))@example.com"
    password = "Fixture-$([guid]::NewGuid().ToString('N'))!"
} | ConvertTo-Json
$registered = Invoke-WebRequest -UseBasicParsing "$base/api/v1/auth/register" `
    -Method Post -ContentType 'application/json' -Body $account
$registered.StatusCode                        # 201
$login = Invoke-WebRequest -UseBasicParsing "$base/api/v1/auth/login" `
    -Method Post -ContentType 'application/json' -Body $account
$login.StatusCode                             # 200
$session = $login.Content | ConvertFrom-Json
$headers = @{ Authorization = "Bearer $($session.access_token)" }

(Invoke-WebRequest -UseBasicParsing "$base/api/v1/profiles" -Headers $headers).StatusCode # 200
$payload = @{
    label = 'Synthetic smoke profile'; input_calendar = 'AD'; entered_date = '2000-01-01'
    time_certainty = 'exact'; time_local = '12:00'; place_name = 'Synthetic place'
    latitude = 27.7; longitude = 85.3; timezone = 'Asia/Kathmandu'
} | ConvertTo-Json
$created = Invoke-WebRequest -UseBasicParsing "$base/api/v1/profiles" -Method Post `
    -Headers $headers -ContentType 'application/json' -Body $payload
$created.StatusCode                           # 201
$profileId = ($created.Content | ConvertFrom-Json).id
$profileUrl = "$base/api/v1/profiles/$profileId"
$fetched = Invoke-WebRequest -UseBasicParsing $profileUrl -Headers $headers
$fetched.StatusCode                           # 200
if (($fetched.Content | ConvertFrom-Json).label -ne 'Synthetic smoke profile') {
    throw 'Unexpected profile returned'
}
(Invoke-WebRequest -UseBasicParsing $profileUrl -Method Delete -Headers $headers).StatusCode # 204
try {
    $null = Invoke-WebRequest -UseBasicParsing $profileUrl -Headers $headers
    throw 'Deleted profile is still accessible'
} catch [System.Net.WebException] {
    if ($null -eq $_.Exception.Response -or [int]$_.Exception.Response.StatusCode -ne 404) { throw }
    404
}
```

For the audit check, use a separate authorized read-only audit session. Filter by the synthetic user ID from the registration response and inspect only `action` and `target_type`. Expect `auth:register` for `user` and `profile:create` and `profile:delete` for `birth_profile`. Successful login and profile reads do not emit a dedicated audit event. Deleting the profile leaves the synthetic user and audit history on the development branch. Close the HTTP shell when finished.

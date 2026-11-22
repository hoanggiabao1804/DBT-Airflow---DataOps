<#
.SYNOPSIS
Check source timestamp integrity and freshness without changing business data.
.NOTES
Requires the running Compose dbt/SQL Server services and a valid local profile.
Exit 0: timestamps valid and freshness PASS/WARN; exit 1: quality/SLA failure;
exit 2: execution or evidence-validation failure. Historical data is NOT exempt.
#>
[CmdletBinding()]
param(
    [string]$OutputDirectory,
    [ValidatePattern('^[A-Za-z0-9_]+$')][string]$Target = 'dev',
    [ValidateRange(1, 8760)][int]$WarnAfterHours = 24,
    [ValidateRange(2, 8760)][int]$ErrorAfterHours = 48
)

$ErrorActionPreference = 'Stop'
if ($WarnAfterHours -ge $ErrorAfterHours) {
    throw 'WarnAfterHours must be smaller than ErrorAfterHours.'
}
$repoRoot = Split-Path -Parent $PSScriptRoot
$runId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $repoRoot "docs/evidence/tuan-week2-day6-7/$runId/freshness"
} elseif (-not [IO.Path]::IsPathRooted($OutputDirectory)) {
    $OutputDirectory = Join-Path $repoRoot $OutputDirectory
}
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
if ((Test-Path -LiteralPath $OutputDirectory) -and @(Get-ChildItem -LiteralPath $OutputDirectory -Force).Count -gt 0) {
    throw "Choose a new or empty output directory; existing evidence is preserved: $OutputDirectory"
}
$null = Get-Command docker -CommandType Application -ErrorAction Stop
$null = New-Item -ItemType Directory -Path $OutputDirectory -Force
$containerRoot = "/tmp/tuan-source-freshness-$runId"
$statusPath = Join-Path $OutputDirectory 'freshness_status.json'
$sourcePath = Join-Path $repoRoot 'dbt/models/bronze/src_adventureworks.yml'
$expectedSources = @(
    'source.dbt_sqlserver_project.adventureworks.Customer',
    'source.dbt_sqlserver_project.adventureworks.SalesOrderDetail',
    'source.dbt_sqlserver_project.adventureworks.SalesOrderHeader',
    'source.dbt_sqlserver_project.adventureworks_person.Person',
    'source.dbt_sqlserver_project.adventureworks_production.Product',
    'source.dbt_sqlserver_project.adventureworks_production.ProductSubcategory'
)
$expectedTests = @($expectedSources | ForEach-Object {
    $parts = $_.Split('.')
    foreach ($test in @('not_null', 'no_future_dates')) {
        'source_{0}_{1}_{2}_ModifiedDate' -f $test, $parts[2], $parts[3]
    }
})
$status = [ordered]@{
    run_id = $runId
    started_at_utc = [DateTime]::UtcNow.ToString('o')
    finished_at_utc = $null
    status = 'running'
    exit_code = $null
    target = $Target
    warn_after_hours = $WarnAfterHours
    error_after_hours = $ErrorAfterHours
    source_definition_sha256 = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant()
    freshness_macro_sha256 = (Get-FileHash -LiteralPath (Join-Path $repoRoot 'dbt/macros/sqlserver__collect_freshness.sql') -Algorithm SHA256).Hash.ToLowerInvariant()
    loaded_at_meaning = 'ModifiedDate is the latest business update, not ingestion or restore time; interpreted as UTC.'
    container_artifact_directory = $containerRoot
    steps = @()
    timestamp_test_counts = $null
    freshness_counts = $null
}

function Save-Status {
    $status | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $statusPath -Encoding UTF8
}

function Invoke-LoggedDocker {
    param([string[]]$Arguments, [string]$LogName)
    $ErrorActionPreference = 'Continue'
    & docker @Arguments 2>&1 | ForEach-Object -ErrorAction Stop {
        $line = $_.ToString()
        Write-Host $line
        $line
    } | Set-Content -LiteralPath (Join-Path $OutputDirectory $LogName) -Encoding UTF8 -ErrorAction Stop
    return $LASTEXITCODE
}

function Copy-Artifact {
    param([string]$Name, [string]$Destination)
    $code = Invoke-LoggedDocker -Arguments @('compose', 'cp', "dbt:$containerRoot/target/$Name",
        (Join-Path $OutputDirectory $Destination)) -LogName "$Destination.copy.txt"
    if ($code -ne 0) { throw "Could not collect $Name; Docker exit $code" }
    return Get-Content -LiteralPath (Join-Path $OutputDirectory $Destination) -Raw -Encoding UTF8 | ConvertFrom-Json
}

Save-Status
Push-Location -LiteralPath $repoRoot
try {
    # YAML flow mapping avoids PowerShell/native double-quote escaping problems.
    $vars = "{source_freshness_warn_hours: $WarnAfterHours, source_freshness_error_hours: $ErrorAfterHours}"
    $steps = @(
        @{ name = 'deps'; args = @('deps') },
        @{ name = 'timestamp_tests'; args = @('test', '--select', 'tag:source_timestamp') },
        @{ name = 'freshness'; args = @('source', 'freshness', '--select',
            'source:adventureworks', 'source:adventureworks_production', 'source:adventureworks_person') }
    )
    foreach ($definition in $steps) {
        $step = [ordered]@{
            name = $definition.name
            command = 'dbt ' + ($definition.args -join ' ')
            started_at_utc = [DateTime]::UtcNow.ToString('o')
            finished_at_utc = $null
            exit_code = $null
            stdout_file = $definition.name + '.stdout.txt'
        }
        $status.steps += $step
        Save-Status
        $dockerArgs = @('compose', 'exec', '-T', '-e', 'DBT_USE_COLORS=false',
            '-e', "DBT_LOG_PATH=$containerRoot/logs", '-e', "DBT_TARGET_PATH=$containerRoot/target",
            'dbt', 'dbt') + $definition.args + @('--profiles-dir', '/usr/app/dbt', '--target', $Target, '--vars', $vars)
        $step.exit_code = Invoke-LoggedDocker -Arguments $dockerArgs -LogName $step.stdout_file
        $step.finished_at_utc = [DateTime]::UtcNow.ToString('o')
        Save-Status
        if ($definition.name -eq 'deps' -and $step.exit_code -ne 0) { throw 'dbt deps failed.' }
        if ($definition.name -eq 'timestamp_tests') {
            $testArtifact = Copy-Artifact -Name 'run_results.json' -Destination 'timestamp_tests.run_results.json'
            $actualTests = @($testArtifact.results | ForEach-Object { $_.unique_id.Split('.')[2] })
            if ($testArtifact.args.which -ne 'test' -or $actualTests.Count -ne 12 -or
                @(Compare-Object $expectedTests $actualTests).Count -ne 0) {
                throw 'Expected the 12 source timestamp tests from this invocation.'
            }
            if (@($testArtifact.results | Where-Object { $_.status -notin @('pass', 'fail') }).Count -gt 0) {
                throw 'A timestamp test did not execute normally; inspect timestamp_tests.run_results.json.'
            }
            $expectedTestExit = if (@($testArtifact.results | Where-Object { $_.status -eq 'fail' }).Count -gt 0) { 1 } else { 0 }
            if ($step.exit_code -ne $expectedTestExit) { throw 'Timestamp test exit code disagrees with its artifact.' }
            $status.timestamp_test_counts = @($testArtifact.results | Group-Object status | Select-Object Name, Count)
        }
        if ($definition.name -eq 'freshness') {
            $freshnessArtifact = Copy-Artifact -Name 'sources.json' -Destination 'sources.json'
            $actualSources = @($freshnessArtifact.results | ForEach-Object { $_.unique_id })
            if ($actualSources.Count -ne 6 -or @(Compare-Object $expectedSources $actualSources).Count -ne 0) {
                throw 'Freshness evidence must contain exactly the six configured sources.'
            }
            if (@($freshnessArtifact.results | Where-Object { $_.status -notin @('pass', 'warn', 'error') }).Count -gt 0) {
                throw 'A freshness query failed; this is not an ordinary stale-data result. See sources.json.'
            }
            $status.freshness_counts = @($freshnessArtifact.results | Group-Object status | Select-Object Name, Count)
        }
    }
    $badTests = @($testArtifact.results | Where-Object { $_.status -ne 'pass' }).Count
    $staleSources = @($freshnessArtifact.results | Where-Object { $_.status -eq 'error' }).Count
    $expectedFreshnessExit = if ($staleSources -gt 0) { 1 } else { 0 }
    if ($status.steps[2].exit_code -ne $expectedFreshnessExit) { throw 'Freshness exit code disagrees with sources.json.' }
    if ($badTests -eq 0 -and $status.steps[1].exit_code -eq 0) {
        $status.status = if ($staleSources -gt 0) { 'stale' } else { 'passed' }
    } else {
        $status.status = 'failed'
    }
    $status.exit_code = if ($status.status -eq 'passed') { 0 } else { 1 }
} catch {
    $status.status = 'failed'
    $status.exit_code = 2
    $status.error = $_.Exception.Message
    Write-Warning $status.error
} finally {
    $status.finished_at_utc = [DateTime]::UtcNow.ToString('o')
    Save-Status
    Pop-Location
}
Write-Host "Source check: $($status.status); exit $($status.exit_code). Evidence: $OutputDirectory"
exit $status.exit_code

<#
.SYNOPSIS
Run the week-1 dbt baseline against an already-running Compose dbt service.
.EXAMPLE
.\scripts\verify_dbt_baseline.ps1 -OutputDirectory docs/evidence/tuan-week1-day1-2/baseline
.NOTES
Requires Docker Compose and the restored AdventureWorks2014 database.
Runs deps, debug, run and test in order; stops on failure. dbt run creates the
configured model relations. Logs and compiled artifacts stay outside the
tracked dbt/logs and dbt/target directories. No credentials are read or printed
by this script. dbt itself prints its normal connection diagnostics.
#>
[CmdletBinding()]
param(
    [string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$runId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $repoRoot "docs/evidence/tuan-week1-day1-2/$runId"
} elseif (-not [IO.Path]::IsPathRooted($OutputDirectory)) {
    $OutputDirectory = Join-Path $repoRoot $OutputDirectory
}
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
$statusPath = Join-Path $OutputDirectory 'baseline_status.json'
if (Test-Path -LiteralPath $statusPath) {
    throw "An existing baseline uses this directory. Choose a new OutputDirectory: $OutputDirectory"
}
$null = Get-Command docker -CommandType Application -ErrorAction Stop
$null = New-Item -ItemType Directory -Path $OutputDirectory -Force
$containerRoot = "/tmp/tuan-dbt-baseline-$runId"
$status = [ordered]@{
    run_id = $runId
    started_at_utc = [DateTime]::UtcNow.ToString('o')
    finished_at_utc = $null
    status = 'running'
    container_artifact_directory = $containerRoot
    steps = @()
}

function Save-BaselineStatus {
    $status | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $statusPath -Encoding UTF8
}

function Invoke-DockerLogged {
    param([string[]]$DockerArguments, [string]$LogPath)
    # Windows PowerShell represents native stderr as ErrorRecord objects.
    # Preserve that text, then determine success using Docker's actual exit code.
    $ErrorActionPreference = 'Continue'
    $PSNativeCommandUseErrorActionPreference = $false
    & docker @DockerArguments 2>&1 |
        ForEach-Object -ErrorAction Stop {
            $line = $_.ToString()
            Write-Host $line
            $line
        } |
        Set-Content -LiteralPath $LogPath -Encoding UTF8 -ErrorAction Stop
    return $LASTEXITCODE
}

Save-BaselineStatus
Push-Location -LiteralPath $repoRoot
try {
    $stepNumber = 0
    foreach ($dbtCommand in @('deps', 'debug', 'run', 'test')) {
        $stepNumber++
        $logName = '{0:00}_{1}.stdout.txt' -f $stepNumber, $dbtCommand
        $step = [ordered]@{
            command = "dbt $dbtCommand --profiles-dir /usr/app/dbt"
            started_at_utc = [DateTime]::UtcNow.ToString('o')
            finished_at_utc = $null
            exit_code = $null
            stdout_file = $logName
            artifact_copy_exit_code = $null
            artifact_validation = $null
            artifact_command = $null
            artifact_file = $null
        }
        $status.steps += $step
        Save-BaselineStatus
        Write-Host "Running dbt $dbtCommand; evidence: $OutputDirectory"
        $dockerArgs = @(
            'compose', 'exec', '-T',
            '-e', 'DBT_USE_COLORS=false',
            '-e', "DBT_LOG_PATH=$containerRoot/logs",
            '-e', "DBT_TARGET_PATH=$containerRoot/target",
            'dbt', 'dbt', $dbtCommand, '--profiles-dir', '/usr/app/dbt'
        )
        $step.exit_code = Invoke-DockerLogged -DockerArguments $dockerArgs -LogPath (Join-Path $OutputDirectory $logName)
        $step.finished_at_utc = [DateTime]::UtcNow.ToString('o')
        Save-BaselineStatus

        # Snapshot immediately: test would otherwise replace run's run_results.
        # Attempt collection even when dbt failed; retain the dbt exit code.
        if ($dbtCommand -in @('run', 'test')) {
            # A test that fails before writing artifacts can leave run's artifact
            # behind. Verify args.which before labeling a snapshot as test output.
            $unverifiedName = "$dbtCommand.run_results.unverified.json"
            $artifactPath = Join-Path $OutputDirectory $unverifiedName
            $step.artifact_copy_exit_code = Invoke-DockerLogged -DockerArguments @(
                'compose', 'cp', "dbt:$containerRoot/target/run_results.json", $artifactPath
            ) -LogPath (Join-Path $OutputDirectory "$dbtCommand.artifact_copy.txt")
            $step.artifact_validation = 'copy_failed'
            if ($step.artifact_copy_exit_code -eq 0) {
                $step.artifact_file = $unverifiedName
                try {
                    $runResults = Get-Content -LiteralPath $artifactPath -Raw -Encoding UTF8 | ConvertFrom-Json
                    $step.artifact_command = [string]$runResults.args.which
                    $step.artifact_validation = 'command_mismatch'
                    if ([string]::IsNullOrWhiteSpace($step.artifact_command)) {
                        $step.artifact_validation = 'missing_command_metadata'
                    } elseif ($step.artifact_command -eq $dbtCommand) {
                        $verifiedName = "$dbtCommand.run_results.json"
                        Move-Item -LiteralPath $artifactPath -Destination (Join-Path $OutputDirectory $verifiedName)
                        $step.artifact_file = $verifiedName
                        $step.artifact_validation = 'verified'
                    }
                } catch {
                    $step.artifact_validation = 'validation_failed'
                    $step.artifact_error = $_.Exception.Message
                }
            }
            Save-BaselineStatus
        }
        if ($step.exit_code -ne 0) {
            throw "dbt $dbtCommand failed with exit code $($step.exit_code). See $logName."
        }
        if ($null -ne $step.artifact_copy_exit_code -and $step.artifact_copy_exit_code -ne 0) {
            throw "dbt $dbtCommand succeeded, but collecting its run_results failed."
        }
        if ($null -ne $step.artifact_validation -and $step.artifact_validation -ne 'verified') {
            throw "dbt $dbtCommand succeeded, but its run_results could not be verified: $($step.artifact_validation)."
        }
    }

    # Persist only the small relation map. Keep the full manifest out of evidence.
    $temporaryManifest = Join-Path ([IO.Path]::GetTempPath()) "tuan-dbt-manifest-$runId.json"
    try {
        $status.manifest_copy_exit_code = Invoke-DockerLogged -DockerArguments @(
            'compose', 'cp', "dbt:$containerRoot/target/manifest.json", $temporaryManifest
        ) -LogPath (Join-Path $OutputDirectory 'manifest.artifact_copy.txt')
        Save-BaselineStatus
        if ($status.manifest_copy_exit_code -ne 0) {
            throw 'The baseline passed, but collecting the model relation map failed.'
        }
        $manifest = Get-Content -LiteralPath $temporaryManifest -Raw -Encoding UTF8 | ConvertFrom-Json
        @($manifest.nodes.PSObject.Properties.Value |
            Where-Object { $_.resource_type -eq 'model' } |
            Select-Object unique_id, database, schema, alias, relation_name) |
            ConvertTo-Json -Depth 4 |
            Set-Content -LiteralPath (Join-Path $OutputDirectory 'model_relations.json') -Encoding UTF8
    } finally {
        if (Test-Path -LiteralPath $temporaryManifest) {
            Remove-Item -LiteralPath $temporaryManifest -Force
        }
    }
    $status.status = 'passed'
} catch {
    $status.status = 'failed'
    $status.error = $_.Exception.Message
    throw
} finally {
    $status.finished_at_utc = [DateTime]::UtcNow.ToString('o')
    Save-BaselineStatus
    Pop-Location
}
Write-Host "Baseline passed. Evidence: $OutputDirectory"

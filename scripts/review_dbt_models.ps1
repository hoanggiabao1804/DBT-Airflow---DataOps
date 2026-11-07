<#
.SYNOPSIS
Run read-only SQL review against a successful, newly captured dbt baseline.
.EXAMPLE
.\scripts\review_dbt_models.ps1 -EvidenceDirectory docs/evidence/tuan-week1-day1-2/<run-id>
.NOTES
Requires the Compose sqlserver service and its existing SA_PASSWORD environment
variable. Credentials are expanded only inside the container, never in command
arguments or logs. Output is UTF-8 and contains aggregate counts, not personal
data. Exit code zero means queries completed; positive issue_count values are
review findings and do not cause sqlcmd to fail. Existing evidence is preserved.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$EvidenceDirectory
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not [IO.Path]::IsPathRooted($EvidenceDirectory)) {
    $EvidenceDirectory = Join-Path $repoRoot $EvidenceDirectory
}
$EvidenceDirectory = [IO.Path]::GetFullPath($EvidenceDirectory)
$baselinePath = Join-Path $EvidenceDirectory 'baseline_status.json'
$relationsPath = Join-Path $EvidenceDirectory 'model_relations.json'
$statusPath = Join-Path $EvidenceDirectory 'sql_review_status.json'
$stdoutPath = Join-Path $EvidenceDirectory 'sql_review.stdout.txt'
$copyLogPath = Join-Path $EvidenceDirectory 'sql_review.copy.txt'
foreach ($existingPath in @($statusPath, $stdoutPath, $copyLogPath)) {
    if (Test-Path -LiteralPath $existingPath) {
        throw "SQL review evidence already exists. Preserve it and use a new baseline directory: $existingPath"
    }
}

$baseline = Get-Content -LiteralPath $baselinePath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($baseline.status -ne 'passed') {
    throw 'EvidenceDirectory must contain a passed baseline_status.json from verify_dbt_baseline.ps1.'
}
# Windows PowerShell 5.1 emits a JSON array as one pipeline object. Assign it
# directly so an outer @() does not wrap the relation array a second time.
$relations = Get-Content -LiteralPath $relationsPath -Raw -Encoding UTF8 | ConvertFrom-Json
$expectedAliases = @(
    'brnz_customers', 'brnz_example', 'brnz_products', 'brnz_sales_orders',
    'slvr_customers', 'slvr_products', 'slvr_sales_orders',
    'gld_customer_metrics', 'gld_product_performance', 'gld_sales_summary'
)
if ($relations.Count -ne 10) {
    throw "Expected exactly 10 model relations, found $($relations.Count)."
}
foreach ($modelAlias in $expectedAliases) {
    if (@($relations | Where-Object { $_.alias -ceq $modelAlias }).Count -ne 1) {
        throw "Expected exactly one relation for model $modelAlias."
    }
}
if (@($relations | Where-Object { $_.database -ne 'AdventureWorks2014' }).Count -gt 0) {
    throw 'All model relations must belong to AdventureWorks2014.'
}

function Get-LayerSchema {
    param([string]$AliasPattern, [int]$ExpectedCount)
    $layerModels = @($relations | Where-Object { $_.alias -like $AliasPattern })
    $schemas = @($layerModels | Select-Object -ExpandProperty schema -Unique)
    if ($layerModels.Count -ne $ExpectedCount -or $schemas.Count -ne 1 -or
        $schemas[0] -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
        throw "Expected $ExpectedCount models with one valid schema for $AliasPattern."
    }
    return [string]$schemas[0]
}

$bronzeSchema = Get-LayerSchema -AliasPattern 'brnz_*' -ExpectedCount 4
$silverSchema = Get-LayerSchema -AliasPattern 'slvr_*' -ExpectedCount 3
$goldSchema = Get-LayerSchema -AliasPattern 'gld_*' -ExpectedCount 3
$sqlPath = Join-Path $PSScriptRoot 'sql/review_dbt_models.sql'
if (-not (Test-Path -LiteralPath $sqlPath -PathType Leaf)) {
    throw "SQL review script was not found: $sqlPath"
}
$null = Get-Command docker -CommandType Application -ErrorAction Stop
$containerSqlPath = '/tmp/review-dbt-models-' + [Guid]::NewGuid().ToString('N') + '.sql'
$status = [ordered]@{
    baseline_run_id = $baseline.run_id
    started_at_utc = [DateTime]::UtcNow.ToString('o')
    finished_at_utc = $null
    status = 'running'
    copy_exit_code = $null
    exit_code = $null
    database = 'AdventureWorks2014'
    bronze_schema = $bronzeSchema
    silver_schema = $silverSchema
    gold_schema = $goldSchema
    sql_file_sha256 = (Get-FileHash -LiteralPath $sqlPath -Algorithm SHA256).Hash
    stdout_file = 'sql_review.stdout.txt'
    result_interpretation = 'Completed means queries executed; positive issue_count values remain review findings.'
}

function Save-SqlReviewStatus {
    $status | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statusPath -Encoding UTF8
}

function Invoke-ReviewDocker {
    param([string[]]$DockerArguments, [string]$LogPath, [string]$InputText)
    $ErrorActionPreference = 'Continue'
    $PSNativeCommandUseErrorActionPreference = $false
    if ($PSBoundParameters.ContainsKey('InputText')) {
        $InputText | & docker @DockerArguments 2>&1 |
            ForEach-Object -ErrorAction Stop { $_.ToString() } |
            Set-Content -LiteralPath $LogPath -Encoding UTF8 -ErrorAction Stop
    } else {
        & docker @DockerArguments 2>&1 |
            ForEach-Object -ErrorAction Stop { $_.ToString() } |
            Set-Content -LiteralPath $LogPath -Encoding UTF8 -ErrorAction Stop
    }
    return $LASTEXITCODE
}

Save-SqlReviewStatus
Push-Location -LiteralPath $repoRoot
try {
    $status.copy_exit_code = Invoke-ReviewDocker -DockerArguments @(
        'compose', 'cp', $sqlPath, "sqlserver:$containerSqlPath"
    ) -LogPath $copyLogPath
    Save-SqlReviewStatus
    if ($status.copy_exit_code -ne 0) {
        throw "Copying SQL review to sqlserver failed with exit code $($status.copy_exit_code)."
    }

    # Literal stdin avoids PowerShell's native command-line quote escaping.
    # One line with a final comment also absorbs a trailing Windows CRLF.
    # Parameters are passed as arguments, never interpolated into shell code.
    $sqlShell = 'SQLCMDPASSWORD="${SA_PASSWORD:?SA_PASSWORD is missing}" exec /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -d AdventureWorks2014 -b -r 1 -f 65001 -W -w 65535 -s "|" -v "BronzeSchema=$1" "SilverSchema=$2" "GoldSchema=$3" -i "$4" # end'
    $status.exit_code = Invoke-ReviewDocker -DockerArguments @(
        'compose', 'exec', '-T', 'sqlserver', 'sh', '-s', '--',
        $bronzeSchema, $silverSchema, $goldSchema, $containerSqlPath
    ) -LogPath $stdoutPath -InputText $sqlShell
    if ($status.exit_code -ne 0) {
        throw "SQL review failed with exit code $($status.exit_code). See sql_review.stdout.txt."
    }
    $status.status = 'completed'
} catch {
    $status.status = 'failed'
    $status.error = $_.Exception.Message
    throw
} finally {
    $status.finished_at_utc = [DateTime]::UtcNow.ToString('o')
    Save-SqlReviewStatus
    Pop-Location
}
Write-Host "SQL review completed. Inspect issue_count findings in $stdoutPath"

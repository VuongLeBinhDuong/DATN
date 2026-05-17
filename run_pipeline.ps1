param(
    [Parameter(Position = 0)]
    [string]$StrayPositional = "",
    [switch]$SkipClean = $false,
    [switch]$SkipDockerClean = $false,
    [string]$DataDir = "",
    [switch]$CrawlViQa = $true,
    [switch]$CrawlReference = $false,
    [switch]$SkipCrawl = $false,
    [int]$QaMaxRowsPerSplit = 0,
    [switch]$UseOllama = $true,
    [string]$OllamaModel = "llama3.1:8b",
    [string]$OllamaHost = "http://localhost:11434",
    [switch]$RunSmokeTest = $false,
    [switch]$RunSmokeTestHybrid = $false,
    [switch]$CleanViQa = $true,
    [switch]$CleanReference = $true,
    [switch]$SkipCleanViQa = $false,
    [int]$CleanMaxRecords = 10000,
    [switch]$StopAfterClean = $false,
    [switch]$SkipIndex = $false,
    [string]$Neo4jComposeFile = "",
    [switch]$SkipNeo4j = $false,
    [switch]$SyncGraphragToNeo4j = $false,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs = @()
)

$skipFlagTokens = @($RemainingArgs) + @($args)
if ($StrayPositional -match '^--') {
    $skipFlagTokens += $StrayPositional
    $StrayPositional = ""
}
foreach ($tok in $skipFlagTokens) {
    switch -Regex ("$tok".Trim()) {
        '^(?i)-{1,2}SkipCrawl$' { $SkipCrawl = $true }
        '^(?i)-{1,2}SkipIndex$' { $SkipIndex = $true }
        '^(?i)-{1,2}SkipClean$' { $SkipClean = $true }
        '^(?i)-{1,2}SkipDockerClean$' { $SkipDockerClean = $true }
        '^(?i)-{1,2}SkipNeo4j$' { $SkipNeo4j = $true }
        '^(?i)-{1,2}SkipDataClean$' { $SkipClean = $true }
    }
}

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$RepoRoot = $PSScriptRoot
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python"
}
$defaultDataDir = Join-Path $RepoRoot "data"
if ($PSBoundParameters.ContainsKey("DataDir") -and $DataDir) {
    if (Test-Path -LiteralPath $DataDir -PathType Leaf) {
        Write-Warning ('DataDir la FILE (' + $DataDir + '), khong phai thu muc. Dung data/ mac dinh. Dung -DataDir "' + $defaultDataDir + '"')
        $DataDir = $defaultDataDir
    }
}
elseif ($StrayPositional) {
    if (Test-Path -LiteralPath $StrayPositional -PathType Leaf) {
        Write-Warning "Bo qua tham so vi tri (la file): $StrayPositional"
        $DataDir = $defaultDataDir
    }
    else {
        $DataDir = $StrayPositional
    }
}
else {
    $DataDir = $defaultDataDir
}
if (-not $Neo4jComposeFile) {
    $Neo4jComposeFile = Join-Path $RepoRoot "deploy\docker-compose.neo4j.yml"
}

$Neo4jComposeProject = "datn-neo4j"

function Get-DockerContainerNames {
    $raw = docker ps -a --format "{{.Names}}" 2>$null
    if ([string]::IsNullOrWhiteSpace($raw)) { return @() }
    return @($raw -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

function Run-Step {
    param(
        [string]$Name,
        [scriptblock]$Command
    )
    Write-Host ""
    Write-Host "=== $Name ===" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Step '$Name' that bai (exit code: $LASTEXITCODE)."
    }
}

function Test-OllamaServer {
    param([string]$BaseUrl)
    try {
        $null = Invoke-RestMethod -Method Get -Uri ($BaseUrl.TrimEnd("/") + "/api/tags")
        return $true
    }
    catch {
        return $false
    }
}

function Ensure-OllamaModel {
    param(
        [string]$BaseUrl,
        [string]$Model
    )

    $tags = Invoke-RestMethod -Method Get -Uri ($BaseUrl.TrimEnd("/") + "/api/tags")
    $names = @($tags.models | ForEach-Object { $_.name })
    if ($names -contains $Model) {
        Write-Host "Model Ollama da co: $Model" -ForegroundColor Green
        return
    }

    Write-Host "Model $Model chua co, dang pull..." -ForegroundColor Yellow
    $ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $ollamaCmd) {
        throw "Khong tim thay lenh 'ollama'. Cai Ollama hoac pull model thu cong truoc."
    }
    ollama pull $Model
}

function Write-SmokeChatInput {
    param([string[]]$PromptLines)
    $p = [System.IO.Path]::GetTempFileName()
    @($PromptLines + @("exit")) | Set-Content -LiteralPath $p -Encoding UTF8
    return $p
}

Run-Step "Kiem tra Docker" {
    docker version | Out-Null
    docker compose version | Out-Null
}

if (-not $SkipDockerClean) {
    Run-Step "Don dep Docker (Neo4j)" {
        $existing = Get-DockerContainerNames
        if ($existing -contains "datn-neo4j") {
            docker rm -f "datn-neo4j" 2>&1 | Out-Null
        }
        if (Test-Path -LiteralPath $Neo4jComposeFile) {
            docker-compose -p $Neo4jComposeProject -f $Neo4jComposeFile down --remove-orphans
        }
    }
}
else {
    Write-Host "Bo qua: don dep Docker (SkipDockerClean)." -ForegroundColor Yellow
}

if (-not $SkipNeo4j) {
    if (-not (Test-Path -LiteralPath $Neo4jComposeFile)) {
        Write-Warning "Neo4j: khong tim thay file compose: $Neo4jComposeFile"
    }
    else {
        Run-Step "Khoi dong Neo4j (7474 / 7687)" {
            docker-compose -p $Neo4jComposeProject -f $Neo4jComposeFile up -d
        }
    }
}
else {
    Write-Host "Bo qua: Neo4j (SkipNeo4j)." -ForegroundColor Yellow
}

if (-not $SkipCrawl -and $CrawlViQa) {
    Run-Step "Crawl QA tieng Viet (Hugging Face) -> data/medical_reference_vi_qa.json" {
        $qaCrawlArgs = @(
            (Join-Path $RepoRoot "scripts\crawl_reference_pages_vi.py"),
            "--output-dir", $DataDir
        )
        if ($QaMaxRowsPerSplit -gt 0) {
            $qaCrawlArgs += @("--qa-max-rows-per-split", $QaMaxRowsPerSplit)
        }
        & $PythonExe @qaCrawlArgs
    }
}
else {
    Write-Host "Bo qua: crawl QA VI." -ForegroundColor Yellow
}

Write-Host "Bo qua: crawl reference EN (tat mac dinh)." -ForegroundColor DarkGray

if (-not $SkipClean) {
    if ($CleanViQa) {
        Run-Step "Clean QA tieng Viet (medical_reference_vi_qa.json -> ghi de)" {
            $cleanArgs = @(
                (Join-Path $RepoRoot "scripts\clean_vi_qa_data.py"),
                "--input", (Join-Path $DataDir "medical_reference_vi_qa.json"),
                "--max-records", $CleanMaxRecords
            )
            & $PythonExe @cleanArgs
        }
    }
    else {
        Write-Host "Bo qua: clean QA VI." -ForegroundColor Yellow
    }
    if ($CleanReference) {
        Run-Step "Clean reference JSON (ghi de data/)" {
            & $PythonExe (Join-Path $RepoRoot "scripts\clean_reference_data.py") --data-dir $DataDir
        }
    }
    else {
        Write-Host "Bo qua: clean reference." -ForegroundColor Yellow
    }
}
else {
    Write-Host "Bo qua: clean data Python (SkipClean)." -ForegroundColor Yellow
}

Run-Step "Copy JSON da clean tu data/ -> graphrag/input" {
    $graphragInput = Join-Path $RepoRoot "graphrag\input"
    New-Item -ItemType Directory -Force -Path $graphragInput | Out-Null
    $src = Join-Path $DataDir "medical_reference_vi_qa.json"
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $graphragInput "medical_reference_vi_qa.json") -Force
        Write-Host "Da copy: medical_reference_vi_qa.json -> graphrag/input/medical_reference_vi_qa.json" -ForegroundColor Green
    }
    else {
        Write-Host "[WARN] Khong co file de copy: $src" -ForegroundColor Yellow
    }
}

if ($StopAfterClean) {
    Write-Host ""
    Write-Host "=== HOAN TAT BUOC 1: CRAWL + CLEAN ===" -ForegroundColor Green
    Write-Host "File output: $DataDir\medical_reference_vi_qa.json" -ForegroundColor Green
    Write-Host "Da copy sang: graphrag\input\medical_reference_vi_qa.json" -ForegroundColor Green
    Write-Host ""
    Write-Host "De chay tiep buoc 2 (index), bo tham so -StopAfterClean" -ForegroundColor Yellow
    return 0
}

if ($SyncGraphragToNeo4j) {
    $entitiesCandidates = @(
        (Join-Path $RepoRoot "graphrag\update_output\entities.parquet"),
        (Join-Path $RepoRoot "graphrag\output\entities.parquet")
    )
    $graphragDataDir = $null
    foreach ($ep in $entitiesCandidates) {
        if (Test-Path -LiteralPath $ep) {
            $graphragDataDir = Split-Path -Parent $ep
            break
        }
    }
    if ($graphragDataDir) {
        Run-Step "Import GraphRAG parquet -> Neo4j (scripts/graphrag_parquet_to_neo4j.py)" {
            & $PythonExe (Join-Path $RepoRoot "scripts\graphrag_parquet_to_neo4j.py") --output-dir $graphragDataDir
        }
    }
    else {
        Write-Host ""
        Write-Host "[WARN] SyncGraphragToNeo4j: chua co entities.parquet. Chay: python -m graphrag index -r graphrag -m standard" -ForegroundColor Yellow
    }
}

if ($UseOllama) {
    # Native Ollama only (no Docker)
    Run-Step "Kiem tra Ollama native server" {
        if (-not (Test-OllamaServer -BaseUrl $OllamaHost)) {
            throw "Khong ket noi duoc Ollama tai $OllamaHost. Hay chay 'ollama serve' truoc."
        }
        Write-Host "   Ollama Native: OK" -ForegroundColor Green
    }

    Run-Step "Kiem tra/Pull model Ollama" {
        Ensure-OllamaModel -BaseUrl $OllamaHost -Model $OllamaModel
    }
}

if ($RunSmokeTest) {
    $smokeHybridVi = "Toi sot 38,5 do C, dau dau va moi nguoi da 2 ngay - co the do dau, nen lam gi tai nha va khi nao phai di kham ngay?"

    if ($RunSmokeTestHybrid) {
        Run-Step "Smoke test chat (GraphRAG Web/API production)" {
            $tmp = Write-SmokeChatInput -PromptLines @($smokeHybridVi)
            try {
                if ($UseOllama) {
                    Get-Content -LiteralPath $tmp | & $PythonExe -m llm_pipeline.chat --use-ollama --ollama-model $OllamaModel --ollama-host $OllamaHost
                }
                else {
                    Get-Content -LiteralPath $tmp | & $PythonExe -m llm_pipeline.chat
                }
            }
            finally {
                Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue
            }
        }
    }
}

Write-Host ""
Write-Host "Hoan tat pipeline: crawl/clean -> GraphRAG input." -ForegroundColor Green
if (-not $SkipNeo4j -or $SyncGraphragToNeo4j) {
    Write-Host ('Neo4j: -SkipNeo4j de tat. Import parquet: -SyncGraphragToNeo4j. File: "' + $Neo4jComposeFile + '"') -ForegroundColor DarkGray
}
Write-Host "Chat GraphRAG (giong production):" -ForegroundColor Yellow
if ($UseOllama) {
    Write-Host ('  python -m llm_pipeline.chat --use-ollama --ollama-model ' + $OllamaModel + ' --ollama-host ' + $OllamaHost)
}
else {
    Write-Host "  python -m llm_pipeline.chat"
}

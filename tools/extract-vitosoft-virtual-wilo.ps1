param(
    [string]$OutputDir = "",
    [string]$Device = "VDensHO1"
)

$ErrorActionPreference = "Stop"

function Find-VitosoftFile {
    param(
        [string[]]$Roots,
        [string]$FileName,
        [string[]]$PreferredRelativePaths
    )

    foreach ($root in $Roots) {
        if (-not $root -or -not (Test-Path -LiteralPath $root)) {
            continue
        }

        foreach ($relative in $PreferredRelativePaths) {
            $candidate = Join-Path $root $relative
            if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                return (Get-Item -LiteralPath $candidate)
            }
        }
    }

    foreach ($root in $Roots) {
        if (-not $root -or -not (Test-Path -LiteralPath $root)) {
            continue
        }

        $found = Get-ChildItem -LiteralPath $root -Filter $FileName -File -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($found) {
            return $found
        }
    }

    return $null
}

function Get-PythonCommand {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @{
            Exe = $py.Source
            Prefix = @("-3")
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @{
            Exe = $python.Source
            Prefix = @()
        }
    }

    $python3 = Get-Command python3 -ErrorAction SilentlyContinue
    if ($python3) {
        return @{
            Exe = $python3.Source
            Prefix = @()
        }
    }

    throw "Python 3 not found. Install Python 3 or make py/python available in PATH."
}

$roots = @()
if ($env:ProgramFiles) {
    $roots += (Join-Path $env:ProgramFiles "Viessmann Vitosoft 300 SID1\ServiceTool")
}
$programFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
if ($programFilesX86) {
    $roots += (Join-Path $programFilesX86 "Viessmann Vitosoft 300 SID1\ServiceTool")
}
$roots = $roots | Select-Object -Unique

Write-Host "Searching Vitosoft production metadata..." -ForegroundColor Cyan

$dp = Find-VitosoftFile -Roots $roots -FileName "DPDefinitions.xml" -PreferredRelativePaths @(
    "Support\DP\DPDefinitions.xml",
    "MobileClient\Config\DPDefinitions.xml"
)
$event = Find-VitosoftFile -Roots $roots -FileName "ecnEventType.xml" -PreferredRelativePaths @(
    "MobileClient\Config\ecnEventType.xml"
)
$textDe = Find-VitosoftFile -Roots $roots -FileName "Textresource_de.xml" -PreferredRelativePaths @(
    "Web\XmlDocuments\Textresource_de.xml",
    "MobileClient\Config\Textresource_de.xml"
)

if (-not $dp) {
    throw "DPDefinitions.xml not found below the Vitosoft ServiceTool directories."
}
if (-not $event) {
    throw "ecnEventType.xml not found below the Vitosoft ServiceTool directories."
}

if (-not $OutputDir) {
    $desktop = [Environment]::GetFolderPath("Desktop")
    $OutputDir = Join-Path $desktop ("vitosoft-wilo-extract-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$localExtractor = Join-Path $PSScriptRoot "extract-vitosoft-project-data.py"
if (Test-Path -LiteralPath $localExtractor -PathType Leaf) {
    $extractor = $localExtractor
    Write-Host "Using extractor from repository checkout:" -ForegroundColor Cyan
    Write-Host "  $extractor"
}
else {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $extractor = Join-Path $OutputDir "extract-vitosoft-project-data.py"
    $extractorUrl = "https://raw.githubusercontent.com/SaulGoodman1337/optolink/main/tools/extract-vitosoft-project-data.py"
    Write-Host "Downloading current extractor from repository..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $extractorUrl -OutFile $extractor
}

Write-Host ""
Write-Host "Selected source files:" -ForegroundColor Cyan
Write-Host "  DPDefinitions.xml : $($dp.FullName)"
Write-Host "  ecnEventType.xml  : $($event.FullName)"
if ($textDe) {
    Write-Host "  Textresource_de   : $($textDe.FullName)"
}
else {
    Write-Warning "Textresource_de.xml not found. Extraction still works, but German labels may be missing."
}

$sourceInfoPath = Join-Path $OutputDir "source-files.txt"
$sourceInfo = @()
foreach ($file in @($dp, $event, $textDe)) {
    if (-not $file) {
        continue
    }
    $hash = Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256
    $sourceInfo += ("{0}`n  Path: {1}`n  Size: {2}`n  SHA256: {3}`n" -f
        $file.Name, $file.FullName, $file.Length, $hash.Hash.ToLowerInvariant())
}
$sourceInfo | Set-Content -LiteralPath $sourceInfoPath -Encoding UTF8

$python = Get-PythonCommand
$pyArgs = @()
$pyArgs += $python.Prefix
$pyArgs += @(
    $extractor,
    "--dp-definitions", $dp.FullName,
    "--event-types", $event.FullName,
    "--device", $Device,
    "--out-dir", $OutputDir,
    "--include-global-wilo"
)
if ($textDe) {
    $pyArgs += @("--textresource-de", $textDe.FullName)
}

Write-Host ""
Write-Host "Running extractor..." -ForegroundColor Cyan
& $python.Exe @pyArgs
if ($LASTEXITCODE -ne 0) {
    throw "Extractor failed with exit code $LASTEXITCODE"
}

$summary = Join-Path $OutputDir ($Device.ToLowerInvariant() + "-extract-summary.json")
$wiloCsv = Join-Path $OutputDir "virtual-wilo-events.csv"

Write-Host ""
Write-Host "=== Extraction summary ===" -ForegroundColor Green
if (Test-Path -LiteralPath $summary) {
    Get-Content -LiteralPath $summary
}

Write-Host ""
Write-Host "=== Virtual-WILO rows ===" -ForegroundColor Green
if (Test-Path -LiteralPath $wiloCsv) {
    $rows = @(Import-Csv -LiteralPath $wiloCsv)
    Write-Host ("Rows: {0}" -f $rows.Count)
    if ($rows.Count -gt 0) {
        $rows |
            Select-Object event_id,name_de,token,address,fc_read,fc_write,prefix_read,prefix_write,block_length,devices |
            Format-Table -AutoSize
    }
}

$zipPath = $OutputDir.TrimEnd("\") + ".zip"
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -Path (Join-Path $OutputDir "*") -DestinationPath $zipPath -Force

Write-Host ""
Write-Host "Finished." -ForegroundColor Green
Write-Host "Output directory:"
Write-Host "  $OutputDir"
Write-Host "ZIP to send back:"
Write-Host "  $zipPath"
Write-Host ""
Write-Host "Please send the ZIP or, at minimum:"
Write-Host "  source-files.txt"
Write-Host "  $($Device.ToLowerInvariant())-extract-summary.json"
Write-Host "  virtual-wilo-events.csv"

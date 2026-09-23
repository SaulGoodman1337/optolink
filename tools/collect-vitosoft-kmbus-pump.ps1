param(
    [string]$Root = "",
    [string]$OutputDir = "",
    [int]$MaxTextHitsPerFile = 500,
    [int]$MaxBinaryMB = 80,
    [int]$ProgressSeconds = 5
)

$ErrorActionPreference = "Stop"

function Get-VitosoftRoots {
    param([string]$ExplicitRoot)

    $roots = New-Object System.Collections.Generic.List[string]

    if ($ExplicitRoot) {
        if (-not (Test-Path -LiteralPath $ExplicitRoot -PathType Container)) {
            throw "Vitosoft root does not exist: $ExplicitRoot"
        }
        $roots.Add((Resolve-Path -LiteralPath $ExplicitRoot).Path)
        return $roots
    }

    $programFilesCandidates = @(
        $env:ProgramFiles,
        [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
    ) | Where-Object { $_ } | Select-Object -Unique

    foreach ($pf in $programFilesCandidates) {
        foreach ($relative in @(
            "Viessmann Vitosoft 300 SID1\ServiceTool",
            "Viessmann\Vitosoft 300 SID1\ServiceTool",
            "Vitosoft 300 SID1\ServiceTool"
        )) {
            $candidate = Join-Path $pf $relative
            if (Test-Path -LiteralPath $candidate -PathType Container) {
                $roots.Add((Resolve-Path -LiteralPath $candidate).Path)
            }
        }
    }

    if ($roots.Count -eq 0) {
        foreach ($pf in $programFilesCandidates) {
            if (-not (Test-Path -LiteralPath $pf -PathType Container)) {
                continue
            }
            Get-ChildItem -LiteralPath $pf -Directory -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -match "Vitosoft|Viessmann" } |
                ForEach-Object {
                    $candidate = $_.FullName
                    if (Test-Path -LiteralPath $candidate -PathType Container) {
                        $roots.Add($candidate)
                    }
                }
        }
    }

    return @($roots | Select-Object -Unique)
}

function Get-RelativePathCompat {
    param(
        [string]$Base,
        [string]$Path
    )
    try {
        return [IO.Path]::GetRelativePath($Base, $Path)
    }
    catch {
        if ($Path.StartsWith($Base, [StringComparison]::OrdinalIgnoreCase)) {
            return $Path.Substring($Base.Length).TrimStart("\")
        }
        return $Path
    }
}

function Get-KeywordMatches {
    param(
        [string]$Text,
        [string[]]$Terms
    )

    $matches = New-Object System.Collections.Generic.List[string]
    foreach ($term in $Terms) {
        if ($Text.IndexOf($term, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            $matches.Add($term)
        }
    }
    return @($matches)
}

function Get-ContextSnippet {
    param(
        [string]$Text,
        [string]$Term,
        [int]$Radius = 160
    )

    $idx = $Text.IndexOf($Term, [StringComparison]::OrdinalIgnoreCase)
    if ($idx -lt 0) {
        return ""
    }

    $start = [Math]::Max(0, $idx - $Radius)
    $length = [Math]::Min($Text.Length - $start, ($Radius * 2) + $Term.Length)
    return ($Text.Substring($start, $length) -replace "[\r\n\t]+", " ")
}

$textTerms = @(
    "KMBUS",
    "KM-BUS",
    "KM Bus",
    "KM_Bus",
    "KM_Error_PumpeIntern",
    "SWIndex_IntPumpe",
    "K30_KennungIntPumpeKM",
    "KE5_KonfiKennung_D_PumpeA1M1_KM",
    "PumpeIntern",
    "IntPumpe",
    "Interne Pumpe",
    "Interne Umwaelzpumpe",
    "Interne Umwälzpumpe",
    "PumpeA1",
    "PumpeA1M1",
    "DrehzahlIntPumpe",
    "InternePumpeDrehzahl",
    "InternePumpeDrehzahl_res",
    "DigitalAusgang_InternePumpe",
    "sysblock_KMBus_LonMemberList",
    "KMBusEquipment",
    "KBUS_MEMBERLIST_READ",
    "KBUS_MEMBERLIST_WRITE",
    "KMBUS_RAM_READ",
    "KMBUS_EEPROM_READ",
    "BusHandlerType",
    "OptolinkHandler",
    "0x0A3C",
    "0x0A54",
    "0x0A35",
    "0x27E5",
    "0x7660",
    "0x7663",
    "0x5730",
    "0x5731",
    "Grundfos",
    "UPM3",
    "UPM",
    "G-HE",
    "GHE"
)

$binaryTerms = @(
    "KMBUS",
    "KM-BUS",
    "KM Bus",
    "KM_Error_PumpeIntern",
    "SWIndex_IntPumpe",
    "K30_KennungIntPumpeKM",
    "KE5_KonfiKennung_D_PumpeA1M1_KM",
    "PumpeIntern",
    "IntPumpe",
    "Interne Pumpe",
    "DrehzahlIntPumpe",
    "InternePumpeDrehzahl",
    "InternePumpeDrehzahl_res",
    "DigitalAusgang_InternePumpe",
    "sysblock_KMBus_LonMemberList",
    "KMBusEquipment",
    "KBUS_MEMBERLIST_READ",
    "KBUS_MEMBERLIST_WRITE",
    "KMBUS_RAM_READ",
    "KMBUS_EEPROM_READ",
    "BusHandlerType",
    "OptolinkHandler",
    "Grundfos",
    "UPM3",
    "G-HE"
)

$textExtensions = @(
    ".xml", ".xsd", ".config", ".ini", ".csv", ".txt", ".md",
    ".json", ".yaml", ".yml", ".ps1", ".py", ".cs", ".vb",
    ".js", ".ts", ".sql", ".properties"
)

$priorityTerms = @(
    "KM_Error_PumpeIntern",
    "SWIndex_IntPumpe",
    "K30_KennungIntPumpeKM",
    "KE5_KonfiKennung_D_PumpeA1M1_KM",
    "DrehzahlIntPumpe",
    "InternePumpeDrehzahl",
    "InternePumpeDrehzahl_res",
    "DigitalAusgang_InternePumpe",
    "sysblock_KMBus_LonMemberList",
    "KMBusEquipment",
    "KBUS_MEMBERLIST_READ",
    "KBUS_MEMBERLIST_WRITE",
    "KMBUS_RAM_READ",
    "KMBUS_EEPROM_READ",
    "BusHandlerType",
    "OptolinkHandler",
    "0x0A3C",
    "0x0A54",
    "0x0A35",
    "0x27E5",
    "0x7660",
    "0x7663",
    "0x5730",
    "0x5731",
    "Grundfos",
    "UPM3",
    "G-HE"
)

$binaryExtensions = @(".exe", ".dll")

$regexOptions = [Text.RegularExpressions.RegexOptions]::IgnoreCase -bor
    [Text.RegularExpressions.RegexOptions]::CultureInvariant
$textPattern = (($textTerms | ForEach-Object { [regex]::Escape($_) }) -join "|")
$binaryPattern = (($binaryTerms | ForEach-Object { [regex]::Escape($_) }) -join "|")
$textSearchRegex = [Text.RegularExpressions.Regex]::new($textPattern, $regexOptions)
$binarySearchRegex = [Text.RegularExpressions.Regex]::new($binaryPattern, $regexOptions)
$priorityPattern = (($priorityTerms | ForEach-Object { [regex]::Escape($_) }) -join "|")
$prioritySearchRegex = [Text.RegularExpressions.Regex]::new($priorityPattern, $regexOptions)

$roots = @(Get-VitosoftRoots -ExplicitRoot $Root)
if ($roots.Count -eq 0) {
    throw "No Vitosoft installation root found. Re-run with -Root 'C:\path\to\ServiceTool'."
}

if (-not $OutputDir) {
    $desktop = [Environment]::GetFolderPath("Desktop")
    $OutputDir = Join-Path $desktop ("vitosoft-kmbus-pump-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$OutputDir = (Resolve-Path -LiteralPath $OutputDir).Path

Write-Host "Vitosoft KM-Bus / internal-pump collector" -ForegroundColor Cyan
Write-Host "Output: $OutputDir"
Write-Host ""
Write-Host "Roots:" -ForegroundColor Cyan
$roots | ForEach-Object { Write-Host "  $_" }

$inventory = New-Object System.Collections.Generic.List[object]
$textHits = New-Object System.Collections.Generic.List[object]
$binaryHits = New-Object System.Collections.Generic.List[object]
$sourceHashes = New-Object System.Collections.Generic.List[object]
$hitSummary = New-Object System.Collections.Generic.List[object]

foreach ($rootPath in $roots) {
    Write-Host ""
    Write-Host "Enumerating files below $rootPath ..." -ForegroundColor Cyan

    $files = @(Get-ChildItem -LiteralPath $rootPath -File -Recurse -ErrorAction SilentlyContinue)
    $fileCount = $files.Count
    Write-Host ("Found {0} files. Starting content scan..." -f $fileCount) -ForegroundColor Cyan

    $scanWatch = [Diagnostics.Stopwatch]::StartNew()
    $nextOverallProgress = [double]$ProgressSeconds
    $fileIndex = 0

    foreach ($file in $files) {
        $fileIndex++
        $relative = Get-RelativePathCompat -Base $rootPath -Path $file.FullName
        $ext = $file.Extension.ToLowerInvariant()

        if ($scanWatch.Elapsed.TotalSeconds -ge $nextOverallProgress) {
            $overallPercent = if ($fileCount -gt 0) {
                [Math]::Round(($fileIndex / [double]$fileCount) * 100, 1)
            }
            else {
                100
            }
            Write-Host (
                "[{0}/{1} {2,5}%] {3} | text hits {4} | binary hits {5}" -f
                $fileIndex, $fileCount, $overallPercent, $relative,
                $textHits.Count, $binaryHits.Count
            )
            $nextOverallProgress = $scanWatch.Elapsed.TotalSeconds + $ProgressSeconds
        }

        $nameMatches = if ($textSearchRegex.IsMatch($relative)) {
            @(Get-KeywordMatches -Text $relative -Terms $textTerms)
        }
        else {
            @()
        }

        $inventory.Add([pscustomobject]@{
            Root = $rootPath
            RelativePath = $relative
            Extension = $ext
            SizeBytes = $file.Length
            LastWriteUtc = $file.LastWriteTimeUtc.ToString("o")
            NameKeywordHits = ($nameMatches -join ";")
        })

        if ($file.Name -in @("DPDefinitions.xml", "ecnEventType.xml", "Textresource_de.xml")) {
            try {
                Write-Host ("  Hashing core metadata: {0} ({1:N1} MB)" -f $relative, ($file.Length / 1MB))
                $hash = Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256
                $sourceHashes.Add([pscustomobject]@{
                    File = $file.Name
                    Path = $file.FullName
                    SizeBytes = $file.Length
                    SHA256 = $hash.Hash.ToLowerInvariant()
                })
            }
            catch {
                Write-Warning "Could not hash $($file.FullName): $($_.Exception.Message)"
            }
        }

        if ($textExtensions -contains $ext) {
            $hitCount = 0
            $storedHitCount = 0
            $limitNoticeStored = $false
            $reader = $null
            try {
                if ($file.Length -ge 10MB) {
                    Write-Host ("  Scanning large text: {0} ({1:N1} MB)" -f $relative, ($file.Length / 1MB))
                }

                $reader = New-Object IO.StreamReader($file.FullName, $true)
                $lineNo = 0
                $nextFileProgress = $scanWatch.Elapsed.TotalSeconds + $ProgressSeconds

                while (-not $reader.EndOfStream) {
                    $line = $reader.ReadLine()
                    $lineNo++

                    if ($scanWatch.Elapsed.TotalSeconds -ge $nextFileProgress) {
                        if ($file.Length -gt 0) {
                            $filePercent = [Math]::Min(
                                100,
                                [Math]::Round(($reader.BaseStream.Position / [double]$file.Length) * 100, 1)
                            )
                        }
                        else {
                            $filePercent = 100
                        }
                        Write-Host (
                            "    [TEXT {0,5}%] {1} | line {2} | file hits {3} | total hits {4}" -f
                            $filePercent, $relative, $lineNo, $hitCount, $textHits.Count
                        )
                        $nextFileProgress = $scanWatch.Elapsed.TotalSeconds + $ProgressSeconds
                        $nextOverallProgress = $nextFileProgress
                    }

                    if (-not $textSearchRegex.IsMatch($line)) {
                        continue
                    }

                    $matchedTerms = @(Get-KeywordMatches -Text $line -Terms $textTerms)
                    if ($matchedTerms.Count -eq 0) {
                        continue
                    }

                    $hitCount++
                    $isPriority = $prioritySearchRegex.IsMatch($line)

                    if (($storedHitCount -lt $MaxTextHitsPerFile) -or $isPriority) {
                        $textHits.Add([pscustomobject]@{
                            Root = $rootPath
                            RelativePath = $relative
                            Line = $lineNo
                            Keywords = ($matchedTerms -join ";")
                            Text = Get-ContextSnippet -Text $line -Term $matchedTerms[0] -Radius 1400
                        })
                        $storedHitCount++
                    }
                    elseif (-not $limitNoticeStored) {
                        $textHits.Add([pscustomobject]@{
                            Root = $rootPath
                            RelativePath = $relative
                            Line = 0
                            Keywords = "<limit>"
                            Text = "Generic stored-hit limit reached: $MaxTextHitsPerFile; scanning continued and priority hits were still retained."
                        })
                        Write-Host ("    Generic hit storage limit reached for {0}: {1}; scan continues" -f $relative, $MaxTextHitsPerFile)
                        $limitNoticeStored = $true
                    }
                }
            }
            catch {
                $textHits.Add([pscustomobject]@{
                    Root = $rootPath
                    RelativePath = $relative
                    Line = 0
                    Keywords = "<read-error>"
                    Text = $_.Exception.Message
                })
            }
            finally {
                if ($null -ne $reader) {
                    $reader.Dispose()
                }
                $hitSummary.Add([pscustomobject]@{
                    Root = $rootPath
                    RelativePath = $relative
                    TotalMatches = $hitCount
                    StoredMatches = $storedHitCount
                    GenericLimitReached = ($hitCount -gt $MaxTextHitsPerFile)
                })
            }
        }
        elseif (($binaryExtensions -contains $ext) -and ($file.Length -le ($MaxBinaryMB * 1MB))) {
            try {
                if ($file.Length -ge 10MB) {
                    Write-Host ("  Scanning binary strings: {0} ({1:N1} MB)" -f $relative, ($file.Length / 1MB))
                }

                $bytes = [IO.File]::ReadAllBytes($file.FullName)

                $ascii = [Text.Encoding]::ASCII.GetString($bytes)
                if ($binarySearchRegex.IsMatch($ascii)) {
                    foreach ($term in $binaryTerms) {
                        if ($ascii.IndexOf($term, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
                            $binaryHits.Add([pscustomobject]@{
                                Root = $rootPath
                                RelativePath = $relative
                                Encoding = "ASCII"
                                Keyword = $term
                                Context = Get-ContextSnippet -Text $ascii -Term $term
                            })
                        }
                    }
                }

                $unicode = [Text.Encoding]::Unicode.GetString($bytes)
                if ($binarySearchRegex.IsMatch($unicode)) {
                    foreach ($term in $binaryTerms) {
                        if ($unicode.IndexOf($term, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
                            $binaryHits.Add([pscustomobject]@{
                                Root = $rootPath
                                RelativePath = $relative
                                Encoding = "UTF-16LE"
                                Keyword = $term
                                Context = Get-ContextSnippet -Text $unicode -Term $term
                            })
                        }
                    }
                }
            }
            catch {
                $binaryHits.Add([pscustomobject]@{
                    Root = $rootPath
                    RelativePath = $relative
                    Encoding = "<read-error>"
                    Keyword = ""
                    Context = $_.Exception.Message
                })
            }
        }
    }

    $scanWatch.Stop()
    Write-Host (
        "Completed {0} files in {1:N1}s | text hits {2} | binary hits {3}" -f
        $fileCount, $scanWatch.Elapsed.TotalSeconds, $textHits.Count, $binaryHits.Count
    ) -ForegroundColor Green
}

$inventoryPath = Join-Path $OutputDir "file-inventory.csv"
$textHitsPath = Join-Path $OutputDir "text-hits.csv"
$binaryHitsPath = Join-Path $OutputDir "binary-string-hits.csv"
$hashesPath = Join-Path $OutputDir "source-hashes.csv"
$hitSummaryPath = Join-Path $OutputDir "hit-summary.csv"

$inventory | Sort-Object Root, RelativePath | Export-Csv -LiteralPath $inventoryPath -NoTypeInformation -Encoding UTF8

if ($textHits.Count -gt 0) {
    $textHits | Sort-Object Root, RelativePath, Line | Export-Csv -LiteralPath $textHitsPath -NoTypeInformation -Encoding UTF8
}
else {
    '"Root","RelativePath","Line","Keywords","Text"' | Set-Content -LiteralPath $textHitsPath -Encoding UTF8
}

if ($binaryHits.Count -gt 0) {
    $binaryHits | Sort-Object Root, RelativePath, Encoding, Keyword | Export-Csv -LiteralPath $binaryHitsPath -NoTypeInformation -Encoding UTF8
}
else {
    '"Root","RelativePath","Encoding","Keyword","Context"' | Set-Content -LiteralPath $binaryHitsPath -Encoding UTF8
}

if ($sourceHashes.Count -gt 0) {
    $sourceHashes | Sort-Object Path | Export-Csv -LiteralPath $hashesPath -NoTypeInformation -Encoding UTF8
}
else {
    '"File","Path","SizeBytes","SHA256"' | Set-Content -LiteralPath $hashesPath -Encoding UTF8
}

if ($hitSummary.Count -gt 0) {
    $hitSummary | Sort-Object TotalMatches -Descending | Export-Csv -LiteralPath $hitSummaryPath -NoTypeInformation -Encoding UTF8
}
else {
    '"Root","RelativePath","TotalMatches","StoredMatches","GenericLimitReached"' | Set-Content -LiteralPath $hitSummaryPath -Encoding UTF8
}

$interestingTextFiles = @(
    $textHits |
        Where-Object { $_.Line -gt 0 } |
        Select-Object -ExpandProperty RelativePath -Unique
)

$interestingBinaryFiles = @(
    $binaryHits |
        Where-Object { $_.Encoding -notlike "<*" } |
        Select-Object -ExpandProperty RelativePath -Unique
)

$summary = [ordered]@{
    generated_utc = (Get-Date).ToUniversalTime().ToString("o")
    roots = @($roots)
    keywords = @($textTerms)
    file_count = $inventory.Count
    text_hit_count = $textHits.Count
    text_files_with_hits = $interestingTextFiles.Count
    binary_string_hit_count = $binaryHits.Count
    binary_files_with_hits = $interestingBinaryFiles.Count
    max_text_hits_per_file = $MaxTextHitsPerFile
    max_binary_mb = $MaxBinaryMB
    progress_seconds = $ProgressSeconds
    notes = @(
        "Read-only collector. It does not modify Vitosoft or the heating controller.",
        "Binary files are not copied; only keyword hit metadata/context is recorded.",
        "Large text/XML files are searched line-by-line; matching lines are capped per file.",
        "Numeric address hits are discovery clues only and can contain false positives outside Vitosoft datapoint metadata."
    )
}
$summaryPath = Join-Path $OutputDir "summary.json"
$summary | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $summaryPath -Encoding UTF8

$readme = @"
Vitosoft KM-Bus / internal-pump research dump
=============================================

This archive was generated read-only.

Files:
  summary.json
  source-hashes.csv
  file-inventory.csv
  text-hits.csv
  binary-string-hits.csv
  hit-summary.csv

Research target:
  Viessmann VDensHO1 / WB2A internal Grundfos G-HE / UPM3 KM-Bus pump.

Priority symbols/addresses:
  K30_KennungIntPumpeKM
  SWIndex_IntPumpe
  KM_Error_PumpeIntern
  KE5_KonfiKennung_D_PumpeA1M1_KM
  InternePumpeDrehzahl
  DigitalAusgang_InternePumpe
  0x5730 / 0x5731
  0x0A54 / 0x0A35
  0x27E5
  0x7660 / 0x7663

Important:
  0x27E5 describes a separate KM-BUS heating-circuit pump A1.
  It is not the installed internal pump and must not be enabled merely because
  the internal G-HE pump itself communicates by KM-Bus.

No executable or DLL is copied into this archive. For binaries, only filename,
encoding, matched keyword and a short local string context are included.
"@
$readme | Set-Content -LiteralPath (Join-Path $OutputDir "README.txt") -Encoding UTF8

Write-Host ""
Write-Host "=== Collector summary ===" -ForegroundColor Green
Write-Host ("Files inventoried:           {0}" -f $inventory.Count)
Write-Host ("Text hit rows:               {0}" -f $textHits.Count)
Write-Host ("Text files with hits:        {0}" -f $interestingTextFiles.Count)
Write-Host ("Binary string hit rows:      {0}" -f $binaryHits.Count)
Write-Host ("Binary files with hits:      {0}" -f $interestingBinaryFiles.Count)

if ($interestingTextFiles.Count -gt 0) {
    Write-Host ""
    Write-Host "Top text files with relevant hits:" -ForegroundColor Cyan
    $textHits |
        Where-Object { $_.Line -gt 0 } |
        Group-Object RelativePath |
        Sort-Object Count -Descending |
        Select-Object -First 20 |
        ForEach-Object { Write-Host ("  {0,5}  {1}" -f $_.Count, $_.Name) }
}

if ($interestingBinaryFiles.Count -gt 0) {
    Write-Host ""
    Write-Host "Binary files with relevant embedded strings:" -ForegroundColor Cyan
    $interestingBinaryFiles | Select-Object -First 40 | ForEach-Object { Write-Host "  $_" }
}

$zipPath = $OutputDir + ".zip"
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -Path (Join-Path $OutputDir "*") -DestinationPath $zipPath -Force

Write-Host ""
Write-Host "Finished." -ForegroundColor Green
Write-Host "ZIP to send back:"
Write-Host "  $zipPath"

param(
  [string]$Root = "",
  [string]$OutputDir = "",
  [string]$Device = "VDensHO1",
  [string]$DeviceIdHex = "20C2",
  [int]$ProgressSeconds = 5,
  [int]$MaxSqlRowsPerTable = 0,
  [switch]$SkipRawTree,
  [switch]$SkipSql,
  [switch]$SkipRegistry,
  [switch]$SkipToolDumps,
  [switch]$CreateArchive
)

$ErrorActionPreference = "Stop"

function Find-VitosoftRoot {
  param([string]$Explicit)
  if ($Explicit) {
    if (-not (Test-Path -LiteralPath $Explicit -PathType Container)) {
      throw "Vitosoft root not found: $Explicit"
    }
    return (Resolve-Path -LiteralPath $Explicit).Path
  }

  $bases = @(
    $env:ProgramFiles,
    [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
  ) | Where-Object { $_ }

  foreach ($base in $bases) {
    foreach ($rel in @(
      "Viessmann Vitosoft 300 SID1\ServiceTool",
      "Viessmann\Vitosoft 300 SID1\ServiceTool",
      "Vitosoft 300 SID1\ServiceTool"
    )) {
      $candidate = Join-Path $base $rel
      if (Test-Path -LiteralPath $candidate -PathType Container) {
        return (Resolve-Path -LiteralPath $candidate).Path
      }
    }
  }

  throw "Vitosoft root not found; pass -Root."
}

function Safe-Name {
  param([string]$Value)
  if (-not $Value) { return "unnamed" }
  $out = $Value
  foreach ($c in [IO.Path]::GetInvalidFileNameChars()) {
    $out = $out.Replace([string]$c,"_")
  }
  $out = $out -replace '[:\\/]+','_'
  return $out
}

function RelPath {
  param([string]$Base,[string]$Path)
  try { return [IO.Path]::GetRelativePath($Base,$Path) }
  catch { return $Path.Substring($Base.Length).TrimStart("\") }
}

function Get-HelperScript {
  param([string]$Name,[string]$DestinationDir)

  $local = Join-Path $PSScriptRoot $Name
  if (Test-Path -LiteralPath $local -PathType Leaf) {
    return (Resolve-Path -LiteralPath $local).Path
  }

  New-Item -ItemType Directory -Path $DestinationDir -Force | Out-Null
  $dest = Join-Path $DestinationDir $Name
  $uri = "https://raw.githubusercontent.com/SaulGoodman1337/optolink/main/tools/" + $Name
  Invoke-WebRequest -Uri $uri -OutFile $dest
  return $dest
}

function Copy-Tree {
  param([string]$Source,[string]$Destination,[System.IO.StreamWriter]$Log)

  if (-not (Test-Path -LiteralPath $Source -PathType Container)) { return }
  New-Item -ItemType Directory -Path $Destination -Force | Out-Null

  if (Get-Command robocopy.exe -ErrorAction SilentlyContinue) {
    $args = @($Source,$Destination,"/E","/COPY:DAT","/DCOPY:DAT","/R:1","/W:1","/XJ","/NP","/NFL","/NDL")
    & robocopy.exe @args | Out-Null
    $code = $LASTEXITCODE
    $Log.WriteLine(('"{0}","{1}","robocopy","{2}"' -f ($Source -replace '"','""'),($Destination -replace '"','""'),$code))
    if ($code -gt 7) { Write-Warning "robocopy reported exit code $code for $Source; continuing with the remaining collection stages." }
  } else {
    Get-ChildItem -LiteralPath $Source -Force -ErrorAction SilentlyContinue |
      Copy-Item -Destination $Destination -Recurse -Force -ErrorAction Stop
    $Log.WriteLine(('"{0}","{1}","Copy-Item","0"' -f ($Source -replace '"','""'),($Destination -replace '"','""')))
  }
}

function Export-RegKey {
  param([string]$Key,[string]$Path)
  if (-not (Get-Command reg.exe -ErrorAction SilentlyContinue)) { return }
  try {
    & reg.exe query $Key 1>$null 2>$null
    if ($LASTEXITCODE -eq 0) {
      & reg.exe export $Key $Path /y 1>$null 2>$null
    }
  } catch {}
}

$Root = Find-VitosoftRoot $Root

if (-not $OutputDir) {
  $OutputDir = Join-Path ([Environment]::GetFolderPath("Desktop")) ("vitosoft-private-archive-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$OutputDir = (Resolve-Path -LiteralPath $OutputDir).Path

$derivedDir = Join-Path $OutputDir "derived"
$rawDir = Join-Path $OutputDir "raw"
$sqlDir = Join-Path $OutputDir "sql"
$systemDir = Join-Path $OutputDir "system"
$registryDir = Join-Path $OutputDir "registry"
$toolsDir = Join-Path $OutputDir "tool-dumps"
$scriptsDir = Join-Path $OutputDir "collector-scripts"

foreach ($d in @($derivedDir,$rawDir,$sqlDir,$systemDir,$registryDir,$toolsDir,$scriptsDir)) {
  New-Item -ItemType Directory -Path $d -Force | Out-Null
}

Write-Host "Vitosoft PRIVATE archive collector" -ForegroundColor Cyan
Write-Host "Root:   $Root"
Write-Host "Output: $OutputDir"
Write-Host ""
Write-Host "WARNING: This bundle is intentionally comprehensive." -ForegroundColor Yellow
Write-Host "It may contain proprietary binaries, database contents, machine paths," -ForegroundColor Yellow
Write-Host "local configuration and credentials present in copied Vitosoft config files." -ForegroundColor Yellow
Write-Host "Keep the result private. Do not commit it to the public optolink repository." -ForegroundColor Yellow
Write-Host ""

try {
  if ($PSCommandPath -and (Test-Path -LiteralPath $PSCommandPath)) {
    Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $scriptsDir "collect-vitosoft-private-archive.ps1") -Force
  }
} catch {}

$deepScript = Get-HelperScript -Name "collect-vitosoft-deep-research.ps1" -DestinationDir $scriptsDir
$sqlScript = Get-HelperScript -Name "export-vitosoft-sql-readonly.ps1" -DestinationDir $scriptsDir
try { Copy-Item -LiteralPath $deepScript -Destination (Join-Path $scriptsDir "collect-vitosoft-deep-research.ps1") -Force } catch {}
try { Copy-Item -LiteralPath $sqlScript -Destination (Join-Path $scriptsDir "export-vitosoft-sql-readonly.ps1") -Force } catch {}

$os = $null
try { $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop }
catch { try { $os = Get-WmiObject Win32_OperatingSystem -ErrorAction Stop } catch {} }

$hostInfo = [ordered]@{
  generated_utc=(Get-Date).ToUniversalTime().ToString("o")
  computer_name=$env:COMPUTERNAME
  os_caption=if($os){$os.Caption}else{$null}
  os_version=if($os){$os.Version}else{$null}
  os_build=if($os){$os.BuildNumber}else{$null}
  os_architecture=if($os){$os.OSArchitecture}else{$env:PROCESSOR_ARCHITECTURE}
  powershell=$PSVersionTable.PSVersion.ToString()
  powershell_edition=if($PSVersionTable.PSEdition){$PSVersionTable.PSEdition}else{"Desktop"}
  culture=(Get-Culture).Name
  ui_culture=(Get-UICulture).Name
  vitosoft_root=$Root
  device=$Device
  device_id_hex=$DeviceIdHex
  program_files=$env:ProgramFiles
  program_files_x86=[Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
  program_data=$env:ProgramData
  user_profile=$env:USERPROFILE
}
$hostInfo | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $systemDir "host.json") -Encoding UTF8

try {
  Get-Service -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match 'Viessmann|Vito|SQL|MSSQL' -or $_.DisplayName -match 'Viessmann|Vito|SQL Server' } |
    Select-Object Name,DisplayName,Status,StartType |
    Export-Csv -LiteralPath (Join-Path $systemDir "related-services.csv") -NoTypeInformation -Encoding UTF8
} catch {}

try {
  Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.ProcessName -match 'Vito|Viess|SQL|MSSQL' } |
    Select-Object ProcessName,Id,Path,StartTime |
    Export-Csv -LiteralPath (Join-Path $systemDir "related-processes.csv") -NoTypeInformation -Encoding UTF8
} catch {}

try {
  Get-ScheduledTask -ErrorAction SilentlyContinue |
    Where-Object { $_.TaskName -match 'Vito|Viess' -or $_.TaskPath -match 'Vito|Viess' } |
    Select-Object TaskPath,TaskName,State,Author,Description |
    Export-Csv -LiteralPath (Join-Path $systemDir "related-scheduled-tasks.csv") -NoTypeInformation -Encoding UTF8
} catch {}

$uninstallPaths = @(
  "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
  "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
  "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*"
)
$installed = @()
foreach ($p in $uninstallPaths) {
  try {
    $installed += Get-ItemProperty $p -ErrorAction SilentlyContinue |
      Where-Object { $_.DisplayName -match 'Viessmann|Vitosoft|SQL Server|LocalDB|Visual C\+\+' } |
      Select-Object DisplayName,DisplayVersion,Publisher,InstallDate,InstallLocation,UninstallString,PSPath
  } catch {}
}
$installed | Sort-Object DisplayName,DisplayVersion -Unique |
  Export-Csv -LiteralPath (Join-Path $systemDir "related-installed-software.csv") -NoTypeInformation -Encoding UTF8

if (-not $SkipRegistry) {
  Write-Host "Collecting relevant registry keys..." -ForegroundColor Cyan
  $regKeys = [ordered]@{
    "hklm-viessmann.reg"="HKLM\SOFTWARE\Viessmann"
    "hklm-wow6432-viessmann.reg"="HKLM\SOFTWARE\WOW6432Node\Viessmann"
    "hkcu-viessmann.reg"="HKCU\Software\Viessmann"
    "hklm-sql-instance-names.reg"="HKLM\SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL"
    "hklm-wow6432-sql-instance-names.reg"="HKLM\SOFTWARE\WOW6432Node\Microsoft\Microsoft SQL Server\Instance Names\SQL"
  }
  foreach ($name in $regKeys.Keys) {
    Export-RegKey -Key $regKeys[$name] -Path (Join-Path $registryDir $name)
  }
}

if (-not $SkipRawTree) {
  Write-Host "Copying raw Vitosoft trees for private archival..." -ForegroundColor Cyan
  $copyLog = New-Object IO.StreamWriter((Join-Path $rawDir "raw-roots.csv"),$false,[Text.UTF8Encoding]::new($true))
  $copyLog.WriteLine('"Source","Destination","Method","ExitCode"')
  try {
    $roots = New-Object System.Collections.ArrayList
    $installParent = Split-Path -Parent $Root
    [void]$roots.Add([pscustomobject]@{Source=$installParent;Label="install-parent"})

    foreach ($candidate in @(
      (Join-Path $env:ProgramData "Viessmann"),
      (Join-Path $env:LOCALAPPDATA "Viessmann"),
      (Join-Path $env:APPDATA "Viessmann"),
      (Join-Path $env:USERPROFILE "Documents\Viessmann"),
      (Join-Path $env:USERPROFILE "Documents\Vitosoft")
    )) {
      if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Container)) {
        [void]$roots.Add([pscustomobject]@{Source=(Resolve-Path -LiteralPath $candidate).Path;Label=(Safe-Name $candidate)})
      }
    }

    $seen = @{}
    foreach ($r in $roots) {
      $key = $r.Source.ToLowerInvariant()
      if ($seen.ContainsKey($key)) { continue }
      $seen[$key] = $true
      Copy-Tree -Source $r.Source -Destination (Join-Path $rawDir $r.Label) -Log $copyLog
    }
  } finally {
    $copyLog.Dispose()
  }
}

Write-Host "Running deep derived collector..." -ForegroundColor Cyan
$deepArgs = @(
  "-NoProfile","-ExecutionPolicy","Bypass","-File",$deepScript,
  "-Root",$Root,
  "-OutputDir",$derivedDir,
  "-Device",$Device,
  "-DeviceIdHex",$DeviceIdHex,
  "-ProgressSeconds",[string]$ProgressSeconds
)
& powershell.exe @deepArgs
$deepExit = $LASTEXITCODE
if ($deepExit -ne 0) {
  "Deep collector exit code: $deepExit" | Set-Content -LiteralPath (Join-Path $derivedDir "private-wrapper-deep-error.txt") -Encoding UTF8
}

if (-not $SkipSql) {
  Write-Host "Running SQL read-only collection..." -ForegroundColor Cyan
  $sqlArgs = @(
    "-NoProfile","-ExecutionPolicy","Bypass","-File",$sqlScript,
    "-Root",$Root,
    "-OutputDir",$sqlDir,
    "-MaxRowsPerTable",[string]$MaxSqlRowsPerTable
  )
  & powershell.exe @sqlArgs
  $sqlExit = $LASTEXITCODE
  if ($sqlExit -ne 0) {
    "SQL collector exit code: $sqlExit" | Set-Content -LiteralPath (Join-Path $sqlDir "private-wrapper-sql-error.txt") -Encoding UTF8
  }
}

$peFiles = @(Get-ChildItem -LiteralPath $Root -File -Recurse -ErrorAction SilentlyContinue | Where-Object {
  $_.Extension.ToLowerInvariant() -in @(".exe",".dll",".sys",".cat",".msi")
})

$signatures = foreach ($f in $peFiles) {
  try {
    $s = Get-AuthenticodeSignature -LiteralPath $f.FullName
    [pscustomobject]@{
      RelativePath=(RelPath $Root $f.FullName)
      Status=[string]$s.Status
      StatusMessage=$s.StatusMessage
      SignerSubject=if($s.SignerCertificate){$s.SignerCertificate.Subject}else{$null}
      SignerIssuer=if($s.SignerCertificate){$s.SignerCertificate.Issuer}else{$null}
      SignerThumbprint=if($s.SignerCertificate){$s.SignerCertificate.Thumbprint}else{$null}
    }
  } catch {
    [pscustomobject]@{
      RelativePath=(RelPath $Root $f.FullName)
      Status="error"
      StatusMessage=$_.Exception.Message
      SignerSubject=$null
      SignerIssuer=$null
      SignerThumbprint=$null
    }
  }
}
$signatures | Export-Csv -LiteralPath (Join-Path $systemDir "authenticode.csv") -NoTypeInformation -Encoding UTF8

if (-not $SkipToolDumps) {
  $ildasm = Get-Command ildasm.exe -ErrorAction SilentlyContinue
  $dumpbin = Get-Command dumpbin.exe -ErrorAction SilentlyContinue
  $toolInfo = [ordered]@{
    ildasm=if($ildasm){$ildasm.Source}else{$null}
    dumpbin=if($dumpbin){$dumpbin.Source}else{$null}
    git=if(Get-Command git.exe -ErrorAction SilentlyContinue){(Get-Command git.exe).Source}else{$null}
    git_lfs=if(Get-Command git-lfs.exe -ErrorAction SilentlyContinue){(Get-Command git-lfs.exe).Source}else{$null}
    sevenzip=if(Get-Command 7z.exe -ErrorAction SilentlyContinue){(Get-Command 7z.exe).Source}else{$null}
  }
  $toolInfo | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $systemDir "optional-tools.json") -Encoding UTF8

  if ($ildasm) {
    $ilDir = Join-Path $toolsDir "ildasm"
    New-Item -ItemType Directory -Path $ilDir -Force | Out-Null
    foreach ($f in $peFiles | Where-Object { $_.Extension.ToLowerInvariant() -in @(".exe",".dll") }) {
      try { [void][Reflection.AssemblyName]::GetAssemblyName($f.FullName) } catch { continue }
      $out = Join-Path $ilDir ((Safe-Name (RelPath $Root $f.FullName)) + ".il")
      try {
        & $ildasm.Source /text /nobar /linenum /tokens ("/out=" + $out) $f.FullName 1>$null 2>$null
      } catch {
        $_.Exception.ToString() | Set-Content -LiteralPath ($out + ".error.txt") -Encoding UTF8
      }
    }
  }

  if ($dumpbin) {
    $dumpDir = Join-Path $toolsDir "dumpbin"
    New-Item -ItemType Directory -Path $dumpDir -Force | Out-Null
    foreach ($f in $peFiles | Where-Object { $_.Extension.ToLowerInvariant() -in @(".exe",".dll") }) {
      $out = Join-Path $dumpDir ((Safe-Name (RelPath $Root $f.FullName)) + ".txt")
      try { & $dumpbin.Source /headers /imports /exports $f.FullName 2>&1 | Out-File -LiteralPath $out -Encoding utf8 } catch {}
    }
  }
}

@"
# PRIVATE Vitosoft archive

This directory is intentionally suitable for a private research repository.

It may contain:
- proprietary Viessmann/Vitosoft binaries and resources;
- complete Vitosoft installation/configuration files;
- MDF/LDF SQL database copies and exported table contents;
- machine-specific paths and registry data;
- credentials if they were stored unencrypted in copied application config.

Do NOT push this directory to the public optolink repository.

Recommended:
1. create a private repository;
2. enable Git LFS before the first commit;
3. review raw config/database content for secrets before granting access;
4. retain archive-manifest.sha256 as the integrity reference.

The public optolink repository should contain only derived research,
reproducible collector scripts, hashes and conclusions.
"@ | Set-Content -LiteralPath (Join-Path $OutputDir "PRIVATE-README.md") -Encoding UTF8

@"
*.dll filter=lfs diff=lfs merge=lfs -text
*.exe filter=lfs diff=lfs merge=lfs -text
*.sys filter=lfs diff=lfs merge=lfs -text
*.lib filter=lfs diff=lfs merge=lfs -text
*.cat filter=lfs diff=lfs merge=lfs -text
*.msi filter=lfs diff=lfs merge=lfs -text
*.mdf filter=lfs diff=lfs merge=lfs -text
*.ldf filter=lfs diff=lfs merge=lfs -text
*.ecndat filter=lfs diff=lfs merge=lfs -text
*.pdb filter=lfs diff=lfs merge=lfs -text
*.cab filter=lfs diff=lfs merge=lfs -text
*.zip filter=lfs diff=lfs merge=lfs -text
*.7z filter=lfs diff=lfs merge=lfs -text
*.bin filter=lfs diff=lfs merge=lfs -text
*.rom filter=lfs diff=lfs merge=lfs -text
*.img filter=lfs diff=lfs merge=lfs -text
"@ | Set-Content -LiteralPath (Join-Path $OutputDir ".gitattributes") -Encoding ASCII

Write-Host "Building final SHA256 manifest..." -ForegroundColor Cyan
$manifestPath = Join-Path $OutputDir "archive-manifest.sha256"
$manifestWriter = New-Object IO.StreamWriter($manifestPath,$false,[Text.UTF8Encoding]::new($false))
try {
  $files = @(Get-ChildItem -LiteralPath $OutputDir -File -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.FullName -ne $manifestPath })
  foreach ($f in $files) {
    try {
      $hash = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
      $manifestWriter.WriteLine($hash + "  " + (RelPath $OutputDir $f.FullName))
    } catch {
      $manifestWriter.WriteLine("<hash-error>  " + (RelPath $OutputDir $f.FullName))
    }
  }
} finally {
  $manifestWriter.Dispose()
}

$summary = [ordered]@{
  generated_utc=(Get-Date).ToUniversalTime().ToString("o")
  vitosoft_root=$Root
  output=$OutputDir
  device=$Device
  device_id_hex=$DeviceIdHex
  raw_tree_collected=(-not $SkipRawTree)
  sql_collected=(-not $SkipSql)
  registry_collected=(-not $SkipRegistry)
  tool_dumps_collected=(-not $SkipToolDumps)
  max_sql_rows_per_table=$MaxSqlRowsPerTable
}
$summary | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $OutputDir "private-archive-summary.json") -Encoding UTF8

if ($CreateArchive) {
  Write-Host "Creating optional archive..." -ForegroundColor Cyan
  $seven = Get-Command 7z.exe -ErrorAction SilentlyContinue
  if ($seven) {
    $archive = $OutputDir + ".7z"
    & $seven.Source a -t7z -mx=5 $archive (Join-Path $OutputDir "*")
    Write-Host "Archive: $archive"
  } else {
    $archive = $OutputDir + ".zip"
    Write-Warning "7z.exe not found; falling back to Compress-Archive. Very large trees may exceed ZIP/.NET limits."
    Compress-Archive -Path (Join-Path $OutputDir "*") -DestinationPath $archive -Force
    Write-Host "Archive: $archive"
  }
}

Write-Host ""
Write-Host "Finished private Vitosoft archive: $OutputDir" -ForegroundColor Green
Write-Host "Keep this output private." -ForegroundColor Yellow

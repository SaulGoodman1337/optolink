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
  [switch]$SkipPrerequisiteInstall,
  [switch]$CreateArchive
)

$ErrorActionPreference = "Stop"

if ($PSVersionTable.PSVersion -lt [version]"5.1") {
  throw "PowerShell 5.1 or newer is required."
}

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

function Format-PublicKeyToken {
  param([byte[]]$Token)
  if ($null -eq $Token -or $Token.Length -eq 0) { return "" }
  return (([BitConverter]::ToString($Token) -replace '-','').ToLowerInvariant())
}

function RelPath {
  param([string]$Base,[string]$Path)
  try { return [IO.Path]::GetRelativePath($Base,$Path) }
  catch { return $Path.Substring($Base.Length).TrimStart("\") }
}

function Get-HelperScript {
  param([string]$Name,[string]$DestinationDir)

  New-Item -ItemType Directory -Path $DestinationDir -Force | Out-Null
  $dest = Join-Path $DestinationDir $Name
  $uri = "https://raw.githubusercontent.com/SaulGoodman1337/optolink/main/tools/" + $Name
  try {
    Invoke-WebRequest -UseBasicParsing -Uri $uri -OutFile $dest
    return $dest
  } catch {
    $local = Join-Path $PSScriptRoot $Name
    if (Test-Path -LiteralPath $local -PathType Leaf) {
      Copy-Item -LiteralPath $local -Destination $dest -Force
      return $dest
    }
    throw
  }
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

function Test-IsAdministrator {
  try {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
  } catch {
    return $false
  }
}

function Find-ToolPath {
  param([string]$Name)

  $cmd = Get-Command $Name -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }

  $pf86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
  $pf = $env:ProgramFiles

  $patterns = @()
  switch ($Name.ToLowerInvariant()) {
    "vswhere.exe" {
      if ($pf86) { $patterns += (Join-Path $pf86 "Microsoft Visual Studio\Installer\vswhere.exe") }
    }
    "dumpbin.exe" {
      if ($pf86) { $patterns += (Join-Path $pf86 "Microsoft Visual Studio\*\*\VC\Tools\MSVC\*\bin\Hostx64\x64\dumpbin.exe") }
      if ($pf)   { $patterns += (Join-Path $pf   "Microsoft Visual Studio\*\*\VC\Tools\MSVC\*\bin\Hostx64\x64\dumpbin.exe") }
    }
    "msbuild.exe" {
      if ($pf86) { $patterns += (Join-Path $pf86 "Microsoft Visual Studio\*\*\MSBuild\Current\Bin\MSBuild.exe") }
      if ($pf)   { $patterns += (Join-Path $pf   "Microsoft Visual Studio\*\*\MSBuild\Current\Bin\MSBuild.exe") }
    }
    "ildasm.exe" {
      foreach ($base in @($pf86,$pf) | Where-Object { $_ }) {
        $sdkRoot = Join-Path $base "Microsoft SDKs\Windows"
        if (Test-Path -LiteralPath $sdkRoot -PathType Container) {
          $hit = Get-ChildItem -LiteralPath $sdkRoot -Filter ildasm.exe -File -Recurse -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending | Select-Object -First 1
          if ($hit) { return $hit.FullName }
        }
      }
    }
    { $_ -in @("corflags.exe","sn.exe","gacutil.exe") } {
      foreach ($base in @($pf86,$pf) | Where-Object { $_ }) {
        $sdkRoot = Join-Path $base "Microsoft SDKs\Windows"
        if (Test-Path -LiteralPath $sdkRoot -PathType Container) {
          $hit = Get-ChildItem -LiteralPath $sdkRoot -Filter $Name -File -Recurse -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending | Select-Object -First 1
          if ($hit) { return $hit.FullName }
        }
      }
    }
    "7z.exe" {
      if ($pf)   { $patterns += (Join-Path $pf "7-Zip\7z.exe") }
      if ($pf86) { $patterns += (Join-Path $pf86 "7-Zip\7z.exe") }
    }
  }

  foreach ($pattern in $patterns) {
    $hit = Get-ChildItem -Path $pattern -File -ErrorAction SilentlyContinue |
      Sort-Object FullName -Descending | Select-Object -First 1
    if ($hit) { return $hit.FullName }
  }

  return $null
}

function Get-PrerequisiteState {
  [ordered]@{
    generated_utc=(Get-Date).ToUniversalTime().ToString("o")
    administrator=(Test-IsAdministrator)
    powershell=$PSVersionTable.PSVersion.ToString()
    winget=if(Get-Command winget.exe -ErrorAction SilentlyContinue){(Get-Command winget.exe).Source}else{$null}
    robocopy=if(Get-Command robocopy.exe -ErrorAction SilentlyContinue){(Get-Command robocopy.exe).Source}else{$null}
    reg=if(Get-Command reg.exe -ErrorAction SilentlyContinue){(Get-Command reg.exe).Source}else{$null}
    ildasm=(Find-ToolPath "ildasm.exe")
    dumpbin=(Find-ToolPath "dumpbin.exe")
    corflags=(Find-ToolPath "corflags.exe")
    sn=(Find-ToolPath "sn.exe")
    gacutil=(Find-ToolPath "gacutil.exe")
    msbuild=(Find-ToolPath "msbuild.exe")
    vswhere=(Find-ToolPath "vswhere.exe")
    dotnet=if(Get-Command dotnet.exe -ErrorAction SilentlyContinue){(Get-Command dotnet.exe).Source}else{$null}
    sqlcmd=if(Get-Command sqlcmd.exe -ErrorAction SilentlyContinue){(Get-Command sqlcmd.exe).Source}else{$null}
    sqllocaldb=if(Get-Command sqllocaldb.exe -ErrorAction SilentlyContinue){(Get-Command sqllocaldb.exe).Source}else{$null}
    sevenzip=(Find-ToolPath "7z.exe")
    git=if(Get-Command git.exe -ErrorAction SilentlyContinue){(Get-Command git.exe).Source}else{$null}
    git_lfs=if(Get-Command git-lfs.exe -ErrorAction SilentlyContinue){(Get-Command git-lfs.exe).Source}else{$null}
  }
}

function Write-PrerequisiteReport {
  param([string]$Path,[object]$State)

  @(
    [pscustomobject]@{Name="PowerShell 5.1+";Required=$true;Available=([version]$State.powershell -ge [version]"5.1");Path=$State.powershell;AutoInstall=$false;Purpose="Collector runtime"}
    [pscustomobject]@{Name="Administrator";Required=$false;Available=[bool]$State.administrator;Path="";AutoInstall=$false;Purpose="Required only for automatic tool installation"}
    [pscustomobject]@{Name="robocopy";Required=$true;Available=[bool]$State.robocopy;Path=$State.robocopy;AutoInstall=$false;Purpose="Reliable raw tree copy"}
    [pscustomobject]@{Name="reg.exe";Required=$true;Available=[bool]$State.reg;Path=$State.reg;AutoInstall=$false;Purpose="Registry exports"}
    [pscustomobject]@{Name="ildasm";Required=$false;Available=[bool]$State.ildasm;Path=$State.ildasm;AutoInstall=$true;Purpose="Managed IL disassembly"}
    [pscustomobject]@{Name="dumpbin";Required=$false;Available=[bool]$State.dumpbin;Path=$State.dumpbin;AutoInstall=$true;Purpose="PE headers/imports/exports/dependencies"}
    [pscustomobject]@{Name="corflags";Required=$false;Available=[bool]$State.corflags;Path=$State.corflags;AutoInstall=$true;Purpose=".NET PE/CLR flags"}
    [pscustomobject]@{Name="sn";Required=$false;Available=[bool]$State.sn;Path=$State.sn;AutoInstall=$true;Purpose="Strong-name token inspection"}
    [pscustomobject]@{Name="gacutil";Required=$false;Available=[bool]$State.gacutil;Path=$State.gacutil;AutoInstall=$true;Purpose="GAC inventory"}
    [pscustomobject]@{Name="msbuild";Required=$false;Available=[bool]$State.msbuild;Path=$State.msbuild;AutoInstall=$true;Purpose="Build-tool/environment inventory"}
    [pscustomobject]@{Name="7-Zip";Required=$false;Available=[bool]$State.sevenzip;Path=$State.sevenzip;AutoInstall=$true;Purpose="Large archive creation"}
    [pscustomobject]@{Name="dotnet";Required=$false;Available=[bool]$State.dotnet;Path=$State.dotnet;AutoInstall=$false;Purpose=".NET runtime/SDK inventory"}
    [pscustomobject]@{Name="sqlcmd";Required=$false;Available=[bool]$State.sqlcmd;Path=$State.sqlcmd;AutoInstall=$false;Purpose="Optional SQL diagnostics; collector uses .NET SqlClient"}
    [pscustomobject]@{Name="sqllocaldb";Required=$false;Available=[bool]$State.sqllocaldb;Path=$State.sqllocaldb;AutoInstall=$false;Purpose="Optional LocalDB inventory"}
    [pscustomobject]@{Name="git";Required=$false;Available=[bool]$State.git;Path=$State.git;AutoInstall=$false;Purpose="Optional private repository workflow"}
    [pscustomobject]@{Name="git-lfs";Required=$false;Available=[bool]$State.git_lfs;Path=$State.git_lfs;AutoInstall=$false;Purpose="Optional private repository large-file workflow"}
  ) | Export-Csv -LiteralPath $Path -NoTypeInformation -Encoding UTF8
}

function Install-ResearchPrerequisites {
  param([string]$LogPath)

  $log = New-Object IO.StreamWriter($LogPath,$false,[Text.UTF8Encoding]::new($true))
  try {
    $before = Get-PrerequisiteState
    $log.WriteLine("Preflight started: " + (Get-Date).ToString("o"))
    $log.WriteLine("Administrator: " + $before.administrator)

    if ($SkipPrerequisiteInstall) {
      $log.WriteLine("Installation skipped by -SkipPrerequisiteInstall.")
      return
    }

    if (-not $before.administrator) {
      $log.WriteLine("Not elevated: automatic prerequisite installation cannot run.")
      Write-Warning "Collector is not running as Administrator. Missing analysis tools cannot be installed automatically."
      return
    }

    # Ildasm is installed with Visual Studio/.NET Framework developer tooling;
    # dumpbin is part of the MSVC build tools. Install only the minimal
    # components we need instead of a full IDE.
    if (-not $before.ildasm -or -not $before.dumpbin) {
      $bootstrap = Join-Path $env:TEMP "vs_buildtools_vitosoft_collector.exe"
      $url = "https://aka.ms/vs/17/release/vs_buildtools.exe"
      try {
        $log.WriteLine("Downloading Visual Studio 2022 Build Tools bootstrapper: $url")
        try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}
        Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $bootstrap

        $installPath = Join-Path ([Environment]::GetEnvironmentVariable("ProgramFiles(x86)")) "Microsoft Visual Studio\2022\BuildTools"
        $quotedInstallPath = '"' + $installPath + '"'
        $args = @(
          "--quiet","--wait","--norestart","--nocache",
          "--installPath",$quotedInstallPath,
          "--add","Microsoft.Component.MSBuild",
          "--add","Microsoft.Net.Component.4.8.SDK",
          "--add","Microsoft.VisualStudio.Component.VC.Tools.x86.x64"
        )
        $log.WriteLine("Installing/updating minimal VS Build Tools components for ildasm/dumpbin.")
        $p = Start-Process -FilePath $bootstrap -ArgumentList $args -Wait -PassThru
        $log.WriteLine("VS Build Tools exit code: " + $p.ExitCode)
        if ($p.ExitCode -notin @(0,3010)) {
          Write-Warning "Visual Studio Build Tools installer returned exit code $($p.ExitCode). Collector will continue and record missing tools."
        }
      } catch {
        $log.WriteLine("VS Build Tools install error: " + $_.Exception.ToString())
        Write-Warning "Could not install Visual Studio Build Tools automatically: $($_.Exception.Message)"
      } finally {
        try { Remove-Item -LiteralPath $bootstrap -Force -ErrorAction SilentlyContinue } catch {}
      }
    }

    # 7-Zip is preferred for the large private archive. If winget is absent,
    # Compress-Archive remains available as a fallback.
    $seven = Find-ToolPath "7z.exe"
    if (-not $seven) {
      $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
      if ($winget) {
        try {
          $log.WriteLine("Installing 7-Zip through winget.")
          & $winget.Source install --id 7zip.7zip -e --silent --accept-package-agreements --accept-source-agreements 2>&1 |
            ForEach-Object { $log.WriteLine([string]$_) }
          $log.WriteLine("winget 7-Zip exit code: " + $LASTEXITCODE)
        } catch {
          $log.WriteLine("7-Zip install error: " + $_.Exception.ToString())
        }
      } else {
        $log.WriteLine("winget unavailable; 7-Zip not auto-installed.")
      }
    }
  }
  finally {
    $log.Flush()
    $log.Dispose()
  }
}

function Invoke-TextCapture {
  param([string]$Path,[scriptblock]$Script)
  try {
    & $Script 2>&1 | Out-File -LiteralPath $Path -Encoding utf8
  } catch {
    $_.Exception.ToString() | Set-Content -LiteralPath ($Path + ".error.txt") -Encoding UTF8
  }
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

$prereqBefore = Get-PrerequisiteState
$prereqBefore | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $systemDir "prerequisites-before.json") -Encoding UTF8
Install-ResearchPrerequisites -LogPath (Join-Path $systemDir "prerequisite-install.log")
$prereqAfter = Get-PrerequisiteState
$prereqAfter | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $systemDir "prerequisites-after.json") -Encoding UTF8
Write-PrerequisiteReport -Path (Join-Path $systemDir "prerequisite-report.csv") -State $prereqAfter

if ((-not $prereqAfter.ildasm -or -not $prereqAfter.dumpbin) -and -not $SkipToolDumps) {
  Write-Warning "ildasm/dumpbin are still unavailable. Raw binaries and managed metadata will still be collected, but tool-dumps will be incomplete."
}

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

# Development/runtime environment. These files are useful when later replaying
# the exact managed-code environment or understanding why a tool was missing.
if (Get-Command dotnet.exe -ErrorAction SilentlyContinue) {
  Invoke-TextCapture -Path (Join-Path $systemDir "dotnet-info.txt") -Script { & dotnet.exe --info }
  Invoke-TextCapture -Path (Join-Path $systemDir "dotnet-sdks.txt") -Script { & dotnet.exe --list-sdks }
  Invoke-TextCapture -Path (Join-Path $systemDir "dotnet-runtimes.txt") -Script { & dotnet.exe --list-runtimes }
}

$vswherePath = Find-ToolPath "vswhere.exe"
if ($vswherePath) {
  Invoke-TextCapture -Path (Join-Path $systemDir "visual-studio-instances.json") -Script {
    & $vswherePath -all -products "*" -format json -utf8
  }
}

try {
  Get-CimInstance Win32_SerialPort -ErrorAction SilentlyContinue |
    Select-Object DeviceID,Name,Description,PNPDeviceID,ProviderType,Status |
    Export-Csv -LiteralPath (Join-Path $systemDir "serial-ports.csv") -NoTypeInformation -Encoding UTF8
} catch {}

try {
  Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue |
    Where-Object {
      $_.PNPDeviceID -match '^(USB|FTDIBUS)\\' -or
      $_.Name -match 'FTDI|CP210|USB Serial|Optolink|Viessmann'
    } |
    Select-Object Name,Manufacturer,PNPClass,PNPDeviceID,Service,Status |
    Export-Csv -LiteralPath (Join-Path $systemDir "usb-pnp-devices.csv") -NoTypeInformation -Encoding UTF8
} catch {}

try {
  Get-CimInstance Win32_Service -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match 'Viessmann|Vito|SQL|MSSQL' -or $_.DisplayName -match 'Viessmann|Vito|SQL Server' } |
    Select-Object Name,DisplayName,State,StartMode,StartName,PathName,ProcessId |
    Export-Csv -LiteralPath (Join-Path $systemDir "related-services-detailed.csv") -NoTypeInformation -Encoding UTF8
} catch {}

try {
  $moduleRows = foreach ($p in Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match 'Vito|Viess|ecn|SQL|MSSQL' }) {
    try {
      foreach ($m in $p.Modules) {
        [pscustomobject]@{
          ProcessName=$p.ProcessName
          ProcessId=$p.Id
          ModuleName=$m.ModuleName
          FileName=$m.FileName
          FileVersion=try{$m.FileVersionInfo.FileVersion}catch{$null}
          ProductVersion=try{$m.FileVersionInfo.ProductVersion}catch{$null}
        }
      }
    } catch {}
  }
  $moduleRows | Export-Csv -LiteralPath (Join-Path $systemDir "related-process-modules.csv") -NoTypeInformation -Encoding UTF8
} catch {}

Invoke-TextCapture -Path (Join-Path $systemDir "network-listeners.txt") -Script { & netstat.exe -ano }

try {
  Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" -ErrorAction SilentlyContinue |
    Select-Object DeviceID,VolumeName,FileSystem,
      @{N='SizeGB';E={[math]::Round($_.Size/1GB,2)}},
      @{N='FreeGB';E={[math]::Round($_.FreeSpace/1GB,2)}} |
    Export-Csv -LiteralPath (Join-Path $systemDir "fixed-disk-space.csv") -NoTypeInformation -Encoding UTF8
} catch {}

try {
  Get-HotFix -ErrorAction SilentlyContinue |
    Sort-Object InstalledOn |
    Select-Object HotFixID,Description,InstalledBy,InstalledOn |
    Export-Csv -LiteralPath (Join-Path $systemDir "windows-hotfixes.csv") -NoTypeInformation -Encoding UTF8
} catch {}

try {
  $since = (Get-Date).AddDays(-30)
  Get-WinEvent -FilterHashtable @{LogName='Application';StartTime=$since} -ErrorAction SilentlyContinue |
    Where-Object {
      $_.ProviderName -match 'Viessmann|Vito|SQL|MSSQL|\.NET Runtime|Application Error' -or
      $_.Message -match 'Viessmann|Vitosoft|ecnViessmann|vsmInterface|ServiceTool'
    } |
    Select-Object TimeCreated,Id,LevelDisplayName,ProviderName,MachineName,Message |
    Export-Csv -LiteralPath (Join-Path $systemDir "related-application-events-30d.csv") -NoTypeInformation -Encoding UTF8
} catch {}

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
    "hklm-dotnet-framework-ndp.reg"="HKLM\SOFTWARE\Microsoft\NET Framework Setup\NDP"
    "hklm-wow6432-dotnet-framework-ndp.reg"="HKLM\SOFTWARE\WOW6432Node\Microsoft\NET Framework Setup\NDP"
    "hklm-visualstudio-sxs.reg"="HKLM\SOFTWARE\Microsoft\VisualStudio\SxS\VS7"
    "hklm-wow6432-visualstudio-sxs.reg"="HKLM\SOFTWARE\WOW6432Node\Microsoft\VisualStudio\SxS\VS7"
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
  $ildasmPath = Find-ToolPath "ildasm.exe"
  $dumpbinPath = Find-ToolPath "dumpbin.exe"
  $corflagsPath = Find-ToolPath "corflags.exe"
  $snPath = Find-ToolPath "sn.exe"
  $gacutilPath = Find-ToolPath "gacutil.exe"
  $msbuildPath = Find-ToolPath "msbuild.exe"
  $vswherePath = Find-ToolPath "vswhere.exe"

  $toolInfo = [ordered]@{
    ildasm=$ildasmPath
    dumpbin=$dumpbinPath
    corflags=$corflagsPath
    sn=$snPath
    gacutil=$gacutilPath
    msbuild=$msbuildPath
    vswhere=$vswherePath
    dotnet=if(Get-Command dotnet.exe -ErrorAction SilentlyContinue){(Get-Command dotnet.exe).Source}else{$null}
    sqlcmd=if(Get-Command sqlcmd.exe -ErrorAction SilentlyContinue){(Get-Command sqlcmd.exe).Source}else{$null}
    sqllocaldb=if(Get-Command sqllocaldb.exe -ErrorAction SilentlyContinue){(Get-Command sqllocaldb.exe).Source}else{$null}
    git=if(Get-Command git.exe -ErrorAction SilentlyContinue){(Get-Command git.exe).Source}else{$null}
    git_lfs=if(Get-Command git-lfs.exe -ErrorAction SilentlyContinue){(Get-Command git-lfs.exe).Source}else{$null}
    sevenzip=(Find-ToolPath "7z.exe")
  }
  $toolInfo | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $systemDir "optional-tools.json") -Encoding UTF8

  if ($msbuildPath) {
    Invoke-TextCapture -Path (Join-Path $toolsDir "msbuild-version.txt") -Script { & $msbuildPath -version }
  }
  if ($ildasmPath) {
    Invoke-TextCapture -Path (Join-Path $toolsDir "ildasm-version.txt") -Script { & $ildasmPath /? }
  }
  if ($dumpbinPath) {
    Invoke-TextCapture -Path (Join-Path $toolsDir "dumpbin-version.txt") -Script { & $dumpbinPath /? }
  }

  $managedFiles = New-Object System.Collections.ArrayList
  foreach ($candidate in $peFiles | Where-Object { $_.Extension.ToLowerInvariant() -in @(".exe",".dll") }) {
    try {
      [void][Reflection.AssemblyName]::GetAssemblyName($candidate.FullName)
      [void]$managedFiles.Add($candidate)
    } catch {}
  }

  # Managed assembly reference graph + manifest resources + MVID. This works
  # even when ildasm is unavailable and is especially useful for tracing
  # vsmInterface/VSKO/GFA call paths.
  $refRows = New-Object System.Collections.ArrayList
  $resRows = New-Object System.Collections.ArrayList
  $asmRows = New-Object System.Collections.ArrayList
  foreach ($f in $managedFiles) {
    try {
      $an = [Reflection.AssemblyName]::GetAssemblyName($f.FullName)
      $asm = [Reflection.Assembly]::ReflectionOnlyLoadFrom($f.FullName)
      [void]$asmRows.Add([pscustomobject]@{
        RelativePath=(RelPath $Root $f.FullName)
        Name=$an.Name
        Version=[string]$an.Version
        CultureName=$an.CultureInfo.Name
        PublicKeyToken=(Format-PublicKeyToken ($an.GetPublicKeyToken()))
        ProcessorArchitecture=[string]$an.ProcessorArchitecture
        MVID=try{[string]$asm.ManifestModule.ModuleVersionId}catch{$null}
      })
      foreach ($ref in $asm.GetReferencedAssemblies()) {
        [void]$refRows.Add([pscustomobject]@{
          RelativePath=(RelPath $Root $f.FullName)
          Assembly=$an.Name
          Reference=$ref.Name
          Version=[string]$ref.Version
          PublicKeyToken=(Format-PublicKeyToken ($ref.GetPublicKeyToken()))
        })
      }
      foreach ($res in $asm.GetManifestResourceNames()) {
        [void]$resRows.Add([pscustomobject]@{
          RelativePath=(RelPath $Root $f.FullName)
          Assembly=$an.Name
          Resource=$res
        })
      }
    } catch {
      [void]$asmRows.Add([pscustomobject]@{
        RelativePath=(RelPath $Root $f.FullName)
        Name="<error>"
        Version=$null
        CultureName=$null
        PublicKeyToken=$null
        ProcessorArchitecture=$null
        MVID=$_.Exception.Message
      })
    }
  }
  $asmRows | Export-Csv -LiteralPath (Join-Path $toolsDir "managed-assembly-identities.csv") -NoTypeInformation -Encoding UTF8
  $refRows | Export-Csv -LiteralPath (Join-Path $toolsDir "managed-assembly-references.csv") -NoTypeInformation -Encoding UTF8
  $resRows | Export-Csv -LiteralPath (Join-Path $toolsDir "managed-manifest-resources.csv") -NoTypeInformation -Encoding UTF8

  if ($ildasmPath) {
    $ilDir = Join-Path $toolsDir "ildasm"
    New-Item -ItemType Directory -Path $ilDir -Force | Out-Null
    foreach ($f in $managedFiles) {
      $out = Join-Path $ilDir ((Safe-Name (RelPath $Root $f.FullName)) + ".il")
      try {
        & $ildasmPath /text /nobar /linenum /tokens /bytes ("/out=" + $out) $f.FullName 1>$null 2>$null
      } catch {
        $_.Exception.ToString() | Set-Content -LiteralPath ($out + ".error.txt") -Encoding UTF8
      }
    }
  }

  if ($dumpbinPath) {
    $dumpDir = Join-Path $toolsDir "dumpbin"
    New-Item -ItemType Directory -Path $dumpDir -Force | Out-Null
    foreach ($f in $peFiles | Where-Object { $_.Extension.ToLowerInvariant() -in @(".exe",".dll",".sys") }) {
      $out = Join-Path $dumpDir ((Safe-Name (RelPath $Root $f.FullName)) + ".txt")
      try {
        & $dumpbinPath /headers /imports /exports /dependents /loadconfig $f.FullName 2>&1 |
          Out-File -LiteralPath $out -Encoding utf8
      } catch {
        $_.Exception.ToString() | Set-Content -LiteralPath ($out + ".error.txt") -Encoding UTF8
      }
    }
  }

  if ($corflagsPath) {
    $corDir = Join-Path $toolsDir "corflags"
    New-Item -ItemType Directory -Path $corDir -Force | Out-Null
    foreach ($f in $managedFiles) {
      $out = Join-Path $corDir ((Safe-Name (RelPath $Root $f.FullName)) + ".txt")
      try { & $corflagsPath $f.FullName 2>&1 | Out-File -LiteralPath $out -Encoding utf8 } catch {}
    }
  }

  if ($snPath) {
    $snDir = Join-Path $toolsDir "strong-name"
    New-Item -ItemType Directory -Path $snDir -Force | Out-Null
    foreach ($f in $managedFiles) {
      $out = Join-Path $snDir ((Safe-Name (RelPath $Root $f.FullName)) + ".txt")
      try { & $snPath -T $f.FullName 2>&1 | Out-File -LiteralPath $out -Encoding utf8 } catch {}
    }
  }

  if ($gacutilPath) {
    Invoke-TextCapture -Path (Join-Path $toolsDir "gac-list.txt") -Script { & $gacutilPath /l }
  }
}

@"
# PRIVATE Vitosoft archive

This directory is intentionally suitable for a private research repository.

It may contain:
- proprietary Viessmann/Vitosoft binaries and resources;
- complete Vitosoft installation/configuration files;
- MDF/LDF SQL database copies and exported table contents;
- full managed IL / PE tool dumps when Visual Studio Build Tools are available;
- managed assembly identities, reference graph and embedded-resource inventory;
- serial/USB hardware, loaded process modules and recent relevant event-log data;
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

try {
  $allOutputFiles = @(Get-ChildItem -LiteralPath $OutputDir -File -Recurse -ErrorAction SilentlyContinue)
  $totalBytes = ($allOutputFiles | Measure-Object -Property Length -Sum).Sum
  if ($null -eq $totalBytes) { $totalBytes = 0 }
  $archiveStats = [ordered]@{
    generated_utc=(Get-Date).ToUniversalTime().ToString("o")
    file_count=$allOutputFiles.Count
    total_bytes=$totalBytes
    total_gib=[math]::Round(($totalBytes / 1GB),3)
    derived_files=@(Get-ChildItem -LiteralPath $derivedDir -File -Recurse -ErrorAction SilentlyContinue).Count
    raw_files=@(Get-ChildItem -LiteralPath $rawDir -File -Recurse -ErrorAction SilentlyContinue).Count
    sql_files=@(Get-ChildItem -LiteralPath $sqlDir -File -Recurse -ErrorAction SilentlyContinue).Count
    tool_dump_files=@(Get-ChildItem -LiteralPath $toolsDir -File -Recurse -ErrorAction SilentlyContinue).Count
  }
  $archiveStats | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $OutputDir "archive-stats.json") -Encoding UTF8
} catch {}

$collectorHash = $null
try {
  if ($PSCommandPath -and (Test-Path -LiteralPath $PSCommandPath -PathType Leaf)) {
    $collectorHash = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
  }
} catch {}

$summary = [ordered]@{
  generated_utc=(Get-Date).ToUniversalTime().ToString("o")
  collector_script_sha256=$collectorHash
  vitosoft_root=$Root
  output=$OutputDir
  device=$Device
  device_id_hex=$DeviceIdHex
  raw_tree_collected=(-not $SkipRawTree)
  sql_collected=(-not $SkipSql)
  registry_collected=(-not $SkipRegistry)
  tool_dumps_collected=(-not $SkipToolDumps)
  prerequisite_install_attempted=(-not $SkipPrerequisiteInstall)
  ildasm=(Find-ToolPath "ildasm.exe")
  dumpbin=(Find-ToolPath "dumpbin.exe")
  sevenzip=(Find-ToolPath "7z.exe")
  max_sql_rows_per_table=$MaxSqlRowsPerTable
}
$summary | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $OutputDir "private-archive-summary.json") -Encoding UTF8

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

if ($CreateArchive) {
  Write-Host "Creating optional archive..." -ForegroundColor Cyan
  $sevenPath = Find-ToolPath "7z.exe"
  if ($sevenPath) {
    $archive = $OutputDir + ".7z"
    if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
    & $sevenPath a -t7z -mx=5 $archive (Join-Path $OutputDir "*")
    if ($LASTEXITCODE -ne 0) {
      throw "7-Zip archive creation failed with exit code $LASTEXITCODE"
    }
    Write-Host "Testing archive integrity..." -ForegroundColor Cyan
    & $sevenPath t $archive | Out-Null
    if ($LASTEXITCODE -ne 0) {
      throw "7-Zip archive integrity test failed with exit code $LASTEXITCODE"
    }
    Write-Host "Archive: $archive" -ForegroundColor Green
  } else {
    $archive = $OutputDir + ".zip"
    Write-Warning "7z.exe not found; falling back to Compress-Archive. Very large trees may exceed ZIP/.NET limits."
    if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
    Compress-Archive -Path (Join-Path $OutputDir "*") -DestinationPath $archive -Force
    Write-Host "Archive: $archive"
  }
}

Write-Host ""
Write-Host "Finished private Vitosoft archive: $OutputDir" -ForegroundColor Green
Write-Host "Keep this output private." -ForegroundColor Yellow

param(
  [string]$Root = "",
  [string]$OutputDir = "",
  [string]$Device = "VDensHO1",
  [string]$DeviceIdHex = "20C2",
  [int]$ProgressSeconds = 5,
  [int]$MinStringLength = 4,
  [switch]$SkipAllPEStrings,
  [switch]$SkipManagedMembers
)

$ErrorActionPreference = "Stop"

function Find-Root {
  param([string]$Explicit)
  if ($Explicit) {
    if (-not (Test-Path -LiteralPath $Explicit -PathType Container)) { throw "Root not found: $Explicit" }
    return (Resolve-Path -LiteralPath $Explicit).Path
  }
  foreach ($pf in @($env:ProgramFiles,[Environment]::GetEnvironmentVariable("ProgramFiles(x86)")) | Where-Object { $_ }) {
    foreach ($rel in @("Viessmann Vitosoft 300 SID1\ServiceTool","Viessmann\Vitosoft 300 SID1\ServiceTool","Vitosoft 300 SID1\ServiceTool")) {
      $p=Join-Path $pf $rel
      if (Test-Path -LiteralPath $p -PathType Container) { return (Resolve-Path -LiteralPath $p).Path }
    }
  }
  throw "Vitosoft root not found; use -Root."
}

function RelPath([string]$Base,[string]$Path) {
  try { return [IO.Path]::GetRelativePath($Base,$Path) }
  catch { return $Path.Substring($Base.Length).TrimStart("\") }
}

function Csv([IO.StreamWriter]$W,[object[]]$V) {
  $x=$V | ForEach-Object {
    $s=if($null -eq $_){""}else{[string]$_}
    '"' + ($s -replace '"','""') + '"'
  }
  $W.WriteLine(($x -join ","))
}

function OneLine([string]$s) {
  if ($null -eq $s) { return "" }
  return ($s -replace "[\r\n\t]+"," ").Trim()
}

function Strings([byte[]]$b,[int]$n) {
  $a=[Text.Encoding]::ASCII.GetString($b)
  $r=[regex]::new("[\x20-\x7E]{"+$n+",}")
  foreach($m in $r.Matches($a)){[pscustomobject]@{Enc="ASCII";Off=$m.Index;Text=$m.Value}}
  $u=[Text.Encoding]::Unicode.GetString($b)
  foreach($m in $r.Matches($u)){[pscustomobject]@{Enc="UTF-16LE";Off=($m.Index*2);Text=$m.Value}}
}

function Core([string]$Root,[string]$Name,[string[]]$Preferred) {
  foreach($r in $Preferred){$p=Join-Path $Root $r;if(Test-Path -LiteralPath $p -PathType Leaf){return (Resolve-Path -LiteralPath $p).Path}}
  $h=Get-ChildItem -LiteralPath $Root -File -Recurse -Filter $Name -ErrorAction SilentlyContinue | Select-Object -First 1
  if($h){return $h.FullName}
  return $null
}

function PythonCmd {
  foreach($x in @(@{Exe="py";Args=@("-3")},@{Exe="python";Args=@()},@{Exe="python3";Args=@()})){
    if(Get-Command $x.Exe -ErrorAction SilentlyContinue){return $x}
  }
  return $null
}

$terms=@(
"VDensHO1","20C2","Optolink","P300","VS2","KMBUS","KM-BUS","KM Bus","KBUS","LON",
"KMBusEquipment","sysblock_KMBus_LonMemberList","KBUS_MEMBERLIST_READ","KBUS_MEMBERLIST_WRITE",
"KMBUS_RAM_READ","KMBUS_EEPROM_READ","KBUS_VIRTUAL_READ","KBUS_DIRECT_READ","KBUS_INDIRECT_READ","KBUS_GATEWAY_READ",
"BusHandlerType","OptolinkHandler","Pumpe","Pump","IntPumpe","PumpeIntern","InternePumpe",
"DrehzahlIntPumpe","InternePumpeDrehzahl","InternePumpeDrehzahl_res","DigitalAusgang_InternePumpe",
"SWIndex_IntPumpe","KM_Error_PumpeIntern","K30_KennungIntPumpe","K30_KennungIntPumpeKM","Heizkreispumpe",
"Grundfos","UPM3","G-HE","GHE","Umschaltventil","Ventil","Hydraulik","Brenner","Burner","Flamme","Flame",
"Ionisation","Ionization","Geblaese","Gebläse","Fan","Gas","Zuendung","Zündung","Ignition","Stabilisierung",
"Stabilization","Modulation","Codierstecker","Kodierstecker","GWG","CodingPlug","EEPROM","XRAM",
"Remote_Procedure_Call","Firmware","Bootrom","Bootloader","Flash","Programming","Programmier","Software-Index",
"SWIndex","Aktorentest","Actuator","Service"
)
$addresses=@("0x0A35","0x0A3C","0x0A4C","0x0A50","0x0A54","0x1010","0x1030","0x1040","0x1070","0x27E5","0x27E6","0x27E7","0x27E8","0x27E9","0x5556","0x55E0","0x5730","0x5731","0x7500","0x7660","0x7663","0x7751","0x778A","0x778B","0x778E","0xA0C2","0xA152","0xA395")
$fwTerms=@("firmware","bootrom","bootloader","flash","device programming","programming","programmierung","software update","software-update",".ugw",".hex",".bin",".mot",".s19",".s28",".s37",".rom",".fw",".dfu",".img")
$textExt=@(".xml",".xsd",".config",".ini",".csv",".txt",".md",".json",".yaml",".yml",".ps1",".py",".cs",".vb",".js",".ts",".sql",".properties",".html",".htm",".aspx",".ascx",".asmx",".asax",".master",".sitemap",".browser",".reg",".inf",".h",".map",".rtf")
$peExt=@(".dll",".exe")
$binExt=@(".mdf",".ldf",".ecndat",".sys",".lib",".cat",".dat",".bin",".hex",".mot",".s19",".s28",".s37",".rom",".fw",".dfu",".img",".ugw")

$opt=[Text.RegularExpressions.RegexOptions]::IgnoreCase -bor [Text.RegularExpressions.RegexOptions]::CultureInvariant
$rx=[regex]::new((($terms+$addresses|ForEach-Object{[regex]::Escape($_)}) -join "|"),$opt)
$fw=[regex]::new((($fwTerms|ForEach-Object{[regex]::Escape($_)}) -join "|"),$opt)

$Root=Find-Root $Root
if(-not $OutputDir){$OutputDir=Join-Path ([Environment]::GetFolderPath("Desktop")) ("vitosoft-deep-research-"+(Get-Date -Format "yyyyMMdd-HHmmss"))}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$OutputDir=(Resolve-Path -LiteralPath $OutputDir).Path
$meta=Join-Path $OutputDir "metadata";New-Item -ItemType Directory -Path $meta -Force | Out-Null

$manifest=New-Object IO.StreamWriter((Join-Path $OutputDir "file-manifest.csv"),$false,[Text.UTF8Encoding]::new($true))
$text=New-Object IO.StreamWriter((Join-Path $OutputDir "text-research-hits.csv"),$false,[Text.UTF8Encoding]::new($true))
$pe=New-Object IO.StreamWriter((Join-Path $OutputDir "pe-manifest.csv"),$false,[Text.UTF8Encoding]::new($true))
$pei=New-Object IO.StreamWriter((Join-Path $OutputDir "pe-research-strings.csv"),$false,[Text.UTF8Encoding]::new($true))
$members=New-Object IO.StreamWriter((Join-Path $OutputDir "managed-members.csv"),$false,[Text.UTF8Encoding]::new($true))
$merr=New-Object IO.StreamWriter((Join-Path $OutputDir "managed-reflection-errors.csv"),$false,[Text.UTF8Encoding]::new($true))
$fwout=New-Object IO.StreamWriter((Join-Path $OutputDir "firmware-candidates.csv"),$false,[Text.UTF8Encoding]::new($true))
$binout=New-Object IO.StreamWriter((Join-Path $OutputDir "binary-research-strings.csv"),$false,[Text.UTF8Encoding]::new($true))
$allstr=$null
if(-not $SkipAllPEStrings){$allstr=New-Object IO.StreamWriter((Join-Path $OutputDir "pe-all-strings.tsv"),$false,[Text.UTF8Encoding]::new($true));$tab=[char]9;$allstr.WriteLine("Root"+$tab+"RelativePath"+$tab+"Encoding"+$tab+"Offset"+$tab+"Text")}

Csv $manifest @("Root","RelativePath","Extension","SizeBytes","LastWriteUtc","SHA256","ResearchNameHit","FirmwareNameHit")
Csv $text @("Root","RelativePath","Line","KeywordsOrAddresses","Text")
Csv $pe @("Root","RelativePath","SizeBytes","SHA256","FileVersion","ProductVersion","CompanyName","ProductName","FileDescription","OriginalFilename","IsManaged","ManagedAssemblyName","ManagedAssemblyVersion")
Csv $pei @("Root","RelativePath","Encoding","Offset","KeywordsOrAddresses","Text")
Csv $members @("Root","RelativePath","Assembly","AssemblyVersion","Type","TypeKind","MemberKind","Member","Signature")
Csv $merr @("Root","RelativePath","Stage","Error")
Csv $fwout @("Root","RelativePath","SizeBytes","SHA256","Reason","Evidence")
Csv $binout @("Root","RelativePath","Encoding","Offset","KeywordsOrAddresses","Text")

$stats=[ordered]@{files=0;hashed=0;text_hits=0;pe_files=0;pe_strings=0;pe_research_strings=0;managed_files=0;managed_members=0;firmware_candidates=0;binary_research_strings=0}

try{
  Write-Host "Vitosoft deep research collector" -ForegroundColor Cyan
  Write-Host "Root: $Root"
  Write-Host "Output: $OutputDir"
  $files=@(Get-ChildItem -LiteralPath $Root -File -Recurse -ErrorAction SilentlyContinue)
  Write-Host ("Found {0} files." -f $files.Count) -ForegroundColor Cyan
  $sw=[Diagnostics.Stopwatch]::StartNew();$next=$ProgressSeconds;$i=0

  foreach($f in $files){
    $i++;$stats.files++;$rel=RelPath $Root $f.FullName;$ext=$f.Extension.ToLowerInvariant()
    if($sw.Elapsed.TotalSeconds -ge $next){$pct=[Math]::Round(($i/[double]$files.Count)*100,1);Write-Host ("[{0}/{1} {2,5}%] {3} | text {4} | PE strings {5}" -f $i,$files.Count,$pct,$rel,$stats.text_hits,$stats.pe_strings);$next=$sw.Elapsed.TotalSeconds+$ProgressSeconds}
    try{$sha=(Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash.ToLowerInvariant();$stats.hashed++}catch{$sha="<hash-error>"}
    $rname=$rx.IsMatch($rel);$fname=$fw.IsMatch($rel) -or ($ext -in @(".bin",".hex",".mot",".s19",".s28",".s37",".rom",".fw",".dfu",".img",".ugw"))
    Csv $manifest @($Root,$rel,$ext,$f.Length,$f.LastWriteTimeUtc.ToString("o"),$sha,$rname,$fname)
    if($fname){Csv $fwout @($Root,$rel,$f.Length,$sha,"filename-or-extension",$rel);$stats.firmware_candidates++}

    if($textExt -contains $ext){
      $reader=$null
      try{$reader=New-Object IO.StreamReader($f.FullName,$true);$ln=0;while(-not $reader.EndOfStream){$line=$reader.ReadLine();$ln++;if(-not $rx.IsMatch($line)){continue};$m=@($rx.Matches($line)|ForEach-Object{$_.Value}|Select-Object -Unique);Csv $text @($Root,$rel,$ln,($m -join ";"),(OneLine $line));$stats.text_hits++;if($fw.IsMatch($line)){$fm=@($fw.Matches($line)|ForEach-Object{$_.Value}|Select-Object -Unique);Csv $fwout @($Root,$rel,$f.Length,$sha,"text-content",(($fm -join ";")+" | "+(OneLine $line)));$stats.firmware_candidates++}}}
      catch{Csv $text @($Root,$rel,0,"<read-error>",$_.Exception.Message)}
      finally{if($reader){$reader.Dispose()}}
    }

    if($peExt -contains $ext){
      $stats.pe_files++;$vi=$f.VersionInfo;$managed=$false;$aname="";$aver=""
      try{$an=[Reflection.AssemblyName]::GetAssemblyName($f.FullName);$managed=$true;$aname=$an.Name;$aver=[string]$an.Version;$stats.managed_files++}catch{}
      Csv $pe @($Root,$rel,$f.Length,$sha,$vi.FileVersion,$vi.ProductVersion,$vi.CompanyName,$vi.ProductName,$vi.FileDescription,$vi.OriginalFilename,$managed,$aname,$aver)
      try{$bytes=[IO.File]::ReadAllBytes($f.FullName);foreach($s in Strings $bytes $MinStringLength){$clean=OneLine $s.Text;if(-not $SkipAllPEStrings){$tab=[char]9;$allstr.WriteLine($Root+$tab+$rel+$tab+$s.Enc+$tab+$s.Off+$tab+($clean -replace [string]$tab," "));$stats.pe_strings++};if($rx.IsMatch($clean)){$m=@($rx.Matches($clean)|ForEach-Object{$_.Value}|Select-Object -Unique);Csv $pei @($Root,$rel,$s.Enc,$s.Off,($m -join ";"),$clean);$stats.pe_research_strings++};if($fw.IsMatch($clean)){$fm=@($fw.Matches($clean)|ForEach-Object{$_.Value}|Select-Object -Unique);Csv $fwout @($Root,$rel,$f.Length,$sha,"pe-string",(($fm -join ";")+" | "+$clean));$stats.firmware_candidates++}}}catch{Csv $pei @($Root,$rel,"<read-error>",0,"",$_.Exception.Message)}
    }elseif($binExt -contains $ext){
      try{$bytes=[IO.File]::ReadAllBytes($f.FullName);foreach($s in Strings $bytes $MinStringLength){$clean=OneLine $s.Text;if($rx.IsMatch($clean)){$m=@($rx.Matches($clean)|ForEach-Object{$_.Value}|Select-Object -Unique);Csv $binout @($Root,$rel,$s.Enc,$s.Off,($m -join ";"),$clean);$stats.binary_research_strings++};if($fw.IsMatch($clean)){$fm=@($fw.Matches($clean)|ForEach-Object{$_.Value}|Select-Object -Unique);Csv $fwout @($Root,$rel,$f.Length,$sha,"binary-string",(($fm -join ";")+" | "+$clean));$stats.firmware_candidates++}}}catch{Csv $binout @($Root,$rel,"<read-error>",0,"",$_.Exception.Message)}
    }
  }

  if(-not $SkipManagedMembers){
    Write-Host "Managed type/method inventory..." -ForegroundColor Cyan
    foreach($f in $files|Where-Object{$_.Extension.ToLowerInvariant() -in $peExt}){
      $rel=RelPath $Root $f.FullName
      try{$an=[Reflection.AssemblyName]::GetAssemblyName($f.FullName)}catch{continue}
      try{$asm=[Reflection.Assembly]::ReflectionOnlyLoadFrom($f.FullName);try{$types=@($asm.GetTypes())}catch [Reflection.ReflectionTypeLoadException]{$types=@($_.Exception.Types|Where-Object{$_});foreach($e in $_.Exception.LoaderExceptions){Csv $merr @($Root,$rel,"GetTypes",$e.Message)}};$flags=[Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::NonPublic -bor [Reflection.BindingFlags]::Instance -bor [Reflection.BindingFlags]::Static -bor [Reflection.BindingFlags]::DeclaredOnly;foreach($t in $types){$kind=if($t.IsInterface){"interface"}elseif($t.IsEnum){"enum"}elseif($t.IsValueType){"struct"}else{"class"};Csv $members @($Root,$rel,$an.Name,[string]$an.Version,$t.FullName,$kind,"type",$t.Name,[string]$t.BaseType);$stats.managed_members++;foreach($m in $t.GetMethods($flags)){$p=@($m.GetParameters()|ForEach-Object{([string]$_.ParameterType)+" "+$_.Name}) -join ", ";Csv $members @($Root,$rel,$an.Name,[string]$an.Version,$t.FullName,$kind,"method",$m.Name,(([string]$m.ReturnType)+" "+$m.Name+"("+$p+")"));$stats.managed_members++};foreach($p in $t.GetProperties($flags)){Csv $members @($Root,$rel,$an.Name,[string]$an.Version,$t.FullName,$kind,"property",$p.Name,(([string]$p.PropertyType)+" "+$p.Name));$stats.managed_members++};foreach($q in $t.GetFields($flags)){Csv $members @($Root,$rel,$an.Name,[string]$an.Version,$t.FullName,$kind,"field",$q.Name,(([string]$q.FieldType)+" "+$q.Name));$stats.managed_members++}}}catch{Csv $merr @($Root,$rel,"ReflectionOnlyLoadFrom",$_.Exception.Message)}
    }
  }

  $dp=Core $Root "DPDefinitions.xml" @("Support\DP\DPDefinitions.xml","MobileClient\Config\DPDefinitions.xml")
  $et=Core $Root "ecnEventType.xml" @("MobileClient\Config\ecnEventType.xml")
  $de=Core $Root "Textresource_de.xml" @("Web\XmlDocuments\Textresource_de.xml","MobileClient\Config\Textresource_de.xml")
  $en=Core $Root "Textresource_en.xml" @("Web\XmlDocuments\Textresource_en.xml","MobileClient\Config\Textresource_en.xml")
  $py=PythonCmd
  $ex=Join-Path $PSScriptRoot "extract-vitosoft-deep-metadata.py"
  if(-not(Test-Path -LiteralPath $ex -PathType Leaf)){$ex=Join-Path $env:TEMP "extract-vitosoft-deep-metadata.py";Invoke-WebRequest -Uri "https://raw.githubusercontent.com/SaulGoodman1337/optolink/main/tools/extract-vitosoft-deep-metadata.py" -OutFile $ex}
  $norm="skipped"
  if($dp -and $et -and $py){$a=@();$a+=$py.Args;$a+=@($ex,"--dp-definitions",$dp,"--event-types",$et,"--device",$Device,"--out-dir",$meta);if($de){$a+=@("--textresource-de",$de)};if($en){$a+=@("--textresource-en",$en)};& $py.Exe @a;if($LASTEXITCODE -eq 0){$norm="ok"}else{$norm="failed:$LASTEXITCODE"}}

  $tool=[ordered]@{powershell=$PSVersionTable.PSVersion.ToString();python=if($py){$py.Exe+" "+($py.Args -join " ")}else{$null};sqlcmd=if(Get-Command sqlcmd.exe -ErrorAction SilentlyContinue){(Get-Command sqlcmd.exe).Source}else{$null};sqllocaldb=if(Get-Command sqllocaldb.exe -ErrorAction SilentlyContinue){(Get-Command sqllocaldb.exe).Source}else{$null};ildasm=if(Get-Command ildasm.exe -ErrorAction SilentlyContinue){(Get-Command ildasm.exe).Source}else{$null};ilspycmd=if(Get-Command ilspycmd.exe -ErrorAction SilentlyContinue){(Get-Command ilspycmd.exe).Source}else{$null};dumpbin=if(Get-Command dumpbin.exe -ErrorAction SilentlyContinue){(Get-Command dumpbin.exe).Source}else{$null}}
  $tool|ConvertTo-Json -Depth 4|Set-Content -LiteralPath (Join-Path $OutputDir "tooling.json") -Encoding UTF8
  $summary=[ordered]@{generated_utc=(Get-Date).ToUniversalTime().ToString("o");root=$Root;device=$Device;device_id_hex=$DeviceIdHex;stats=$stats;metadata_normalizer=$norm;core=[ordered]@{DPDefinitions=$dp;ecnEventType=$et;Textresource_de=$de;Textresource_en=$en}}
  $summary|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $OutputDir "summary.json") -Encoding UTF8
  @"
Vitosoft deep research bundle
Target: $Device / $DeviceIdHex

Derived data only; raw vendor DLL/EXE binaries are not copied.

Key files:
 file-manifest.csv
 text-research-hits.csv
 pe-manifest.csv
 pe-all-strings.tsv
 pe-research-strings.csv
 managed-members.csv
 managed-reflection-errors.csv
 binary-research-strings.csv
 firmware-candidates.csv
 metadata/

Commit normalized metadata, hashes, symbol/member inventories and conclusions.
Do not commit raw proprietary binaries or firmware images to a public repository.
"@|Set-Content -LiteralPath (Join-Path $OutputDir "README.txt") -Encoding UTF8

  foreach($w in @($manifest,$text,$pe,$pei,$members,$merr,$fwout,$binout,$allstr)){if($w){$w.Flush()}}
  $zip=$OutputDir+".zip";if(Test-Path -LiteralPath $zip){Remove-Item -LiteralPath $zip -Force}
  Compress-Archive -Path (Join-Path $OutputDir "*") -DestinationPath $zip -Force
  Write-Host "Finished: $zip" -ForegroundColor Green
}
finally{
  foreach($w in @($manifest,$text,$pe,$pei,$members,$merr,$fwout,$binout,$allstr)){if($w){try{$w.Dispose()}catch{}}}
}

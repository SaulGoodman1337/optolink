param(
  [string]$Root = "",
  [string]$OutputDir = "",
  [int]$ConnectTimeoutSeconds = 4,
  [int]$MaxRowsPerTable = 0
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

function CsvEscape {
  param([object]$Value)
  if ($null -eq $Value -or $Value -is [DBNull]) {
    return '"<NULL>"'
  }

  if ($Value -is [byte[]]) {
    $s = "base64:" + [Convert]::ToBase64String($Value)
  } elseif ($Value -is [DateTime]) {
    $s = $Value.ToUniversalTime().ToString("o")
  } else {
    $s = [string]$Value
  }

  return '"' + ($s -replace '"','""') + '"'
}

function Safe-Name {
  param([string]$Value)
  if (-not $Value) { return "unnamed" }
  $bad = [IO.Path]::GetInvalidFileNameChars()
  $out = $Value
  foreach ($c in $bad) {
    $out = $out.Replace([string]$c, "_")
  }
  return $out
}

function Redact-ConnectionString {
  param([string]$ConnectionString)
  try {
    $b = New-Object System.Data.SqlClient.SqlConnectionStringBuilder($ConnectionString)
    if ($b.ContainsKey("Password")) { $b.Password = "<redacted>" }
    if ($b.ContainsKey("Pwd")) { $b["Pwd"] = "<redacted>" }
    return $b.ConnectionString
  } catch {
    return ($ConnectionString -replace '(?i)(Password|Pwd)\s*=\s*[^;]+','$1=<redacted>')
  }
}

function Write-DataReaderCsv {
  param(
    [System.Data.SqlClient.SqlDataReader]$Reader,
    [string]$Path,
    [string[]]$Keywords = @(),
    [System.IO.StreamWriter]$HitWriter = $null,
    [string]$SourceLabel = ""
  )

  $enc = New-Object Text.UTF8Encoding($true)
  $writer = New-Object IO.StreamWriter($Path,$false,$enc)
  $rowNumber = 0

  try {
    $headers = @()
    for ($i=0; $i -lt $Reader.FieldCount; $i++) {
      $headers += (CsvEscape $Reader.GetName($i))
    }
    $writer.WriteLine(($headers -join ","))

    while ($Reader.Read()) {
      $rowNumber++
      $values = New-Object object[] $Reader.FieldCount
      $Reader.GetValues($values) | Out-Null
      $writer.WriteLine((($values | ForEach-Object { CsvEscape $_ }) -join ","))

      if ($HitWriter -and $Keywords.Count -gt 0) {
        for ($i=0; $i -lt $Reader.FieldCount; $i++) {
          $v = $values[$i]
          if ($null -eq $v -or $v -is [DBNull] -or $v -is [byte[]]) { continue }
          $s = [string]$v
          foreach ($kw in $Keywords) {
            if ($s.IndexOf($kw,[StringComparison]::OrdinalIgnoreCase) -ge 0) {
              $HitWriter.WriteLine((
                (CsvEscape $SourceLabel) + "," +
                (CsvEscape $rowNumber) + "," +
                (CsvEscape $Reader.GetName($i)) + "," +
                (CsvEscape $kw) + "," +
                (CsvEscape $s)
              ))
              break
            }
          }
        }
      }
    }
  } finally {
    $writer.Dispose()
  }

  return $rowNumber
}

function Invoke-QueryToCsv {
  param(
    [System.Data.SqlClient.SqlConnection]$Connection,
    [string]$Query,
    [string]$Path,
    [int]$TimeoutSeconds = 60
  )

  $cmd = $Connection.CreateCommand()
  $cmd.CommandText = $Query
  $cmd.CommandTimeout = $TimeoutSeconds
  $reader = $cmd.ExecuteReader()
  try {
    return Write-DataReaderCsv -Reader $reader -Path $Path
  } finally {
    $reader.Close()
    $cmd.Dispose()
  }
}

function Get-DataTable {
  param(
    [System.Data.SqlClient.SqlConnection]$Connection,
    [string]$Query,
    [int]$TimeoutSeconds = 60
  )
  $cmd = $Connection.CreateCommand()
  $cmd.CommandText = $Query
  $cmd.CommandTimeout = $TimeoutSeconds
  $da = New-Object System.Data.SqlClient.SqlDataAdapter($cmd)
  $dt = New-Object System.Data.DataTable
  try {
    [void]$da.Fill($dt)
  } finally {
    $da.Dispose()
    $cmd.Dispose()
  }
  return ,$dt
}

function Add-Candidate {
  param(
    [System.Collections.ArrayList]$List,
    [string]$ConnectionString,
    [string]$Source
  )

  if (-not $ConnectionString) { return }
  try {
    $b = New-Object System.Data.SqlClient.SqlConnectionStringBuilder($ConnectionString)
  } catch {
    return
  }

  if ($b.ContainsKey("AttachDbFilename") -and $b.AttachDBFilename) {
    [void]$script:SkippedAttach.Add([pscustomobject]@{
      Source=$Source
      Reason="AttachDbFilename present; automatic attach intentionally skipped"
      ConnectionString=(Redact-ConnectionString $ConnectionString)
    })
    return
  }

  if (-not $b.DataSource) { return }

  $key = ($b.DataSource + "|" + $b.InitialCatalog + "|" + $b.UserID).ToLowerInvariant()
  foreach ($existing in $List) {
    if ($existing.Key -eq $key) { return }
  }

  [void]$List.Add([pscustomobject]@{
    Key=$key
    Source=$Source
    ConnectionString=$ConnectionString
    DataSource=$b.DataSource
    InitialCatalog=$b.InitialCatalog
  })
}

function Export-Database {
  param(
    [string]$ConnectionString,
    [string]$DatabaseName,
    [string]$Destination,
    [int]$MaxRows
  )

  New-Item -ItemType Directory -Path $Destination -Force | Out-Null
  New-Item -ItemType Directory -Path (Join-Path $Destination "tables") -Force | Out-Null
  New-Item -ItemType Directory -Path (Join-Path $Destination "priority") -Force | Out-Null

  $b = New-Object System.Data.SqlClient.SqlConnectionStringBuilder($ConnectionString)
  $b.InitialCatalog = $DatabaseName
  $b.ConnectTimeout = $ConnectTimeoutSeconds
  $b.ApplicationName = "VitosoftPrivateCollector"
  if ($b.ContainsKey("AttachDbFilename")) { $b.Remove("AttachDbFilename") | Out-Null }

  $conn = New-Object System.Data.SqlClient.SqlConnection($b.ConnectionString)
  $conn.Open()

  $hitPath = Join-Path $Destination "keyword-hits.csv"
  $hitWriter = New-Object IO.StreamWriter($hitPath,$false,[Text.UTF8Encoding]::new($true))
  $hitWriter.WriteLine('"Source","Row","Column","Keyword","Value"')
  $keywords = @(
    "VDensHO1","20C2","WB2A",
    "ecnUpdateDefinition","ecnDeviceSoftwareUpdate",
    "softwareupdate","ReadyForUpdate","BeginUpdate","EndUpdate",
    "DeviceTypeId","UsingIdentification","UpdateUsingIdentification"
  )

  try {
    $metadataQueries = [ordered]@{
      "database-info.csv" = @"
SELECT
  DB_NAME() AS DatabaseName,
  DATABASEPROPERTYEX(DB_NAME(),'Status') AS Status,
  DATABASEPROPERTYEX(DB_NAME(),'Recovery') AS RecoveryModel,
  DATABASEPROPERTYEX(DB_NAME(),'Collation') AS Collation,
  DATABASEPROPERTYEX(DB_NAME(),'Version') AS InternalVersion;
"@
      "database-files.csv" = @"
SELECT file_id, name, type_desc, physical_name, size, max_size, growth
FROM sys.database_files
ORDER BY file_id;
"@
      "tables.csv" = @"
SELECT
  s.name AS SchemaName,
  t.name AS TableName,
  t.object_id,
  t.create_date,
  t.modify_date
FROM sys.tables t
JOIN sys.schemas s ON s.schema_id=t.schema_id
ORDER BY s.name,t.name;
"@
      "columns.csv" = @"
SELECT
  s.name AS SchemaName,
  t.name AS TableName,
  c.column_id,
  c.name AS ColumnName,
  ty.name AS TypeName,
  c.max_length,
  c.precision,
  c.scale,
  c.is_nullable,
  c.is_identity,
  c.is_computed
FROM sys.tables t
JOIN sys.schemas s ON s.schema_id=t.schema_id
JOIN sys.columns c ON c.object_id=t.object_id
JOIN sys.types ty ON ty.user_type_id=c.user_type_id
ORDER BY s.name,t.name,c.column_id;
"@
      "indexes.csv" = @"
SELECT
  s.name AS SchemaName,
  t.name AS TableName,
  i.name AS IndexName,
  i.type_desc,
  i.is_unique,
  i.is_primary_key,
  i.is_unique_constraint,
  c.name AS ColumnName,
  ic.key_ordinal,
  ic.is_included_column
FROM sys.tables t
JOIN sys.schemas s ON s.schema_id=t.schema_id
JOIN sys.indexes i ON i.object_id=t.object_id
LEFT JOIN sys.index_columns ic ON ic.object_id=i.object_id AND ic.index_id=i.index_id
LEFT JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id
WHERE i.index_id > 0
ORDER BY s.name,t.name,i.index_id,ic.key_ordinal,ic.index_column_id;
"@
      "foreign-keys.csv" = @"
SELECT
  fk.name AS ForeignKey,
  sch1.name AS ParentSchema,
  tab1.name AS ParentTable,
  col1.name AS ParentColumn,
  sch2.name AS ReferencedSchema,
  tab2.name AS ReferencedTable,
  col2.name AS ReferencedColumn
FROM sys.foreign_key_columns fkc
JOIN sys.foreign_keys fk ON fk.object_id=fkc.constraint_object_id
JOIN sys.tables tab1 ON tab1.object_id=fkc.parent_object_id
JOIN sys.schemas sch1 ON sch1.schema_id=tab1.schema_id
JOIN sys.columns col1 ON col1.object_id=fkc.parent_object_id AND col1.column_id=fkc.parent_column_id
JOIN sys.tables tab2 ON tab2.object_id=fkc.referenced_object_id
JOIN sys.schemas sch2 ON sch2.schema_id=tab2.schema_id
JOIN sys.columns col2 ON col2.object_id=fkc.referenced_object_id AND col2.column_id=fkc.referenced_column_id
ORDER BY sch1.name,tab1.name,fk.name,fkc.constraint_column_id;
"@
      "sql-modules.csv" = @"
SELECT
  s.name AS SchemaName,
  o.name AS ObjectName,
  o.type_desc,
  o.create_date,
  o.modify_date,
  m.definition
FROM sys.objects o
JOIN sys.schemas s ON s.schema_id=o.schema_id
JOIN sys.sql_modules m ON m.object_id=o.object_id
ORDER BY o.type_desc,s.name,o.name;
"@
    }

    foreach ($name in $metadataQueries.Keys) {
      try {
        [void](Invoke-QueryToCsv -Connection $conn -Query $metadataQueries[$name] -Path (Join-Path $Destination $name) -TimeoutSeconds 120)
      } catch {
        $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $Destination ($name + ".error.txt")) -Encoding UTF8
      }
    }

    $tables = Get-DataTable -Connection $conn -Query @"
SELECT s.name AS SchemaName,t.name AS TableName
FROM sys.tables t
JOIN sys.schemas s ON s.schema_id=t.schema_id
ORDER BY s.name,t.name;
"@

    $counts = New-Object IO.StreamWriter((Join-Path $Destination "table-row-counts.csv"),$false,[Text.UTF8Encoding]::new($true))
    $counts.WriteLine('"Schema","Table","RowsExported","CountBig","Error"')

    try {
      foreach ($row in $tables.Rows) {
        $schema = [string]$row.SchemaName
        $table = [string]$row.TableName
        $qualified = "[" + $schema.Replace("]","]]") + "].[" + $table.Replace("]","]]") + "]"
        $safe = (Safe-Name ($schema + "__" + $table)) + ".csv"
        $outPath = Join-Path (Join-Path $Destination "tables") $safe

        $top = ""
        if ($MaxRows -gt 0) { $top = "TOP (" + $MaxRows + ") " }
        $query = "SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED; SELECT " + $top + "* FROM " + $qualified + ";"

        $exported = 0
        $countBig = ""
        $err = ""

        try {
          $cmd = $conn.CreateCommand()
          $cmd.CommandText = $query
          $cmd.CommandTimeout = 300
          $reader = $cmd.ExecuteReader()
          try {
            $exported = Write-DataReaderCsv -Reader $reader -Path $outPath -Keywords $keywords -HitWriter $hitWriter -SourceLabel ($schema + "." + $table)
          } finally {
            $reader.Close()
            $cmd.Dispose()
          }

          $countCmd = $conn.CreateCommand()
          $countCmd.CommandText = "SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED; SELECT COUNT_BIG(*) FROM " + $qualified + ";"
          $countCmd.CommandTimeout = 300
          try { $countBig = [string]$countCmd.ExecuteScalar() } finally { $countCmd.Dispose() }

          if ($table -ieq "ecnUpdateDefinition" -or $table -ieq "ecnDeviceSoftwareUpdate") {
            Copy-Item -LiteralPath $outPath -Destination (Join-Path (Join-Path $Destination "priority") $safe) -Force
          }
        } catch {
          $err = $_.Exception.Message
          $_.Exception.ToString() | Set-Content -LiteralPath ($outPath + ".error.txt") -Encoding UTF8
        }

        $counts.WriteLine((
          (CsvEscape $schema) + "," +
          (CsvEscape $table) + "," +
          (CsvEscape $exported) + "," +
          (CsvEscape $countBig) + "," +
          (CsvEscape $err)
        ))
      }
    } finally {
      $counts.Dispose()
    }
  } finally {
    $hitWriter.Dispose()
    $conn.Close()
    $conn.Dispose()
  }
}

$Root = Find-VitosoftRoot $Root
if (-not $OutputDir) {
  $OutputDir = Join-Path ([Environment]::GetFolderPath("Desktop")) ("vitosoft-sql-readonly-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$OutputDir = (Resolve-Path -LiteralPath $OutputDir).Path
New-Item -ItemType Directory -Path (Join-Path $OutputDir "raw-database") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $OutputDir "exports") -Force | Out-Null

Write-Host "Vitosoft SQL read-only collector" -ForegroundColor Cyan
Write-Host "Root:   $Root"
Write-Host "Output: $OutputDir"

# Preserve MDF/LDF bytes first.
$dbFiles = @(Get-ChildItem -LiteralPath $Root -File -Recurse -ErrorAction SilentlyContinue | Where-Object {
  $_.Extension -in @(".mdf",".ldf")
})
foreach ($f in $dbFiles) {
  Copy-Item -LiteralPath $f.FullName -Destination (Join-Path (Join-Path $OutputDir "raw-database") $f.Name) -Force
}

# Inventory SQL-relevant config lines and candidate connection strings.
$connectionHits = New-Object IO.StreamWriter((Join-Path $OutputDir "connection-string-hits.csv"),$false,[Text.UTF8Encoding]::new($true))
$connectionHits.WriteLine('"File","Line","RedactedText"')

$candidates = New-Object System.Collections.ArrayList
$script:SkippedAttach = New-Object System.Collections.ArrayList
$configExt = @(".config",".xml",".ini",".txt",".json",".settings",".properties")
$connectionRegex = [regex]'(?i)connectionString\s*=\s*"([^"]+)"'
$connectionRegex2 = [regex]'(?i)(Data Source|Server)\s*=\s*[^;\r\n"]+(?:;[^\r\n"]*)?'

foreach ($f in Get-ChildItem -LiteralPath $Root -File -Recurse -ErrorAction SilentlyContinue) {
  if ($configExt -notcontains $f.Extension.ToLowerInvariant()) { continue }
  $reader = $null
  try {
    $reader = New-Object IO.StreamReader($f.FullName,$true)
    $lineNo = 0
    while (-not $reader.EndOfStream) {
      $line = $reader.ReadLine()
      $lineNo++
      if ($line -notmatch '(?i)(connectionString|Data Source\s*=|Server\s*=|Initial Catalog\s*=|Database\s*=|AttachDbFilename|\.mdf)') { continue }
      $connectionHits.WriteLine((CsvEscape $f.FullName) + "," + (CsvEscape $lineNo) + "," + (CsvEscape (Redact-ConnectionString $line)))

      foreach ($m in $connectionRegex.Matches($line)) {
        Add-Candidate -List $candidates -ConnectionString $m.Groups[1].Value -Source ($f.FullName + ":" + $lineNo)
      }

      if ($line -notmatch '(?i)connectionString\s*=') {
        foreach ($m in $connectionRegex2.Matches($line)) {
          Add-Candidate -List $candidates -ConnectionString $m.Value -Source ($f.FullName + ":" + $lineNo)
        }
      }
    }
  } catch {
  } finally {
    if ($reader) { $reader.Dispose() }
  }
}
$connectionHits.Dispose()

# Add common local servers without ever attaching an MDF.
foreach ($server in @(
  ".\SQLEXPRESS",
  "localhost\SQLEXPRESS",
  "(local)\SQLEXPRESS",
  "(localdb)\MSSQLLocalDB",
  "(localdb)\v11.0",
  ".",
  "(local)"
)) {
  $cs = "Data Source=" + $server + ";Initial Catalog=master;Integrated Security=SSPI;Connect Timeout=" + $ConnectTimeoutSeconds + ";Application Name=VitosoftPrivateCollector"
  Add-Candidate -List $candidates -ConnectionString $cs -Source "built-in-local-candidate"
}

$candidateWriter = New-Object IO.StreamWriter((Join-Path $OutputDir "sql-connection-candidates.csv"),$false,[Text.UTF8Encoding]::new($true))
$candidateWriter.WriteLine('"Source","DataSource","InitialCatalog","ConnectionStringRedacted"')
foreach ($c in $candidates) {
  $candidateWriter.WriteLine((
    (CsvEscape $c.Source) + "," +
    (CsvEscape $c.DataSource) + "," +
    (CsvEscape $c.InitialCatalog) + "," +
    (CsvEscape (Redact-ConnectionString $c.ConnectionString))
  ))
}
$candidateWriter.Dispose()

$skipWriter = New-Object IO.StreamWriter((Join-Path $OutputDir "skipped-attach-connections.csv"),$false,[Text.UTF8Encoding]::new($true))
$skipWriter.WriteLine('"Source","Reason","ConnectionStringRedacted"')
foreach ($s in $script:SkippedAttach) {
  $skipWriter.WriteLine((CsvEscape $s.Source) + "," + (CsvEscape $s.Reason) + "," + (CsvEscape $s.ConnectionString))
}
$skipWriter.Dispose()

# Capture local SQL tooling and services.
$tooling = [ordered]@{
  generated_utc=(Get-Date).ToUniversalTime().ToString("o")
  sqlcmd=if (Get-Command sqlcmd.exe -ErrorAction SilentlyContinue) { (Get-Command sqlcmd.exe).Source } else { $null }
  sqllocaldb=if (Get-Command sqllocaldb.exe -ErrorAction SilentlyContinue) { (Get-Command sqllocaldb.exe).Source } else { $null }
  powershell=$PSVersionTable.PSVersion.ToString()
}
$tooling | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $OutputDir "sql-tooling.json") -Encoding UTF8

try {
  Get-Service -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match 'SQL|MSSQL|Viessmann|Vito' -or $_.DisplayName -match 'SQL|Viessmann|Vito' } |
    Select-Object Name,DisplayName,Status,StartType |
    Export-Csv -LiteralPath (Join-Path $OutputDir "related-services.csv") -NoTypeInformation -Encoding UTF8
} catch {}

if (Get-Command sqllocaldb.exe -ErrorAction SilentlyContinue) {
  try { & sqllocaldb.exe i 2>&1 | Out-File -LiteralPath (Join-Path $OutputDir "sqllocaldb-instances.txt") -Encoding utf8 }
  catch { $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $OutputDir "sqllocaldb.error.txt") -Encoding UTF8 }
}

$attemptWriter = New-Object IO.StreamWriter((Join-Path $OutputDir "connection-attempts.csv"),$false,[Text.UTF8Encoding]::new($true))
$attemptWriter.WriteLine('"Source","DataSource","Connected","Database","Result"')

$exportedDatabases = @{}
foreach ($candidate in $candidates) {
  $b = $null
  try {
    $b = New-Object System.Data.SqlClient.SqlConnectionStringBuilder($candidate.ConnectionString)
    if ($b.ContainsKey("AttachDbFilename")) { $b.Remove("AttachDbFilename") | Out-Null }
    $b.InitialCatalog = "master"
    $b.ConnectTimeout = $ConnectTimeoutSeconds
    $b.ApplicationName = "VitosoftPrivateCollector"
    $conn = New-Object System.Data.SqlClient.SqlConnection($b.ConnectionString)
    $conn.Open()

    $dbs = Get-DataTable -Connection $conn -Query "SELECT name,state_desc,user_access_desc FROM sys.databases ORDER BY name;"
    $conn.Close()
    $conn.Dispose()

    $catalogHints = New-Object System.Collections.ArrayList
    if ($candidate.InitialCatalog -and $candidate.InitialCatalog -ne "master") { [void]$catalogHints.Add($candidate.InitialCatalog) }

    foreach ($row in $dbs.Rows) {
      $name = [string]$row.name
      if ($name -match '(?i)(viess|vito|ecn)') { [void]$catalogHints.Add($name) }
    }

    $uniqueDbs = @($catalogHints | Select-Object -Unique)
    if ($uniqueDbs.Count -eq 0) {
      $userDbs = @($dbs.Rows | Where-Object { $_.name -notin @("master","model","msdb","tempdb") } | ForEach-Object { [string]$_.name })
      if ($userDbs.Count -eq 1) { $uniqueDbs = $userDbs }
    }

    if ($uniqueDbs.Count -eq 0) {
      $attemptWriter.WriteLine((CsvEscape $candidate.Source) + "," + (CsvEscape $candidate.DataSource) + ',"true","master","connected; no target database inferred"')
      continue
    }

    foreach ($dbName in $uniqueDbs) {
      $key = ($candidate.DataSource + "|" + $dbName).ToLowerInvariant()
      if ($exportedDatabases.ContainsKey($key)) { continue }

      $dest = Join-Path (Join-Path $OutputDir "exports") ((Safe-Name $candidate.DataSource) + "__" + (Safe-Name $dbName))
      try {
        Export-Database -ConnectionString $candidate.ConnectionString -DatabaseName $dbName -Destination $dest -MaxRows $MaxRowsPerTable
        $exportedDatabases[$key] = $true
        $attemptWriter.WriteLine((CsvEscape $candidate.Source) + "," + (CsvEscape $candidate.DataSource) + ',"true",' + (CsvEscape $dbName) + ',"exported"')
      } catch {
        $attemptWriter.WriteLine((CsvEscape $candidate.Source) + "," + (CsvEscape $candidate.DataSource) + ',"true",' + (CsvEscape $dbName) + "," + (CsvEscape $_.Exception.Message))
      }
    }
  } catch {
    $attemptWriter.WriteLine((CsvEscape $candidate.Source) + "," + (CsvEscape $candidate.DataSource) + ',"false","","' + (($_.Exception.Message -replace '"','""')) + '"')
  }
}
$attemptWriter.Dispose()

@"
Vitosoft SQL collection
=======================

Safety model
------------
This collector does not attach, restore, modify, update, insert or delete any
database. It only:
  * preserves MDF/LDF bytes;
  * scans configuration for SQL connection metadata;
  * connects to already reachable SQL Server instances;
  * runs SELECT-only metadata and table exports.

Connections that require AttachDbFilename are intentionally recorded but not
opened automatically because attaching an MDF changes SQL Server state.

Priority research
-----------------
Look under exports/*/priority for:
  dbo.ecnUpdateDefinition
  dbo.ecnDeviceSoftwareUpdate

Also inspect keyword-hits.csv for:
  VDensHO1
  20C2
  WB2A
  softwareupdate
  ReadyForUpdate
  BeginUpdate
  EndUpdate

If no live SQL export was produced, the preserved raw-database MDF/LDF files
can be examined later on an isolated SQL Server instance or forensic copy.
"@ | Set-Content -LiteralPath (Join-Path $OutputDir "README.txt") -Encoding UTF8

Write-Host "SQL collection finished: $OutputDir" -ForegroundColor Green

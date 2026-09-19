param([Parameter(Mandatory=$true)][int]$AppProcessId, [int]$Seconds=30, [string]$Output="resource-report.json")
$ErrorActionPreference = "Stop"
if ($Seconds -lt 2 -or $Seconds -gt 300) { throw "Seconds must be 2..300." }
$rootProcess=Get-Process -Id $AppProcessId
$rootStart=$rootProcess.StartTime
$samples=@()
$previousCpu=@{}
$previousTime=Get-Date
for ($sampleIndex=0; $sampleIndex -lt $Seconds; $sampleIndex++) {
    $tree=Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name
    $owned=[System.Collections.Generic.HashSet[int]]::new()
    $currentRoot=Get-Process -Id $AppProcessId -ErrorAction SilentlyContinue
    if ($null -ne $currentRoot -and $currentRoot.StartTime -eq $rootStart) { [void]$owned.Add($AppProcessId) }
    do {
        $added=$false
        foreach ($entry in $tree) {
            if ($owned.Contains([int]$entry.ParentProcessId) -and $owned.Add([int]$entry.ProcessId)) { $added=$true }
        }
    } while ($added)
    $now=Get-Date
    $elapsed=($now-$previousTime).TotalSeconds
    $groups=@{}
    foreach ($group in @('app_and_children','obs','edge')) { $groups[$group]=@{process_count=0;working_set_bytes=0L;private_bytes=0L;cpu_percent=$null;cpu_delta=0.0} }
    foreach ($entry in $tree) {
        $group = if ($owned.Contains([int]$entry.ProcessId)) {'app_and_children'} elseif ($entry.Name -in @('obs64.exe','obs32.exe')) {'obs'} elseif ($entry.Name -eq 'msedge.exe') {'edge'} else {$null}
        if ($null -eq $group) { continue }
        $process=Get-Process -Id $entry.ProcessId -ErrorAction SilentlyContinue
        if ($null -eq $process) { continue }
        try { $identity="$($process.Id)-$($process.StartTime.Ticks)"; $cpu=$process.CPU } catch { continue }
        $groups[$group].process_count++
        $groups[$group].working_set_bytes += $process.WorkingSet64
        $groups[$group].private_bytes += $process.PrivateMemorySize64
        if ($previousCpu.ContainsKey($identity) -and $elapsed -gt 0) {
            $groups[$group].cpu_delta += [Math]::Max(0,$cpu-$previousCpu[$identity])
            $groups[$group].cpu_percent=0.0
        }
        $previousCpu[$identity]=$cpu
    }
    foreach ($group in $groups.Values) {
        if ($null -ne $group.cpu_percent) { $group.cpu_percent=[Math]::Round(100*$group.cpu_delta/$elapsed/[Environment]::ProcessorCount,3) }
        $group.Remove('cpu_delta')
    }
    $samples+=@{time=$now.ToString('o');groups=$groups}
    $previousTime=$now
    Start-Sleep -Seconds 1
}
@{schema_version=1;cpu_basis='percent of all logical processors';memory_note='Working-set sums can double-count shared pages; private bytes are reported separately.';root_pid=$AppProcessId;samples=$samples} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Output -Encoding utf8
Write-Output "Saved resource samples: $Output"

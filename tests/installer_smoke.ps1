# SPDX-License-Identifier: GPL-3.0-only
param([Parameter(Mandatory=$true)][string]$Installer)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$testRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot ('build\installer-test-' + [Guid]::NewGuid().ToString('N'))))
if (-not $testRoot.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe test path' }
$setupPath = (Resolve-Path -LiteralPath $Installer).Path
$uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{9C35AC65-C171-4B85-BB5B-6A2EA35C5A83}_is1'
if (Test-Path -LiteralPath $uninstallKey) { throw 'An installed copy exists. Do not run this test on a used installation.' }
New-Item -ItemType Directory -Path $testRoot | Out-Null
$target = Join-Path $testRoot 'Program'
$taskName = 'RouteRefit-Gebieden-installer-test-' + [Guid]::NewGuid().ToString('N')
$foreignTaskName = 'RouteRefit-Gebieden-installer-other-' + [Guid]::NewGuid().ToString('N')

function Invoke-TestSetup([string]$LogName) {
    $logPath = Join-Path $testRoot $LogName
    $setupProcess = Start-Process -FilePath $setupPath -WindowStyle Hidden -Wait -PassThru -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CURRENTUSER','/NOICONS','/TASKS=""',('/DIR="' + $target + '"'),('/LOG="' + $logPath + '"'))
    return $setupProcess.ExitCode
}
function Get-PrivateHashes {
    $result = @{}
    foreach ($name in @('Mijn GPX','Kaarten','voorkeuren.json')) {
        $path = Join-Path $target $name
        if (Test-Path -LiteralPath $path -PathType Container) {
            foreach ($file in Get-ChildItem -LiteralPath $path -File -Recurse) { $result[$file.FullName] = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash }
        } elseif (Test-Path -LiteralPath $path -PathType Leaf) { $result[$path] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash }
    }
    return $result
}
function Assert-PrivateHashes($Expected) {
    $actual = Get-PrivateHashes
    if ($actual.Count -ne $Expected.Count) { throw 'Private file count changed' }
    foreach ($name in $Expected.Keys) { if ($actual[$name] -ne $Expected[$name]) { throw 'Private file changed' } }
}

try {
    if ((Invoke-TestSetup 'install.log') -ne 0) { throw 'Initial install failed' }
    $installedExe = Join-Path $target 'RouteRefit.exe'
    if (-not (Test-Path -LiteralPath $installedExe)) { throw 'Stable executable missing' }
    $version = (Get-Item -LiteralPath $installedExe).VersionInfo
    if ($version.ProductName -ne 'RouteRefit') { throw 'Product identity missing' }
    if ((Get-ChildItem -LiteralPath (Join-Path $target 'Handleidingen') -Filter '*.pdf').Count -ne 6) { throw 'Manuals missing' }
    foreach ($name in @('Mijn GPX','Kaarten','voorkeuren.json')) { if (Test-Path -LiteralPath (Join-Path $target $name)) { throw 'Setup included or created personal data' } }
    New-Item -ItemType Directory -Path (Join-Path $target 'Mijn GPX\synthetic'),(Join-Path $target 'Kaarten\synthetic') | Out-Null
    '<gpx version="1.1"><trk><name>Synthetic installer test</name></trk></gpx>' | Set-Content -LiteralPath (Join-Path $target 'Mijn GPX\synthetic\route.gpx') -Encoding utf8
    'Synthetic edited route - retain exactly' | Set-Content -LiteralPath (Join-Path $target 'Mijn GPX\synthetic\edit.txt') -Encoding utf8
    'Synthetic map fixture - not real map data' | Set-Content -LiteralPath (Join-Path $target 'Kaarten\synthetic\map.bin') -Encoding utf8
    '{"language":"nl"}' | Set-Content -LiteralPath (Join-Path $target 'voorkeuren.json') -Encoding utf8
    $before = Get-PrivateHashes

    # An open program file must block installation; no forced process termination.
    $programLock = [IO.File]::Open($installedExe,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    try { if ((Invoke-TestSetup 'busy.log') -eq 0) { throw 'Installer ignored a locked application' } }
    finally { $programLock.Dispose() }
    Assert-PrivateHashes $before
    if ((Invoke-TestSetup 'upgrade.log') -ne 0) { throw 'Reinstall failed' }
    Assert-PrivateHashes $before

    # Triggerless test tasks never execute. Uninstall must remove only its own task.
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited
    $action = New-ScheduledTaskAction -Execute $installedExe -Argument '--package-worker synthetic-unused'
    Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal | Out-Null
    $foreignAction = New-ScheduledTaskAction -Execute (Join-Path $testRoot 'Other\RouteRefit.exe')
    Register-ScheduledTask -TaskName $foreignTaskName -Action $foreignAction -Principal $principal | Out-Null
    $uninstaller = [IO.Path]::GetFullPath((Join-Path $target 'unins000.exe'))
    if (-not $uninstaller.StartsWith($testRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe uninstall target' }
    $uninstallProcess = Start-Process -FilePath $uninstaller -WindowStyle Hidden -Wait -PassThru -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',('/LOG="' + (Join-Path $testRoot 'uninstall.log') + '"'))
    if ($uninstallProcess.ExitCode -ne 0) { throw 'Uninstall failed' }
    if (Test-Path -LiteralPath $installedExe) { throw 'Program was not uninstalled' }
    Assert-PrivateHashes $before
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) { throw 'Own background task was not removed' }
    if (-not (Get-ScheduledTask -TaskName $foreignTaskName -ErrorAction SilentlyContinue)) { throw 'Other installation task was removed' }
    if (Test-Path -LiteralPath $uninstallKey) { throw 'Uninstall registration remains' }
    Write-Output 'PASS: install, locked-file refusal, reinstall, personal-data preservation, uninstall, task isolation.'
    Write-Output ('Logs and retained synthetic data: ' + $testRoot)
} finally {
    foreach ($name in @($taskName,$foreignTaskName)) {
        if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) { Unregister-ScheduledTask -TaskName $name -Confirm:$false }
    }
}

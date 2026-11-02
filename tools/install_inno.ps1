# SPDX-License-Identifier: GPL-3.0-only
# Bootstrap only the pinned, signature-verified build tool; not part of RouteRefit runtime.
param([string]$Destination = (Join-Path $PSScriptRoot '..\build\inno'))
$ErrorActionPreference = 'Stop'
$destinationPath = [IO.Path]::GetFullPath($Destination)
$downloadFolder = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\build\compiler-download'))
New-Item -ItemType Directory -Path $downloadFolder -Force | Out-Null
$download = Join-Path $downloadFolder 'innosetup-7.1.1-x64.exe'
Invoke-WebRequest -Uri 'https://github.com/jrsoftware/issrc/releases/download/is-7_1_1/innosetup-7.1.1-x64.exe' -OutFile $download
$expected = '8A5A6711C3766A6E5FB74F280BA0E3551E719CE94538D901FDBD1F8F9920B3F0'
if ((Get-FileHash -LiteralPath $download -Algorithm SHA256).Hash -ne $expected) { throw 'Compiler checksum mismatch' }
$signature = Get-AuthenticodeSignature -LiteralPath $download
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Pyrsys B.V.') { throw 'Compiler signature mismatch' }
$process = Start-Process -FilePath $download -WindowStyle Hidden -Wait -PassThru -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CURRENTUSER','/NOICONS','/TASKS=""',('/DIR="' + $destinationPath + '"'))
if ($process.ExitCode -ne 0) { throw 'Compiler setup failed' }
$compiler = Join-Path $destinationPath 'ISCC.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw 'Compiler missing after setup' }
Write-Output $compiler

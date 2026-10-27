param(
  [string]$Version = "0.4.1",
  [int]$BuildNumber = 1
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$flutterCommand = Get-Command flutter.bat -ErrorAction SilentlyContinue
if ($null -eq $flutterCommand) {
  $flutterCommand = Get-Command flutter -ErrorAction SilentlyContinue
}
if ($null -eq $flutterCommand) {
  throw "Flutter executable was not found in PATH."
}
$flutter = $flutterCommand.Source
$source = Join-Path $root "build\windows\x64\runner\Release"
$releaseRoot = Join-Path $root "release"
$package = Join-Path $releaseRoot "Mup-Flutter-v$Version"
$archive = Join-Path $releaseRoot "Mup-Flutter-v$Version-windows-x64.zip"

& $flutter build windows --release --build-name $Version --build-number $BuildNumber
if ($LASTEXITCODE -ne 0) {
  throw "Flutter release build failed."
}

if (Test-Path -LiteralPath $package) {
  $resolved = (Resolve-Path -LiteralPath $package).Path
  $expectedParent = (Resolve-Path -LiteralPath $releaseRoot).Path
  if (-not $resolved.StartsWith($expectedParent, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to replace a package outside the release directory."
  }
  Remove-Item -LiteralPath $resolved -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $package | Out-Null
Copy-Item -Path (Join-Path $source "*") -Destination $package -Recurse -Force
$oldExe = Join-Path $package "Mup.exe"
$versionedExe = Join-Path $package "Mup-v$Version.exe"
Move-Item -LiteralPath $oldExe -Destination $versionedExe

if (Test-Path -LiteralPath $archive) {
  Remove-Item -LiteralPath $archive -Force
}
Compress-Archive -Path $package -DestinationPath $archive -CompressionLevel Optimal

Write-Output $package
Write-Output $archive

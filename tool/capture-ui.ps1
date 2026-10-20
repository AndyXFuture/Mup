param(
  [Parameter(Mandatory = $true)][string]$Name,
  [string]$AppArguments = "",
  [int]$WaitSeconds = 7
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $root "build\windows\x64\runner\Debug\Mup.exe"
$output = Join-Path $root "docs\$Name.png"

Get-Process -ErrorAction SilentlyContinue |
  Where-Object { $_.Path -like "$root\*" } |
  Stop-Process -Force

$process = Start-Process -FilePath $exe `
  -WorkingDirectory (Split-Path -Parent $exe) `
  -ArgumentList $AppArguments `
  -PassThru

for ($i = 0; $i -lt $WaitSeconds; $i++) {
  Start-Sleep -Seconds 1
  $process.Refresh()
  if ($process.HasExited) {
    throw "Mup exited before capture with code $($process.ExitCode)"
  }
  if ($process.MainWindowHandle -ne 0) {
    break
  }
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class MupUiCapture {
  [StructLayout(LayoutKind.Sequential)]
  public struct RECT {
    public int Left;
    public int Top;
    public int Right;
    public int Bottom;
  }
  [DllImport("user32.dll")]
  public static extern bool GetWindowRect(IntPtr window, out RECT rect);
  [DllImport("user32.dll")]
  public static extern bool MoveWindow(
      IntPtr window, int x, int y, int width, int height, bool repaint);
  [DllImport("user32.dll")]
  public static extern bool SetWindowPos(
      IntPtr window, IntPtr insertAfter, int x, int y, int width, int height,
      uint flags);
}
"@

$process.Refresh()
$window = $process.MainWindowHandle
[MupUiCapture]::MoveWindow($window, 100, 100, 1080, 720, $true) | Out-Null
[MupUiCapture]::SetWindowPos(
  $window, [IntPtr](-1), 100, 100, 1080, 720, 0x0040) | Out-Null
[MupUiCapture]::SetWindowPos(
  $window, [IntPtr](-2), 100, 100, 1080, 720, 0x0043) | Out-Null
Start-Sleep -Milliseconds 800

$screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$desktop = New-Object System.Drawing.Bitmap $screen.Width, $screen.Height
$graphics = [System.Drawing.Graphics]::FromImage($desktop)
$graphics.CopyFromScreen(
  $screen.Location, [System.Drawing.Point]::Empty, $screen.Size)
$graphics.Dispose()

$rect = New-Object MupUiCapture+RECT
[MupUiCapture]::GetWindowRect($window, [ref]$rect) | Out-Null
$crop = New-Object System.Drawing.Rectangle $rect.Left, $rect.Top, `
  ($rect.Right - $rect.Left), ($rect.Bottom - $rect.Top)
$windowImage = $desktop.Clone($crop, $desktop.PixelFormat)
$windowImage.Save($output, [System.Drawing.Imaging.ImageFormat]::Png)
$desktop.Dispose()
$windowImage.Dispose()

Write-Output $output

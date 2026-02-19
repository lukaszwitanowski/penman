Param(
    [string]$Version = "0.1.0"
)

$ErrorActionPreference = "Stop"

Write-Host "Installing build dependencies..."
python -m pip install --upgrade pip
pip install pyinstaller

Write-Host "Running quality gates..."
python -m compileall .
python -m unittest discover -s tests -v

Write-Host "Building executable..."
pyinstaller `
  --noconfirm `
  --clean `
  --name Penman `
  --windowed `
  main.py

$platform = "windows"
$artifactName = "Penman_${Version}_${platform}"
$artifactDir = Join-Path -Path "dist" -ChildPath $artifactName

if (Test-Path $artifactDir) {
    Remove-Item -Recurse -Force $artifactDir
}
New-Item -ItemType Directory -Path $artifactDir | Out-Null
Copy-Item -Recurse -Path "dist\\Penman\\*" -Destination $artifactDir

$zipPath = "dist\\${artifactName}.zip"
if (Test-Path $zipPath) {
    Remove-Item -Force $zipPath
}
Compress-Archive -Path "$artifactDir\\*" -DestinationPath $zipPath

Write-Host "Build completed: $zipPath"

# Create a backend-only shareable zip from the repo root.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$dest = Join-Path $root "excavation-risk-backend-poc.zip"
if (Test-Path $dest) { Remove-Item $dest -Force }

$staging = Join-Path $env:TEMP "excavation-risk-backend-staging"
if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
New-Item -ItemType Directory -Path $staging | Out-Null

$copy = @(
  @{ Src = "backend"; Dst = "backend" },
  @{ Src = "docs"; Dst = "docs" },
  @{ Src = "BACKEND_HANDOFF.md"; Dst = "BACKEND_HANDOFF.md" },
  @{ Src = "ZIP_CONTENTS.md"; Dst = "ZIP_CONTENTS.md" },
  @{ Src = "README.md"; Dst = "README.md" },
  @{ Src = "runtime.txt"; Dst = "runtime.txt" },
  @{ Src = "render.yaml"; Dst = "render.yaml" },
  @{ Src = ".gitignore"; Dst = ".gitignore" }
)

foreach ($item in $copy) {
  $srcPath = Join-Path $root $item.Src
  if (-not (Test-Path $srcPath)) { continue }
  $dstPath = Join-Path $staging $item.Dst
  Copy-Item -Path $srcPath -Destination $dstPath -Recurse -Force
}

$excludeDirNames = @(
  ".venv", "__pycache__", ".pytest_cache", "node_modules", "dist",
  ".cursor", ".vscode", ".idea"
)
Get-ChildItem -Path $staging -Recurse -Directory | Where-Object {
  $excludeDirNames -contains $_.Name
} | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Get-ChildItem -Path $staging -Recurse -Include ".env", "*.log" -File |
  Remove-Item -Force -ErrorAction SilentlyContinue

Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $dest -Force
Remove-Item $staging -Recurse -Force
Write-Host "Created $dest"

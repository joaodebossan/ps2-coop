# Baixa o Python portátil para Windows quando o usuário não tem Python instalado.
# Executado por iniciar.bat. Não instala nada no sistema.
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$root = Split-Path -Parent $PSScriptRoot
$destination = Join-Path $root "runtime\python"
$python = Join-Path $destination "python.exe"

if (Test-Path $python) {
    Write-Host "Python portátil já está pronto."
    exit 0
}

$version = "3.12.10"
$arch = if ($env:PROCESSOR_ARCHITECTURE -match "ARM64") { "arm64" } else { "amd64" }
$url = "https://www.python.org/ftp/python/$version/python-$version-embed-$arch.zip"
$zip = Join-Path $env:TEMP "ps2coop-python-$version-$arch.zip"

New-Item -ItemType Directory -Force -Path $destination | Out-Null
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

Write-Host "Baixando Python $version portátil ($arch)..."
try {
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $zip
    Expand-Archive -Force -Path $zip -DestinationPath $destination
} catch {
    Write-Error "Não foi possível baixar o Python portátil. Verifique a internet e tente de novo. Detalhe: $_"
    exit 1
} finally {
    Remove-Item -Force -ErrorAction SilentlyContinue $zip
}

# O Python embeddable usa pythonXY._pth e não adiciona a pasta do script ao
# sys.path. ".." aponta para a raiz do PS2 Co-op, onde fica o pacote ps2coop/.
$pth = Get-ChildItem -Path $destination -Filter "python*._pth" | Select-Object -First 1
if ($pth) {
    $lines = Get-Content -LiteralPath $pth.FullName
    if ($lines -notcontains "..") {
        Add-Content -LiteralPath $pth.FullName -Value ".."
    }
}

if (-not (Test-Path $python)) {
    Write-Error "O Python portátil não foi extraído corretamente."
    exit 1
}

Write-Host "Python portátil pronto em runtime\python."
exit 0

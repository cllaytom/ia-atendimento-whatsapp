# Atalho para rodar o worker da campanha sem precisar configurar o PATH.
#
#   .\campanha-whatsapp\start.ps1              -> simulacao
#   .\campanha-whatsapp\start.ps1 --parear     -> vincular aparelho (QR)
#   .\campanha-whatsapp\start.ps1 --enviar     -> envio real (exige liberacao)
#
# Se o Windows bloquear o script:
#   powershell -ExecutionPolicy Bypass -File .\campanha-whatsapp\start.ps1

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $Argumentos
)

$ErrorActionPreference = "Stop"

function Achar-Node {
    $cmd = Get-Command node -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $fnm = Join-Path $env:APPDATA "fnm\node-versions"
    if (Test-Path $fnm) {
        $versoes = Get-ChildItem $fnm -Directory |
            Where-Object { $_.Name -match "^v?\d+(\.\d+)+$" } |
            Sort-Object { [version]($_.Name.TrimStart("v")) } -Descending
        foreach ($versao in $versoes) {
            $candidato = Join-Path $versao.FullName "installation\node.exe"
            if (Test-Path $candidato) { return $candidato }
        }
    }
    return $null
}

$node = Achar-Node
if (-not $node) {
    Write-Host "Node.js nao encontrado." -ForegroundColor Red
    Write-Host "Instale com: winget install OpenJS.NodeJS.LTS"
    exit 1
}

$worker = Join-Path $PSScriptRoot "worker.cjs"
if (-not (Test-Path $worker)) {
    Write-Host "worker.cjs nao encontrado em $PSScriptRoot" -ForegroundColor Red
    exit 1
}

if (-not $Argumentos) { $Argumentos = @() }

Write-Host "node: $node" -ForegroundColor DarkGray
& $node $worker @Argumentos
exit $LASTEXITCODE

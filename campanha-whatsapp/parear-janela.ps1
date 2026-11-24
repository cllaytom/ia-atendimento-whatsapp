# Abre uma janela de terminal dedicada ao pareamento da campanha.
#
#   .\campanha-whatsapp\parear-janela.ps1
#
# Usa o perfil EXCLUSIVO da campanha (dados\campanha-sessao\session).
# O QR aparece nesta janela; nada e enviado durante o pareamento.

$ErrorActionPreference = "Continue"
$Host.UI.RawUI.WindowTitle = "Campanha ConnectTV - pareamento (perfil exclusivo)"

try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    chcp 65001 > $null
} catch { }

$raiz = Split-Path -Parent $PSScriptRoot
$log = Join-Path $raiz "dados\campanha-pareamento.log"

Write-Host "Perfil do Chrome: $raiz\dados\campanha-sessao\session" -ForegroundColor DarkGray
Write-Host "Este perfil e exclusivo da campanha; o Chrome padrao nao e usado." -ForegroundColor DarkGray
Write-Host ""

& powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "start.ps1") --parear 2>&1 |
    Tee-Object -FilePath $log

Write-Host ""
Write-Host "Fim do pareamento. Se apareceu 'pareado com o numero', pode fechar esta janela." -ForegroundColor Green
Write-Host "Se o QR ficou ilegivel, rode: .\campanha-whatsapp\start.ps1 --parear --mostrar" -ForegroundColor DarkGray

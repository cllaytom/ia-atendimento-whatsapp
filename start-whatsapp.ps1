# Atendimento automatico no WhatsApp (canal nao oficial)
# Primeira vez (escaneia o QR):   .\start-whatsapp.ps1 -Login
# Depois, para deixar atendendo:  .\start-whatsapp.ps1
param([switch]$Login)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)
if ($Login) {
  python -m app.atendimento.vigia_whatsapp --login
} else {
  python -m app.atendimento.vigia_whatsapp
}

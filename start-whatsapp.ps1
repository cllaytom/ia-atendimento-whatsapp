param([switch]$Login)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)
if ($Login) {
    python -m app.atendimento.whatsapp_local --login
} else {
    python -m app.atendimento.whatsapp_local
}

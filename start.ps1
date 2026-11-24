# sobe a API em modo desenvolvimento (local)
$env:PYTHONPATH = $PSScriptRoot

$banco = Join-Path $PSScriptRoot "dados\assinaturas.db"
if (-not (Test-Path $banco)) {
    $origem = "D:\area  nova\planilha clientes\GERENCIAMENTO DE ASSINATURAS IPTV 86.7 - Copia.xlsb"
    if (Test-Path $origem) {
        Write-Host "Banco nao encontrado. Importando $origem ..."
        python "$PSScriptRoot\scripts\importar_planilha.py" $origem
    } else {
        Write-Warning "Banco vazio e planilha de origem nao encontrada. Rode scripts\importar_planilha.py."
    }
}

# Porta da API. Troque aqui ou defina a variavel de ambiente PORTA.
$porta = if ($env:PORTA) { $env:PORTA } else { "8010" }

# Robo do WhatsApp da campanha em janela separada
$worker = Join-Path $PSScriptRoot "campanha-whatsapp\start.cmd"
if (Test-Path $worker) {
    Start-Process cmd.exe -ArgumentList "/k", "`"$worker`" --enviar"
} else {
    Write-Warning "Robo da campanha nao encontrado: $worker"
}

python -m uvicorn app.main:app --host 127.0.0.1 --port $porta --reload

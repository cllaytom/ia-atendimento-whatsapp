# sobe o Atendimento IA em modo desenvolvimento (local)
$env:PYTHONPATH = $PSScriptRoot

# Porta da API. Troque aqui ou defina a variavel de ambiente PORTA.
$porta = if ($env:PORTA) { $env:PORTA } else { "8010" }

python -m uvicorn app.main:app --host 127.0.0.1 --port $porta --reload

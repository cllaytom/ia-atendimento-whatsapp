$arquivo = Get-ChildItem -Path "D:\planilhas\ia atendimento" -Recurse -Filter "conhecimento.json" -File | Select-Object -First 1

if (-not $arquivo) {
    Write-Host "conhecimento.json nao encontrado."
    exit
}

Write-Host "Arquivo encontrado:"
Write-Host $arquivo.FullName

$copia = $arquivo.FullName + ".antes-aviso-sinal-2.bak"
Copy-Item $arquivo.FullName $copia -Force

$dados = Get-Content $arquivo.FullName -Raw -Encoding UTF8 | ConvertFrom-Json

$antigo = " Para a internet funcionar, seu celular precisa estar com sinal 4G, 5G ou LTE. Em 3G, H+, H, G, E ou sem sinal, a conexão pode não funcionar ou ficar instável."

$novo = "`n✅ Para a internet funcionar, seu celular precisa estar com sinal 4G, 5G ou LTE.`n❌ Em 3G, H+, H, G, E ou sem sinal, a conexão pode não funcionar ou ficar instável."

$alterado = $false

foreach ($item in $dados.entradas) {
    if ($item.pergunta -eq "Como funciona o teste gratis?") {
        if ($item.resposta -like "*4G, 5G ou LTE*") {
            $item.resposta = $item.resposta.Replace($antigo, "")
        }

        if ($item.resposta -notlike "*✅ Para a internet funcionar*") {
            $item.resposta = $item.resposta + $novo
            $alterado = $true
        }
    }
}

if ($alterado) {
    $json = $dados | ConvertTo-Json -Depth 10
    Set-Content -Path $arquivo.FullName -Value $json -Encoding UTF8
    Write-Host "Aviso atualizado com sucesso."
} else {
    Write-Host "Nao foi possivel atualizar. A pergunta do teste nao foi encontrada."
}
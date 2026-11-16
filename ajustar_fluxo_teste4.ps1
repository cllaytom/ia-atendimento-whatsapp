$m = "D:\planilhas\ia atendimento\app\atendimento\motor.py"

if (-not (Test-Path $m)) {
    Write-Host "motor.py nao encontrado."
    exit
}

Copy-Item $m ($m + ".antes-fluxo-teste4.bak") -Force

$conteudo = (Get-Content $m -Raw) -replace "`r`n", "`n"

$antigo = @'
        if not pergunta_simples:
            _atualizar_dados(conversa, teste=True)
'@ -replace "`r`n", "`n"

$novo = @'
        if not pergunta_simples:
            _atualizar_dados(conversa, teste=True)
            return iniciar_internet(db, conversa, texto, teste=True, contratar=True)
'@ -replace "`r`n", "`n"

if ($conteudo.Contains($antigo)) {
    $conteudo = $conteudo.Replace($antigo, $novo)
    Set-Content -Path $m -Value $conteudo -Encoding UTF8
    Write-Host "Fluxo de teste ajustado com sucesso."
} else {
    Write-Host "Nao encontrei o bloco. Nada foi alterado."
}
$m = "D:\planilhas\ia atendimento\app\atendimento\motor.py"

if (-not (Test-Path $m)) {
    Write-Host "motor.py nao encontrado."
    exit
}

Copy-Item $m ($m + ".antes-fluxo-teste5.bak") -Force

$conteudo = (Get-Content $m -Raw) -replace "`r`n", "`n"

$antigo = @'
        if (conversa.dados or {}).get("quer_contratar"):
            return transferir(db, conversa, _motivo_internet(conversa))
        conversa.etapa = INTERNET_CONFIRMAR
        return [_msg(db, conversa, "ia", oferta.confirmar_internet())]
'@ -replace "`r`n", "`n"

$novo = @'
        if (conversa.dados or {}).get("quer_contratar") and not (conversa.dados or {}).get("teste"):
            return transferir(db, conversa, _motivo_internet(conversa))
        conversa.etapa = INTERNET_CONFIRMAR
        return [_msg(db, conversa, "ia", oferta.confirmar_internet())]
'@ -replace "`r`n", "`n"

if ($conteudo.Contains($antigo)) {
    $conteudo = $conteudo.Replace($antigo, $novo)
    Set-Content -Path $m -Value $conteudo -Encoding UTF8
    Write-Host "Fluxo de teste ajustado com sucesso."
} else {
    Write-Host "Nao encontrei o bloco. Nada foi alterado."
}
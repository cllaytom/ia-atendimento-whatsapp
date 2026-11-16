$m = "D:\planilhas\ia atendimento\app\atendimento\motor.py"

if (-not (Test-Path $m)) {
    Write-Host "motor.py nao encontrado."
    exit
}

Copy-Item $m ($m + ".antes-fluxo-teste3.bak") -Force

$conteudo = (Get-Content $m -Raw) -replace "`r`n", "`n"

$antigo1 = @'
        if not pergunta_simples:
            _atualizar_dados(conversa, teste=True)
'@ -replace "`r`n", "`n"

$novo1 = @'
        if not pergunta_simples:
            _atualizar_dados(conversa, teste=True)
            return iniciar_internet(db, conversa, texto, teste=True, contratar=True)
'@ -replace "`r`n", "`n"

if ($conteudo.Contains($antigo1)) {
    $conteudo = $conteudo.Replace($antigo1, $novo1)
    Write-Host "Pedido de teste agora inicia a validacao."
} else {
    Write-Host "Nao encontrei o bloco 1. Nada foi alterado."
    exit
}

$antigo2 = @'
    confirmou = resposta_sim_nao(texto)
    if confirmou is True or quer_contratar(texto):
        _atualizar_dados(conversa, quer_contratar=True)
        return transferir(db, conversa, _motivo_internet(conversa))
'@ -replace "`r`n", "`n"

$novo2 = @'
    confirmou = resposta_sim_nao(texto)
    if confirmou is True or quer_contratar(texto):
        if (conversa.dados or {}).get("teste"):
            if not pode_criar(conversa.contato):
                return transferir(
                    db,
                    conversa,
                    "Cliente solicitou outro teste antes do intervalo de 48 horas",
                    aviso=(
                        "Para solicitar um novo teste, vou encaminhar você "
                        "para o atendimento humano."
                    ),
                )

            resultado = criar_teste(
                conversa.contato,
                os.environ.get("LINKSSH_TOKEN", ""),
            )

            if not resultado.get("ok"):
                return transferir(
                    db,
                    conversa,
                    "Falha ao criar teste SSH: " + str(resultado.get("erro")),
                    aviso=(
                        "Não consegui criar seu teste agora. "
                        "Vou encaminhar você para o atendimento humano."
                    ),
                )

            _atualizar_dados(
                conversa,
                teste_ssh_login=resultado["login"],
                teste_ssh_expira=resultado["expira"],
            )

            return [
                _msg(
                    db,
                    conversa,
                    "ia",
                    (
                        "Validação concluída. Seu teste SSH de 3 horas foi criado.\n\n"
                        f"Login: {resultado['login']}\n"
                        f"Senha: {resultado['senha']}\n"
                        f"Validade: {resultado['expira']}\n\n"
                        "Use esses dados no aplicativo para conectar."
                    ),
                )
            ]

        _atualizar_dados(conversa, quer_contratar=True)
        return transferir(db, conversa, _motivo_internet(conversa))
'@ -replace "`r`n", "`n"

if ($conteudo.Contains($antigo2)) {
    $conteudo = $conteudo.Replace($antigo2, $novo2)
    Set-Content -Path $m -Value $conteudo -Encoding UTF8
    Write-Host "Fluxo de teste ajustado com sucesso."
} else {
    Write-Host "Nao encontrei o bloco 2. Nada foi alterado."
}
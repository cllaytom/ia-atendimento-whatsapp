# CHANGELOG

## 2026-11-24

- Corrigida a duração do teste grátis de 4h para 3h em app/atendimento/oferta.py
- INTERNET_TRIAL_HORAS alterado de 4 para 3
- Mensagem de confirmação passa a usar a constante INTERNET_TRIAL_HORAS
- Commit: 4b763dccbf6cb0710cb5db573451e80fc77dd7d2
- Branch: correcao-teste-3h
- PR #1 aberto: Unifica a duração do teste grátis em 3 horas

## 2026-11-25

- Confirmado que a API de atendimento roda na porta 8033
- Confirmado que o robô whatsapp-web depende da API na 8033
- Erro fetch failed no robô ocorre quando a API não está rodando
- 404 em /login identificado como rota inexistente (não é erro do bot)

## 2026-11-26

- Criada documentação de continuidade (PROJECT_STATUS.md, ROADMAP.md, CHANGELOG.md, DECISIONS.md)

# PROJECT_STATUS

## Estado atual

Projeto de atendimento via WhatsApp para ConnectTV (internet ilimitada + VPN e IPTV).

- Repositório: cllaytom/ia-atendimento-whatsapp
- Branch principal: main
- Execução local: Windows + PowerShell + Uvicorn
- API de atendimento: http://127.0.0.1:8033
- Painel/assinaturas: porta 8010
- Robô WhatsApp: pasta whatsapp-web (Node.js)

## Funcionalidades implementadas

- Menu e fluxo de atendimento (internet, IPTV completo, IPTV básico, atendente)
- Fluxo de internet: operadora (TIM/Vivo), recarga nos últimos 3 meses, Android/iPhone, instalação do app
- Fluxo de IPTV: marca da TV, smart ou não, foto da loja de apps, TV Box e modelo
- FAQ determinístico (preço, teste, operadoras, recarga, aplicativo, streamers, VPN)
- Base de conhecimento editável (dados/conhecimento.json)
- Aprendizado: dúvidas não respondidas viram pendências e podem ser respondidas/ensinadas
- Transferência para atendente humano e alerta de conversa aguardando
- Simulador de conversa via API (/atendimento/conversas, mensagens, assumir, responder, devolver, encerrar)
- Banco SQLite (dados/atendimento.db) com conversas, mensagens e dúvidas
- Robô WhatsApp local (whatsapp-web) integrado à API na porta 8033

## Funcionalidades incompletas / pendentes

- Merge do PR #1 (correção do teste grátis para 3 horas) ainda não feito
- Validação ponta a ponta do robô (conexão, resposta e envio) ainda não confirmada
- Filtragem de conversas de conexão para ensino da IA ainda não implementada
- Conteúdo sobre sinal/clima (4G/5G/LTE, H+/H/G/E, chuva) ainda não adicionado à base de conhecimento
- Migração para VPS ainda não executada
- Painel de assinaturas (CRUD de produtos) ainda não confirmado como implementado/testado

## Problemas conhecidos

- 404 em /login não é erro do bot; é rota inexistente nessa API
- fetch failed no robô ocorre quando a API na 8033 não está rodando

## Última etapa concluída

- Correção do teste grátis para 3 horas em app/atendimento/oferta.py
- Commit 4b763dccbf6cb0710cb5db573451e80fc77dd7d2 na branch correcao-teste-3h
- PR #1 aberto (Unifica a duração do teste grátis em 3 horas)

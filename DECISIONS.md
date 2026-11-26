# DECISIONS

## Decisões técnicas

1. Sem API oficial do WhatsApp — usa integração via WhatsApp Web/local para evitar custo
2. Separação de escopos — assinaturas/créditos em API separada (D:\planilhas), atendimento é módulo próprio
3. Execução local primeiro — Windows + PowerShell + Uvicorn, migração para VPS planejada
4. Portas fixas — API de atendimento na 8033, painel/assinaturas na 8010
5. Dados sensíveis fora do Git — .env, sessões do WhatsApp e bancos locais não vão para o repositório
6. Teste grátis fixo em 3 horas — padronizado via constante INTERNET_TRIAL_HORAS
7. Regras de teste — 1 teste por número a cada 3 horas; checagem de sinal 4G/4G+/5G/LTE antes de criar teste; repetição de teste ou assinatura vai para atendente

## Regras que não devem ser alteradas sem autorização

- Duração do teste grátis: 3 horas
- Limite de 1 teste por número a cada 3 horas
- Checagem de sinal antes de criar teste
- Não reiniciar a jornada do cliente nem repetir perguntas já respondidas
- Dados sensíveis permanecem fora do Git

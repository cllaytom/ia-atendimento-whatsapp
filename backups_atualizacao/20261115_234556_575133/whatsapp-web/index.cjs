'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { Client, LocalAuth } = require('whatsapp-web.js');
const qr = require('qrcode-terminal');
require('dotenv').config({ path: path.resolve(__dirname, '..', '.env') });
const base = new URL(process.env.WHATSAPP_API_URL || 'http://127.0.0.1:8033');
if (base.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname)) throw Error('API deve ser HTTP local.');
const key = process.env.API_KEY;
if (!key) throw Error('API_KEY ausente no ambiente ou .env da raiz.');
const live = process.env.WHATSAPP_ENVIAR === '1';
const file = path.join(__dirname, 'estado.json');
const state = fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')) : {};
if (!state || Array.isArray(state) || typeof state !== 'object') throw Error('Estado invalido.');
const queues = new Map();
const blocked = new Set();
let started = Infinity;
let connected = false;
function save() {
  fs.writeFileSync(file + '.tmp', JSON.stringify(state));
  fs.renameSync(file + '.tmp', file);
}
async function api(route, body) {
  const response = await fetch(new URL(route, base), {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'X-API-Key': key, 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(300000), redirect: 'error'
  });
  if (!response.ok) throw Error('API HTTP ' + response.status);
  return response.json();
}
const client = new Client({
  authStrategy: new LocalAuth({ dataPath: path.join(__dirname, '.wwebjs_auth') }),
  puppeteer: { headless: false }
});
client.on('qr', code => {
  console.log('Escaneie o QR em Aparelhos conectados. Nao compartilhe este QR.');
  qr.generate(code, { small: true });
});
client.on('ready', () => {
  started = Math.floor(Date.now() / 1000);
  connected = true;
  console.log(live ? 'CONECTADO - ENVIO ATIVO' : 'CONECTADO - PREVIA SEM ENVIO');
});
client.on('auth_failure', () => { connected = false; console.error('Falha de autenticacao.'); });
client.on('disconnected', () => { connected = false; console.error('Desconectado. Reinicie; nao ha replay automatico.'); });
async function phone(remote) {
  let pn = remote;
  if (remote.endsWith('@lid')) {
    const result = await client.getContactLidAndPhone([remote]);
    const item = result.find(x => x.lid === remote);
    pn = item && item.pn;
  }
  const match = /^(\d{12,15})@(c\.us|s\.whatsapp\.net)$/.exec(pn || '');
  if (!match) throw Error('Telefone nao confirmado; conversa bloqueada.');
  return match[1];
}
async function handle(msg) {
  const id = msg.id && msg.id._serialized;
  if (!connected || !id || Object.hasOwn(state, id) || msg.timestamp <= started) return;
  if (msg.fromMe || msg.type !== 'chat' || msg.hasMedia || !msg.body.trim()) return;
  if (!/@(c\.us|s\.whatsapp\.net|lid)$/.test(msg.from)) return;
  const chat = await msg.getChat();
  if (chat.isGroup) return;
  const number = await phone(msg.from);
  if (blocked.has(number)) return;
  if (!live) { console.log('Entrada identificada; previa sem chamar motor nem enviar.'); return; }
  if (msg.body.length > 4000) throw Error('Texto acima de 4000 caracteres.');
  state[id] = 'processando';
  save();
  try {
    const result = await api('/whatsapp/receber', { contato: number, texto: msg.body });
    if (!Array.isArray(result.respostas) || typeof result.estado !== 'string') throw Error('Resposta inesperada da API.');
    const answer = result.respostas.filter(x => typeof x === 'string' && x.trim()).join('\n\n');
    if (!answer) { state[id] = 'sem_resposta'; save(); return; }
    const status = await api('/whatsapp/status/' + number);
    if (!connected || status.estado !== result.estado || !['ia', 'aguardando_humano'].includes(status.estado)) {
      state[id] = 'cancelado_estado'; save(); console.log('Resposta cancelada: estado mudou.'); return;
    }
    const sent = await client.sendMessage(msg.from, answer);
    if (!sent || !sent.id) throw Error('Resultado de envio indeterminado.');
    state[id] = 'enviado'; save();
    console.log('Resposta submetida ao WhatsApp; entrega ao aparelho nao confirmada.');
  } catch (error) {
    blocked.add(number);
    state[id] = 'falha_sem_retry'; save();
    throw error;
  }
}
client.on('message', msg => {
  if (!connected || msg.fromMe) return;
  const remote = msg.from;
  const previous = queues.get(remote) || Promise.resolve();
  const task = previous.then(() => handle(msg)).catch(error => {
    console.error('Conversa nao processada:', error.message);
  });
  queues.set(remote, task);
  task.finally(() => { if (queues.get(remote) === task) queues.delete(remote); });
});
async function stop() {
  connected = false;
  try { await client.destroy(); } finally { process.exit(0); }
}
process.on('SIGINT', stop);
process.on('SIGTERM', stop);
(async () => {
  await api('/atendimento/config');
  await client.initialize();
})().catch(error => { console.error('Inicializacao falhou:', error.message); process.exit(1); });

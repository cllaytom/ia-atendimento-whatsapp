import wweb from 'whatsapp-web.js';
import qr from 'qrcode-terminal';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const {Client, LocalAuth} = wweb;
const dir = path.dirname(fileURLToPath(import.meta.url));
const base = process.env.API_URL || 'http://127.0.0.1:8010';
if (!['127.0.0.1','localhost'].includes(new URL(base).hostname)) throw Error('API deve ser local');
const key = process.env.API_KEY;
if (!key || key === 'SUBSTITUA_PELA_CHAVE_LOCAL') throw Error('Configure API_KEY');
const live = process.env.ENVIAR === '1';
const allowed = new Set((process.env.CONTATOS_TESTE || '').split(',').map(x => x.replace(/\D/g, '')).filter(Boolean));
if (!allowed.size) throw Error('Configure CONTATOS_TESTE; nao existe modo aberto a todos nesta versao');
const statePath = path.join(dir, 'local-state.json');
let state = {paused: [], seen: []};
if (fs.existsSync(statePath)) state = JSON.parse(fs.readFileSync(statePath, 'utf8'));
const paused = new Set(state.paused);
const seen = new Set(state.seen);
function save() {
  const tmp = statePath + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify({paused: [...paused], seen: [...seen].slice(-20000)}));
  fs.renameSync(tmp, statePath);
}
let since = Infinity;
let epoch = 0;
let chain = Promise.resolve();
const sending = new Set();
const client = new Client({authStrategy: new LocalAuth({dataPath: path.join(dir, '.wwebjs_auth')}), puppeteer: {headless: true}});
async function api(route, payload) {
  const r = await fetch(base + route, {method: payload ? 'POST' : 'GET', headers: {'X-API-Key': key, 'Content-Type': 'application/json'}, body: payload ? JSON.stringify(payload) : undefined, signal: AbortSignal.timeout(30000)});
  if (!r.ok) throw Error('API HTTP ' + r.status);
  return r.json();
}
function stop() { since = Infinity; epoch++; }
client.on('qr', code => qr.generate(code, {small: true}));
client.on('ready', () => {since = Math.floor(Date.now()/1000); epoch++; console.log('Conectado. Somente mensagens posteriores a este instante. Envio:', live);});
client.on('disconnected', stop);
client.on('auth_failure', stop);
client.on('change_state', value => {if (value !== 'CONNECTED') stop();});
// Toda mensagem manual de saida pausa o contato. Nao retomar automaticamente.
client.on('message_create', msg => {
  if (msg.fromMe && !sending.has(msg.to)) {paused.add(msg.to); save();}
});
client.on('message', msg => {
  const receivedEpoch = epoch;
  if (msg.fromMe || msg.type !== 'chat' || msg.hasMedia || !['c.us','lid'].some(s => msg.from.endsWith('@' + s))) return;
  if (!Number.isFinite(msg.timestamp) || msg.timestamp <= since) return;
  const jid = msg.from;
  const id = msg.id._serialized;
  if (!id || seen.has(id) || paused.has(jid)) return;
  // LIDs nao sao numeros: so atender IDs c.us explicitamente autorizados.
  if (!jid.endsWith('@c.us') || !allowed.has(jid.split('@')[0])) return;
  seen.add(id); save();
  chain = chain.then(async () => {
    if (epoch !== receivedEpoch || paused.has(jid) || msg.timestamp <= since) return;
    const cfg = await api('/atendimento/config');
    if (cfg.ia_ativa) throw Error('IA ativa: envio bloqueado');
    const text = (msg.body || '').trim();
    if (!text || text.length > 4000) return;
    if (!live) {console.log('SIMULACAO: mensagem nova elegivel; nenhum envio nem mudanca na conversa.'); return;}
    const result = await api('/whatsapp-web/mensagem', {id, contato: jid, texto: text});
    for (const answer of result.respostas || []) {
      if (epoch !== receivedEpoch || paused.has(jid)) return;
      if (!answer || /foto|print|imagem|video|vídeo|audio|áudio/i.test(answer)) continue;
      // Reconsulta o estado imediatamente antes de cada envio.
      const detail = await api('/atendimento/conversas/' + result.conversa_id);
      if (detail.conversa.estado === 'humano' || detail.conversa.estado === 'encerrada') return;
      sending.add(jid);
      try {await client.sendMessage(jid, answer);} finally {sending.delete(jid);}
    }
  }).catch(() => console.error('Falha no processamento; mensagem descartada, sem repeticao automatica.'));
});
process.on('SIGINT', async () => {stop(); await client.destroy(); process.exit(0);});
await api('/health');
const cfg = await api('/atendimento/config');
if (cfg.ia_ativa) throw Error('Use o servidor app.whatsapp_web:app, exclusivo sem IA');
await client.initialize();

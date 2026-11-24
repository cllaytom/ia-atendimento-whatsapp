#!/usr/bin/env node
/**
 * Worker da campanha (fase 2).
 *
 * O cerebro fica no Python (D:\planilhas\app\campanha\conector.py). Este
 * arquivo so obedece:
 *   1. pergunta se pode falar
 *   2. reserva 1 alvo
 *   3. digita, envia (ou so mostra, no modo simulacao) e confirma
 *
 * MODOS
 *   (padrao)    simulacao: mostra a mensagem e devolve o alvo para a fila
 *   --parear    abre o WhatsApp Web e mostra o QR para vincular o aparelho
 *   --teste     envia UMA mensagem para o numero de teste (nunca para a fila)
 *   --enviar    envia de verdade (exige trava liberada + CAMPANHA_MODO=real)
 *   --perfil    mostra o perfil do Chrome exclusivo e sai
 *
 * Uso (PowerShell, na pasta D:\planilhas):
 *   node campanha-whatsapp\worker.cjs                 # simulacao
 *   node campanha-whatsapp\worker.cjs --uma-vez
 *   node campanha-whatsapp\worker.cjs --perfil        # conferir o perfil
 *   node campanha-whatsapp\worker.cjs --parear        # vincular aparelho
 *   node campanha-whatsapp\worker.cjs --enviar        # envio real
 *
 * A sessao do WhatsApp fica em dados/campanha-sessao/session (LocalAuth e
 * perfil do Chrome proprios), separada do robo de atendimento e do perfil
 * padrao do Chrome.
 *
 * Chave da API: variavel CAMPANHA_API_KEY, argumento --chave ou a linha
 * API_KEY do .env da raiz (nunca e exibida).
 */

"use strict";

const fs = require("node:fs");
const path = require("node:path");

const RAIZ = path.resolve(__dirname, "..");
const SESSAO = path.join(RAIZ, "dados", "campanha-sessao");

// Perfil do Chrome EXCLUSIVO da campanha. O LocalAuth usa exatamente
// <SESSAO>/session; declaramos o caminho aqui para deixar isso explicito e
// para travar contra o perfil padrao do Chrome (usado pelo outro robo).
const PERFIL = path.join(SESSAO, "session");

let parado = false;
// Ultimo numero pareado visto nesta execucao (vai no pulso, para o painel).
let numeroConectado = "";
let reservaAtual = null;

class ErroHttp extends Error {
  constructor(status, detalhe) {
    super(`HTTP ${status}: ${typeof detalhe === "string" ? detalhe : JSON.stringify(detalhe)}`);
    this.status = status;
    this.detalhe = detalhe;
  }
}

class ErroRede extends Error {}

function relogio() {
  return new Date().toLocaleTimeString("pt-BR", { hour12: false });
}

// Log em arquivo para o painel conferir depois (dados/campanha-worker.log).
// Roda em paralelo ao console e nunca derruba o worker se o disco falhar.
const LOG_ARQUIVO = path.join(RAIZ, "dados", "campanha-worker.log");
const LOG_MAX_BYTES = 2 * 1024 * 1024;

function gravarLogArquivo(linha) {
  try {
    fs.mkdirSync(path.dirname(LOG_ARQUIVO), { recursive: true });
    try {
      if (fs.statSync(LOG_ARQUIVO).size > LOG_MAX_BYTES) {
        fs.renameSync(LOG_ARQUIVO, `${LOG_ARQUIVO}.1`);
      }
    } catch {
      /* arquivo ainda nao existe */
    }
    fs.appendFileSync(LOG_ARQUIVO, `${linha}\n`, "utf8");
  } catch {
    /* log em arquivo e opcional */
  }
}

function log(mensagem) {
  const linha = `[${relogio()}] ${mensagem}`;
  console.log(linha);
  gravarLogArquivo(linha);
}

async function dormir(ms) {
  const limite = Date.now() + Math.max(0, ms);
  while (Date.now() < limite && !parado) {
    await new Promise((resolver) => setTimeout(resolver, Math.min(500, limite - Date.now())));
  }
}

function lerArgumentos(argv) {
  const opcoes = {
    simular: true,
    enviar: false,
    manual: false,
    parear: false,
    desconectar: false,
    teste: false,
    perfil: false,
    estado: false,
    numeroTeste: "",
    umaVez: false,
    pausa: 5,
    chave: "",
    mostrar: false,
    api: process.env.CAMPANHA_API || "http://127.0.0.1:8010",
    ajuda: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--simular") opcoes.simular = true;
    else if (arg === "--enviar") {
      opcoes.enviar = true;
      opcoes.simular = false;
    } else if (arg === "--parear") opcoes.parear = true;
    else if (arg === "--desconectar") opcoes.desconectar = true;
    else if (arg === "--manual") {
      opcoes.manual = true;
      opcoes.simular = false;
    } else if (arg === "--teste") opcoes.teste = true;
    else if (arg === "--perfil") opcoes.perfil = true;
    else if (arg === "--estado") opcoes.estado = true;
    else if (arg === "--numero-teste") opcoes.numeroTeste = argv[++i] || "";
    else if (arg === "--uma-vez") opcoes.umaVez = true;
    else if (arg === "--mostrar") opcoes.mostrar = true;
    else if (arg === "--ajuda" || arg === "-h") opcoes.ajuda = true;
    else if (arg === "--pausa") opcoes.pausa = Math.max(1, Number(argv[++i]) || 5);
    else if (arg === "--chave") opcoes.chave = argv[++i] || "";
    else if (arg === "--api") opcoes.api = String(argv[++i] || opcoes.api).replace(/\/+$/, "");
    else {
      console.error(`Argumento desconhecido: ${arg} (use --ajuda)`);
      process.exitCode = 2;
    }
  }
  return opcoes;
}

function ajuda() {
  console.log(
    [
      "Worker da campanha (fase 2)",
      "",
      "  node campanha-whatsapp/worker.cjs [opcoes]",
      "",
      "  --simular        mostra o que enviaria e devolve o alvo (padrao)",
      "  --uma-vez        executa um ciclo e sai (so no modo simulacao)",
      "  --parear         abre o WhatsApp Web e mostra o QR do dispositivo",
      "  --desconectar    desvincula o numero atual (logout) e sai",
      "  --teste          envia 1 mensagem para o numero de teste (nao usa a fila)",
      "  --enviar         envia de verdade (exige trava liberada e modo real)",
      "  --manual         fica conectado esperando 'Enviar agora' no painel",
      "  --perfil         mostra o perfil do Chrome exclusivo e sai",
      "  --estado         consulta o estado do conector na API e sai",
      "  --numero-teste N salva o numero de teste na campanha e sai",
      "  --mostrar        abre a janela do navegador (util no pareamento)",
      "  --pausa N        segundos entre ciclos na simulacao (padrao 5)",
      "  --api URL        endereco da API (padrao http://127.0.0.1:8010)",
      "  --chave CHAVE    chave da API (prefira a variavel CAMPANHA_API_KEY)",
      "  --ajuda          esta mensagem",
    ].join("\n")
  );
}

function acharChave(opcoes) {
  if (opcoes.chave) return { valor: opcoes.chave, origem: "argumento --chave" };
  if (process.env.CAMPANHA_API_KEY) {
    return { valor: process.env.CAMPANHA_API_KEY, origem: "variavel CAMPANHA_API_KEY" };
  }
  const arquivo = path.join(RAIZ, ".env");
  try {
    const linha = fs
      .readFileSync(arquivo, "utf8")
      .split(/\r?\n/)
      .find((linha) => /^\s*API_KEY\s*=/.test(linha));
    if (linha) {
      const valor = linha
        .slice(linha.indexOf("=") + 1)
        .trim()
        .replace(/^["']|["']$/g, "");
      if (valor) return { valor, origem: ".env (API_KEY)" };
    }
  } catch {
    /* sem .env: segue para o erro amigavel */
  }
  return null;
}

function clienteApi(base, chave) {
  async function chamar(metodo, caminho, corpo) {
    let resposta;
    try {
      resposta = await fetch(base + caminho, {
        method: metodo,
        headers: {
          "X-API-Key": chave,
          "Content-Type": "application/json",
        },
        body: corpo === undefined ? undefined : JSON.stringify(corpo),
        signal: AbortSignal.timeout(15000),
      });
    } catch (erro) {
      throw new ErroRede(`API fora do ar em ${base} (${erro.message})`);
    }

    const texto = await resposta.text();
    let dados = null;
    try {
      dados = texto ? JSON.parse(texto) : null;
    } catch {
      dados = { texto };
    }
    if (!resposta.ok) {
      throw new ErroHttp(resposta.status, dados && dados.detail ? dados.detail : dados);
    }
    return dados;
  }

  return {
    estado: () => chamar("GET", "/campanha/conector/estado"),
    proximo: () => chamar("POST", "/campanha/conector/proximo"),
    devolver: (alvoId) => chamar("POST", "/campanha/conector/devolver", { alvo_id: alvoId }),
    confirmar: (alvoId, situacao, erro) =>
      chamar("POST", "/campanha/conector/confirmar", {
        alvo_id: alvoId,
        situacao,
        erro: erro || null,
      }),
    salvarTeste: (numero) => chamar("POST", "/campanha/numero", { teste: numero }),
    erro: (motivo) => chamar("POST", "/campanha/conector/erro", { motivo }),
    pulso: (modo) =>
      chamar("POST", "/campanha/conector/pulso", {
        modo,
        pid: process.pid,
        numero: numeroConectado || undefined,
      }),
    numero: (numero) => chamar("POST", "/campanha/conector/numero", { numero }),
    manual: () => chamar("POST", "/campanha/conector/manual/proximo"),
    contatos: (itens, fim) => chamar("POST", "/campanha/contatos", { itens, fim }),
  };
}

function motivoDe(erro) {
  if (erro && erro.status === 409) {
    const detalhe = erro.detalhe || {};
    return {
      motivo: detalhe.motivo || "bloqueado",
      esperar: Number(detalhe.esperar_segundos) || 0,
    };
  }
  return null;
}

// ------------------------------- simulacao ---------------------------------

function mostrarAlvo(alvo) {
  log(`--- alvo #${alvo.alvo_id} (validade ${alvo.validade_minutos} min) ---`);
  log(`telefone : +${alvo.telefone}`);
  log(`cliente  : ${alvo.nome || "(sem nome)"}`);
  log(`digitacao: ${alvo.digitacao_segundos}s`);
  log("mensagem :");
  console.log(
    String(alvo.texto)
      .split("\n")
      .map((linha) => `   | ${linha}`)
      .join("\n")
  );
}

async function simular(opcoes, api, chave) {
  let ultimoAviso = "";

  log(`worker da campanha | MODO SIMULACAO | API ${opcoes.api}`);
  log(`chave: ${chave.origem} (nao sera exibida)`);

  const ciclo = async () => {
    let estado;
    try {
      estado = await api.estado();
    } catch (erro) {
      log(erro.message);
      return opcoes.pausa;
    }

    if (!estado.liberado) {
      const linha =
        `aguardando: ${estado.motivo}` +
        ` | hoje ${estado.enviados_hoje}/${estado.cota_dia}` +
        ` | fila ${estado.pendentes} | reservados ${estado.reservados}`;
      if (linha !== ultimoAviso) {
        log(linha);
        ultimoAviso = linha;
      }
      return Math.min(Math.max(estado.esperar_segundos || 0, opcoes.pausa), 60);
    }
    ultimoAviso = "";

    const alvo = await api.proximo();
    reservaAtual = alvo.alvo_id;
    mostrarAlvo(alvo);
    await api.devolver(alvo.alvo_id);
    reservaAtual = null;
    log("SIMULACAO: nada foi enviado; alvo devolvido para a fila.");
    return opcoes.pausa;
  };

  if (opcoes.umaVez) {
    try {
      await ciclo();
    } catch (erro) {
      const bloqueio = motivoDe(erro);
      log(bloqueio ? `bloqueado: ${bloqueio.motivo}` : `erro: ${erro.message}`);
    }
    return;
  }

  while (!parado) {
    let esperar = opcoes.pausa;
    try {
      esperar = await ciclo();
    } catch (erro) {
      const bloqueio = motivoDe(erro);
      log(bloqueio ? `bloqueado: ${bloqueio.motivo}` : `erro: ${erro.message}`);
      esperar = Math.max(opcoes.pausa, 10);
    }
    if (!parado) await dormir(esperar * 1000);
  }
}

// ------------------------------- WhatsApp ----------------------------------

function carregarWhatsApp() {
  try {
    return require("whatsapp-web.js");
  } catch (erro) {
    console.error("whatsapp-web.js nao esta instalado.");
    console.error("Na pasta campanha-whatsapp, rode: npm install");
    console.error(`Detalhe: ${erro.message}`);
    process.exitCode = 4;
    return null;
  }
}

function imprimirQr(qr) {
  try {
    require("qrcode-terminal").generate(qr, { small: true });
  } catch {
    console.log("QR (texto):", qr);
  }
}

// Envia texto por telefone (JID @c.us), nunca pelo LID que o getNumberId
// devolve hoje. O LID deixa a mensagem em ack=0 (nunca sai do aparelho).
// waitUntilMsgSent faz o sendMessage esperar o servidor; ack < 1 = falha.
async function enviarTexto(cliente, telefone, texto, digitacaoSegundos) {
  const jid = `${telefone}@c.us`;
  const conversa = await cliente.getChatById(jid);
  if (conversa) {
    try {
      await conversa.sendStateTyping();
      await dormir(Math.max(1, Number(digitacaoSegundos) || 4) * 1000);
      await conversa.clearState();
    } catch {
      /* sem chat ainda: envia direto */
    }
  }
  const mensagem = await cliente.sendMessage(jid, texto, { waitUntilMsgSent: true });
  if (!mensagem || Number(mensagem.ack) < 1) {
    throw new Error("servidor nao confirmou o envio (ack 0)");
  }
  return mensagem;
}

// Envia um alvo (auto ou manual) e confirma no cerebro. Nao trata excecao de
// envio: quem chama decide o que fazer com a falha.
async function enviarUm(cliente, alvo, api) {
  const existente = await cliente.getNumberId(alvo.telefone);
  if (!existente) {
    await api.confirmar(alvo.alvo_id, "falha", "numero sem WhatsApp");
    log(`+${alvo.telefone} nao tem WhatsApp; marcado como falha (nao sera tentado de novo).`);
    return { enviado: false, motivo: "sem whatsapp" };
  }
  const mensagem = await enviarTexto(
    cliente,
    alvo.telefone,
    alvo.texto,
    alvo.digitacao_segundos
  );
  await api.confirmar(alvo.alvo_id, "enviado");
  log(`enviado para +${alvo.telefone} (alvo #${alvo.alvo_id}, ack ${mensagem.ack}).`);
  return { enviado: true };
}

// Usa um navegador que ja existe na maquina (Chrome, Brave, Edge) em vez de
// baixar o Chromium do Puppeteer. Firefox nao serve: whatsapp-web.js precisa
// de um navegador Chromium.
function acharNavegador() {
  const programas = process.env.PROGRAMFILES || "C:\\Program Files";
  const programasX86 = process.env["PROGRAMFILES(X86)"] || "C:\\Program Files (x86)";
  const local = process.env.LOCALAPPDATA || "";
  const candidatos = [
    process.env.CAMPANHA_CHROME,
    path.join(programas, "Google", "Chrome", "Application", "chrome.exe"),
    path.join(programasX86, "Google", "Chrome", "Application", "chrome.exe"),
    path.join(local, "Google", "Chrome", "Application", "chrome.exe"),
    path.join(programas, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
    path.join(programasX86, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
    path.join(local, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
    path.join(programas, "Microsoft", "Edge", "Application", "msedge.exe"),
    path.join(programasX86, "Microsoft", "Edge", "Application", "msedge.exe"),
  ].filter(Boolean);

  for (const candidato of candidatos) {
    try {
      if (fs.existsSync(candidato)) return candidato;
    } catch {
      /* candidato invalido: tenta o proximo */
    }
  }
  return "";
}

function conferirPerfilExclusivo(dir) {
  const alvo = path.resolve(dir).toLowerCase();
  const raizDados = path.join(RAIZ, "dados").toLowerCase();
  const proibidos = [];

  if (process.env.LOCALAPPDATA) {
    proibidos.push(path.join(process.env.LOCALAPPDATA, "Google", "Chrome", "User Data"));
  }
  if (process.env.APPDATA) {
    proibidos.push(path.join(process.env.APPDATA, "Mozilla", "Firefox", "Profiles"));
  }
  proibidos.push(path.join(RAIZ, "ia atendimento", "whatsapp-web", ".wwebjs_auth"));

  for (const proibido of proibidos) {
    const caminho = path.resolve(proibido).toLowerCase();
    if (alvo === caminho || alvo.startsWith(caminho + path.sep)) {
      throw new Error(
        `perfil do Chrome nao pode ser compartilhado com outro robo: ${dir}`
      );
    }
  }

  if (alvo === raizDados || !alvo.startsWith(raizDados + path.sep)) {
    throw new Error(`perfil do Chrome precisa ficar dentro de dados/: ${dir}`);
  }
}

function mostrarPerfil() {
  const navegador = acharNavegador();
  const existe = fs.existsSync(PERFIL);
  console.log(`navegador : ${navegador || "Chromium do Puppeteer"}`);
  console.log(`perfil    : ${PERFIL}`);
  console.log(`existe    : ${existe ? "sim" : "nao (sera criado no primeiro --parear)"}`);
  try {
    conferirPerfilExclusivo(PERFIL);
    console.log("trava     : perfil exclusivo confirmado (fora do Chrome padrao)");
  } catch (erro) {
    console.log(`trava     : ${erro.message}`);
    process.exitCode = 9;
  }
}

function criarCliente(WhatsApp, opcoes) {
  const { Client, LocalAuth } = WhatsApp;
  conferirPerfilExclusivo(PERFIL);
  const navegador = acharNavegador();
  const puppeteer = {
    headless: !opcoes.mostrar,
    // Sem isso o Chrome poderia reaproveitar um perfil ja aberto (o do outro
    // robo). O LocalAuth so aceita este userDataDir se for o mesmo que ele
    // calcula: <SESSAO>/session.
    userDataDir: PERFIL,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--no-first-run",
      "--no-default-browser-check",
    ],
  };
  if (navegador) puppeteer.executablePath = navegador;

  const cliente = new Client({
    authStrategy: new LocalAuth({ dataPath: SESSAO }),
    // O WhatsApp Web as vezes demora para expor window.Debug na primeira
    // carga; o padrao de 30s derruba o cliente cedo demais.
    authTimeoutMs: 180000,
    puppeteer,
  });

  log(`navegador: ${navegador || "Chromium do Puppeteer"}`);
  log(`perfil do Chrome: ${PERFIL} (exclusivo da campanha)`);
  cliente.on("qr", (qr) => {
    log("escaneie o QR abaixo com o WhatsApp do numero remetente:");
    imprimirQr(qr);
  });
  cliente.on("authenticated", () => log("dispositivo autenticado."));
  cliente.on("auth_failure", (motivo) => {
    log(`falha de autenticacao: ${motivo}`);
    parado = true;
  });
  cliente.on("disconnected", (motivo) => {
    log(`desconectado do WhatsApp: ${motivo}`);
    parado = true;
  });
  return cliente;
}

function esperarPronto(cliente, timeoutMs = 300000) {
  return new Promise((resolver, rejeitar) => {
    let concluido = false;
    const vigia = setInterval(() => {
      if (parado) falhar(new Error("interrompido pelo operador"));
    }, 500);

    const encerrarVigia = () => clearInterval(vigia);

    const pronto = () => {
      if (concluido) return;
      concluido = true;
      encerrarVigia();
      resolver();
    };
    const falhar = (erro) => {
      if (concluido) return;
      concluido = true;
      encerrarVigia();
      rejeitar(erro);
    };
    cliente.once("ready", pronto);
    cliente.once("auth_failure", (motivo) => falhar(new Error(`falha de autenticacao: ${motivo}`)));
    setTimeout(() => falhar(new Error("tempo esgotado esperando o WhatsApp (5 min)")), timeoutMs).unref();
    cliente.initialize().catch(falhar);
  });
}

async function parear(opcoes, api) {
  const WhatsApp = carregarWhatsApp();
  if (!WhatsApp) return;

  log("abrindo o WhatsApp Web para vincular um dispositivo novo...");
  log(`sessao: ${SESSAO}`);
  log("o robo de atendimento (24h) nao e afetado: a sessao e separada.");

  const cliente = criarCliente(WhatsApp, opcoes);
  try {
    await esperarPronto(cliente);
    const numero = cliente.info && cliente.info.wid ? cliente.info.wid.user : "(desconhecido)";
    numeroConectado = numero === "(desconhecido)" ? "" : numero;
    if (numeroConectado && api) {
      await api.numero(numeroConectado).catch(() => {});
    }
    log(`pareado com o numero ${numero}. Sessao salva em dados/campanha-sessao.`);
    log("nada foi enviado. Para enviar, use --enviar (exige a campanha liberada).");
  } catch (erro) {
    log(`nao foi possivel parear: ${erro.message}`);
    process.exitCode = 5;
  } finally {
    await cliente.destroy().catch(() => {});
  }
}

// Desvincula o numero da campanha (logout de verdade: o aparelho some da lista
// de dispositivos conectados no celular). Usado pelo botao "Trocar numero".
async function desconectarNumero(opcoes, api) {
  const WhatsApp = carregarWhatsApp();
  if (!WhatsApp) return;

  log("desconectando o numero atual da campanha...");
  const cliente = criarCliente(WhatsApp, opcoes);
  try {
    await esperarPronto(cliente);
    const numero = cliente.info && cliente.info.wid ? cliente.info.wid.user : "(desconhecido)";
    await cliente.logout();
    numeroConectado = "";
    if (api) await api.numero("").catch(() => {});
    log(`numero ${numero} desconectado. O aparelho foi desvinculado.`);
    log("agora use --parear para vincular o novo numero.");
  } catch (erro) {
    log(`nao foi possivel desconectar: ${erro.message}`);
    process.exitCode = 5;
  } finally {
    await cliente.destroy().catch(() => {});
  }
}

async function enviar(opcoes, api, chave) {
  const inicial = await api.estado().catch((erro) => {
    log(erro.message);
    return null;
  });
  if (!inicial) {
    process.exitCode = 2;
    return;
  }
  if (inicial.trava) {
    log("envio real bloqueado pela trava do servidor (ENVIO_REAL_HABILITADO = False).");
    log("use --simular para conferir o texto ou --parear para vincular o aparelho.");
    process.exitCode = 6;
    return;
  }
  if (inicial.modo !== "real") {
    log(`modo atual: ${inicial.modo}. O envio exige CAMPANHA_MODO=real.`);
    process.exitCode = 6;
    return;
  }

  const WhatsApp = carregarWhatsApp();
  if (!WhatsApp) return;

  log(`worker da campanha | MODO ENVIO REAL | API ${opcoes.api}`);
  log(`chave: ${chave.origem} (nao sera exibida)`);
  log("abrindo WhatsApp Web (sessao da campanha)...");

  const cliente = criarCliente(WhatsApp, opcoes);
  try {
    await esperarPronto(cliente);
  } catch (erro) {
    log(`nao abriu o WhatsApp: ${erro.message}`);
    log("se o aparelho ainda nao foi vinculado, rode primeiro: --parear");
    await cliente.destroy().catch(() => {});
    process.exitCode = 5;
    return;
  }

  const numero = cliente.info && cliente.info.wid ? cliente.info.wid.user : "(desconhecido)";
  numeroConectado = numero === "(desconhecido)" ? "" : numero;
  log(`conectado como ${numero}. Consultando o cerebro a cada 5s.`);
  log("para parar: Ctrl+C (ou Pausar na tela).");

  // Erro fatal do WhatsApp: avisa o servidor na hora, que desliga a campanha.
  // Sem isso, o worker ficaria tentando enviar com a sessao caida.
  let erroFatal = "";
  let encerrando = false;
  let pausaPedido = null;
  const avisarErroFatal = (motivo) => {
    if (erroFatal || encerrando) return;
    erroFatal = motivo;
    log(`erro fatal: ${motivo}. Pedindo pausa automatica ao servidor.`);
    pausaPedido = api
      .erro(`worker: ${motivo}`)
      .catch((erro) => log(`nao foi possivel pausar pelo servidor: ${erro.message}`));
  };
  cliente.on("auth_failure", (motivo) =>
    avisarErroFatal(`falha de autenticacao: ${motivo}`)
  );
  cliente.on("disconnected", (motivo) =>
    avisarErroFatal(`desconectado do WhatsApp: ${motivo}`)
  );

  let ultimoAviso = "";
  try {
    while (!parado) {
      const pulso = await api.pulso("auto").catch(() => null);
      if (pulso && pulso.parar) {
        log("pedido do painel: encerrando o worker...");
        parado = true;
        break;
      }
      if (pulso && pulso.pedir_contatos) await exportarContatos(cliente, api);
      let estado;
      try {
        estado = await api.estado();
      } catch (erro) {
        log(erro.message);
        await dormir(10000);
        continue;
      }

      if (!estado.liberado) {
        const linha =
          `aguardando: ${estado.motivo}` +
          ` | hoje ${estado.enviados_hoje}/${estado.cota_dia}` +
          ` | fila ${estado.pendentes}`;
        if (linha !== ultimoAviso) {
          log(linha);
          ultimoAviso = linha;
        }
        await dormir(Math.min(Math.max(estado.esperar_segundos || 0, 5), 60) * 1000);
        continue;
      }
      ultimoAviso = "";

      let alvo;
      try {
        alvo = await api.proximo();
      } catch (erro) {
        const bloqueio = motivoDe(erro);
        log(bloqueio ? `bloqueado: ${bloqueio.motivo}` : `erro ao reservar: ${erro.message}`);
        await dormir(bloqueio && bloqueio.esperar ? bloqueio.esperar * 1000 : 10000);
        continue;
      }
      reservaAtual = alvo.alvo_id;

      try {
        await enviarUm(cliente, alvo, api);
      } catch (erro) {
        const motivo = String((erro && erro.message) || erro).slice(0, 300);
        await api.confirmar(alvo.alvo_id, "falha", motivo).catch(() => {});
        log(`falha no alvo #${alvo.alvo_id}: ${motivo}`);
      }
      reservaAtual = null;

      const depois = await api.estado().catch(() => null);
      if (depois && depois.esperar_segundos > 0) {
        log(`intervalo antes do proximo: ${depois.esperar_segundos}s`);
        await dormir(depois.esperar_segundos * 1000);
      }
    }
  } finally {
    encerrando = true;
    if (pausaPedido) await pausaPedido;
    if (reservaAtual) {
      await api.devolver(reservaAtual).catch(() => {});
      log(`alvo #${reservaAtual} devolvido para a fila.`);
      reservaAtual = null;
    }
    await cliente.destroy().catch(() => {});
    log("conector encerrado. nada mais sera enviado.");
  }
}

// Le a agenda do numero conectado e manda ao painel em lotes. Nada e enviado
// aos contatos: a lista so serve para conferir/completar a fila.
async function exportarContatos(cliente, api) {
  log("pedido do painel: lendo a lista de contatos do WhatsApp...");
  let contatos = [];
  try {
    contatos = await cliente.getContacts();
  } catch (erro) {
    log(`nao foi possivel ler os contatos: ${erro.message}`);
    await api.contatos([], true).catch(() => {});
    return;
  }

  const itens = [];
  for (const contato of contatos) {
    if (!contato || contato.isGroup) continue;
    const id = contato.id || {};
    if (id.server && id.server !== "c.us") continue;
    const telefone = String(contato.number || id.user || "").replace(/\D/g, "");
    if (!telefone) continue;
    itens.push({
      telefone,
      nome: String(contato.name || contato.pushname || contato.shortName || "").slice(0, 120),
    });
  }

  const tamanho = 500;
  let enviados = 0;
  if (!itens.length) {
    await api.contatos([], true).catch(() => {});
    log("nenhum contato valido para enviar ao painel.");
    return;
  }
  for (let i = 0; i < itens.length; i += tamanho) {
    const parte = itens.slice(i, i + tamanho);
    const ultimo = i + tamanho >= itens.length;
    try {
      await api.contatos(parte, ultimo);
      enviados += parte.length;
    } catch (erro) {
      log(`falha ao enviar os contatos ao painel: ${erro.message}`);
      await api.contatos([], true).catch(() => {});
      break;
    }
  }
  log(`${enviados} contato(s) enviados ao painel (de ${itens.length} lidos).`);
}

// --------------------------------- manual ----------------------------------

async function enviarManual(opcoes, api, chave) {
  const inicial = await api.estado().catch((erro) => {
    log(erro.message);
    return null;
  });
  if (!inicial) {
    process.exitCode = 2;
    return;
  }
  if (inicial.trava) {
    log("envio bloqueado pela trava do servidor (ENVIO_REAL_HABILITADO = False).");
    process.exitCode = 6;
    return;
  }
  if (inicial.modo !== "real") {
    log(`modo atual: ${inicial.modo}. O envio manual exige CAMPANHA_MODO=real.`);
    process.exitCode = 6;
    return;
  }

  const WhatsApp = carregarWhatsApp();
  if (!WhatsApp) return;

  log(`worker da campanha | MODO MANUAL | API ${opcoes.api}`);
  log(`chave: ${chave.origem} (nao sera exibida)`);
  log("nada sai sozinho: cada envio comeca com 'Enviar agora' no painel.");

  const cliente = criarCliente(WhatsApp, opcoes);
  try {
    await esperarPronto(cliente);
  } catch (erro) {
    log(`nao abriu o WhatsApp: ${erro.message}`);
    log("se o aparelho ainda nao foi vinculado, rode primeiro: --parear");
    await cliente.destroy().catch(() => {});
    process.exitCode = 5;
    return;
  }

  const numero = cliente.info && cliente.info.wid ? cliente.info.wid.user : "(desconhecido)";
  numeroConectado = numero === "(desconhecido)" ? "" : numero;
  log(`conectado como ${numero}. Esperando pedidos do painel.`);
  log("para parar: Ctrl+C (ou Pausar na tela).");

  let erroFatal = "";
  let encerrando = false;
  let pausaPedido = null;
  const avisarErroFatal = (motivo) => {
    if (erroFatal || encerrando) return;
    erroFatal = motivo;
    log(`erro fatal: ${motivo}. Pedindo pausa automatica ao servidor.`);
    pausaPedido = api
      .erro(`worker: ${motivo}`)
      .catch((erro) => log(`nao foi possivel pausar pelo servidor: ${erro.message}`));
  };
  cliente.on("auth_failure", (motivo) =>
    avisarErroFatal(`falha de autenticacao: ${motivo}`)
  );
  cliente.on("disconnected", (motivo) =>
    avisarErroFatal(`desconectado do WhatsApp: ${motivo}`)
  );

  let reservaAtual = null;
  let ultimoAviso = "";
  try {
    while (!parado) {
      const pulso = await api.pulso("manual").catch(() => null);
      if (pulso && pulso.parar) {
        log("pedido do painel: encerrando o worker...");
        parado = true;
        break;
      }
      if (pulso && pulso.pedir_contatos) await exportarContatos(cliente, api);

      let resposta;
      try {
        resposta = await api.manual();
      } catch (erro) {
        const bloqueio = motivoDe(erro);
        const linha = bloqueio
          ? `aguardando: ${bloqueio.motivo}`
          : `erro ao consultar pedidos: ${erro.message}`;
        if (linha !== ultimoAviso) {
          log(linha);
          ultimoAviso = linha;
        }
        await dormir(bloqueio ? 5000 : 3000);
        continue;
      }

      const alvo = resposta && resposta.alvo;
      if (!alvo) {
        await dormir(2000);
        continue;
      }
      ultimoAviso = "";
      reservaAtual = alvo.alvo_id;

      try {
        await enviarUm(cliente, alvo, api);
      } catch (erro) {
        const motivo = String((erro && erro.message) || erro).slice(0, 300);
        await api.confirmar(alvo.alvo_id, "falha", motivo).catch(() => {});
        log(`falha no alvo #${alvo.alvo_id}: ${motivo}`);
      }
      reservaAtual = null;
    }
  } finally {
    encerrando = true;
    if (pausaPedido) await pausaPedido;
    if (reservaAtual) {
      await api.devolver(reservaAtual).catch(() => {});
      log(`alvo #${reservaAtual} devolvido para a fila.`);
      reservaAtual = null;
    }
    await cliente.destroy().catch(() => {});
    log("worker manual encerrado. nada mais sera enviado.");
  }
}

// ---------------------------------- teste ----------------------------------

const TEXTO_TESTE =
  "Teste do conector da campanha ConnectTV. " +
  "Se você recebeu esta mensagem, o envio está funcionando. " +
  "Pode ignorar e apagar.";

async function testar(opcoes, api, chave) {
  const inicial = await api.estado().catch((erro) => {
    log(erro.message);
    return null;
  });
  if (!inicial) {
    process.exitCode = 2;
    return;
  }
  if (inicial.trava) {
    log("envio bloqueado pela trava do servidor (ENVIO_REAL_HABILITADO = False).");
    process.exitCode = 6;
    return;
  }
  if (inicial.modo !== "real") {
    log(`modo atual: ${inicial.modo}. O teste de envio exige CAMPANHA_MODO=real.`);
    process.exitCode = 6;
    return;
  }

  const destino = String(inicial.numero_teste || "").trim();
  if (!destino) {
    log("numero de teste nao configurado.");
    log("na tela Campanha, salve o campo 'numero de teste' (um WhatsApp seu).");
    process.exitCode = 7;
    return;
  }
  if (destino === String(inicial.numero_remetente || "")) {
    log("o numero de teste e igual ao remetente; use outro aparelho para conferir.");
    process.exitCode = 7;
    return;
  }

  const WhatsApp = carregarWhatsApp();
  if (!WhatsApp) return;

  log(`worker da campanha | MODO TESTE | API ${opcoes.api}`);
  log(`destino: +${destino} | chave: ${chave.origem} (nao sera exibida)`);
  log("a fila NAO e usada neste modo: nenhum cliente recebe nada.");

  const cliente = criarCliente(WhatsApp, opcoes);
  try {
    await esperarPronto(cliente);
  } catch (erro) {
    log(`nao abriu o WhatsApp: ${erro.message}`);
    log("se o aparelho ainda nao foi vinculado, rode primeiro: --parear");
    await cliente.destroy().catch(() => {});
    process.exitCode = 5;
    return;
  }

  try {
    const existente = await cliente.getNumberId(destino);
    if (!existente) {
      log(`+${destino} nao tem WhatsApp; nada foi enviado.`);
      process.exitCode = 8;
      return;
    }
    const mensagem = await enviarTexto(cliente, destino, TEXTO_TESTE, 4);
    log(`teste enviado para +${destino} (ack ${mensagem.ack}). confira no aparelho.`);
  } catch (erro) {
    log(`falha no teste: ${erro.message}`);
    process.exitCode = 8;
  } finally {
    await cliente.destroy().catch(() => {});
  }
}

// --------------------------------- estado ----------------------------------

async function mostrarEstado(opcoes, api, chave) {
  log(`API ${opcoes.api} | chave: ${chave.origem} (nao sera exibida)`);
  let estado;
  try {
    estado = await api.estado();
  } catch (erro) {
    log(erro.message);
    process.exitCode = 2;
    return;
  }
  console.log(`liberado : ${estado.liberado}`);
  console.log(`motivo   : ${estado.motivo}`);
  console.log(`modo     : ${estado.modo}`);
  console.log(`trava    : ${estado.trava}`);
  console.log(`hoje     : ${estado.enviados_hoje}/${estado.cota_dia}`);
  console.log(`fila     : ${estado.pendentes} pendentes, ${estado.reservados} reservados`);
  console.log(`remetente: ${estado.numero_remetente ? "+" + estado.numero_remetente : "(nao configurado)"}`);
  console.log(`teste    : ${estado.numero_teste ? "+" + estado.numero_teste : "(nao configurado)"}`);
}

// ------------------------------ numero teste -------------------------------

async function salvarNumeroTeste(opcoes, api, chave) {
  log(`API ${opcoes.api} | chave: ${chave.origem} (nao sera exibida)`);
  try {
    const dados = await api.salvarTeste(opcoes.numeroTeste);
    log(`numero de teste salvo: +${dados.numero_teste}`);
  } catch (erro) {
    log(erro.message);
    process.exitCode = 2;
  }
}

// ---------------------------------- main -----------------------------------

async function principal() {
  const opcoes = lerArgumentos(process.argv.slice(2));
  if (opcoes.ajuda) return ajuda();
  if (opcoes.perfil) return mostrarPerfil();

  const chave = acharChave(opcoes);
  if (!chave) {
    console.error("Falta a chave da API.");
    console.error("Defina CAMPANHA_API_KEY ou use --chave SUACHAVE.");
    process.exitCode = 2;
    return;
  }

  const api = clienteApi(opcoes.api, chave.valor);
  const parar = () => {
    if (parado) return;
    log("Ctrl+C recebido, encerrando...");
    parado = true;
  };
  process.on("SIGINT", parar);
  process.on("SIGTERM", parar);

  if (opcoes.desconectar) return desconectarNumero(opcoes, api);
  if (opcoes.parear) return parear(opcoes, api);
  if (opcoes.numeroTeste) return salvarNumeroTeste(opcoes, api, chave);
  if (opcoes.estado) return mostrarEstado(opcoes, api, chave);
  if (opcoes.teste) return testar(opcoes, api, chave);
  if (opcoes.manual) return enviarManual(opcoes, api, chave);
  if (opcoes.enviar) return enviar(opcoes, api, chave);
  return simular(opcoes, api, chave);
}

void principal();

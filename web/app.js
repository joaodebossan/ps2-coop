const $ = (id) => document.getElementById(id);
const TOKEN = document.querySelector('meta[name="ps2coop-token"]')?.getAttribute("content") || "";

let appState = null;
let refreshing = false;
let pollTimer = null;
let flashTimer = null;
let autoRequested = false;

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setText(id, text) {
  const el = $(id);
  if (el) el.textContent = text ?? "";
}

function setBadge(id, text, cls = "") {
  const el = $(id);
  if (!el) return;
  el.textContent = text;
  el.className = "badge " + cls;
}

function setChip(id, text, cls) {
  const el = $(id);
  if (!el) return;
  el.textContent = text;
  el.className = "chip " + cls;
}

function shortPath(value, max = 38) {
  const text = String(value || "");
  if (!text) return "—";
  if (text.length <= max) return text;
  const parts = text.split(/[\\/]/);
  return "…/" + parts.slice(-2).join("/");
}

async function api(path, body, method = "POST") {
  const options = {
    method,
    headers: {
      "X-PS2Coop-Token": TOKEN,
      "Accept": "application/json",
    },
  };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (!response.ok || (data && data.ok === false)) {
    throw new Error((data && data.error) || `HTTP ${response.status}`);
  }
  return data;
}

function flash(text, ok = false) {
  const el = $("message");
  if (!el) return;
  el.textContent = text || "";
  el.className = "message" + (ok ? " ok" : "");
  if (flashTimer) clearTimeout(flashTimer);
  if (text) flashTimer = setTimeout(() => {
    if (el.textContent === text) {
      el.textContent = "";
      el.className = "message";
    }
  }, 7000);
}

function formatSize(bytes) {
  const value = Number(bytes || 0);
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
  return `${(value / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

function renderJob(prefix, job) {
  const box = $(`${prefix}-job`);
  if (!box) return;
  if (!job) {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  const bar = box.querySelector(".progress span");
  const label = box.querySelector("small");
  const indeterminate = job.progress === null || job.progress === undefined || job.progress < 0;
  box.querySelector(".progress")?.classList.toggle("indeterminate", indeterminate);
  if (bar) bar.style.width = indeterminate ? "35%" : `${Math.max(2, Math.min(100, job.progress * 100))}%`;
  if (label) label.textContent = job.error || job.message || job.status;
}

function setOptions(select, items, value, labelKey, valueKey) {
  if (!select) return;
  const signature = items.map((item) => `${item[valueKey]}:${item[labelKey]}`).join("|");
  if (select.dataset.signature !== signature) {
    select.dataset.signature = signature;
    select.innerHTML = "";
    if (!items.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "Nenhuma ISO, CHD ou CSO nesta pasta";
      select.append(option);
    } else {
      for (const item of items) {
        const option = document.createElement("option");
        option.value = item[valueKey];
        option.textContent = item[labelKey];
        select.append(option);
      }
    }
  }
  if (value !== undefined && value && select.value !== value) select.value = value;
}

function plural(count, singular, pluralWord) {
  return `${count} ${Number(count) === 1 ? singular : pluralWord}`;
}

function confirmGuestReduction(players, hostLocal) {
  const remote = Math.max(0, players - (hostLocal ? 1 : 0));
  const connected = appState?.session?.connected_guests || 0;
  if (remote >= connected) return true;
  return confirm(
    `Isso reduz a sessão para ${plural(remote, "convidado", "convidados")} e vai desconectar ${plural(connected - remote, "pessoa conectada", "pessoas conectadas")}. Continuar?`
  );
}

function virtualCount(data) {
  if (data.app.os === "linux") return data.emulation.gamepads.virtual;
  return data.session.connected_guests;
}

function padsReady(data) {
  const pads = data.emulation.gamepads;
  const session = data.session;
  const hostOk = !data.game.host_local || pads.physical > 0;
  const guestsOk = session.remote_players === 0 || session.connected_guests >= session.remote_players;
  const virtualOk =
    data.app.os !== "linux" ||
    session.remote_players === 0 ||
    pads.virtual >= pads.required;
  return hostOk && guestsOk && virtualOk;
}

function renderAuto(setup) {
  const banner = $("auto-banner");
  if (!banner) return;
  const job = setup.auto;
  if (!job || (job.status === "done" && setup.ready)) {
    banner.hidden = true;
    return;
  }
  banner.hidden = false;
  banner.classList.toggle("done", job.status === "done");
  banner.classList.toggle("error", job.status === "error");
  const running = job.status === "running" || job.status === "pending";
  const blocked = job.status === "blocked";
  setText(
    "auto-title",
    running ? "Preparando automaticamente…" : job.status === "done" ? "Preparação concluída" : blocked ? "Falta só um arquivo" : "A preparação falhou"
  );
  setText("auto-detail", job.error || job.message || "Aguarde…");
  const spinner = $("auto-spinner");
  if (spinner) spinner.hidden = !running;
  const progress = $("auto-progress");
  if (progress) {
    progress.hidden = false;
    const indeterminate = job.progress === null || job.progress === undefined || job.progress < 0;
    progress.classList.toggle("indeterminate", indeterminate);
    const bar = $("auto-bar");
    if (bar) bar.style.width = indeterminate ? "35%" : `${Math.max(2, Math.min(100, (job.progress || 0) * 100))}%`;
  }
  const retry = $("auto-retry");
  if (retry) retry.hidden = job.status !== "error";
}

function renderSetup(data) {
  const setup = data.setup;
  const ready = setup.ready;
  const count = [
    setup.pcsx2.installed,
    setup.moonlight.installed && setup.moonlight.can_host,
    setup.bios.ok,
    setup.image.ok,
  ].filter(Boolean).length;
  setBadge("setup-badge", `${count}/4 ${ready ? "pronto" : "itens"}`, ready ? "ok" : "warn");
  renderAuto(setup);

  setBadge(
    "pcsx2-badge",
    setup.pcsx2.installed ? `v${setup.pcsx2.version || "?"}` : "falta",
    setup.pcsx2.installed ? "ok" : "bad"
  );
  setText(
    "pcsx2-detail",
    setup.pcsx2.installed
      ? `Emulador pronto${setup.pcsx2.path ? ` · ${shortPath(setup.pcsx2.path)}` : ""}.`
      : "Baixa o PCSX2 portátil automaticamente, sem instalar nada no sistema."
  );
  const pcsx2Button = $("install-pcsx2");
  if (pcsx2Button) {
    pcsx2Button.hidden = setup.pcsx2.installed;
    const job = setup.pcsx2.job;
    pcsx2Button.disabled = (!!job && job.status === "running") || data.emulation.running;
  }
  renderJob("pcsx2", setup.pcsx2.job);

  const moonOk = setup.moonlight.installed && setup.moonlight.can_host;
  setBadge(
    "moonlight-badge",
    moonOk ? (setup.moonlight.running ? "rodando" : "instalado") : "falta",
    moonOk ? "ok" : "bad"
  );
  let moonDetail = "Servidor de streaming no navegador.";
  if (setup.moonlight.installed && !setup.moonlight.can_host) {
    moonDetail = "O AppImage portátil não captura a tela local. Instale o pacote do sistema (.deb/.rpm).";
  } else if (setup.moonlight.installed) {
    moonDetail = setup.moonlight.running
      ? `Rodando${setup.moonlight.version ? ` · v${setup.moonlight.version}` : ""}.`
      : "Instalado. O app inicia quando você gerar os convites.";
  }
  setText("moonlight-detail", moonDetail);
  const moonButton = $("install-moonlight");
  if (moonButton) {
    moonButton.hidden = moonOk;
    moonButton.textContent = setup.moonlight.installed && !setup.moonlight.can_host
      ? "Instalar pacote nativo"
      : "Instalar MoonlightWeb";
    const job = setup.moonlight.job;
    moonButton.disabled = (!!job && job.status === "running") || data.emulation.running;
  }
  renderJob("moonlight", setup.moonlight.job);

  setBadge("bios-badge", setup.bios.ok ? "ok" : "falta", setup.bios.ok ? "ok" : "bad");
  setText(
    "bios-detail",
    setup.bios.ok
      ? `Configurada: ${setup.bios.name || "BIOS"}.`
      : "Envie o .bin da BIOS do seu PS2 ou use uma BIOS já instalada no PCSX2."
  );
  const biosSelect = $("bios-candidates");
  const adopt = $("adopt-bios");
  const candidates = setup.bios.candidates || [];
  if (biosSelect && adopt) {
    if (candidates.length && !setup.bios.ok) {
      setOptions(biosSelect, candidates.map((path) => ({ path, label: path })), undefined, "label", "path");
      biosSelect.hidden = false;
      adopt.hidden = false;
    } else {
      biosSelect.hidden = true;
      adopt.hidden = true;
    }
  }

  setBadge("shortcut-badge", setup.shortcut.ok ? "criado" : "—", setup.shortcut.ok ? "ok" : "");
  setText(
    "shortcut-detail",
    setup.shortcut.ok
      ? "Ícone na área de trabalho deste jogo."
      : setup.shortcut.error || "Cria um ícone para abrir esta plataforma."
  );
  const shortcutButton = $("create-shortcut");
  if (shortcutButton) {
    shortcutButton.disabled = setup.shortcut.ok;
    shortcutButton.textContent = setup.shortcut.ok ? "Atalho criado" : "Criar atalho";
  }
}

function renderChips(data) {
  const setup = data.setup;
  const session = data.session;
  const moonClass = setup.moonlight.running && setup.moonlight.can_host
    ? "ok"
    : setup.moonlight.installed
      ? "warn"
      : "bad";
  setChip("chip-moon", "MoonlightWeb", moonClass);
  setChip("chip-pcsx2", "PCSX2", setup.pcsx2.installed ? "ok" : "bad");
  setChip("chip-bios", "BIOS", setup.bios.ok ? "ok" : "bad");
  const pads = data.emulation.gamepads;
  const ready = padsReady(data);
  let controlText = `${session.connected_guests}/${session.remote_players} ${session.remote_players === 1 ? "convidado" : "convidados"}`;
  if (data.game.host_local) {
    controlText = `Host ${pads.physical > 0 ? "ok" : "falta"}`;
    if (session.remote_players > 0) controlText += ` · ${session.connected_guests}/${session.remote_players} ${session.remote_players === 1 ? "convidado" : "convidados"}`;
  }
  setChip(
    "chip-pads",
    controlText,
    ready ? "ok" : session.connected_guests > 0 || pads.virtual > 0 || pads.physical > 0 ? "warn" : "bad"
  );
  const next = nextStep(data);
  const autoRunning = setup.auto && (setup.auto.status === "running" || setup.auto.status === "pending");
  setText(
    "status-note",
    autoRunning
      ? setup.auto.message || "Preparando o ambiente…"
      : data.problems?.[0] || next[0] || (setup.ready ? "Tudo pronto para jogar." : "Complete a preparação.")
  );
}

function nextStep(data) {
  const setup = data.setup;
  const game = data.game;
  const session = data.session;
  const auto = setup.auto;
  if (!setup.image.ok) {
    return ["Coloque o jogo na pasta", "Copie uma ISO, CHD ou CSO do PS2 para esta pasta. O app encontra sozinho.", "Falta ISO", "warn"];
  }
  if (auto && auto.status === "running") {
    return ["Preparando o ambiente", auto.message || "Baixando e configurando o necessário…", "Preparando", "warn"];
  }
  if (auto && auto.status === "blocked") {
    return ["Falta a BIOS do PS2", auto.message || "Envie o .bin da BIOS do seu console na etapa acima.", "Falta BIOS", "warn"];
  }
  if (auto && auto.status === "error") {
    return ["A preparação falhou", auto.error || auto.message || "Use “Tentar de novo”.", "Erro", "bad"];
  }
  if (!setup.pcsx2.installed) {
    return ["Baixe o PCSX2", "O emulador é portátil e fica dentro da pasta do app.", "Falta PCSX2", "warn"];
  }
  if (!setup.moonlight.installed) {
    return ["Instale o MoonlightWeb", "Ele transmite a tela para os amigos entrarem pelo navegador.", "Falta Moonlight", "warn"];
  }
  if (!setup.moonlight.can_host) {
    return ["Instale o MoonlightWeb do sistema", "No Linux, o AppImage não captura a tela local. Use o pacote .deb/.rpm.", "Pacote nativo", "warn"];
  }
  if (!setup.bios.ok) {
    return ["Configure a BIOS", "Envie o arquivo .bin da BIOS do seu PS2. O app não baixa BIOS.", "Falta BIOS", "warn"];
  }
  if (data.emulation.running) {
    return ["Jogo em execução", "O PCSX2 está rodando. Use “Parar jogo” para encerrar e fazer o backup.", "Em jogo", "ok"];
  }
  if (session.remote_players > 0) {
    const invites = data.invites || [];
    const withUrl = invites.filter((invite) => invite.url).length;
    if (!withUrl) {
      return ["Convide os amigos", `Gere ${plural(session.remote_players, "convite", "convites")} com link e PIN.`, "Convidar", "warn"];
    }
    if (session.connected_guests < session.remote_players) {
      return [
        "Aguardando os amigos",
        `${session.connected_guests}/${session.remote_players} ${session.connected_guests === 1 ? "conectado" : "conectados"}. Peça para abrirem o link, digitar o PIN e apertar um botão.`,
        "Aguardando",
        "warn",
      ];
    }
  }
  if (!moonlightReady(data) && session.remote_players > 0) {
    return ["Inicie o MoonlightWeb", "Gere os convites para iniciar a transmissão.", "Moonlight", "warn"];
  }
  if (!padsReady(data)) {
    return ["Controles ainda não estão prontos", "Conecte o controle físico do host e os controles dos convidados.", "Controles", "warn"];
  }
  return [
    "Tudo pronto",
    `${game.players} jogador(es) configurado(s). Os convidados podem entrar e o jogo já pode iniciar.`,
    "Pronto",
    "ok",
  ];
}

function moonlightReady(data) {
  return data.setup.moonlight.running && data.setup.moonlight.can_host;
}

function renderSession(data) {
  const game = data.game;
  const setup = data.setup;
  const pads = data.emulation.gamepads;
  const session = data.session;

  let mode = `${game.players} ${game.players === 1 ? "jogador" : "jogadores"}`;
  if (session.remote_players === 0) mode += " · somente neste PC";
  else if (game.host_local) mode += ` · você + ${session.remote_players} no navegador`;
  else mode += " · todos no navegador";
  if ((game.images || []).length > 1) mode += " · dica: uma pasta por jogo separa os saves";
  setText("session-mode", mode);
  setBadge(
    "session-state",
    data.emulation.running ? "Em jogo" : setup.ready ? "Pronto" : "Configurar",
    data.emulation.running || setup.ready ? "ok" : "warn"
  );

  setOptions($("game-select"), game.images || [], game.image, "name", "name");
  const gameSelect = $("game-select");
  if (gameSelect) gameSelect.disabled = data.emulation.running || (game.images || []).length < 2;

  for (const button of document.querySelectorAll("#players-seg [data-players]")) {
    button.classList.toggle("active", Number(button.dataset.players) === game.players);
    button.disabled = data.emulation.running;
  }
  const hostLocal = $("host-local");
  if (hostLocal) {
    hostLocal.checked = !!game.host_local;
    hostLocal.disabled = data.emulation.running;
  }
  const biosFile = $("bios-file");
  if (biosFile) biosFile.disabled = data.emulation.running;
  const adoptBios = $("adopt-bios");
  if (adoptBios) adoptBios.disabled = data.emulation.running;
  const biosCandidates = $("bios-candidates");
  if (biosCandidates) biosCandidates.disabled = data.emulation.running;

  setText("pad-number", String(virtualCount(data)));
  setText("pad-need", `/ ${pads.required} ${pads.required === 1 ? "controle virtual" : "controles virtuais"}`);
  const names = [...(pads.virtual_names || []), ...(pads.physical_names || [])];
  if (data.app.os !== "linux" && session.connected_guests > 0) {
    names.push(`${session.connected_guests} convidado(s) online`);
  }
  setText(
    "pad-names",
    names.length
      ? `${plural(names.length, "controle detectado", "controles detectados")}: ${names.join(" · ")}`
      : "Conecte o controle físico do host e peça para cada convidado apertar um botão."
  );

  const map = pads.map || [];
  const mapBox = $("pad-map");
  if (mapBox) {
    mapBox.innerHTML = map.length
      ? map
          .map(
            (pad) => `<span class="pad-pill ${pad.connected ? "ok" : ""} ${pad.virtual ? "virtual" : ""}" title="${esc(pad.name || "Não conectado")}">
              <i class="pad-dot" aria-hidden="true"></i><b>P${pad.player}</b>
              ${esc(pad.connected ? pad.name : "não conectado")}
              ${pad.sdl !== null && pad.sdl !== undefined ? `<code>SDL-${pad.sdl}</code>` : ""}
            </span>`
          )
          .join("")
      : "";
  }

  const invites = data.invites || [];
  const withUrl = invites.filter((invite) => invite.url).length;
  const remote = session.remote_players;
  const flows = {
    "flow-invites": remote === 0 ? "done" : withUrl >= remote ? "done" : "active",
    "flow-guests": remote === 0 ? "done" : session.connected_guests >= remote ? "done" : withUrl >= remote ? "active" : "",
    "flow-start": data.emulation.running ? "done" : session.connected_guests >= remote && withUrl >= remote ? "active" : "",
  };
  for (const [id, state] of Object.entries(flows)) {
    const el = $(id);
    if (!el) continue;
    el.classList.toggle("done", state === "done");
    el.classList.toggle("active", state === "active");
  }

  const force = $("force");
  const start = $("start-game");
  const autoRunning = setup.auto && (setup.auto.status === "running" || setup.auto.status === "pending");
  if (start) {
    start.disabled =
      data.emulation.running ||
      !setup.ready ||
      !!autoRunning ||
      (!session.can_start && !(force && force.checked));
  }
  const stop = $("stop-game");
  if (stop) stop.disabled = !data.emulation.running;
  const backup = $("backup");
  if (backup) {
    backup.disabled = data.emulation.running;
    backup.title = data.emulation.running ? "Pare o jogo para copiar o memory card" : "";
  }
  const openHost = $("open-host");
  if (openHost) openHost.disabled = !setup.moonlight.installed || !setup.moonlight.can_host;
  const createInvites = $("create-invites");
  if (createInvites) {
    createInvites.disabled = !setup.moonlight.installed || !setup.moonlight.can_host || remote === 0;
    createInvites.textContent = remote > 0 ? `1. Convidar ${plural(remote, "amigo", "amigos")}` : "Sem convites no modo solo";
  }
}

function renderInvites(data) {
  const game = data.game;
  const session = data.session;
  const invites = data.invites || [];
  const needed = session.remote_players;
  const withUrl = invites.filter((invite) => invite.url).length;
  const connected = invites.filter((invite) => invite.connected).length;

  if (needed === 0) {
    setBadge("invite-badge", "modo solo", "ok");
    const list = $("invite-list");
    if (list) list.innerHTML = '<p class="muted">Sessão de 1 jogador. Nenhum convite necessário.</p>';
    setText("generate-invites", "Sem convites no modo solo");
    const gen = $("generate-invites");
    if (gen) gen.disabled = true;
    return;
  }

  setBadge(
    "invite-badge",
    `${withUrl}/${needed} links · ${connected}/${needed} online`,
    connected >= needed ? "ok" : "warn"
  );
  const gen = $("generate-invites");
  if (gen) {
    gen.disabled = !data.setup.moonlight.installed || !data.setup.moonlight.can_host;
    gen.textContent = withUrl ? "Gerar / atualizar convites" : "Gerar convites";
  }
  const select = $("invite-network");
  if (select) select.value = game.invite_network || "auto";
  const revoke = $("revoke-invites");
  if (revoke) revoke.disabled = !data.setup.moonlight.installed || !data.setup.moonlight.can_host;

  const list = $("invite-list");
  if (!list) return;
  if (!invites.length) {
    list.innerHTML = '<p class="muted">Nenhum convite carregado. Clique em “Gerar convites”.</p>';
    return;
  }

  list.innerHTML = invites
    .map((invite) => {
      const status = invite.connected
        ? '<span class="connected">conectado</span>'
        : invite.url
          ? '<span class="waiting">aguardando entrar</span>'
          : '<span class="waiting">sem link ativo</span>';
      const link = invite.url
        ? `<code title="${esc(invite.url)}">${esc(invite.url)}</code>`
        : `<span class="muted">${invite.state === "off" ? "Gere o convite para este jogador." : "Link expirado — gere novamente."}</span>`;
      const pin = invite.pin ? `<span class="pin">PIN ${esc(invite.pin)}</span>` : "";
      const reach = invite.reach ? `<span class="badge ${invite.reach === "public" ? "ok" : ""}">${esc(invite.reach)}</span>` : "";
      const copy = invite.url
        ? `<button class="btn btn-ghost btn-sm" data-copy-url="${esc(invite.url)}" type="button">Copiar link</button>
           <button class="btn btn-ghost btn-sm" data-copy-invite="${esc(invite.slot)}" type="button">Copiar tudo</button>`
        : "";
      return `<div class="invite-row ${invite.url ? "ready" : ""}">
        <div class="invite-head"><strong>${esc(invite.name || `Jogador ${invite.player}`)}</strong> ${status} ${reach}</div>
        <div class="invite-link">${link} ${pin} ${copy}</div>
      </div>`;
    })
    .join("");

  const hint = $("invite-hint");
  if (hint) {
    hint.textContent = connected >= needed
      ? `${needed === 1 ? "O convidado está conectado" : "Todos os convidados estão conectados"}. Inicie o jogo e mantenha esta página aberta. Ao terminar, clique em Revogar para fechar os links.`
      : `Gera ${plural(needed, "convite", "convites")}. O PIN é separado do link de propósito. Peça para cada amigo abrir o link, digitar o PIN e apertar um botão no controle antes do boot. Ao terminar, revogue os convites.`;
  }
}

function renderConnection(data) {
  const connection = data.connection || {};
  setText("lan-link", connection.lan || "—");
  setText("public-link", connection.public || (connection.public_enabled ? "Sem link público agora" : "Internet desligada"));
  const status = connection.public
    ? ["Internet", "ok"]
    : connection.running
      ? ["Somente LAN", "warn"]
      : ["Offline", "bad"];
  setBadge("net-status", status[0], status[1]);
  setText(
    "net-notice",
    connection.public
      ? "O link público é para amigos fora da sua rede. O link de LAN é para quem está no mesmo roteador e usa um certificado autoassinado — o amigo precisa aceitar o aviso."
      : connection.public_enabled
        ? "Internet Access está ligado, mas o link público ainda não está disponível. O link de LAN funciona na mesma rede."
        : "Internet Access está desligado. O link de LAN funciona na mesma rede; para fora, ligue no Admin do MoonlightWeb. O certificado de LAN é autoassinado."
  );
  for (const button of document.querySelectorAll("[data-copy]")) {
    const source = $(button.dataset.copy);
    if (source) button.disabled = !/^https?:\/\//.test((source.textContent || "").trim());
  }
}

function renderChecklist(data) {
  const setup = data.setup;
  const pads = data.emulation.gamepads;
  const session = data.session;
  const set = (id, cls) => {
    const el = $(id);
    if (el) el.className = cls;
  };
  set("chk-moon", setup.moonlight.running && setup.moonlight.can_host ? "ok" : setup.moonlight.installed ? "warn" : "bad");
  set("chk-pcsx2", setup.pcsx2.installed ? "ok" : "bad");
  set("chk-bios", setup.bios.ok ? "ok" : "bad");
  set("chk-iso", setup.image.ok ? "ok" : "bad");
  const ready = padsReady(data);
  set("chk-pads", ready ? "ok" : pads.virtual > 0 || session.connected_guests > 0 ? "warn" : "bad");
}

function renderSaves(data) {
  const list = $("backup-list");
  if (!list) return;
  const backups = data.saves?.backups || [];
  if (!backups.length) {
    list.innerHTML = '<li class="muted">Nenhum backup ainda.</li>';
    return;
  }
  list.innerHTML = backups
    .map(
      (backup) => `<li class="backup-row">
        <div><strong>${esc(backup.name)}</strong><br><small>${backup.files} arquivo(s) · ${formatSize(backup.size)}</small></div>
        <button class="btn btn-ghost btn-sm" data-restore="${esc(backup.name)}" type="button" ${data.emulation.running ? "disabled" : ""}>Restaurar</button>
      </li>`
    )
    .join("");
}

function renderDiagnostics(data) {
  const setup = data.setup;
  const connection = data.connection || {};
  setText("diag-version", `${data.app.name} v${data.app.version}`);
  setText("diag-os", `${data.app.platform || data.app.os}`);
  setText("diag-pcsx2", setup.pcsx2.installed ? `v${setup.pcsx2.version || "?"} · ${shortPath(setup.pcsx2.path, 30)}` : "não instalado");
  setText("diag-moonlight", setup.moonlight.installed ? `${setup.moonlight.running ? "rodando" : "instalado"} · ${shortPath(setup.moonlight.path, 24)}` : "não instalado");
  setText("diag-port", connection.running ? String(connection.port || "—") : "offline");
  setText(
    "diag-hint",
    `MoonlightWeb: ${data.app.logs || "runtime/logs"}. PCSX2: .ps2coop/logs na pasta do jogo.`
  );
}

function render(data) {
  appState = data;
  const game = data.game;
  document.title = `${game.title} — PS2 Co-op`;
  setText("game-title", game.title);

  const [title, text, badgeText, badgeClass] = nextStep(data);
  setText("next-title", title);
  setText("next-text", text);
  setBadge("next-badge", badgeText, badgeClass);

  renderChips(data);
  renderSetup(data);
  renderSession(data);
  renderInvites(data);
  renderConnection(data);
  renderChecklist(data);
  renderSaves(data);
  renderDiagnostics(data);

  maybeRequestAutoSetup(data);

  const jobRunning = Object.values(data.jobs || {}).some((job) => job.status === "running" || job.status === "pending");
  schedulePoll(data.emulation.running || jobRunning ? 1200 : 2800);
}

function maybeRequestAutoSetup(data) {
  const setup = data.setup;
  const auto = setup.auto;
  if (!setup.auto_enabled) return;
  if (autoRequested || !setup.image.ok || setup.ready) return;
  if (auto) return;
  autoRequested = true;
  api("/api/setup/auto", {})
    .then(() => refresh())
    .catch(() => {
      autoRequested = false;
    });
}

function schedulePoll(delay) {
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = setTimeout(refresh, document.hidden ? Math.max(delay, 5000) : delay);
}

async function refresh() {
  if (refreshing) return;
  refreshing = true;
  try {
    const response = await fetch("/api/status", { headers: { Accept: "application/json" } });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || "Falha ao consultar o estado.");
    render(data);
  } catch (error) {
    setText("status-note", error.message || "Servidor indisponível.");
    schedulePoll(4000);
  } finally {
    refreshing = false;
  }
}

async function copyText(text) {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    flash("Copiado.", true);
  } catch {
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.append(area);
    area.select();
    try {
      document.execCommand("copy");
      flash("Copiado.", true);
    } catch {
      flash("Não foi possível copiar.");
    }
    area.remove();
  }
}

function syncThemeControls() {
  const mode = window.PS2Theme?.mode || "system";
  for (const button of document.querySelectorAll("[data-theme-choice]")) {
    button.setAttribute("aria-pressed", String(button.dataset.themeChoice === mode));
  }
}

function bind() {
  $("install-pcsx2")?.addEventListener("click", async () => {
    try {
      await api("/api/setup/pcsx2", {});
      flash("Baixando PCSX2…", true);
      refresh();
    } catch (error) {
      flash(error.message);
    }
  });

  $("install-moonlight")?.addEventListener("click", async () => {
    try {
      await api("/api/setup/moonlight", {});
      flash("Instalando MoonlightWeb…", true);
      refresh();
    } catch (error) {
      flash(error.message);
    }
  });

  $("auto-retry")?.addEventListener("click", async () => {
    try {
      await api("/api/setup/auto", {});
      flash("Tentando preparar de novo…", true);
      refresh();
    } catch (error) {
      flash(error.message);
    }
  });

  $("create-shortcut")?.addEventListener("click", async () => {
    try {
      await api("/api/setup/shortcut", {});
      flash("Atalho criado na área de trabalho.", true);
      refresh();
    } catch (error) {
      flash(error.message);
    }
  });

  $("game-select")?.addEventListener("change", async (event) => {
    try {
      await api("/api/game/select", { image: event.target.value });
      autoRequested = false;
      refresh();
    } catch (error) {
      flash(error.message);
    }
  });

  for (const button of document.querySelectorAll("#players-seg [data-players]")) {
    button.addEventListener("click", async () => {
      try {
        let players = Number(button.dataset.players);
        let hostLocal = $("host-local")?.checked || false;
        if (players === 4 && !hostLocal) {
          hostLocal = true;
          if ($("host-local")) $("host-local").checked = true;
          flash("4 jogadores ativa o Host local: você + 3 convidados.", true);
        }
        if (!confirmGuestReduction(players, hostLocal)) {
          refresh();
          return;
        }
        await api("/api/game/players", { players, host_local: hostLocal });
        autoRequested = false;
        refresh();
      } catch (error) {
        flash(error.message);
      }
    });
  }

  $("host-local")?.addEventListener("change", async (event) => {
    try {
      let players = appState?.game?.players || 2;
      if (!event.target.checked && players === 4) {
        players = 3;
        flash("Sem host local, o limite é 3 jogadores. Ajustado para 3.", true);
      }
      if (!confirmGuestReduction(players, event.target.checked)) {
        refresh();
        return;
      }
      await api("/api/game/players", {
        players,
        host_local: event.target.checked,
      });
      refresh();
    } catch (error) {
      flash(error.message);
      refresh();
    }
  });

  $("force")?.addEventListener("change", () => {
    if (appState) render(appState);
  });

  $("start-game")?.addEventListener("click", async () => {
    flash("");
    try {
      await api("/api/start", { force: $("force")?.checked || false });
      flash("Jogo iniciado.", true);
      refresh();
    } catch (error) {
      flash(error.message);
    }
  });

  $("stop-game")?.addEventListener("click", async () => {
    flash("");
    try {
      const result = await api("/api/stop", {});
      flash(result.backup ? "Jogo encerrado e backup copiado." : "Jogo encerrado. Ainda não há memory card para backup.", true);
      refresh();
    } catch (error) {
      flash(error.message);
    }
  });

  $("open-host")?.addEventListener("click", () => api("/api/open/host", {}).catch((error) => flash(error.message)));
  $("open-admin")?.addEventListener("click", () => api("/api/open/admin", {}).catch((error) => flash(error.message)));
  $("open-folder")?.addEventListener("click", () => api("/api/open/folder", {}).catch((error) => flash(error.message)));
  $("open-saves")?.addEventListener("click", () => api("/api/open/saves", {}).catch((error) => flash(error.message)));
  $("open-logs")?.addEventListener("click", () => api("/api/open/logs", {}).catch((error) => flash(error.message)));
  $("open-pcsx2-logs")?.addEventListener("click", () => api("/api/open/pcsx2logs", {}).catch((error) => flash(error.message)));
  $("moonlight-start")?.addEventListener("click", async () => {
    try {
      await api("/api/moonlight/start", {});
      flash("MoonlightWeb iniciado.", true);
      refresh();
    } catch (error) {
      flash(error.message);
    }
  });

  $("generate-invites")?.addEventListener("click", async () => {
    const connected = (appState?.invites || []).some((invite) => invite.connected);
    if (connected && !confirm("Há convidados conectados. Atualizar os convites vai desconectá-los. Continuar?")) return;
    try {
      await api("/api/invites/create", { link_address: $("invite-network")?.value || "auto" });
      flash("Convites atualizados.", true);
      refresh();
    } catch (error) {
      flash(error.message);
    }
  });

  $("revoke-invites")?.addEventListener("click", async () => {
    if (!confirm("Revogar todos os convites? Os amigos conectados serão desconectados.")) return;
    try {
      await api("/api/invites/revoke", {});
      flash("Convites revogados.", true);
      refresh();
    } catch (error) {
      flash(error.message);
    }
  });

  $("invite-network")?.addEventListener("change", async (event) => {
    try {
      await api("/api/settings", { invite_network: event.target.value });
      flash("Preferência de rede salva.", true);
      refresh();
    } catch (error) {
      flash(error.message);
    }
  });

  $("backup")?.addEventListener("click", async () => {
    try {
      await api("/api/saves/backup", {});
      flash("Backup criado.", true);
      refresh();
    } catch (error) {
      flash(error.message);
    }
  });

  $("quit-app")?.addEventListener("click", async () => {
    if (!confirm("Fechar o portal? O jogo e a transmissão do MoonlightWeb continuam. Revogue os convites antes de sair.")) return;
    try {
      await api("/api/quit", {});
      document.body.innerHTML = '<main class="page"><section class="card"><h1>Portal fechado</h1><p class="muted">Você pode fechar esta aba. O jogo no PCSX2 continua aberto.</p></section></main>';
    } catch (error) {
      flash(error.message);
    }
  });

  $("bios-file")?.addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const response = await fetch(`/api/setup/bios?name=${encodeURIComponent(file.name)}`, {
        method: "POST",
        headers: {
          "X-Filename": file.name,
          "X-PS2Coop-Token": TOKEN,
          "Content-Type": "application/octet-stream",
        },
        body: await file.arrayBuffer(),
      });
      const data = await response.json();
      if (!response.ok || data.ok === false) throw new Error(data.error || "Falha ao enviar a BIOS.");
      flash("BIOS configurada.", true);
      autoRequested = false;
      refresh();
    } catch (error) {
      flash(error.message);
    } finally {
      event.target.value = "";
    }
  });

  $("adopt-bios")?.addEventListener("click", async () => {
    const path = $("bios-candidates")?.value;
    if (!path) return;
    try {
      await api("/api/setup/bios/adopt", { path });
      flash("BIOS importada.", true);
      autoRequested = false;
      refresh();
    } catch (error) {
      flash(error.message);
    }
  });

  for (const button of document.querySelectorAll("[data-theme-choice]")) {
    button.addEventListener("click", () => {
      window.PS2Theme?.set(button.dataset.themeChoice || "system");
      syncThemeControls();
    });
  }
  window.addEventListener("ps2coop-theme", syncThemeControls);
  syncThemeControls();

  document.addEventListener("click", (event) => {
    const copy = event.target.closest("[data-copy]");
    if (copy) {
      const source = $(copy.dataset.copy);
      if (source) copyText(source.textContent || "");
      return;
    }
    const copyUrl = event.target.closest("[data-copy-url]");
    if (copyUrl) {
      copyText(copyUrl.dataset.copyUrl || "");
      return;
    }
    const copyInvite = event.target.closest("[data-copy-invite]");
    if (copyInvite) {
      const invite = (appState?.invites || []).find((item) => String(item.slot) === String(copyInvite.dataset.copyInvite));
      if (invite) {
        const text = [
          `Convite PS2 Co-op — ${invite.name || `Jogador ${invite.player}`}`,
          invite.url ? `Link: ${invite.url}` : "",
          invite.pin ? `PIN: ${invite.pin}` : "",
        ].filter(Boolean).join("\n");
        copyText(text);
      }
      return;
    }
    const restore = event.target.closest("[data-restore]");
    if (restore) {
      const name = restore.dataset.restore;
      if (!confirm(`Restaurar o save ${name}? O progresso atual será copiado antes.`)) return;
      api("/api/saves/restore", { name })
        .then(() => {
          flash("Save restaurado.", true);
          refresh();
        })
        .catch((error) => flash(error.message));
    }
  });

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refresh();
  });
}

bind();
refresh();

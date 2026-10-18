(function () {
  "use strict";
  if (window.__acidModLoaderInjected) return;
  window.__acidModLoaderInjected = true;

  const style = document.createElement("style");
  style.textContent = `
    .acid-loader-fab{position:fixed;left:24px;top:90px;z-index:40;background:#00ff00;color:#111;
      border:0;height:44px;padding:0 16px;display:flex;align-items:center;gap:10px;font-size:.72rem;
      font-weight:900;text-transform:uppercase;letter-spacing:.08em;box-shadow:0 10px 30px #0009;
      cursor:pointer;font-family:Oswald,Impact,Arial Narrow,sans-serif}
    .acid-loader-fab:hover{background:#1b5e20;color:#fff}
    .acid-loader-fab em{font-style:normal;color:#083}
    .acid-loader-fab:hover em{color:#bdf5c8}
    .acid-loader-gb-fab{position:fixed;left:24px;top:146px;z-index:40;background:#ffb400;color:#1a1200;
      border:0;height:44px;padding:0 16px;display:flex;align-items:center;gap:10px;font-size:.72rem;
      font-weight:900;text-transform:uppercase;letter-spacing:.08em;box-shadow:0 10px 30px #0009;
      cursor:pointer;font-family:Oswald,Impact,Arial Narrow,sans-serif}
    .acid-loader-gb-fab:hover{background:#7a4b00;color:#fff}
    .acid-loader-drop{position:fixed;left:24px;bottom:24px;z-index:40;width:340px;height:170px;box-sizing:border-box;
      padding:20px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;
      text-align:center;border:3px dashed #00ff00;border-radius:10px;
      background:#111e;color:#00ff00;cursor:pointer;box-shadow:0 14px 40px #000b;
      font-family:Oswald,Impact,Arial Narrow,sans-serif;text-transform:uppercase;letter-spacing:.08em;
      transition:background .12s,transform .12s,width .12s,height .12s}
    .acid-loader-drop .acid-drop-icon{font-size:2.6rem;line-height:1}
    .acid-loader-drop strong{font-size:1.15rem;font-weight:900}
    .acid-loader-drop span{font-size:.75rem;color:#7fbf8a;letter-spacing:.06em}
    .acid-loader-drop:hover{background:#1b5e20;color:#fff}
    .acid-loader-drop.is-over{background:#00ff00;color:#111;width:420px;height:220px;border-style:solid}
    .acid-loader-drop.is-over span{color:#083}
    .acid-loader-drop.is-busy{opacity:.8;pointer-events:none;border-color:#ffb400;color:#ffb400}
    .acid-loader-navbar{position:fixed;top:8px;left:8px;z-index:2147483000;display:flex;
      background:#111d;border:1px solid #0f04;border-radius:6px;overflow:hidden;
      box-shadow:0 6px 18px #0009}
    .acid-loader-nav-btn{background:transparent;color:#0f0;border:0;width:32px;height:28px;
      font-size:.95rem;line-height:1;cursor:pointer;display:flex;align-items:center;
      justify-content:center;font-family:Consolas,Menlo,monospace}
    .acid-loader-nav-btn:hover{background:#1b5e20;color:#fff}
    .acid-loader-nav-btn+.acid-loader-nav-btn{border-left:1px solid #0f04}
    dialog#acid-install-log{width:min(610px,calc(100vw - 32px));background:#111;color:#00ff00;
      border:1px solid #4b4129;padding:clamp(26px,5vw,48px);box-shadow:0 30px 100px #000;position:fixed}
    dialog#acid-install-log::backdrop{background:rgba(0,0,0,.82);backdrop-filter:blur(6px)}
    dialog#acid-install-log h2{font-size:1.8rem;text-transform:uppercase;margin:0;color:#fff;
      font-family:Oswald,Impact,Arial Narrow,sans-serif}
    dialog#acid-install-log .acid-dialog-close{position:absolute;right:18px;top:12px;color:#aaa;
      border:0;background:transparent;font-size:1.5rem;cursor:pointer}
    dialog#acid-install-log pre{white-space:pre-wrap;font-family:Consolas,Menlo,monospace;
      font-size:.82rem;max-height:50vh;overflow:auto;margin-top:18px}
    .mod-card a.button[data-acid-state="busy"]{opacity:.75;pointer-events:none;filter:grayscale(.3)}
    .mod-card a.button[data-acid-state="done"]{background:#00ff00;box-shadow:0 0 26px rgba(0,255,0,.65)}
    .mod-card a.button[data-acid-state="error"]{background:#ff5c5c;color:#1a0000;box-shadow:none}
    header#top{display:none !important}
  `;
  document.head.appendChild(style);

  const dialog = document.createElement("dialog");
  dialog.id = "acid-install-log";
  dialog.innerHTML = `
    <button class="acid-dialog-close" type="button" aria-label="Close">×</button>
    <h2 id="acid-install-log-title">Installing…</h2>
    <pre id="acid-install-log-body"></pre>
  `;
  document.body.appendChild(dialog);
  dialog.querySelector(".acid-dialog-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", event => {
    if (event.target === dialog) dialog.close();
  });

  function showLog(title, lines, ok) {
    const titleEl = document.getElementById("acid-install-log-title");
    const body = document.getElementById("acid-install-log-body");
    titleEl.textContent = title;
    titleEl.style.color = ok ? "#fff" : "#ff5c5c";
    body.textContent = (lines || []).join("\n");
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  const navbar = document.createElement("div");
  navbar.className = "acid-loader-navbar";
  navbar.innerHTML = `
    <button type="button" class="acid-loader-nav-btn" data-act="back" title="Back">←</button>
    <button type="button" class="acid-loader-nav-btn" data-act="fwd" title="Forward">→</button>
    <button type="button" class="acid-loader-nav-btn" data-act="reload" title="Reload">⟳</button>
  `;
  document.body.appendChild(navbar);
  navbar.addEventListener("click", event => {
    const btn = event.target.closest("button[data-act]");
    if (!btn) return;
    if (btn.dataset.act === "back") history.back();
    else if (btn.dataset.act === "fwd") history.forward();
    else if (btn.dataset.act === "reload") location.reload();
  });

  const fab = document.createElement("button");
  fab.type = "button";
  fab.className = "acid-loader-fab";
  fab.innerHTML = `📁 <em id="acid-loader-fab-path">Brawlhalla: not set</em>`;
  document.body.appendChild(fab);

  function shortenPath(path) {
    if (!path) return "not set — click to choose";
    return path.length > 42 ? "…" + path.slice(-40) : path;
  }

  async function refreshFabPath() {
    const path = await window.pywebview.api.get_brawlhalla_path();
    document.getElementById("acid-loader-fab-path").textContent = "Brawlhalla: " + shortenPath(path);
  }


  function openPathDialog(onDone) {
    if (document.getElementById("acid-path-overlay")) return;
    const overlay = document.createElement("div");
    overlay.id = "acid-path-overlay";
    overlay.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,.65);z-index:2147483647;display:flex;align-items:center;justify-content:center;font-family:system-ui,sans-serif;";
    overlay.innerHTML = `
      <div style="background:#14161a;color:#e8e8e8;border:1px solid #2c3037;border-radius:10px;padding:18px;width:min(560px,92vw);box-shadow:0 10px 40px rgba(0,0,0,.6)">
        <div style="font-weight:600;margin-bottom:8px">📁 Carpeta de Brawlhalla</div>
        <input id="acid-path-input" type="text" spellcheck="false" autocomplete="off"
          placeholder="/home/usuario/.local/share/Steam/steamapps/common/Brawlhalla"
          style="width:100%;box-sizing:border-box;padding:9px;border-radius:6px;border:1px solid #3a3f48;background:#0b0c0f;color:#fff;font-family:monospace;font-size:13px">
        <div id="acid-path-msg" style="min-height:18px;margin:8px 0;font-size:12px;color:#ff8a8a"></div>
        <div style="display:flex;gap:8px;justify-content:flex-end">
          <button type="button" id="acid-path-browse" style="padding:7px 12px;border-radius:6px;border:1px solid #3a3f48;background:#1d2127;color:#ddd;cursor:pointer">Examinar…</button>
          <button type="button" id="acid-path-cancel" style="padding:7px 12px;border-radius:6px;border:1px solid #3a3f48;background:#1d2127;color:#ddd;cursor:pointer">Cancelar</button>
          <button type="button" id="acid-path-save" style="padding:7px 14px;border-radius:6px;border:0;background:#7c4dff;color:#fff;cursor:pointer;font-weight:600">Guardar</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    const input = overlay.querySelector("#acid-path-input");
    const msg = overlay.querySelector("#acid-path-msg");
    const close = () => overlay.remove();
    window.pywebview.api.get_brawlhalla_path().then((p) => { input.value = p || ""; input.select(); });
    input.focus();

    async function save() {
      const res = await window.pywebview.api.set_brawlhalla_path(input.value);
      if (!res.ok) { msg.style.color = "#ff8a8a"; msg.textContent = res.error; return; }
      if (res.warning) { msg.style.color = "#ffd27a"; msg.textContent = res.warning; setTimeout(close, 1800); }
      else close();
      onDone && onDone();
    }
    overlay.querySelector("#acid-path-save").addEventListener("click", save);
    overlay.querySelector("#acid-path-cancel").addEventListener("click", close);
    overlay.querySelector("#acid-path-browse").addEventListener("click", async () => {
      const p = await window.pywebview.api.pick_brawlhalla_folder();
      if (p) input.value = p;
    });
    overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) close(); });
    input.addEventListener("keydown", (e) => {
      e.stopPropagation();
      if (e.key === "Enter") save();
      if (e.key === "Escape") close();
    });
  }

  fab.addEventListener("click", () => openPathDialog(refreshFabPath));
  refreshFabPath();

  const gbFab = document.createElement("button");
  gbFab.type = "button";
  gbFab.className = "acid-loader-gb-fab";
  gbFab.textContent = "🍌 Go to GameBanana";
  gbFab.addEventListener("click", () => {
    window.pywebview.api.navigate("https://gamebanana.com/mods/games/5704");
  });
  document.body.appendChild(gbFab);

  // ---- Drop zone: suelta .zip / .swf / .bmod para instalarlos ----
  const dropZone = document.createElement("div");
  dropZone.className = "acid-loader-drop";
  dropZone.innerHTML = `<div class="acid-drop-icon">⬇</div><strong>Drop mod here</strong><span>.zip · .swf · .bmod — or click</span>`;
  document.body.appendChild(dropZone);

  const dropInput = document.createElement("input");
  dropInput.type = "file";
  dropInput.multiple = true;
  dropInput.accept = ".zip,.rar,.7z,.swf,.bmod";
  dropInput.style.display = "none";
  document.body.appendChild(dropInput);

  const DROP_IDLE_HTML = dropZone.innerHTML;
  let dropBusy = false;

  function readAsBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const text = String(reader.result);
        resolve(text.slice(text.indexOf(",") + 1));
      };
      reader.onerror = () => reject(reader.error || new Error("Couldn't read " + file.name));
      reader.readAsDataURL(file);
    });
  }

  async function installDropped(fileList) {
    const files = Array.from(fileList || []);
    if (!files.length || dropBusy) return;
    dropBusy = true;
    dropZone.classList.remove("is-over");
    dropZone.classList.add("is-busy");

    const allLog = [];
    let allOk = true;
    try {
      for (const file of files) {
        dropZone.innerHTML = `<div class="acid-drop-icon">⏳</div><strong>Installing…</strong><span>${file.name.replace(/[<&]/g, "")}</span>`;
        allLog.push(`=== ${file.name} ===`);
        try {
          const b64 = await readAsBase64(file);
          const result = await window.pywebview.api.install_dropped_file(file.name, b64);
          if (!(result && result.ok)) allOk = false;
          allLog.push(...((result && result.log) || ["Unknown error."]));
        } catch (err) {
          allOk = false;
          allLog.push("[X] " + String(err));
        }
        allLog.push("");
      }
    } finally {
      dropBusy = false;
      dropZone.classList.remove("is-busy");
      dropZone.innerHTML = DROP_IDLE_HTML;
      dropInput.value = "";
    }
    showLog(allOk ? "Installed" : "Install finished with errors", allLog, allOk);
  }

  function dragHasFiles(event) {
    const types = event.dataTransfer && event.dataTransfer.types;
    return !!types && Array.from(types).includes("Files");
  }

  // Evita que WebView2 navegue al archivo si se suelta fuera de la zona;
  // soltar en cualquier parte de la ventana instala el archivo.
  window.addEventListener("dragenter", event => {
    if (!dragHasFiles(event)) return;
    event.preventDefault();
    dropZone.classList.add("is-over");
  });
  window.addEventListener("dragover", event => {
    if (!dragHasFiles(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    dropZone.classList.add("is-over");
  });
  window.addEventListener("dragleave", event => {
    if (!event.relatedTarget) dropZone.classList.remove("is-over");
  });
  window.addEventListener("drop", event => {
    if (!dragHasFiles(event)) return;
    event.preventDefault();
    installDropped(event.dataTransfer.files);
  });

  dropZone.addEventListener("click", () => dropInput.click());
  dropInput.addEventListener("change", () => installDropped(dropInput.files));

  function setButtonState(link, state, text) {
    link.dataset.acidState = state;
    link.textContent = text;
  }

  async function installFromLink(link) {
    if (link.dataset.acidState === "busy") return;
    const url = link.href;
    const originalLabel = link.dataset.acidOriginalLabel || link.textContent;
    link.dataset.acidOriginalLabel = originalLabel;

    setButtonState(link, "busy", "Installing…");
    try {
      const card = link.closest(".mod-card");
      const titleEl = card && card.querySelector("h1,h2,h3,h4,.mod-title,.title");
      const title = titleEl ? titleEl.textContent.trim() : "";
      const result = await window.pywebview.api.install_mod(url, title);
      if (result && result.ok) {
        setButtonState(link, "done", "Installed ✓");
        showLog("Installed", result.log, true);
      } else {
        setButtonState(link, "error", "Install failed ✕");
        showLog("Install failed", (result && result.log) || ["Unknown error."], false);
      }
    } catch (err) {
      setButtonState(link, "error", "Install failed ✕");
      showLog("Install failed", [String(err)], false);
    } finally {
      setTimeout(() => setButtonState(link, "idle", originalLabel), 2600);
    }
  }

  function hideAcidToolsPromo() {
    const heading = document.getElementById("mods-tools-title");
    if (!heading) return;
    const intro = heading.closest(".services-tab-intro");
    if (!intro || intro.dataset.acidToolsHidden) return;
    const cta = intro.nextElementSibling;
    const grid = cta && cta.nextElementSibling;
    [intro, cta, grid].forEach(el => { if (el) el.style.display = "none"; });
    intro.dataset.acidToolsHidden = "1";
  }

  function hideMusicWidget() {
    const toggle = document.getElementById("music-toggle");
    const panel = document.getElementById("music-panel");
    const audio = document.getElementById("bg-audio");
    if (toggle) toggle.style.display = "none";
    if (panel) panel.style.display = "none";
    if (audio) {
      audio.muted = true;
      audio.volume = 0;
      if (!audio.paused) audio.pause();
    }
  }

  function getGameModGrids() {
    const modsSection = document.getElementById("mods");
    if (!modsSection) return [];
    const toolsWrapper = modsSection.querySelector('div[style*="max-width:1500px"]');
    return Array.from(modsSection.querySelectorAll(".mods-grid")).filter(
      grid => !(toolsWrapper && toolsWrapper.contains(grid))
    );
  }

  function convertModCards() {
    getGameModGrids().forEach(grid => {
      grid.querySelectorAll(".mod-card a.button[href]").forEach(link => {
        if (link.dataset.acidWired) return;
        link.dataset.acidWired = "1";
        link.removeAttribute("download");
        setButtonState(link, "idle", "Install ⚡");
        link.addEventListener("click", event => {
          event.preventDefault();
          installFromLink(link);
        });
      });
    });
  }

  function onPageChange() {
    convertModCards();
    hideAcidToolsPromo();
    hideMusicWidget();
  }

  onPageChange();
  new MutationObserver(onPageChange).observe(document.body, { childList: true, subtree: true });
})();

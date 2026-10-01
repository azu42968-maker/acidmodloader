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

  fab.addEventListener("click", async () => {
    await window.pywebview.api.pick_brawlhalla_folder();
    refreshFabPath();
  });
  refreshFabPath();

  const gbFab = document.createElement("button");
  gbFab.type = "button";
  gbFab.className = "acid-loader-gb-fab";
  gbFab.textContent = "🍌 Go to GameBanana";
  gbFab.addEventListener("click", () => {
    window.pywebview.api.navigate("https://gamebanana.com/mods/games/5704");
  });
  document.body.appendChild(gbFab);

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

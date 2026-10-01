(function () {
  "use strict";
  if (window.__acidModLoaderGbInjected) return;
  window.__acidModLoaderGbInjected = true;

  const style = document.createElement("style");
  style.textContent = `
    .acid-loader-fab-stack{position:fixed;right:20px;bottom:20px;z-index:2147483000;
      display:flex;flex-direction:column;align-items:flex-end;gap:8px}
    .acid-loader-fab{background:#00ff00;color:#111;
      border:0;height:40px;padding:0 14px;display:flex;align-items:center;gap:8px;font-size:.68rem;
      font-weight:900;text-transform:uppercase;letter-spacing:.06em;box-shadow:0 10px 30px #0009;
      cursor:pointer;font-family:Oswald,Impact,Arial Narrow,sans-serif;white-space:nowrap}
    .acid-loader-fab:hover{background:#1b5e20;color:#fff}
    .acid-loader-fab em{font-style:normal;color:#083}
    .acid-loader-fab:hover em{color:#bdf5c8}
    .acid-loader-back-fab{background:#00ff00;color:#111;
      border:0;height:40px;padding:0 14px;display:flex;align-items:center;gap:8px;font-size:.68rem;
      font-weight:900;text-transform:uppercase;letter-spacing:.06em;box-shadow:0 10px 30px #0009;
      cursor:pointer;font-family:Oswald,Impact,Arial Narrow,sans-serif;white-space:nowrap}
    .acid-loader-back-fab:hover{background:#1b5e20;color:#fff}
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
    .acid-loader-busy-banner{position:fixed;top:8px;left:50%;transform:translateX(-50%);
      z-index:2147483000;background:#3a2f00;color:#ffd24a;border:1px solid #ffb400;
      border-radius:6px;padding:10px 18px;font-size:.78rem;font-weight:700;
      display:flex;align-items:center;gap:10px;box-shadow:0 10px 30px #000a;
      font-family:Oswald,Impact,Arial Narrow,sans-serif;text-transform:uppercase;
      letter-spacing:.04em;max-width:calc(100vw - 32px);text-align:center}
    .acid-loader-busy-banner .acid-spinner{width:14px;height:14px;border-radius:50%;
      border:2px solid #ffb40055;border-top-color:#ffb400;flex:0 0 auto;
      animation:acid-spin 0.8s linear infinite}
    @keyframes acid-spin{to{transform:rotate(360deg)}}
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

  const busyBanner = document.createElement("div");
  busyBanner.className = "acid-loader-busy-banner";
  busyBanner.style.display = "none";
  busyBanner.innerHTML = `<span class="acid-spinner"></span><span>Installing — please don't navigate away…</span>`;
  document.body.appendChild(busyBanner);

  let busyCount = 0;
  function beginBusy() {
    busyCount++;
    busyBanner.style.display = "flex";
    navbar.querySelectorAll("button").forEach(b => { b.disabled = true; });
  }
  function endBusy() {
    busyCount = Math.max(0, busyCount - 1);
    if (busyCount === 0) {
      busyBanner.style.display = "none";
      navbar.querySelectorAll("button").forEach(b => { b.disabled = false; });
    }
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

  const stack = document.createElement("div");
  stack.className = "acid-loader-fab-stack";
  document.body.appendChild(stack);

  const fab = document.createElement("button");
  fab.type = "button";
  fab.className = "acid-loader-fab";
  fab.title = "Click any GameBanana Download button to install it straight into your Brawlhalla folder.";
  fab.innerHTML = `📁 <em id="acid-loader-fab-path">Brawlhalla: not set</em>`;
  stack.appendChild(fab);

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

  const backFab = document.createElement("button");
  backFab.type = "button";
  backFab.className = "acid-loader-back-fab";
  backFab.textContent = "⚡ Go to Acid Mods";
  backFab.addEventListener("click", () => {
    window.pywebview.api.navigate("https://acidorg.com/#mods");
  });
  stack.appendChild(backFab);

  const AD_IFRAME_HOST_RE = new RegExp(
    [
      "doubleclick\\.net", "googlesyndication", "googleadservices", "googletagservices",
      "adservice\\.google", "2mdn\\.net", "amazon-adsystem", "adnxs\\.com", "quantserve",
      "criteo", "advertising\\.com", "pubmatic", "rubiconproject", "openx\\.net",
      "contextweb", "adsafeprotected", "moatads", "adsrvr\\.org", "casalemedia",
      "smartadserver", "media\\.net", "indexww\\.com", "sonobi\\.com", "triplelift\\.com",
      "districtm\\.io", "sharethrough\\.com", "yieldmo\\.com", "gumgum\\.com",
      "bidswitch\\.net", "adform\\.net", "admixer\\.net", "sortable\\.com",
      "taboola", "outbrain", "mgid\\.com", "revcontent\\.com", "adskeeper", "smi2\\.net",
      "mediago\\.io", "teads\\.tv", "connatix\\.com", "primis\\.tech", "unruly\\.co",
      "vidazoo\\.com", "playwire\\.com", "ezoic\\.net", "vidible\\.tv", "spotxchange",
      "aniview\\.com",
      "propellerads", "popads\\.net", "adcash\\.com", "exoclick\\.com", "juicyads\\.com",
      "hilltopads\\.net", "clickadu\\.com", "exdynsrv\\.com", "trafficjunky",
      "gamebanana\\.com/ads",
    ].join("|"),
    "i"
  );
  const AD_TOKEN_RE = /(^|[\s_-])(ad|ads|advert|advertisement|sponsor|dfp|gpt-ad|adslot|ad-slot|ad-unit|adunit|outstream|sticky-ad|adhesion|interstitial|prebid)([\s_-]|$)/i;

  function looksLikeAdContainer(el) {
    const id = el.id || "";
    const cls = typeof el.className === "string" ? el.className : "";
    return AD_TOKEN_RE.test(id) || AD_TOKEN_RE.test(cls);
  }

  function hideLikelyAds() {
    document
      .querySelectorAll(
        'ins.adsbygoogle, div[id^="div-gpt-ad"], iframe[id^="google_ads_iframe"], ' +
          "[data-ad-client], [data-ad-slot], amp-ad, amp-embed, " +
          '[aria-label="Advertisement" i]'
      )
      .forEach(el => el.style.setProperty("display", "none", "important"));

    document.querySelectorAll("iframe[src]").forEach(frame => {
      if (frame.dataset.acidAdChecked) return;
      frame.dataset.acidAdChecked = "1";
      if (AD_IFRAME_HOST_RE.test(frame.src)) {
        const wrapper = frame.closest('div[id],div[class]') || frame;
        wrapper.style.setProperty("display", "none", "important");
      }
    });

    document.querySelectorAll("div[id],div[class],aside[id],aside[class]").forEach(el => {
      if (el.dataset.acidAdChecked) return;
      el.dataset.acidAdChecked = "1";
      if (el.closest(".acid-loader-fab-stack") || el.closest(".acid-loader-navbar") || el.id === "acid-install-log") return;
      if (looksLikeAdContainer(el)) {
        el.style.setProperty("display", "none", "important");
      }
    });
  }

  hideLikelyAds();
  setInterval(hideLikelyAds, 1000);

  function isGamebananaDownloadLink(rawHref) {
    let u;
    try {
      u = new URL(rawHref, window.location.href);
    } catch (e) {
      return false;
    }
    if (u.protocol !== "http:" && u.protocol !== "https:") return false;
    if (!/(^|\.)gamebanana\.com$/i.test(u.hostname)) return false;
    if (/\/(?:mmdl|dl)\/\d+/i.test(u.pathname)) return true;
    if (/\.(?:zip|rar|7z|swf|bmod)$/i.test(u.pathname)) return true;
    return false;
  }

  const busyLinks = new WeakSet();

  document.addEventListener(
    "click",
    async event => {
      const link = event.target.closest && event.target.closest("a[href]");
      if (!link) return;
      if (!isGamebananaDownloadLink(link.href)) return;

      event.preventDefault();
      event.stopImmediatePropagation();

      if (busyLinks.has(link)) return;
      busyLinks.add(link);
      const originalOutline = link.style.outline;
      const originalOffset = link.style.outlineOffset;
      link.style.outline = "3px solid #ffb400";
      link.style.outlineOffset = "2px";

      try {
        beginBusy();
        const h1 = document.querySelector("h1");
        const title = h1 ? h1.textContent.trim() : "";
        const result = await window.pywebview.api.install_mod(link.href, title);
        if (result && result.ok) {
          showLog("Installed", result.log, true);
          link.style.outline = "3px solid #00ff00";
        } else {
          showLog("Install failed", (result && result.log) || ["Unknown error."], false);
          link.style.outline = "3px solid #ff5c5c";
        }
      } catch (err) {
        showLog("Install failed", [String(err)], false);
        link.style.outline = "3px solid #ff5c5c";
      } finally {
        endBusy();
        busyLinks.delete(link);
        setTimeout(() => {
          link.style.outline = originalOutline;
          link.style.outlineOffset = originalOffset;
        }, 2600);
      }
    },
    true
  );
})();

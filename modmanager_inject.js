(function () {
  "use strict";
  if (window.__acidModManagerInjected) return;
  window.__acidModManagerInjected = true;

  const style = document.createElement("style");
  style.textContent = `
    .acid-mm-fab{background:#00ff00;color:#111;border:0;height:40px;padding:0 14px;display:flex;
      align-items:center;gap:8px;font-size:.68rem;font-weight:900;text-transform:uppercase;
      letter-spacing:.06em;box-shadow:0 10px 30px #0009;cursor:pointer;white-space:nowrap;
      font-family:Oswald,Impact,Arial Narrow,sans-serif}
    .acid-mm-fab:hover{background:#1b5e20;color:#fff}
    .acid-mm-fab.acid-mm-floating{position:fixed;left:24px;top:202px;z-index:40}
    dialog#acid-mm-dialog{width:min(680px,calc(100vw - 32px));background:#111;color:#e8e8e8;
      border:1px solid #4b4129;padding:28px 28px 22px;box-shadow:0 30px 100px #000;position:fixed}
    dialog#acid-mm-dialog::backdrop{background:rgba(0,0,0,.82);backdrop-filter:blur(6px)}
    #acid-mm-dialog h2{font-size:1.7rem;text-transform:uppercase;margin:0;color:#fff;
      font-family:Oswald,Impact,Arial Narrow,sans-serif}
    #acid-mm-dialog .acid-mm-sub{margin:4px 0 0;color:#9a9a9a;font-size:.82rem}
    #acid-mm-dialog .acid-mm-close{position:absolute;right:16px;top:10px;color:#aaa;border:0;
      background:transparent;font-size:1.5rem;cursor:pointer}
    #acid-mm-dialog .acid-mm-close:hover{color:#fff}
    #acid-mm-list{list-style:none;margin:18px 0 0;padding:0;max-height:46vh;overflow:auto;
      border-top:1px solid #2a2a2a}
    #acid-mm-list li{display:flex;align-items:center;gap:14px;padding:12px 4px;
      border-bottom:1px solid #2a2a2a}
    #acid-mm-list .acid-mm-info{flex:1 1 auto;min-width:0}
    #acid-mm-list .acid-mm-name{color:#fff;font-weight:700;font-size:.98rem;overflow:hidden;
      text-overflow:ellipsis;white-space:nowrap}
    #acid-mm-list .acid-mm-meta{color:#8a8a8a;font-size:.78rem;margin-top:2px;overflow:hidden;
      text-overflow:ellipsis;white-space:nowrap}
    #acid-mm-list .acid-mm-partial{color:#ffb400;font-weight:700}
    .acid-mm-btn{background:transparent;color:#ff8a8a;border:1px solid #ff5c5c;height:32px;
      padding:0 14px;font-size:.72rem;font-weight:900;text-transform:uppercase;letter-spacing:.06em;
      cursor:pointer;font-family:Oswald,Impact,Arial Narrow,sans-serif;flex:0 0 auto}
    .acid-mm-btn:hover:not(:disabled){background:#ff5c5c;color:#1a0000}
    .acid-mm-btn:disabled{opacity:.45;cursor:default}
    #acid-mm-empty{margin:22px 0 6px;color:#9a9a9a;line-height:1.5}
    #acid-mm-foot{display:flex;justify-content:flex-end;margin-top:16px}
    #acid-mm-log{white-space:pre-wrap;font-family:Consolas,Menlo,monospace;font-size:.8rem;
      color:#00ff00;max-height:22vh;overflow:auto;margin:16px 0 0}
  `;
  document.head.appendChild(style);

  const dialog = document.createElement("dialog");
  dialog.id = "acid-mm-dialog";
  dialog.innerHTML = `
    <button class="acid-mm-close" type="button" aria-label="Close">×</button>
    <h2>Installed mods</h2>
    <p class="acid-mm-sub" id="acid-mm-sub"></p>
    <ul id="acid-mm-list"></ul>
    <p id="acid-mm-empty" hidden>No mods installed yet. Mods you install with this app show up here, and uninstalling one puts the original game files back.</p>
    <div id="acid-mm-foot"><button class="acid-mm-btn" type="button" id="acid-mm-all">Uninstall all</button></div>
    <pre id="acid-mm-log" hidden></pre>
  `;
  document.body.appendChild(dialog);

  const listEl = dialog.querySelector("#acid-mm-list");
  const emptyEl = dialog.querySelector("#acid-mm-empty");
  const subEl = dialog.querySelector("#acid-mm-sub");
  const allBtn = dialog.querySelector("#acid-mm-all");
  const logEl = dialog.querySelector("#acid-mm-log");

  dialog.querySelector(".acid-mm-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", event => {
    if (event.target === dialog) dialog.close();
  });

  function formatDate(iso) {
    const d = new Date(iso);
    if (isNaN(d)) return "";
    return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  }

  function setBusy(busy) {
    dialog.querySelectorAll(".acid-mm-btn").forEach(b => { b.disabled = busy; });
  }

  function showLog(lines) {
    logEl.textContent = (lines || []).join("\n");
    logEl.hidden = !(lines && lines.length);
    logEl.scrollTop = logEl.scrollHeight;
  }

  function renderList(mods) {
    listEl.textContent = "";
    emptyEl.hidden = mods.length > 0;
    listEl.hidden = mods.length === 0;
    allBtn.hidden = mods.length < 2;
    subEl.textContent = mods.length
      ? mods.length + (mods.length === 1 ? " mod" : " mods") + ", newest first"
      : "";

    mods.forEach(mod => {
      const li = document.createElement("li");

      const info = document.createElement("div");
      info.className = "acid-mm-info";
      const name = document.createElement("div");
      name.className = "acid-mm-name";
      name.textContent = mod.name;
      name.title = mod.name;
      const meta = document.createElement("div");
      meta.className = "acid-mm-meta";
      const bits = [];
      if (mod.filename && mod.filename !== mod.name) bits.push(mod.filename);
      const when = formatDate(mod.installed_at);
      if (when) bits.push(when);
      bits.push(mod.file_count + (mod.file_count === 1 ? " file" : " files"));
      meta.textContent = bits.join("  ·  ");
      if (mod.partial) {
        const flag = document.createElement("span");
        flag.className = "acid-mm-partial";
        flag.textContent = "  Install didn't finish";
        meta.appendChild(flag);
      }
      info.append(name, meta);

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "acid-mm-btn";
      btn.textContent = "Uninstall";
      btn.addEventListener("click", () => uninstallOne(mod));

      li.append(info, btn);
      listEl.appendChild(li);
    });
  }

  async function refresh() {
    try {
      renderList(await window.pywebview.api.list_installed_mods());
    } catch (err) {
      renderList([]);
      showLog(["[X] Couldn't read the installed mods list: " + String(err)]);
    }
  }

  async function uninstallOne(mod) {
    if (!confirm('Uninstall "' + mod.name + '"?\n\nThe original game files will be restored.\nClose Brawlhalla first if it is running.')) return;
    setBusy(true);
    showLog(["Uninstalling…"]);
    try {
      const result = await window.pywebview.api.uninstall_mod(mod.id);
      showLog(result.log);
    } catch (err) {
      showLog(["[X] " + String(err)]);
    }
    await refresh();
    setBusy(false);
  }

  allBtn.addEventListener("click", async () => {
    if (!confirm("Uninstall ALL mods?\n\nThe original game files will be restored.\nClose Brawlhalla first if it is running.")) return;
    setBusy(true);
    showLog(["Uninstalling…"]);
    try {
      const result = await window.pywebview.api.uninstall_all_mods();
      showLog(result.log);
    } catch (err) {
      showLog(["[X] " + String(err)]);
    }
    await refresh();
    setBusy(false);
  });

  const fab = document.createElement("button");
  fab.type = "button";
  fab.className = "acid-mm-fab";
  fab.textContent = "📦 Installed mods";
  fab.addEventListener("click", async () => {
    showLog([]);
    await refresh();
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  });

  const stack = document.querySelector(".acid-loader-fab-stack");
  if (stack) {
    stack.insertBefore(fab, stack.firstChild);
  } else {
    fab.classList.add("acid-mm-floating");
    document.body.appendChild(fab);
  }
})();

(() => {
  if (window.__acidUpdateInjected) return;
  window.__acidUpdateInjected = true;

  const api = () => window.pywebview && window.pywebview.api;
  const ready = async () => {
    for (let i = 0; i < 100; i++) {
      if (api() && api().check_update) return true;
      await new Promise(r => setTimeout(r, 100));
    }
    return false;
  };

  const btn = document.createElement('button');
  btn.textContent = '⟳ Updates';
  Object.assign(btn.style, {
    position: 'fixed', right: '16px', bottom: '16px', zIndex: 2147483647,
    padding: '10px 14px', border: '1px solid #3a3d42', borderRadius: '10px',
    background: '#15171a', color: '#e8e8e8', font: '600 13px system-ui, sans-serif',
    cursor: 'pointer', boxShadow: '0 4px 14px rgba(0,0,0,.4)'
  });

  const dot = document.createElement('span');
  Object.assign(dot.style, {
    display: 'none', width: '9px', height: '9px', borderRadius: '50%',
    background: '#ff4d4f', marginLeft: '8px', verticalAlign: 'middle'
  });
  btn.appendChild(dot);

  const panel = document.createElement('div');
  Object.assign(panel.style, {
    position: 'fixed', right: '16px', bottom: '64px', zIndex: 2147483647, width: '300px',
    padding: '14px', border: '1px solid #3a3d42', borderRadius: '12px', display: 'none',
    background: '#15171a', color: '#e8e8e8', font: '13px/1.45 system-ui, sans-serif',
    boxShadow: '0 8px 24px rgba(0,0,0,.5)'
  });

  const msg = document.createElement('div');
  const action = document.createElement('button');
  Object.assign(action.style, {
    marginTop: '10px', padding: '8px 12px', border: 0, borderRadius: '8px', display: 'none',
    background: '#7c5cff', color: '#fff', font: '600 13px system-ui, sans-serif', cursor: 'pointer'
  });
  panel.append(msg, action);

  // --- Casilla del bloqueador de anuncios (GameBanana) ---
  const adRow = document.createElement('label');
  Object.assign(adRow.style, {
    display: 'flex', alignItems: 'center', gap: '8px', marginTop: '12px',
    paddingTop: '10px', borderTop: '1px solid #2a2d31', cursor: 'pointer'
  });
  const adChk = document.createElement('input');
  adChk.type = 'checkbox';
  const adTxt = document.createElement('span');
  adRow.append(adChk, adTxt);
  panel.append(adRow);

  async function loadAdblock() {
    if (!(await ready()) || !api().get_adblock) return;
    adChk.checked = await api().get_adblock();
    const st = await api().adblock_stats();
    adTxt.textContent = 'Block ads on GameBanana' + (st.blocked ? ` · ${st.blocked} blocked` : '');
    adRow.title = st.network ? '' : 'Network blocking unavailable: only hiding ads on the page.';
  }
  adChk.onchange = async () => { await api().set_adblock(adChk.checked); loadAdblock(); };

  let state = null;

  const render = (html, actionLabel, onClick) => {
    msg.innerHTML = html;
    action.style.display = actionLabel ? 'inline-block' : 'none';
    action.textContent = actionLabel || '';
    action.disabled = false;
    action.onclick = onClick || null;
  };
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  async function check(manual) {
    if (!(await ready())) return;
    if (manual) render('Checking for updates…');
    state = await api().check_update();
    if (state.error) {
      dot.style.display = 'none';
      if (manual) render(esc(state.error), 'Retry', () => check(true));
      return;
    }
    if (state.available && state.needs_new_exe) {
      dot.style.display = 'inline-block';
      render(`Version <b>${esc(state.latest)}</b> needs a new download of the app (you have ${esc(state.current)}).`);
    } else if (state.available) {
      dot.style.display = 'inline-block';
      render(
        `<b>Update available:</b> ${esc(state.current)} → <b>${esc(state.latest)}</b>` +
        (state.notes ? `<div style="opacity:.75;margin-top:6px;white-space:pre-wrap">${esc(state.notes)}</div>` : ''),
        'Update now', apply
      );
    } else {
      dot.style.display = 'none';
      render(`You're up to date (v${esc(state.current)}).`, 'Check again', () => check(true));
    }
  }

  async function apply() {
    action.disabled = true;
    render('Downloading update…');
    const res = await api().apply_update();
    if (!res.ok) { render(esc(res.error), 'Retry', apply); return; }
    render(`Updated to v${esc(res.version)}. Restarting…`);
    setTimeout(() => api().restart_app(), 600);
  }

  btn.onclick = () => {
    const open = panel.style.display === 'none';
    panel.style.display = open ? 'block' : 'none';
    if (open) { check(true); loadAdblock(); }
  };

  document.body.append(panel, btn);
  check(false); // chequeo silencioso al abrir: solo prende el puntito rojo
})();

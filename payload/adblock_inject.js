(() => {
  // Solo actua en gamebanana.com. Se ejecuta al crear el documento (si WebView2
  // lo permite) y otra vez al terminar de cargar; es idempotente.
  if (!/(^|\.)gamebanana\.com$/.test(location.hostname)) return;
  if (window.__acidAdblock) return;

  const RULES = __RULES__;
  const STYLE_ID = 'acid-adblock-css';
  let enabled = true;
  const hidden = [];

  const css = RULES.selectors.join(',\n') +
    '{display:none!important;visibility:hidden!important;height:0!important;' +
    'min-height:0!important;margin:0!important;padding:0!important}';

  function addStyle() {
    if (!enabled || document.getElementById(STYLE_ID)) return;
    const s = document.createElement('style');
    s.id = STYLE_ID;
    s.textContent = css;
    (document.head || document.documentElement).appendChild(s);
  }
  function removeStyle() {
    const s = document.getElementById(STYLE_ID);
    if (s) s.remove();
  }

  // Aviso "Ads keep us online / please unblock us": se oculta el contenedor
  // pequeno mas cercano al texto (nunca contenedores grandes).
  const noticeRe = RULES.notice.length ? new RegExp(RULES.notice.join('|'), 'i') : null;
  function hideNotice() {
    if (!enabled || !noticeRe || !document.body) return;
    for (const el of document.body.querySelectorAll('div,section,aside,p,span')) {
      if (el.dataset.acidHidden) continue;
      const text = el.textContent || '';
      if (text.length > 600 || !noticeRe.test(text)) continue;
      let target = el;
      while (target.parentElement && target.parentElement !== document.body &&
             (target.parentElement.textContent || '').length < 900) {
        target = target.parentElement;
      }
      hidden.push([target, target.style.display]);
      target.dataset.acidHidden = '1';
      target.style.setProperty('display', 'none', 'important');
    }
  }
  function restoreNotice() {
    while (hidden.length) {
      const [el, prev] = hidden.pop();
      el.style.display = prev;
      delete el.dataset.acidHidden;
    }
  }

  let pending = false;
  const observer = new MutationObserver(() => {
    if (pending) return;
    pending = true;
    setTimeout(() => { pending = false; addStyle(); hideNotice(); }, 400);
  });

  function start() {
    addStyle();
    hideNotice();
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }

  window.__acidAdblock = {
    on()  { enabled = true;  addStyle(); hideNotice(); },
    off() { enabled = false; removeStyle(); restoreNotice(); },
  };

  start();
})();

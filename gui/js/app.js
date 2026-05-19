// ===========================================================
// app.js - Shared helpers, tab routing, API wrappers
// ===========================================================

const App = (() => {
  let alphabetsCache = null;
  let settingsCache = null;
  let apiReady = false;
  const apiReadyCallbacks = [];

  // ----- API readiness -----
  // pywebview.api becomes available asynchronously. We wait for it.
  function onApiReady(cb) {
    if (apiReady) { cb(); return; }
    apiReadyCallbacks.push(cb);
  }

  window.addEventListener('pywebviewready', () => {
    apiReady = true;
    apiReadyCallbacks.forEach(cb => cb());
    apiReadyCallbacks.length = 0;
  });

  // ----- API call wrapper -----
  async function api(method, ...args) {
    if (!window.pywebview || !window.pywebview.api) {
      throw new Error('PyWebView API not ready');
    }
    if (!window.pywebview.api[method]) {
      throw new Error('API method not found: ' + method);
    }
    return await window.pywebview.api[method](...args);
  }

  // ----- Toast notifications -----
  function toast(message, type = 'info', duration = 3500) {
    const container = document.getElementById('toast-container');
    const el = document.createElement('div');
    el.className = 'toast ' + type;
    el.textContent = message;
    container.appendChild(el);
    setTimeout(() => {
      el.style.opacity = '0';
      el.style.transition = 'opacity 0.2s';
      setTimeout(() => el.remove(), 200);
    }, duration);
  }

  // ----- Confirm modal -----
  function confirm(title, body) {
    return new Promise((resolve) => {
      const backdrop = document.getElementById('modal-backdrop');
      document.getElementById('modal-title').textContent = title;
      document.getElementById('modal-body').textContent = body;
      backdrop.classList.remove('hidden');
      const okBtn = document.getElementById('modal-confirm');
      const cancelBtn = document.getElementById('modal-cancel');
      const cleanup = () => {
        backdrop.classList.add('hidden');
        okBtn.removeEventListener('click', onOk);
        cancelBtn.removeEventListener('click', onCancel);
      };
      const onOk = () => { cleanup(); resolve(true); };
      const onCancel = () => { cleanup(); resolve(false); };
      okBtn.addEventListener('click', onOk);
      cancelBtn.addEventListener('click', onCancel);
    });
  }

  // ----- Tab routing -----
  function switchTab(name) {
    document.querySelectorAll('.tab').forEach(t => {
      const active = t.dataset.tab === name;
      t.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    document.querySelectorAll('.tab-panel').forEach(p => {
      p.classList.toggle('active', p.dataset.panel === name);
    });
    if (typeof Tabs !== 'undefined' && Tabs[name] && Tabs[name].onShow) {
      Tabs[name].onShow();
    }
  }

  document.addEventListener('click', (e) => {
    const t = e.target.closest('.tab');
    if (t) switchTab(t.dataset.tab);
  });

  // ----- Drag-drop helper -----
  // pywebview passes dropped file paths via dataTransfer.files in modern versions.
  // We register a global handler and route to the active tab.
  function setupDropZone(elementId, onFile) {
    const zone = document.getElementById(elementId);
    if (!zone) return;
    zone.addEventListener('dragover', (e) => {
      e.preventDefault();
      e.stopPropagation();
      zone.classList.add('dragging');
    });
    zone.addEventListener('dragleave', (e) => {
      e.stopPropagation();
      // Only un-highlight if leaving the zone entirely
      if (!zone.contains(e.relatedTarget)) zone.classList.remove('dragging');
    });
    zone.addEventListener('drop', async (e) => {
      e.preventDefault();
      e.stopPropagation();
      zone.classList.remove('dragging');
      // pywebview 6.x exposes file paths via dataTransfer.files[i].path
      const files = e.dataTransfer.files;
      if (!files || !files.length) return;
      const f = files[0];
      // Try .path (Electron-style; pywebview/CEF), then .name (browsers)
      const path = f.path || f.name;
      if (path) onFile(path);
    });
  }

  // ----- Estimate output length given filesize and base -----
  function estimateChars(fileSize, base, encrypted, headerOverhead) {
    if (!fileSize || !base) return null;
    // AES-256-CBC adds 16 bytes of padding/IV + 8 bytes salt header (OpenSSL)
    let size = fileSize;
    if (encrypted) size += 16 + 16;  // padding + IV-ish overhead
    const log2 = Math.log2(base);
    const dataChars = Math.ceil(size * 8 / log2);
    return dataChars + (headerOverhead || 0);
  }

  // ----- Format bytes -----
  function fmtBytes(b) {
    if (b < 1024) return b + ' B';
    if (b < 1024 * 1024) return (b / 1024).toFixed(1) + ' KB';
    return (b / 1024 / 1024).toFixed(2) + ' MB';
  }

  // ----- Get alphabets (cached) -----
  async function getAlphabets(force = false) {
    if (alphabetsCache && !force) return alphabetsCache;
    const r = await api('list_alphabets');
    if (!r.ok) {
      toast('Failed to load alphabets: ' + r.error, 'error');
      return [];
    }
    alphabetsCache = r.alphabets;
    return alphabetsCache;
  }

  async function getSettings(force = false) {
    if (settingsCache && !force) return settingsCache;
    const r = await api('get_settings');
    if (r.ok) settingsCache = r.settings;
    return settingsCache || {};
  }

  function invalidateAlphabets() { alphabetsCache = null; }
  function invalidateSettings() { settingsCache = null; }

  // ----- Populate a <select> with alphabets -----
  function populateAlphabetSelect(selectEl, alphabets, selectedId) {
    selectEl.innerHTML = '';
    alphabets.forEach(a => {
      const opt = document.createElement('option');
      opt.value = a.id;
      opt.textContent = `${a.name}  (base ${a.base}${a.builtin ? '' : ', custom'})`;
      if (a.id === selectedId) opt.selected = true;
      selectEl.appendChild(opt);
    });
  }

  // ----- Segmented control helpers -----
  function bindSegmented(elementId, onChange) {
    const root = document.getElementById(elementId);
    if (!root) return;
    root.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-val]');
      if (!btn) return;
      root.querySelectorAll('button').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      if (onChange) onChange(btn.dataset.val);
    });
  }
  function getSegmentedValue(elementId) {
    const root = document.getElementById(elementId);
    const active = root && root.querySelector('button.active');
    return active ? active.dataset.val : null;
  }
  function setSegmentedValue(elementId, val) {
    const root = document.getElementById(elementId);
    if (!root) return;
    root.querySelectorAll('button').forEach(b => {
      b.classList.toggle('active', b.dataset.val === val);
    });
  }

  // ----- Query string parser -----
  function getQueryParam(name) {
    const m = window.location.search.match(new RegExp('[?&]' + name + '=([^&]+)'));
    return m ? decodeURIComponent(m[1]) : null;
  }

  // ----- Public surface -----
  return {
    api,
    onApiReady,
    toast,
    confirm,
    switchTab,
    setupDropZone,
    estimateChars,
    fmtBytes,
    getAlphabets,
    getSettings,
    invalidateAlphabets,
    invalidateSettings,
    populateAlphabetSelect,
    bindSegmented,
    getSegmentedValue,
    setSegmentedValue,
    getQueryParam,
  };
})();

// Tab lifecycle registry
const Tabs = {};

// Listen for messages from embedded editor iframe
window.addEventListener('message', (e) => {
  if (e.data && e.data.type === 'alphabet-saved') {
    App.invalidateAlphabets();
    App.toast(`Saved alphabet "${e.data.entry.name}"`, 'success');
    // Refresh library if open
    if (Tabs.library && Tabs.library.refresh) Tabs.library.refresh();
    // Re-populate alphabet selects in encode/decode
    refreshAlphabetSelects();
  }
});

async function refreshAlphabetSelects() {
  const alphabets = await App.getAlphabets(true);
  const encSel = document.getElementById('encode-alph');
  const decSel = document.getElementById('decode-alph');
  const setSel = document.getElementById('set-default-alph');
  if (encSel) App.populateAlphabetSelect(encSel, alphabets, encSel.value);
  if (decSel) App.populateAlphabetSelect(decSel, alphabets, decSel.value);
  if (setSel) App.populateAlphabetSelect(setSel, alphabets, setSel.value);
}

// Boot
App.onApiReady(async () => {
  // Initialize each tab module
  if (Tabs.encode && Tabs.encode.init) Tabs.encode.init();
  if (Tabs.decode && Tabs.decode.init) Tabs.decode.init();
  if (Tabs.library && Tabs.library.init) Tabs.library.init();
  if (Tabs.vault && Tabs.vault.init) Tabs.vault.init();
  if (Tabs.tattoo && Tabs.tattoo.init) Tabs.tattoo.init();
  if (Tabs.settings && Tabs.settings.init) Tabs.settings.init();
  if (Tabs.help && Tabs.help.init) Tabs.help.init();

  // If launched with an initial file, route to Decode tab
  const initial = App.getQueryParam('initial');
  if (initial) {
    App.switchTab('decode');
    if (Tabs.decode && Tabs.decode.loadFile) {
      Tabs.decode.loadFile(decodeURIComponent(initial));
    }
  }

  App.toast('Sovereign ready', 'success', 2000);
});

// ===========================================================
// settings.js - Settings tab + Compression engines management
// ===========================================================

Tabs.settings = (() => {

  async function init() {
    await populate();
    document.getElementById('set-save').addEventListener('click', save);
    document.getElementById('set-vault-browse').addEventListener('click', browseVault);
    document.getElementById('set-openssl-browse').addEventListener('click', browseOpenssl);
    document.getElementById('set-tesseract-browse').addEventListener('click', browseTesseract);
    document.getElementById('set-engines-refresh').addEventListener('click', refreshEngines);
    document.getElementById('set-engines-open-bin').addEventListener('click', openBinFolder);
    document.getElementById('set-anthropic-save').addEventListener('click', saveAnthropicKey);
    document.getElementById('set-anthropic-clear').addEventListener('click', clearAnthropicKey);
    document.getElementById('anthropic-link').addEventListener('click', async (e) => {
      e.preventDefault();
      await App.api('copy_to_clipboard', 'https://console.anthropic.com/');
      App.toast('URL copied to clipboard', 'info', 1800);
    });
    App.bindSegmented('set-default-fpsize');
    App.bindSegmented('set-default-salt');
    App.bindSegmented('set-default-compression');
    await refreshEngines();
    await refreshAnthropicStatus();
  }

  async function populate() {
    const s = await App.getSettings(true);
    const alphabets = await App.getAlphabets();
    App.populateAlphabetSelect(document.getElementById('set-default-alph'), alphabets, s.default_alphabet || 'b32');
    App.setSegmentedValue('set-default-fpsize', s.default_fpsize || '8');
    App.setSegmentedValue('set-default-salt', s.default_salt_mode || 'salt');
    App.setSegmentedValue('set-default-compression', s.default_compression || 'none');
    document.getElementById('set-default-selfdesc').checked = !!s.default_selfdesc;
    document.getElementById('set-vault-folder').value = s.vault_folder || '';
    document.getElementById('set-openssl').value = s.openssl_path || '';
    document.getElementById('set-tesseract').value = s.tesseract_path || '';
  }

  async function save() {
    const settings = {
      default_alphabet: document.getElementById('set-default-alph').value,
      default_fpsize: App.getSegmentedValue('set-default-fpsize') || '8',
      default_salt_mode: App.getSegmentedValue('set-default-salt') || 'salt',
      default_selfdesc: document.getElementById('set-default-selfdesc').checked,
      default_compression: App.getSegmentedValue('set-default-compression') || 'none',
      vault_folder: document.getElementById('set-vault-folder').value,
      openssl_path: document.getElementById('set-openssl').value,
      tesseract_path: document.getElementById('set-tesseract').value,
    };
    const r = await App.api('save_settings', settings);
    if (r.ok) {
      App.invalidateSettings();
      App.toast('Settings saved', 'success');
    } else {
      App.toast('Save failed: ' + r.error, 'error');
    }
  }

  async function browseVault() {
    const r = await App.api('open_file_dialog', 'folder');
    if (r.ok && r.path) document.getElementById('set-vault-folder').value = r.path;
  }

  async function browseOpenssl() {
    const r = await App.api('open_file_dialog', 'open');
    if (r.ok && r.path) document.getElementById('set-openssl').value = r.path;
  }

  async function browseTesseract() {
    const r = await App.api('open_file_dialog', 'open');
    if (r.ok && r.path) document.getElementById('set-tesseract').value = r.path;
  }

  // =========================================================================
  // Compression engines
  // =========================================================================

  async function refreshEngines() {
    const list = document.getElementById('engines-list');
    list.innerHTML = '<div class="muted small" style="padding:8px">Loading…</div>';
    const r = await App.api('engines_list');
    if (!r.ok) {
      list.innerHTML = `<div class="muted small" style="padding:8px">Error: ${esc(r.error)}</div>`;
      return;
    }
    list.innerHTML = '';
    r.engines.forEach(e => list.appendChild(renderEngine(e)));
  }

  function renderEngine(e) {
    const card = document.createElement('div');
    card.className = 'engine-card';
    card.dataset.id = e.id;

    const statusLabel = !e.integrated
      ? '<span class="badge engine-status-wip">Future</span>'
      : (e.installed
          ? '<span class="badge engine-status-installed">Installed ✓</span>'
          : '<span class="badge engine-status-missing">Not installed</span>');

    // Show a hint when the binary was found in a version subfolder rather than
    // directly in bin/  (e.is_canonical comes from sv_engines.list_engines)
    const subfolderHint = (e.installed && !e.is_canonical)
      ? '<div class="engine-subfolder-hint muted small">Found in subfolder — copy to bin/ root for canonical placement</div>'
      : '';

    // Only show "Remove" when the canonical top-level copy exists
    const removeBtn = (e.installed && e.is_canonical)
      ? `<button class="btn ghost small engine-remove" data-id="${escA(e.id)}">Remove from bin/</button>`
      : '';

    card.innerHTML = `
      <div class="engine-header">
        <div class="engine-main">
          <div class="engine-name">${esc(e.name)} ${statusLabel}</div>
          <div class="engine-desc muted small">${esc(e.description || '')}</div>
        </div>
      </div>
      <div class="engine-grid">
        <div class="engine-row">
          <span>Expected filename</span>
          <span class="mono-small">${esc(e.filename)}</span>
        </div>
        <div class="engine-row">
          <span>Path</span>
          <span class="mono-small">${esc(e.installed_path || '— not installed —')}</span>
        </div>
        ${subfolderHint}
        <div class="engine-row">
          <span>License</span>
          <span>${esc(e.license || '')}</span>
        </div>
        <div class="engine-row">
          <span>Source</span>
          <span><a class="link engine-homepage" data-url="${escA(e.homepage)}">${esc(e.homepage)}</a></span>
        </div>
      </div>
      <div class="engine-actions">
        ${e.integrated ? `<button class="btn small engine-browse" data-id="${escA(e.id)}">Browse for binary…</button>` : ''}
        ${e.integrated && e.installed ? `<button class="btn ghost small engine-test" data-id="${escA(e.id)}">Test round-trip</button>` : ''}
        ${removeBtn}
        <button class="btn ghost small engine-copy-url" data-url="${escA(e.homepage)}">Copy URL</button>
      </div>
    `;

    // Wire up actions
    const browse = card.querySelector('.engine-browse');
    if (browse) browse.addEventListener('click', () => browseInstall(e));

    const test = card.querySelector('.engine-test');
    if (test) test.addEventListener('click', () => testEngine(e));

    const remove = card.querySelector('.engine-remove');
    if (remove) remove.addEventListener('click', () => removeEngine(e));

    card.querySelectorAll('.engine-copy-url, .engine-homepage').forEach(el => {
      el.addEventListener('click', async (ev) => {
        ev.preventDefault();
        const url = el.dataset.url || el.textContent;
        await App.api('copy_to_clipboard', url);
        App.toast('URL copied to clipboard', 'success', 1800);
      });
    });

    return card;
  }

  async function browseInstall(e) {
    const dlg = await App.api('open_file_dialog', 'open');
    if (!dlg.ok || !dlg.path) return;
    const r = await App.api('engine_install', e.id, dlg.path);
    if (r.ok) {
      App.toast(`${e.name} installed`, 'success');
      refreshEngines();
    } else {
      App.toast(`Install failed: ${r.error}`, 'error');
    }
  }

  async function testEngine(e) {
    const r = await App.api('engine_test', e.id);
    if (r.ok) {
      const ratio = (r.ratio * 100).toFixed(1);
      const verb = r.roundtrip ? '✓ round-trip OK' : '✗ round-trip MISMATCH';
      App.toast(`${e.name}: ${r.original_bytes} → ${r.compressed_bytes} bytes (${ratio}%) — ${verb}`,
                r.roundtrip ? 'success' : 'error', 4500);
    } else {
      App.toast(`${e.name} test failed: ${r.error}`, 'error', 4500);
    }
  }

  async function removeEngine(e) {
    const ok = await App.confirm(
      'Remove engine binary?',
      `Delete ${e.filename} from bin/? You can re-install it later by browsing again.`
    );
    if (!ok) return;
    const r = await App.api('engine_remove', e.id);
    if (r.ok) {
      App.toast(`${e.name} removed`, 'success');
      refreshEngines();
    } else {
      App.toast(`Remove failed: ${r.error}`, 'error');
    }
  }

  async function openBinFolder() {
    const r = await App.api('engines_list');
    if (r.ok && r.bin_dir) await App.api('open_folder', r.bin_dir);
  }

  // =========================================================================
  // Anthropic API key (Windows Credential Manager)
  // =========================================================================

  async function refreshAnthropicStatus() {
    const statusEl = document.getElementById('set-anthropic-status');
    const r = await App.api('get_anthropic_key_status');
    if (r.ok && r.configured) {
      statusEl.textContent = 'Key saved in Credential Manager';
      statusEl.style.color = 'var(--color-success, #4ade80)';
    } else {
      statusEl.textContent = 'Not configured';
      statusEl.style.color = '';
    }
  }

  async function saveAnthropicKey() {
    const key = document.getElementById('set-anthropic-key').value.trim();
    if (!key) { App.toast('Enter an API key first', 'error'); return; }
    const r = await App.api('save_anthropic_key', key);
    if (r.ok) {
      document.getElementById('set-anthropic-key').value = '';
      App.toast('API key saved to Credential Manager', 'success');
      await refreshAnthropicStatus();
    } else {
      App.toast('Save failed: ' + r.error, 'error', 4500);
    }
  }

  async function clearAnthropicKey() {
    const ok = await App.confirm('Remove API key?', 'This will delete the Anthropic API key from Windows Credential Manager. Claude Vision features will stop working.');
    if (!ok) return;
    await App.api('delete_anthropic_key');
    App.toast('API key removed', 'success');
    await refreshAnthropicStatus();
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function escA(s) { return esc(s).replace(/"/g, '&quot;'); }

  return { init, onShow: () => { populate(); refreshEngines(); refreshAnthropicStatus(); } };
})();

// ===========================================================
// vault.js - Key vault: stored passwords, key cards, key records
// ===========================================================

Tabs.vault = (() => {

  async function init() {
    document.getElementById('vault-pw-refresh').addEventListener('click', refreshPasswords);
    document.getElementById('vault-kc-refresh').addEventListener('click', refreshKeycards);
    document.getElementById('vault-kc-folder').addEventListener('click', openVaultFolder);
    document.getElementById('vault-kr-refresh').addEventListener('click', refreshKeyRecords);
    await Promise.all([refreshPasswords(), refreshKeycards(), refreshKeyRecords()]);
  }

  async function onShow() {
    await Promise.all([refreshPasswords(), refreshKeycards(), refreshKeyRecords()]);
  }

  // =========================================================================
  // Stored passwords (Windows Credential Manager)
  // =========================================================================

  async function refreshPasswords() {
    const r = await App.api('vault_list');
    const list = document.getElementById('vault-pw-list');
    list.innerHTML = '';
    if (!r.ok) { App.toast('Vault load failed: ' + r.error, 'error'); return; }
    if (r.entries.length === 0) {
      list.innerHTML = '<li class="muted small" style="padding:8px 10px">No stored passwords. Enable "Save password to keyring" on the Encode tab.</li>';
      return;
    }
    r.entries.forEach(e => {
      const li = document.createElement('li');
      li.innerHTML = `
        <div class="vault-item-main">
          <div class="vault-item-name">${esc(e.hint || e.label)}</div>
          <div class="vault-item-meta">label: ${esc(e.label)} — saved ${esc(e.created || '')}</div>
        </div>
        <button class="btn ghost small" data-label="${escA(e.label)}">Delete</button>
      `;
      list.appendChild(li);
    });
    list.querySelectorAll('button[data-label]').forEach(btn => {
      btn.addEventListener('click', async (ev) => {
        ev.stopPropagation();
        const label = btn.dataset.label;
        const ok = await App.confirm(
          'Delete stored password?',
          `Remove "${label}" from Windows Credential Manager? You'll need to re-enter the password to decode.`
        );
        if (!ok) return;
        const r2 = await App.api('vault_delete', label);
        if (r2.ok) { App.toast('Password deleted', 'success'); refreshPasswords(); }
        else App.toast('Delete failed: ' + r2.error, 'error');
      });
    });
  }

  // =========================================================================
  // Key cards (legacy .keycard.txt files on disk)
  // =========================================================================

  async function refreshKeycards() {
    const settings = await App.getSettings();
    const r = await App.api('list_keycards', settings.vault_folder);
    const list = document.getElementById('vault-kc-list');
    list.innerHTML = '';
    document.getElementById('vault-kc-preview').classList.add('hidden');
    if (!r.ok) { App.toast('Key cards load failed: ' + r.error, 'error'); return; }
    if (r.cards.length === 0) {
      list.innerHTML = `<li class="muted small" style="padding:8px 10px">No key cards found. Folder: ${esc(r.folder)}</li>`;
      return;
    }
    r.cards.forEach(c => {
      const li = document.createElement('li');
      const title = c.alphabet || c.name;
      const fp = c.fingerprint || '';
      li.innerHTML = `
        <div class="vault-item-main">
          <div class="vault-item-name">${esc(title)}</div>
          <div class="vault-item-meta">${esc(c.path)}${fp ? ' — fp:' + esc(fp) : ''}</div>
        </div>
      `;
      li.dataset.path = c.path;
      li.addEventListener('click', () => previewKeycard(c.path, li));
      list.appendChild(li);
    });
  }

  async function previewKeycard(path, liEl) {
    document.querySelectorAll('#vault-kc-list li').forEach(l => l.classList.remove('active'));
    if (liEl) liEl.classList.add('active');
    const r = await App.api('read_keycard', path);
    const pre = document.getElementById('vault-kc-preview');
    if (r.ok) {
      pre.textContent = r.content;
      pre.classList.remove('hidden');
    } else {
      App.toast('Preview failed: ' + r.error, 'error');
    }
  }

  async function openVaultFolder() {
    const settings = await App.getSettings();
    await App.api('open_folder', settings.vault_folder);
  }

  // =========================================================================
  // Key Vault records (sv_key_records.json)
  // =========================================================================

  async function refreshKeyRecords() {
    const r = await App.api('keyrecord_list');
    const container = document.getElementById('vault-kr-list');
    container.innerHTML = '';

    if (!r.ok) {
      container.innerHTML = `<div class="muted small" style="padding:8px 0">Error loading records: ${esc(r.error)}</div>`;
      return;
    }
    if (!r.records || r.records.length === 0) {
      container.innerHTML = '<div class="muted small" style="padding:8px 0">No key records yet. Use Key Vault mode on the Encode tab.</div>';
      return;
    }

    r.records.forEach(rec => renderKeyRecord(container, rec));
  }

  function renderKeyRecord(container, rec) {
    const card = document.createElement('div');
    card.className = 'kr-card';
    card.dataset.id = rec.id;

    const headerMode = rec.header_mode || '';
    const headerLabel = { bare: 'Bare', keyref: 'Key ref', fullsv1: 'Full SV1' }[headerMode] || headerMode;
    const encLabel = rec.encryption === 'aes256cbc-kv' ? 'Key Vault AES-256' : rec.encryption || 'none';
    const hasOrigText = rec.original_text && rec.original_text.trim().length > 0;

    card.innerHTML = `
      <div class="kr-header" role="button" tabindex="0">
        <div class="kr-summary">
          <span class="kr-label">${esc(rec.label || '(no label)')}</span>
          <span class="kr-meta">
            <span class="badge kr-badge-alph">${esc(rec.alphabet_id || '')}</span>
            <span class="badge kr-badge-enc">${esc(encLabel)}</span>
            <span class="badge kr-badge-header">${esc(headerLabel)}</span>
          </span>
        </div>
        <div class="kr-meta-right muted small">${esc(rec.id)} · ${esc(rec.created || '')}</div>
        <span class="kr-toggle">▶</span>
      </div>
      <div class="kr-body hidden">
        <div class="kr-grid">
          <div class="kr-row"><span>Alphabet</span><span>${esc(rec.alphabet_name || rec.alphabet_id)}</span></div>
          <div class="kr-row"><span>Fingerprint</span><span>${esc(rec.alphabet_fingerprint || '—')}</span></div>
          <div class="kr-row"><span>Base</span><span>${esc(String(rec.base || ''))}</span></div>
          <div class="kr-row"><span>KDF</span><span>${esc(rec.kdf || '')} · ${esc(String(rec.kdf_iterations || ''))} iterations</span></div>
          <div class="kr-row"><span>Source</span><span>${esc(rec.source || '')}</span></div>
          <div class="kr-row"><span>Original size</span><span>${esc(String(rec.original_size_bytes || '—'))} bytes</span></div>
          <div class="kr-row"><span>SHA-256</span><span class="mono-small">${esc(rec.original_sha256 || '—')}</span></div>
          <div class="kr-row"><span>Chars</span><span>${esc(String(rec.char_count || '—'))}</span></div>
        </div>

        ${hasOrigText ? `
        <div class="kr-orig-text">
          <div class="muted small" style="margin-bottom:4px">Original text</div>
          <pre class="kr-orig-pre">${esc(rec.original_text)}</pre>
        </div>` : ''}

        <div class="kr-encoded-label muted small" style="margin:10px 0 4px">Encoded string</div>
        <pre class="kr-encoded-string">${esc(rec.encoded_string || '')}</pre>

        <div class="kr-actions">
          <button class="btn small kr-btn-copy" data-id="${escA(rec.id)}">Copy string</button>
          <button class="btn ghost small kr-btn-export" data-id="${escA(rec.id)}">Export card</button>
          <button class="btn danger small kr-btn-delete" data-id="${escA(rec.id)}">Delete</button>
        </div>
      </div>
    `;

    // Toggle expand/collapse
    const header = card.querySelector('.kr-header');
    const body   = card.querySelector('.kr-body');
    const toggle = card.querySelector('.kr-toggle');
    header.addEventListener('click', () => {
      const open = !body.classList.contains('hidden');
      body.classList.toggle('hidden', open);
      toggle.textContent = open ? '▶' : '▼';
    });
    header.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); header.click(); }
    });

    // Copy string
    card.querySelector('.kr-btn-copy').addEventListener('click', async (ev) => {
      ev.stopPropagation();
      const encoded = rec.encoded_string || '';
      if (!encoded) { App.toast('No encoded string in record', 'warning'); return; }
      const r = await App.api('copy_to_clipboard', encoded);
      if (r.ok) App.toast('Copied to clipboard', 'success');
      else App.toast('Copy failed: ' + r.error, 'error');
    });

    // Export card
    card.querySelector('.kr-btn-export').addEventListener('click', async (ev) => {
      ev.stopPropagation();
      const dlg = await App.api('open_file_dialog', 'save', `sv_keyrecord_${rec.id}.txt`);
      if (!dlg.ok || !dlg.path) return;
      const r = await App.api('keyrecord_export', rec.id, dlg.path);
      if (r.ok) {
        let msg = `Card saved to ${r.card_path}`;
        if (r.html_path) msg += ` + recovery.html`;
        App.toast(msg, 'success');
      } else {
        App.toast('Export failed: ' + r.error, 'error');
      }
    });

    // Delete
    card.querySelector('.kr-btn-delete').addEventListener('click', async (ev) => {
      ev.stopPropagation();
      const ok = await App.confirm(
        'Delete key record?',
        `Delete record "${rec.label || rec.id}"? If the encoded data is KV-encrypted and you have no other backup of this record, the data will be unrecoverable.`
      );
      if (!ok) return;
      const r = await App.api('keyrecord_delete', rec.id);
      if (r.ok) {
        App.toast('Record deleted', 'success');
        refreshKeyRecords();
      } else {
        App.toast('Delete failed: ' + r.error, 'error');
      }
    });

    container.appendChild(card);
  }

  // =========================================================================
  // Utilities
  // =========================================================================

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }
  function escA(s) { return esc(s).replace(/"/g, '&quot;'); }

  return { init, onShow };
})();

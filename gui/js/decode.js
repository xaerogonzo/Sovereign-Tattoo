// ===========================================================
// decode.js - Decode tab logic
// Supports standard decode AND Key Vault decode.
// ===========================================================

Tabs.decode = (() => {
  let currentFile = null;
  let alphabets   = [];
  let settings    = {};
  let lastResult  = null;
  let kvRecord    = null;   // the active KV record (auto-detected or picked)

  async function init() {
    settings  = await App.getSettings();
    alphabets = await App.getAlphabets();
    const sel = document.getElementById('decode-alph');
    App.populateAlphabetSelect(sel, alphabets, settings.default_alphabet || 'b32');

    App.bindSegmented('decode-enc', (val) => {
      togglePasswordRow(val !== 'none');
    });
    App.setSegmentedValue('decode-enc', settings.default_salt_mode || 'salt');
    togglePasswordRow((settings.default_salt_mode || 'salt') !== 'none');

    App.setupDropZone('decode-drop', (path) => loadFile(path));

    document.getElementById('decode-browse').addEventListener('click', async () => {
      const r = await App.api('open_file_dialog', 'open');
      if (r.ok && r.path) loadFile(r.path);
    });

    document.getElementById('decode-clear').addEventListener('click', clearFile);

    document.getElementById('decode-pw-eye').addEventListener('click', () => {
      const pw = document.getElementById('decode-pw');
      pw.type = pw.type === 'password' ? 'text' : 'password';
    });

    document.getElementById('decode-go').addEventListener('click', doDecode);
    document.getElementById('decode-tryall').addEventListener('click', doTryAll);

    document.getElementById('decode-paste-use').addEventListener('click', usePastedText);

    document.getElementById('decode-result-open').addEventListener('click', () => {
      if (lastResult && lastResult.out_path) App.api('open_folder', lastResult.out_path);
    });

    // Vault picker
    document.getElementById('decode-pick-vault').addEventListener('click', openKvPicker);
    document.getElementById('kv-picker-cancel').addEventListener('click', closeKvPicker);
    document.getElementById('decode-kv-clear').addEventListener('click', clearKvRecord);
  }

  function togglePasswordRow(show) {
    document.getElementById('decode-pw-row').style.display = show ? '' : 'none';
  }

  // ---------------------------------------------------------------------------
  // File loading + header detection
  // ---------------------------------------------------------------------------

  async function loadFile(path) {
    const info = await App.api('file_info', path);
    if (!info.ok) { App.toast('Cannot read file: ' + info.error, 'error'); return; }
    currentFile = info;
    document.getElementById('decode-empty').classList.add('hidden');
    document.getElementById('decode-file-card').classList.remove('hidden');
    document.getElementById('decode-file-name').textContent = info.name;
    document.getElementById('decode-file-size').textContent = App.fmtBytes(info.size) + '  —  ' + info.modified;
    document.getElementById('decode-go').disabled = false;
    document.getElementById('decode-tryall').disabled = false;

    // Peek header
    const peek = await App.api('peek_header', path);
    const dt = document.getElementById('decode-detect-text');
    clearKvRecord();  // reset KV state before re-detection

    const cprefix = peek && peek.compression && peek.compression !== 'none'
      ? `[Compressed: ${peek.compression}] ` : '';

    if (peek.ok && peek.has_header) {
      if (peek.header_type === 'kv') {
        if (peek.record_found) {
          const r = await App.api('keyrecord_get', peek.record_id);
          if (r.ok) {
            setKvRecord(r.record, `Auto-detected from KV| header (record ${peek.record_id})`);
            dt.textContent = `${cprefix}Key Vault header — record ${peek.record_id} found in vault`;
          } else {
            dt.textContent = `${cprefix}Key Vault header — record ${peek.record_id} NOT in vault`;
          }
        } else {
          dt.textContent = `${cprefix}Key Vault header — record ${peek.record_id} NOT in vault. Restore the key record file first.`;
        }
        if (peek.alph_id) {
          const match = alphabets.find(a => a.id === peek.alph_id);
          if (match) document.getElementById('decode-alph').value = match.id;
        }
      } else if (peek.header_type === 'cv1') {
        dt.textContent = `Bare compressed (${peek.compression}). Select alphabet manually.`;
      } else {
        const fpPart = peek.fp ? ' fp:' + peek.fp : '';
        dt.textContent = `${cprefix}SV1 header found: base ${peek.base}${fpPart}`;
        let match = null;
        if (peek.fp) match = alphabets.find(a => a.fingerprint.startsWith(peek.fp));
        if (!match) match = alphabets.find(a => a.base === peek.base);
        if (match) document.getElementById('decode-alph').value = match.id;
      }
    } else {
      // No header — try to find a KV record by full-string match
      const enc = await App.api('read_encoded_text', path);
      if (enc.ok && enc.text) {
        const found = await App.api('keyrecord_find_by_string', enc.text);
        if (found.ok) {
          setKvRecord(found.record, `Auto-matched by encoded string to record ${found.record.id}`);
          dt.textContent = `Matched key record ${found.record.id} by encoded string`;
        } else {
          dt.textContent = 'No header — select alphabet manually';
        }
      } else {
        dt.textContent = 'No header — select alphabet manually';
      }
    }

    // Check keyring for stored password
    const hint = document.getElementById('decode-pw-hint');
    if (kvRecord) {
      // For KV: keyring lookup is by record id
      const lookup = await App.api('vault_label_for_file', path); // not relevant for KV, but harmless
      hint.textContent = 'Enter your password (will check keyring as fallback).';
    } else {
      const lookup = await App.api('vault_label_for_file', path);
      if (lookup.ok && lookup.stored) {
        hint.textContent = 'Password found in keyring — will auto-use if password field empty.';
      } else {
        hint.textContent = '';
      }
    }
  }

  function clearFile() {
    currentFile = null;
    document.getElementById('decode-empty').classList.remove('hidden');
    document.getElementById('decode-file-card').classList.add('hidden');
    document.getElementById('decode-go').disabled = true;
    document.getElementById('decode-tryall').disabled = true;
    document.getElementById('decode-detect-text').textContent = 'No file selected';
    document.getElementById('decode-pw-hint').textContent = '';
    document.getElementById('decode-result').classList.add('hidden');
    clearKvRecord();
  }

  async function usePastedText() {
    const txt = document.getElementById('decode-paste').value.trim();
    if (!txt) { App.toast('Paste some text first', 'warning'); return; }
    const root = await App.api('project_root');
    const tmpPath = root.path + '/_pasted.svtmp';
    const wr = await App.api('write_text_file', tmpPath, txt);
    if (!wr.ok) { App.toast('Failed to save paste: ' + wr.error, 'error'); return; }
    loadFile(tmpPath);
  }

  // ---------------------------------------------------------------------------
  // KV record state
  // ---------------------------------------------------------------------------

  function setKvRecord(record, note) {
    kvRecord = record;
    const banner = document.getElementById('decode-kv-banner');
    const label  = document.getElementById('decode-kv-record-label');
    banner.classList.remove('hidden');
    label.textContent = `${record.label || '(no label)'} · ${record.id} · ${record.alphabet_id}`;
    // Force encryption segmented to "salt" placeholder (KV uses its own path) — but visually we hide enc selection irrelevance via the banner
    // Pre-fill alphabet
    const match = alphabets.find(a => a.id === record.alphabet_id);
    if (match) document.getElementById('decode-alph').value = match.id;
    // Ensure password field is visible
    togglePasswordRow(true);
  }

  function clearKvRecord() {
    kvRecord = null;
    const banner = document.getElementById('decode-kv-banner');
    if (banner) banner.classList.add('hidden');
  }

  // ---------------------------------------------------------------------------
  // Vault picker modal
  // ---------------------------------------------------------------------------

  async function openKvPicker() {
    const backdrop = document.getElementById('kv-picker-backdrop');
    const list = document.getElementById('kv-picker-list');
    list.innerHTML = '<div class="muted small" style="padding:10px">Loading…</div>';
    backdrop.classList.remove('hidden');

    const r = await App.api('keyrecord_list');
    if (!r.ok) {
      list.innerHTML = `<div class="muted small" style="padding:10px">Error: ${esc(r.error)}</div>`;
      return;
    }
    if (!r.records || r.records.length === 0) {
      list.innerHTML = '<div class="muted small" style="padding:10px">No key records yet. Use Key Vault mode on the Encode tab to create one.</div>';
      return;
    }

    list.innerHTML = '';
    r.records.forEach(rec => {
      const row = document.createElement('div');
      row.className = 'kv-picker-row';
      row.innerHTML = `
        <div class="kv-picker-main">
          <div class="kv-picker-label">${esc(rec.label || '(no label)')}</div>
          <div class="kv-picker-meta">${esc(rec.id)} · ${esc(rec.alphabet_id)} · ${esc(rec.created || '')}</div>
        </div>
        <div class="kv-picker-chars muted small">${esc(String(rec.char_count || '?'))} chars</div>
      `;
      row.addEventListener('click', () => useKvRecord(rec));
      list.appendChild(row);
    });
  }

  function closeKvPicker() {
    document.getElementById('kv-picker-backdrop').classList.add('hidden');
  }

  async function useKvRecord(rec) {
    closeKvPicker();
    setKvRecord(rec, `Loaded from vault: ${rec.id}`);
    // Load the encoded string from the record into a temp file so currentFile flow works
    const encodedStr = rec.encoded_string || '';
    if (!encodedStr) {
      App.toast('Record has no encoded string', 'warning');
      return;
    }
    const root = await App.api('project_root');
    const tmpPath = root.path + '/_kv_from_vault.svtmp';
    const wr = await App.api('write_text_file', tmpPath, encodedStr);
    if (!wr.ok) { App.toast('Failed to load record string: ' + wr.error, 'error'); return; }
    await loadFile(tmpPath);  // this clears kvRecord and re-detects, which should re-set it via peek_header
    // Re-set kvRecord explicitly in case auto-detect didn't catch it
    setKvRecord(rec, 'Loaded from vault');
    document.getElementById('decode-detect-text').textContent =
      `Loaded record ${rec.id} from vault. Enter password and click Decode.`;
  }

  // ---------------------------------------------------------------------------
  // Decode dispatch
  // ---------------------------------------------------------------------------

  async function doDecode() {
    if (!currentFile && !kvRecord) return;

    const password = document.getElementById('decode-pw').value;
    const btn = document.getElementById('decode-go');
    btn.disabled = true;
    btn.textContent = 'Decoding…';

    try {
      if (kvRecord) {
        await doDecodeKv(password);
      } else {
        await doDecodeStandard(password);
      }
    } finally {
      btn.disabled = false;
      btn.textContent = 'Decode';
    }
  }

  async function doDecodeKv(password) {
    // Get encoded string either from the file or directly from the record
    let encoded_string = kvRecord.encoded_string || '';
    if (!encoded_string && currentFile) {
      const enc = await App.api('read_encoded_text', currentFile.path);
      if (enc.ok) encoded_string = enc.text;
    }
    if (!encoded_string) { App.toast('No encoded string to decode', 'error'); return; }

    const params = {
      encoded_string,
      record_id: kvRecord.id,
    };
    if (password) params.password = password;

    const r = await App.api('decode_keyvault', params);
    if (!r.ok) { App.toast('KV decode failed: ' + r.error, 'error'); return; }

    lastResult = r;
    showKvResult(r);

    const integrityNote = r.integrity_ok === true ? ' · integrity ✓'
      : r.integrity_ok === false ? ' · integrity ✗ (mismatch!)'
      : '';
    App.toast(`Decoded ${r.bytes} bytes${integrityNote}`,
              r.integrity_ok === false ? 'warning' : 'success');
  }

  async function doDecodeStandard(password) {
    const alph_id = document.getElementById('decode-alph').value;
    const enc = App.getSegmentedValue('decode-enc');

    const params = {
      in_path: currentFile.path,
      alph_id,
      salt_mode: enc === 'none' ? 'salt' : enc,
    };
    if (enc !== 'none' && password) params.password = password;

    const r = await App.api('decode', params);
    if (!r.ok) { App.toast('Decode failed: ' + r.error, 'error'); return; }

    lastResult = r;
    showResult(r);
    App.toast('Decoded ' + r.bytes + ' bytes', 'success');

    const preview = await App.api('read_text_preview', r.out_path);
    if (preview.ok && preview.is_text) {
      const el = document.getElementById('decode-result-preview');
      el.textContent = preview.preview + (preview.truncated ? '\n…' : '');
      el.classList.remove('hidden');
    } else {
      document.getElementById('decode-result-preview').classList.add('hidden');
    }
  }

  // ---------------------------------------------------------------------------
  // Result display
  // ---------------------------------------------------------------------------

  function showResult(r) {
    const card = document.getElementById('decode-result');
    card.classList.remove('hidden');
    card.querySelector('.result-badge').textContent = 'OK';
    card.querySelector('.result-badge').className = 'result-badge ok';
    document.getElementById('decode-result-file').textContent = r.out_path;
    document.getElementById('decode-result-bytes').textContent = r.bytes + ' bytes';
    if (r.autodetect) {
      document.getElementById('decode-result-auto-row').classList.remove('hidden');
      document.getElementById('decode-result-auto').textContent = r.autodetect;
    } else {
      document.getElementById('decode-result-auto-row').classList.add('hidden');
    }
  }

  function showKvResult(r) {
    const card = document.getElementById('decode-result');
    card.classList.remove('hidden');
    const badge = card.querySelector('.result-badge');
    if (r.integrity_ok === false) {
      badge.textContent = 'INTEGRITY';
      badge.className = 'result-badge err';
    } else {
      badge.textContent = 'KV';
      badge.className = 'result-badge ok';
    }
    document.getElementById('decode-result-file').textContent = r.out_path;
    document.getElementById('decode-result-bytes').textContent =
      r.bytes + ' bytes' +
      (r.integrity_ok === true  ? '  ·  SHA-256 verified ✓' :
       r.integrity_ok === false ? '  ·  SHA-256 MISMATCH ✗' : '');
    const autoRow = document.getElementById('decode-result-auto-row');
    autoRow.classList.remove('hidden');
    document.getElementById('decode-result-auto').textContent =
      `Key Vault record ${(r.record && r.record.id) || ''}`;

    if (r.preview) {
      const el = document.getElementById('decode-result-preview');
      el.textContent = r.preview;
      el.classList.remove('hidden');
    } else {
      document.getElementById('decode-result-preview').classList.add('hidden');
    }
  }

  async function doTryAll() {
    if (!currentFile) return;
    const password = document.getElementById('decode-pw').value;
    const params = { in_path: currentFile.path };
    if (password) params.password = password;

    const btn = document.getElementById('decode-tryall');
    btn.disabled = true;
    btn.textContent = 'Trying…';

    const r = await App.api('tryall', params);
    btn.disabled = false;
    btn.textContent = 'Try all alphabets';

    if (!r.ok) { App.toast('TryAll failed: ' + r.error, 'error'); return; }

    App.toast(`Tried ${r.tried}, ${r.hits.length} hits`, r.hits.length > 0 ? 'success' : 'warning', 5000);
    if (r.hits.length > 0) {
      const list = r.hits.map(h => `${h.label}: ${h.path} (${h.bytes_desc})`).join('\n');
      const el = document.getElementById('decode-result-preview');
      el.textContent = 'TryAll hits:\n\n' + list;
      el.classList.remove('hidden');
      document.getElementById('decode-result').classList.remove('hidden');
      document.getElementById('decode-result-file').textContent = 'Multiple candidates → ' + currentFile.path + '.tryall.*';
      document.getElementById('decode-result-bytes').textContent = '(see preview)';
    }
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  return { init, loadFile };
})();

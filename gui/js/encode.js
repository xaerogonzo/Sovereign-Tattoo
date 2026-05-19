// ===========================================================
// encode.js - Encode tab logic
// Two-axis model: Header (bare|keyref|fullsv1) × Encryption (none|kv|salt|nosalt)
// ===========================================================

Tabs.encode = (() => {
  let currentFile = null;  // { path, name, size } -- File mode
  let sourceMode  = 'file'; // 'file' | 'text'
  let encMode     = 'salt'; // 'none' | 'kv' | 'salt' | 'nosalt'
  let headerMode  = 'keyref'; // 'bare' | 'keyref' | 'fullsv1'
  let compMode    = 'none'; // 'none' | 'auto' | 'zlib' | 'lzma' | 'lpaq'
  let alphabets   = [];
  let settings    = {};

  // Encryption mode notes shown below the segmented control
  const ENC_NOTES = {
    none:   'No encryption. Output is raw base-encoded bytes.',
    kv:     'AES-256 with salt/IV stored in the key record — zero overhead in the tattoo string.',
    salt:   'OpenSSL AES-256-CBC with Salted__ prefix (+~20 chars in output).',
    nosalt: 'OpenSSL AES-256-CBC, deterministic. Same input+password = same output.',
  };

  // Header mode notes
  const HEADER_NOTES = {
    bare:    'No prefix. Smallest output. Key record (or the alphabet) required to decode.',
    keyref:  'Adds KV|XXXXXXXX| (12 chars) linking to your key record for automatic decode.',
    fullsv1: 'Self-describing: embeds alphabet fingerprint and base number in the string.',
  };

  async function init() {
    settings  = await App.getSettings();
    alphabets = await App.getAlphabets();

    const sel = document.getElementById('encode-alph');
    App.populateAlphabetSelect(sel, alphabets, settings.default_alphabet || 'b32');
    sel.addEventListener('change', () => { updateAlphNote(); updateEstimate(); });
    updateAlphNote();

    // Encryption segmented
    App.bindSegmented('encode-enc', (val) => {
      encMode = val;
      onEncChange(val);
      updateEstimate();
      updateInfoBlurb();
    });

    // Header segmented
    App.bindSegmented('encode-header', (val) => {
      headerMode = val;
      onHeaderChange(val);
      updateEstimate();
      updateInfoBlurb();
    });

    // FpSize
    App.bindSegmented('encode-fpsize', () => { updateEstimate(); updateInfoBlurb(); });

    // Compression
    App.bindSegmented('encode-compression', (val) => {
      compMode = val;
      updateInfoBlurb();
      updateEstimate();
    });

    // Disable external-engine buttons whose binaries aren't installed in bin/
    try {
      const eng = await App.api('engines_list');
      if (eng.ok) {
        eng.engines.forEach(e => {
          const btn = document.getElementById(`encode-comp-${e.id}`);
          if (!btn) return;
          if (!e.installed || !e.integrated) {
            btn.disabled = true;
            btn.style.opacity = '0.4';
            btn.title = e.integrated
              ? `Drop ${e.filename} into bin/ to enable (see Settings)`
              : `${e.name} is not wired up for compression yet`;
          }
        });
      }
    } catch(err) { /* harmless if API not ready */ }

    // Apply saved default compression
    if (settings.default_compression && settings.default_compression !== 'none') {
      App.setSegmentedValue('encode-compression', settings.default_compression);
      compMode = settings.default_compression;
    }

    // Source mode toggle (File / Text)
    App.bindSegmented('encode-source', (val) => {
      sourceMode = val;
      setSourceMode(val);
    });

    // Apply saved defaults
    const defaultEnc = settings.default_salt_mode || 'salt';
    App.setSegmentedValue('encode-enc', defaultEnc);
    encMode = defaultEnc;
    onEncChange(defaultEnc);

    App.setSegmentedValue('encode-fpsize', settings.default_fpsize || '8');

    // Drop zone (File mode)
    App.setupDropZone('encode-drop', (path) => loadFile(path));

    // Browse button
    document.getElementById('encode-browse').addEventListener('click', async () => {
      const r = await App.api('open_file_dialog', 'open');
      if (r.ok && r.path) loadFile(r.path);
    });

    document.getElementById('encode-clear').addEventListener('click', clearFile);

    // Text mode textarea: live byte count + button enablement
    document.getElementById('encode-text-input').addEventListener('input', () => {
      const bytes = new TextEncoder().encode(
        document.getElementById('encode-text-input').value
      ).length;
      document.getElementById('encode-text-bytes').textContent =
        bytes > 0 ? App.fmtBytes(bytes) : '0 bytes';
      document.getElementById('encode-go').disabled = bytes === 0;
      updateEstimate();
    });

    // Password show/hide
    document.getElementById('encode-pw-eye').addEventListener('click', () => {
      const pw = document.getElementById('encode-pw');
      pw.type = pw.type === 'password' ? 'text' : 'password';
    });

    // Encode button
    document.getElementById('encode-go').addEventListener('click', doEncode);

    // Result actions
    document.getElementById('encode-result-copy').addEventListener('click', copyEncodedText);
    document.getElementById('encode-result-open').addEventListener('click', () => {
      if (lastResult && lastResult.out_path) App.api('open_folder', lastResult.out_path);
    });

    // "Save key record" toggle — dims the save-original option when unchecked
    document.getElementById('encode-kv-save-record').addEventListener('change', (e) => {
      const origLabel = document.getElementById('encode-kv-save-orig-label');
      origLabel.style.opacity = e.target.checked ? '' : '0.4';
      origLabel.style.pointerEvents = e.target.checked ? '' : 'none';
    });

    // Apply initial header state
    onHeaderChange(headerMode);
    updateInfoBlurb();
  }

  // ---------------------------------------------------------------------------
  // Context-sensitive info blurb
  // ---------------------------------------------------------------------------

  function updateInfoBlurb() {
    const title = document.getElementById('encode-info-title');
    const body  = document.getElementById('encode-info-body');
    if (!title || !body) return;

    const pieces = [];
    let summary = '';

    // Encryption explanation
    if (encMode === 'none') {
      summary = 'No encryption';
      pieces.push('Anyone with the encoded string can decode. Use for non-sensitive archival.');
    } else if (encMode === 'kv') {
      summary = 'Key Vault encryption';
      pieces.push('AES-256 with salt &amp; IV stored in a key record (not in the output). Zero crypto overhead in the encoded string.');
      pieces.push('<strong>You will need three things to decode:</strong> the encoded string, the key record (back it up!), and your password.');
    } else if (encMode === 'salt') {
      summary = 'Salted AES-256';
      pieces.push('Standard OpenSSL mode. Adds <code>Salted__</code> + random salt (+~20 chars) to the output. Encoded string is self-contained — only the password is needed to decode.');
    } else if (encMode === 'nosalt') {
      summary = 'No-salt AES-256';
      pieces.push('Deterministic: same input + password = same output. Vulnerable to rainbow tables for weak passwords. Power-user option.');
    }

    // Header explanation
    if (headerMode === 'bare') {
      summary += ' &middot; Bare header';
      pieces.push('<strong>Bare header (0 chars):</strong> smallest output. Decoder must know the alphabet — store it separately or use a built-in.');
    } else if (headerMode === 'keyref') {
      summary += ' &middot; Key ref header';
      pieces.push('<strong>Key ref header (+12 chars):</strong> embeds an 8-char ID linking to your key record so the decoder auto-loads the alphabet. Most useful with Key Vault encryption.');
    } else if (headerMode === 'fullsv1') {
      const fpsize = App.getSegmentedValue('encode-fpsize') || '8';
      summary += ' &middot; Full SV1';
      let fpInfo;
      if (fpsize === '8')      fpInfo = 'Full 8-char fingerprint — unambiguous.';
      else if (fpsize === '2') fpInfo = 'Short 2-char fingerprint — saves 6 chars, 1-in-256 chance of alphabet collision on decode.';
      else                     fpInfo = 'No fingerprint — saves 12 chars, decoder relies on base number only.';
      pieces.push(`<strong>Full SV1 header:</strong> self-describing; decoder needs no extra context. ${fpInfo}`);
    }

    // Compression note
    if (compMode && compMode !== 'none') {
      const COMP_NOTE = {
        auto:   'Try every available algorithm (stdlib + installed engines) and pick the smallest. Adds <code>CV1|c:X|</code> (+6 chars) if anything beats the original; otherwise nothing.',
        zlib:   'Raw deflate (Python stdlib). Often best for tiny text. Adds <code>CV1|c:z|</code> (+6 chars).',
        lzma:   'Raw LZMA2 at max preset (stdlib). Usually denser than Deflate above ~150 chars. Adds <code>CV1|c:l|</code> (+7 chars).',
        lpaq8:  'LPAQ8 (external binary in <code>bin/</code>) &mdash; strongest compression for short English text. Adds <code>CV1|c:lp|</code> (+7 chars).',
        paq8o:  'PAQ8O (external binary in <code>bin/</code>) &mdash; heavier PAQ variant; better than LPAQ8 on 100+ char text but slower. Adds <code>CV1|c:po|</code> (+7 chars).',
      };
      pieces.push(`<strong>Compression:</strong> ${COMP_NOTE[compMode] || ''}`);
      summary += ' &middot; +' + (compMode === 'auto' ? 'auto-comp' : compMode);
    }

    // Combo warning for KV without backup-friendly header
    if (encMode === 'kv') {
      pieces.push('<strong class="info-warn">Back up the key record.</strong> Use the Vault tab → Export card after encoding. The recovery.html lets you decode in any browser if this app is lost.');
    }

    title.innerHTML = summary;
    body.innerHTML = pieces.map(p => `<div class="info-line">${p}</div>`).join('');
  }

  // ---------------------------------------------------------------------------
  // Encryption mode change handler
  // ---------------------------------------------------------------------------

  function onEncChange(val) {
    const needsPw  = val !== 'none';
    const isKv     = val === 'kv';

    togglePasswordRow(needsPw);
    document.getElementById('encode-kv-row').classList.toggle('hidden', !isKv);
    document.getElementById('encode-enc-note').textContent = ENC_NOTES[val] || '';

    // KV mode strongly suggests keyref or bare header; nudge if on fullsv1
    // (but don't force — user may want fullsv1 + kv)
    if (isKv && headerMode === 'fullsv1') {
      // No forced change — just show a note via header note
    }

    updateHeaderNote();
  }

  // ---------------------------------------------------------------------------
  // Header mode change handler
  // ---------------------------------------------------------------------------

  function onHeaderChange(val) {
    headerMode = val;
    const isSV1 = val === 'fullsv1';
    document.getElementById('encode-fpsize-col').style.display = isSV1 ? '' : 'none';
    updateHeaderNote();
    updateEstimate();
  }

  function updateHeaderNote() {
    const note = document.getElementById('encode-header-note');
    if (note) note.textContent = HEADER_NOTES[headerMode] || '';
  }

  // ---------------------------------------------------------------------------
  // Source mode switching
  // ---------------------------------------------------------------------------

  function setSourceMode(mode) {
    const dropzone    = document.getElementById('encode-drop');
    const textSection = document.getElementById('encode-text-section');
    const openFolderBtn = document.getElementById('encode-result-open');
    if (mode === 'text') {
      dropzone.classList.add('hidden');
      textSection.classList.remove('hidden');
      const bytes = new TextEncoder().encode(
        document.getElementById('encode-text-input').value
      ).length;
      document.getElementById('encode-go').disabled = bytes === 0;
    } else {
      dropzone.classList.remove('hidden');
      textSection.classList.add('hidden');
      document.getElementById('encode-go').disabled = currentFile === null;
    }
    if (openFolderBtn) openFolderBtn.classList.toggle('hidden', mode === 'text');
    updateEstimate();
  }

  function togglePasswordRow(show) {
    document.getElementById('encode-pw-row').style.display = show ? '' : 'none';
  }

  function updateAlphNote() {
    const id = document.getElementById('encode-alph').value;
    const a  = alphabets.find(x => x.id === id);
    const note = document.getElementById('encode-alph-note');
    if (!a) { note.textContent = ''; return; }
    note.textContent = `base ${a.base} — ${a.notes || ''}${a.builtin ? '' : ' [custom]'}`;
  }

  // ---------------------------------------------------------------------------
  // File mode helpers
  // ---------------------------------------------------------------------------

  async function loadFile(path) {
    const info = await App.api('file_info', path);
    if (!info.ok) { App.toast('Cannot read file: ' + info.error, 'error'); return; }
    currentFile = info;
    document.getElementById('encode-empty').classList.add('hidden');
    document.getElementById('encode-file-card').classList.remove('hidden');
    document.getElementById('encode-file-name').textContent = info.name;
    document.getElementById('encode-file-size').textContent =
      App.fmtBytes(info.size) + '  —  ' + info.modified;
    document.getElementById('encode-go').disabled = false;
    updateEstimate();
  }

  function clearFile() {
    currentFile = null;
    document.getElementById('encode-empty').classList.remove('hidden');
    document.getElementById('encode-file-card').classList.add('hidden');
    document.getElementById('encode-go').disabled = true;
    document.getElementById('encode-est-chars').textContent = '--';
    document.getElementById('encode-result').classList.add('hidden');
  }

  // ---------------------------------------------------------------------------
  // Estimate
  // ---------------------------------------------------------------------------

  function updateEstimate() {
    let byteSize = null;
    if (sourceMode === 'file') {
      byteSize = currentFile ? currentFile.size : null;
    } else {
      const txt = document.getElementById('encode-text-input').value;
      byteSize = txt.length > 0 ? new TextEncoder().encode(txt).length : null;
    }

    if (byteSize === null) {
      document.getElementById('encode-est-chars').textContent = '--';
      return;
    }

    const id = document.getElementById('encode-alph').value;
    const a  = alphabets.find(x => x.id === id);
    if (!a) return;

    // Encryption adds bytes to the data before encoding:
    //   kv:     +0 (salt/IV NOT in output)
    //   salt:   +16 (Salted__ prefix)
    //   nosalt: +0 (but OpenSSL may pad differently — same estimate as plain)
    //   none:   +0
    const encBytesOverhead = (encMode === 'salt') ? 16 : 0;
    const hasEncryption    = encMode !== 'none';

    // Header prefix overhead in output characters:
    //   bare:    0
    //   keyref:  'KV|XXXXXXXX|' = 12
    //   fullsv1: 'SV1|fp:XXXXXXXX|b:NN|' = variable
    let headerOverhead = 0;
    if (headerMode === 'keyref') {
      headerOverhead = 12;  // KV|12345678|
    } else if (headerMode === 'fullsv1') {
      const fpsize  = App.getSegmentedValue('encode-fpsize') || '8';
      const baseStr = a.base.toString();
      if (fpsize === '0')    headerOverhead = 'SV1|b:|'.length + baseStr.length;
      else headerOverhead = 'SV1|fp:|b:|'.length + parseInt(fpsize) + baseStr.length;
    }

    const chars = App.estimateChars(byteSize + encBytesOverhead, a.base, false, headerOverhead);
    document.getElementById('encode-est-chars').textContent = chars != null ? chars : '--';
  }

  // ---------------------------------------------------------------------------
  // Encode dispatch
  // ---------------------------------------------------------------------------

  let lastResult      = null;
  let lastEncodedText = '';

  async function doEncode() {
    const alph_id    = document.getElementById('encode-alph').value;
    const password   = document.getElementById('encode-pw').value;
    const password2  = document.getElementById('encode-pw2').value;
    const fpsize     = App.getSegmentedValue('encode-fpsize') || '8';
    const dualverify = document.getElementById('encode-dualverify').checked;
    const save_pw    = document.getElementById('encode-save-pw').checked;

    // Validate password
    const needsPw = encMode !== 'none';
    if (needsPw) {
      if (!password) { App.toast('Password required for encryption', 'error'); return; }
      if (password !== password2) { App.toast('Passwords do not match', 'error'); return; }
    }

    const btn = document.getElementById('encode-go');
    btn.disabled = true;
    btn.textContent = 'Encoding…';

    try {
      if (encMode === 'kv') {
        await doEncodeKv(alph_id, password, fpsize, dualverify, save_pw);
      } else {
        await doEncodeStandard(alph_id, password, fpsize, dualverify, save_pw);
      }
    } finally {
      btn.disabled = false;
      btn.textContent = 'Encode';
    }
  }

  // --- Key Vault encode ---

  async function doEncodeKv(alph_id, password, fpsize, dualverify, save_pw) {
    const label      = document.getElementById('encode-kv-label').value.trim();
    const saveRecord = document.getElementById('encode-kv-save-record').checked;
    const saveOrig   = saveRecord && document.getElementById('encode-kv-save-orig').checked;

    const params = {
      alph_id,
      password,
      label,
      save_record:   saveRecord,
      save_original: saveOrig,
      header_mode:   headerMode,
      fpsize,
      dualverify,
      save_password: save_pw && saveRecord,  // only cache pw if record is being saved
      compression:   compMode,
    };

    if (sourceMode === 'text') {
      const text = document.getElementById('encode-text-input').value;
      if (!text.trim()) { App.toast('No text to encode', 'error'); return; }
      params.text = text;
    } else {
      if (!currentFile) return;
      params.in_path = currentFile.path;
    }

    const r = await App.api('encode_keyvault', params);

    if (!r.ok) {
      App.toast('KV encode failed: ' + r.error, 'error');
      return;
    }

    lastEncodedText = r.encoded_string || '';
    lastResult = { ...r, out_path: null, chars: r.char_count };
    showKvResult(r);
    const wasSaved = r.record_saved !== false;  // default true if API didn't return it
    const savedNote = wasSaved ? ' — key record saved' : ' — no record saved';
    App.toast(`Encoded ${r.char_count} chars${savedNote}`, wasSaved ? 'success' : 'info');
  }

  // --- Standard encode (None / Salted / No-salt) ---

  async function doEncodeStandard(alph_id, password, fpsize, dualverify, save_pw) {
    const selfdesc = (headerMode === 'fullsv1');
    // Header choices: bare or fullsv1 map to existing SV1 on/off
    // keyref is KV-only; if user has non-KV encryption + keyref header, treat as bare
    const effectiveHeader = (headerMode === 'keyref') ? 'bare' : headerMode;
    const useSelfdesc = effectiveHeader === 'fullsv1';

    const commonParams = {
      alph_id,
      salt_mode: encMode === 'none' ? 'salt' : encMode,
      selfdesc: useSelfdesc,
      fpsize,
      dualverify,
      save_password: save_pw,
      compression: compMode,
    };
    if (encMode !== 'none') commonParams.password = password;

    let r;
    if (sourceMode === 'text') {
      const text = document.getElementById('encode-text-input').value;
      if (!text.trim()) { App.toast('No text to encode', 'error'); return; }
      r = await App.api('encode_text', { ...commonParams, text });
      if (r.ok) lastEncodedText = r.encoded_text || '';
    } else {
      if (!currentFile) return;
      r = await App.api('encode', { ...commonParams, in_path: currentFile.path });
      if (r.ok) {
        const tr = await App.api('read_encoded_text', r.out_path);
        lastEncodedText = tr.ok ? tr.text : '';
      }
    }

    if (!r.ok) {
      App.toast('Encode failed: ' + r.error, 'error');
      return;
    }

    lastResult = r;
    showResult(r);
    App.toast('Encoded ' + r.chars + ' chars', 'success');
  }

  // ---------------------------------------------------------------------------
  // Result display
  // ---------------------------------------------------------------------------

  function showKvResult(r) {
    const card = document.getElementById('encode-result');
    card.classList.remove('hidden');

    // Adjust badge to show KV mode
    card.querySelector('.result-badge').textContent = 'KV';
    card.querySelector('.result-title').textContent =
      `Key Vault record saved (ID: ${r.id})`;

    const fileRow = document.getElementById('encode-result-file-row');
    if (fileRow) fileRow.classList.add('hidden');  // no file in KV text mode

    document.getElementById('encode-result-chars').textContent =
      (r.char_count || '?') + ' characters';
    document.getElementById('encode-result-fp').textContent =
      r.fingerprint || '(none)';

    // Key card row re-used for record label
    const kcRow = document.getElementById('encode-result-kc-row');
    if (kcRow) {
      kcRow.classList.remove('hidden');
      document.getElementById('encode-result-kc').textContent =
        `Key record ${r.id} saved to vault`;
    }

    document.getElementById('encode-result-text').textContent = lastEncodedText;
  }

  function showResult(r) {
    const isTextMode = sourceMode === 'text';
    const card = document.getElementById('encode-result');
    card.classList.remove('hidden');

    card.querySelector('.result-badge').textContent = 'OK';
    card.querySelector('.result-title').textContent = 'Encoded';

    const fileRow = document.getElementById('encode-result-file-row');
    if (fileRow) fileRow.classList.toggle('hidden', isTextMode);
    if (!isTextMode) document.getElementById('encode-result-file').textContent = r.out_path;

    document.getElementById('encode-result-chars').textContent = r.chars + ' characters';
    document.getElementById('encode-result-fp').textContent = r.fingerprint || '(none)';

    if (r.keycard_path) {
      document.getElementById('encode-result-kc-row').classList.remove('hidden');
      document.getElementById('encode-result-kc').textContent = r.keycard_path;
    } else {
      document.getElementById('encode-result-kc-row').classList.add('hidden');
    }
    document.getElementById('encode-result-text').textContent = lastEncodedText;
  }

  async function copyEncodedText() {
    if (!lastEncodedText) { App.toast('Nothing to copy', 'warning'); return; }
    const r = await App.api('copy_to_clipboard', lastEncodedText);
    if (r.ok) App.toast('Copied to clipboard', 'success');
    else App.toast('Copy failed: ' + r.error, 'error');
  }

  return { init, loadFile };
})();

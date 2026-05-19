// ===========================================================
// tattoo.js — Tattoo Studio tab: My Tattoos, Layout Studio, Body Map
// ===========================================================

Tabs.tattoo = (() => {

  // ── Shared data ────────────────────────────────────────────────────────
  let placements  = [];   // from tattoo_log_list API
  let statuses    = [];
  let logEntries  = [];   // all tattoo log entries (My Tattoos)
  let keyRecords  = [];   // key record list (for linking + Layout Studio)

  // My Tattoos filter state
  let currentFilter  = { status: '', placement: '', type: '', search: '' };
  let bodyMapFilter  = null;  // placement key or null = all
  let editingId      = null;  // null = new entry; string = existing entry id
  let editInkColors  = [];    // working copy during editing

  // Layout Studio state
  let catalog            = [];
  let currentLayoutKey   = null;
  let currentParams      = {};
  let glyphAdvanceEm     = 0.62;
  let renderDebounceTimer = null;
  let adapters           = [];

  // ── DOM refs ───────────────────────────────────────────────────────────
  let elSubTabs, elSubPanels;

  // My Tattoos toolbar
  let elTlogNew, elTlogSearch, elTlogFilterStatus, elTlogFilterPlacement,
      elTlogFilterType, elTlogCount, elTlogGrid;

  // Entry editor
  let elEditor, elEditorTitle, elEditorClose;
  let elEdName, elEdPlacement, elEdPlacementNotes;
  let elEdArtist, elEdStudio, elEdStyle, elEdStatus, elEdDate;
  let elEdSize, elEdPrice, elEdCurrency, elEdNotes;
  let elEdColorsWrap, elEdColorInput, elEdColorAdd;
  let elEdPhotosWrap, elEdPhotosEmpty, elEdPhotoAdd;
  let elEdEncodedSection, elEdRecordLinked, elEdRecordLabel;
  let elEdRecordUnlink, elEdRecordOpenStudio;
  let elEdRecordUnlinked, elEdRecordPicker, elEdRecordLink;
  let elEdSave, elEdCancel, elEdDelete;

  // Layout Studio
  let elSourceRadios, elLogEntryPicker, elRecordPicker, elPasteInput;
  let elChipRow, elParamsForm;
  let elCanvas, elFontSize, elFontSizeVal, elStats;
  let elCopyText, elSaveSvg, elSavePng, elSaveRecord;
  let elImgMgr, elImgThumb, elImgEmpty, elImgInfo, elImgImport, elImgRemove, elImgRecognize;
  let elOcrReview, elOcrAdapter, elOcrReason, elOcrText, elOcrUse, elOcrDiscard;

  // Body Map
  let elBmapFrontBtn, elBmapBackBtn, elBmapClearFilter;
  let elBmapFront, elBmapBack, elBmapZoneList;

  // ── INIT ───────────────────────────────────────────────────────────────

  async function init() {
    // Sub-nav routing
    elSubTabs   = document.querySelectorAll('.sub-tab');
    elSubPanels = document.querySelectorAll('.tattoo-sub-panel');
    elSubTabs.forEach(btn =>
      btn.addEventListener('click', () => switchSubTab(btn.dataset.sub))
    );

    // ── My Tattoos toolbar ──
    elTlogNew             = document.getElementById('tlog-new');
    elTlogSearch          = document.getElementById('tlog-search');
    elTlogFilterStatus    = document.getElementById('tlog-filter-status');
    elTlogFilterPlacement = document.getElementById('tlog-filter-placement');
    elTlogFilterType      = document.getElementById('tlog-filter-type');
    elTlogCount           = document.getElementById('tlog-count');
    elTlogGrid            = document.getElementById('tlog-grid');

    elTlogNew.addEventListener('click', () => openEditor(null));
    elTlogSearch.addEventListener('input', () => {
      currentFilter.search = elTlogSearch.value;
      applyFilters();
    });
    elTlogFilterStatus.addEventListener('change', () => {
      currentFilter.status = elTlogFilterStatus.value;
      applyFilters();
    });
    elTlogFilterPlacement.addEventListener('change', () => {
      currentFilter.placement = elTlogFilterPlacement.value;
      applyFilters();
    });
    elTlogFilterType.addEventListener('change', () => {
      currentFilter.type = elTlogFilterType.value;
      applyFilters();
    });

    // ── Entry editor ──
    elEditor             = document.getElementById('tlog-editor');
    elEditorTitle        = document.getElementById('tlog-editor-title');
    elEditorClose        = document.getElementById('tlog-editor-close');
    elEdName             = document.getElementById('tled-name');
    elEdPlacement        = document.getElementById('tled-placement');
    elEdPlacementNotes   = document.getElementById('tled-placement-notes');
    elEdArtist           = document.getElementById('tled-artist');
    elEdStudio           = document.getElementById('tled-studio');
    elEdStyle            = document.getElementById('tled-style');
    elEdStatus           = document.getElementById('tled-status');
    elEdDate             = document.getElementById('tled-date');
    elEdSize             = document.getElementById('tled-size');
    elEdPrice            = document.getElementById('tled-price');
    elEdCurrency         = document.getElementById('tled-currency');
    elEdNotes            = document.getElementById('tled-notes');
    elEdColorsWrap       = document.getElementById('tled-colors-wrap');
    elEdColorInput       = document.getElementById('tled-color-input');
    elEdColorAdd         = document.getElementById('tled-color-add');
    elEdPhotosWrap       = document.getElementById('tled-photos-wrap');
    elEdPhotosEmpty      = document.getElementById('tled-photos-empty');
    elEdPhotoAdd         = document.getElementById('tled-photo-add');
    elEdEncodedSection   = document.getElementById('tled-encoded-section');
    elEdRecordLinked     = document.getElementById('tled-record-linked');
    elEdRecordLabel      = document.getElementById('tled-record-label');
    elEdRecordUnlink     = document.getElementById('tled-record-unlink');
    elEdRecordOpenStudio = document.getElementById('tled-record-open-studio');
    elEdRecordUnlinked   = document.getElementById('tled-record-unlinked');
    elEdRecordPicker     = document.getElementById('tled-record-picker');
    elEdRecordLink       = document.getElementById('tled-record-link');
    elEdSave             = document.getElementById('tled-save');
    elEdCancel           = document.getElementById('tled-cancel');
    elEdDelete           = document.getElementById('tled-delete');

    elEditorClose.addEventListener('click', closeEditor);
    elEdCancel.addEventListener('click', closeEditor);
    elEdSave.addEventListener('click', saveEditor);
    elEdDelete.addEventListener('click', onDeleteEntry);
    elEdColorAdd.addEventListener('click', onAddInkColor);
    elEdColorInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); onAddInkColor(); }
    });
    elEdPhotoAdd.addEventListener('click', onAddPhoto);
    elEdRecordLink.addEventListener('click', onLinkRecord);
    elEdRecordUnlink.addEventListener('click', onUnlinkRecord);
    elEdRecordOpenStudio.addEventListener('click', onOpenInLayoutStudio);
    document.querySelectorAll('input[name="tled-type"]').forEach(r =>
      r.addEventListener('change', syncTypeSection)
    );

    // ── Layout Studio ──
    elSourceRadios   = document.querySelectorAll('input[name="tattoo-source"]');
    elLogEntryPicker = document.getElementById('tattoo-log-entry-picker');
    elRecordPicker   = document.getElementById('tattoo-record-picker');
    elPasteInput     = document.getElementById('tattoo-paste-input');
    elChipRow        = document.getElementById('tattoo-layout-chips');
    elParamsForm     = document.getElementById('tattoo-params-form');
    elCanvas         = document.getElementById('tattoo-canvas');
    elFontSize       = document.getElementById('tattoo-font-size');
    elFontSizeVal    = document.getElementById('tattoo-font-size-val');
    elStats          = document.getElementById('tattoo-stats');
    elCopyText       = document.getElementById('tattoo-copy-text');
    elSaveSvg        = document.getElementById('tattoo-save-svg');
    elSavePng        = document.getElementById('tattoo-save-png');
    elSaveRecord     = document.getElementById('tattoo-save-to-record');
    elImgMgr         = document.getElementById('tattoo-image-mgr');
    elImgThumb       = document.getElementById('tattoo-image-thumb');
    elImgEmpty       = document.getElementById('tattoo-image-empty');
    elImgInfo        = document.getElementById('tattoo-image-info');
    elImgImport      = document.getElementById('tattoo-image-import');
    elImgRemove      = document.getElementById('tattoo-image-remove');
    elImgRecognize   = document.getElementById('tattoo-image-recognize');
    elOcrReview      = document.getElementById('tattoo-ocr-review');
    elOcrAdapter     = document.getElementById('tattoo-ocr-adapter');
    elOcrReason      = document.getElementById('tattoo-ocr-adapter-reason');
    elOcrText        = document.getElementById('tattoo-ocr-text');
    elOcrUse         = document.getElementById('tattoo-ocr-use');
    elOcrDiscard     = document.getElementById('tattoo-ocr-discard');

    elSourceRadios.forEach(r => r.addEventListener('change', onSourceChange));
    elLogEntryPicker.addEventListener('change', requestRender);
    elRecordPicker.addEventListener('change', () => {
      const rec = currentStudioRecord();
      if (rec && rec.tattoo_layout) maybeRestoreLayoutFromRecord(rec);
      refreshImageManager();
      requestRender();
    });
    elPasteInput.addEventListener('input', requestRender);
    elFontSize.addEventListener('input', () => {
      elFontSizeVal.textContent = elFontSize.value + ' px';
      requestRender();
    });
    elCopyText.addEventListener('click', onCopyText);
    elSaveSvg.addEventListener('click', onSaveSvg);
    elSavePng.addEventListener('click', onSavePng);
    elSaveRecord.addEventListener('click', onSaveLayoutToRecord);
    elImgImport.addEventListener('click', onImportImage);
    elImgRemove.addEventListener('click', onRemoveImage);
    elImgRecognize.addEventListener('click', onRecognizeImage);
    elOcrAdapter.addEventListener('change', updateOcrAdapterReason);
    elOcrUse.addEventListener('click', onUseOcrText);
    elOcrDiscard.addEventListener('click', discardOcrReview);
    elOcrText.addEventListener('keydown', e => {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); onUseOcrText(); }
      else if (e.key === 'Escape') { e.preventDefault(); discardOcrReview(); }
    });

    // ── Body Map ──
    elBmapFrontBtn    = document.getElementById('bmap-front-btn');
    elBmapBackBtn     = document.getElementById('bmap-back-btn');
    elBmapClearFilter = document.getElementById('bmap-clear-filter');
    elBmapFront       = document.getElementById('bmap-front');
    elBmapBack        = document.getElementById('bmap-back');
    elBmapZoneList    = document.getElementById('bmap-zone-list');

    elBmapFrontBtn.addEventListener('click', () => {
      elBmapFrontBtn.classList.add('active');   elBmapBackBtn.classList.remove('active');
      elBmapFront.classList.remove('hidden');   elBmapBack.classList.add('hidden');
    });
    elBmapBackBtn.addEventListener('click', () => {
      elBmapBackBtn.classList.add('active');    elBmapFrontBtn.classList.remove('active');
      elBmapBack.classList.remove('hidden');    elBmapFront.classList.add('hidden');
    });
    elBmapClearFilter.addEventListener('click', () => {
      bodyMapFilter = null;
      clearZoneSelections();
      applyFilters();
    });
    // Wire SVG zone interactions
    document.querySelectorAll('.bz').forEach(el => {
      el.addEventListener('click',      () => onZoneClick(el.id));
      el.addEventListener('mouseenter', () => onZoneHover(el.id, true));
      el.addEventListener('mouseleave', () => onZoneHover(el.id, false));
    });

    // Load layout catalog
    const r = await App.api('tattoo_list_layouts');
    if (!r.ok) {
      App.toast('Failed to load layouts: ' + (r.error || 'unknown'), 'error');
      return;
    }
    catalog = r.layouts;
    glyphAdvanceEm = r.glyph_advance_em;
    renderChips();

    // Load OCR adapters
    const ra = await App.api('tattoo_adapters_list');
    if (ra.ok) { adapters = ra.adapters; populateOcrAdapterSelect(); }

    // Load tattoo log and key records
    await loadAll();
  }

  async function onShow() {
    await loadAll();
  }

  async function loadAll() {
    await Promise.all([loadLog(), loadKeyRecords()]);
  }

  // ── SUB-NAV ────────────────────────────────────────────────────────────

  function switchSubTab(name) {
    elSubTabs.forEach(b => b.classList.toggle('active', b.dataset.sub === name));
    elSubPanels.forEach(p => p.classList.toggle('active', p.id === 'tattoo-sub-' + name));
  }

  // ── MY TATTOOS: data loading ───────────────────────────────────────────

  async function loadLog() {
    const r = await App.api('tattoo_log_list');
    if (!r.ok) { App.toast('Failed to load tattoo log: ' + r.error, 'error'); return; }
    logEntries = r.entries  || [];
    placements = r.placements || [];
    statuses   = r.statuses   || [];

    populateFilterDropdowns();
    populateEditorDropdowns();
    applyFilters();
    refreshBodyMap();
    populateLogEntryPicker();
  }

  async function loadKeyRecords() {
    const r = await App.api('keyrecord_list');
    keyRecords = r.ok ? (r.records || []) : [];
    populateStudioRecordPicker();
  }

  function populateFilterDropdowns() {
    // Status
    elTlogFilterStatus.innerHTML = '<option value="">All statuses</option>' +
      statuses.map(s => `<option value="${s}">${statusLabel(s)}</option>`).join('');

    // Placement (grouped)
    const cats = groupByCat(placements);
    elTlogFilterPlacement.innerHTML = '<option value="">All placements</option>';
    cats.forEach(([cat, ps]) => {
      const og = document.createElement('optgroup');
      og.label = cat;
      ps.forEach(p => {
        const o = document.createElement('option');
        o.value = p.key; o.textContent = p.label;
        og.appendChild(o);
      });
      elTlogFilterPlacement.appendChild(og);
    });
  }

  function populateEditorDropdowns() {
    // Placement select inside the editor
    const cats = groupByCat(placements);
    elEdPlacement.innerHTML = '<option value="">— Select placement —</option>';
    cats.forEach(([cat, ps]) => {
      const og = document.createElement('optgroup');
      og.label = cat;
      ps.forEach(p => {
        const o = document.createElement('option');
        o.value = p.key; o.textContent = p.label;
        og.appendChild(o);
      });
      elEdPlacement.appendChild(og);
    });

    // Status select inside the editor
    elEdStatus.innerHTML = statuses.map(s =>
      `<option value="${s}">${statusLabel(s)}</option>`
    ).join('');
  }

  function populateLogEntryPicker() {
    if (!elLogEntryPicker) return;
    const encoded = logEntries.filter(e => e.type === 'encoded' && e.key_record_id);
    if (!encoded.length) {
      elLogEntryPicker.innerHTML = '<option value="">(no encoded tattoos in My Tattoos)</option>';
      return;
    }
    elLogEntryPicker.innerHTML = encoded.map(e => {
      const pl = placements.find(p => p.key === e.placement);
      const suffix = pl ? ` · ${pl.label}` : '';
      return `<option value="${e.id}">${escapeHtml((e.name || e.id) + suffix)}</option>`;
    }).join('');
  }

  function populateStudioRecordPicker() {
    if (!elRecordPicker) return;
    if (!keyRecords.length) {
      elRecordPicker.innerHTML = '<option value="">(no records — use Encode tab)</option>';
      return;
    }
    elRecordPicker.innerHTML = keyRecords.map(rec => {
      const label = rec.label ? `${rec.label} (${rec.id})` : `untitled ${rec.id}`;
      return `<option value="${rec.id}">${escapeHtml(label)}</option>`;
    }).join('');
    if (keyRecords[0] && keyRecords[0].tattoo_layout) maybeRestoreLayoutFromRecord(keyRecords[0]);
    refreshImageManager();
    requestRender();
  }

  function groupByCat(items) {
    // Returns [[catLabel, [items...]], ...]  preserving insertion order
    const map = new Map();
    items.forEach(p => {
      if (!map.has(p.cat)) map.set(p.cat, []);
      map.get(p.cat).push(p);
    });
    return [...map.entries()];
  }

  // ── MY TATTOOS: filtering + card grid ─────────────────────────────────

  function applyFilters() {
    let filtered = logEntries;

    const search = currentFilter.search.toLowerCase().trim();
    if (search) {
      filtered = filtered.filter(e =>
        (e.name         || '').toLowerCase().includes(search) ||
        (e.artist_name  || '').toLowerCase().includes(search) ||
        (e.studio_name  || '').toLowerCase().includes(search) ||
        (e.style        || '').toLowerCase().includes(search)
      );
    }
    if (currentFilter.status)
      filtered = filtered.filter(e => e.status === currentFilter.status);
    if (currentFilter.placement)
      filtered = filtered.filter(e => e.placement === currentFilter.placement);
    if (currentFilter.type)
      filtered = filtered.filter(e => e.type === currentFilter.type);
    if (bodyMapFilter)
      filtered = filtered.filter(e => e.placement === bodyMapFilter);

    elTlogCount.textContent = `${filtered.length} of ${logEntries.length}`;
    renderCardGrid(filtered);
  }

  function renderCardGrid(entries) {
    // Remove existing cards (keep #tlog-empty)
    Array.from(elTlogGrid.children).forEach(c => {
      if (c.id !== 'tlog-empty') c.remove();
    });
    const emptyEl = document.getElementById('tlog-empty');

    if (!entries.length) {
      emptyEl.style.display = '';
      emptyEl.textContent = logEntries.length
        ? 'No tattoos match the current filter.'
        : 'No tattoos yet. Click "+ New tattoo" to add your first entry.';
      return;
    }
    emptyEl.style.display = 'none';

    entries.forEach(entry => {
      const card = document.createElement('div');
      card.className = 'tlog-card';

      // Photo area
      const photoDiv = document.createElement('div');
      photoDiv.className = 'tlog-card-photo';
      const icon = document.createElement('span');
      icon.className = 'tlog-card-photo-placeholder';
      icon.textContent = entry.type === 'encoded' ? '🔐' : '🎨';
      photoDiv.appendChild(icon);
      if (entry.photos && entry.photos.length > 0) {
        const cnt = document.createElement('span');
        cnt.className = 'tlog-card-photo-count';
        cnt.textContent = `${entry.photos.length} photo${entry.photos.length !== 1 ? 's' : ''}`;
        photoDiv.appendChild(cnt);
      }
      card.appendChild(photoDiv);

      // Body
      const body = document.createElement('div');
      body.className = 'tlog-card-body';

      const nameEl = document.createElement('div');
      nameEl.className = 'tlog-card-name';
      nameEl.textContent = entry.name || '(untitled)';
      body.appendChild(nameEl);

      const pl = placements.find(p => p.key === entry.placement);
      const meta = document.createElement('div');
      meta.className = 'tlog-card-meta';
      const parts = [pl ? '📍 ' + pl.label : null, entry.artist_name || null].filter(Boolean);
      meta.textContent = parts.join(' · ') || '—';
      body.appendChild(meta);

      const badges = document.createElement('div');
      badges.className = 'tlog-card-badges';
      badges.innerHTML =
        `<span class="status-badge status-${entry.status}">${statusLabel(entry.status)}</span>` +
        `<span class="type-badge type-${entry.type}">${entry.type === 'encoded' ? '🔐 Encoded' : 'Art'}</span>`;
      body.appendChild(badges);
      card.appendChild(body);

      // Footer
      const footer = document.createElement('div');
      footer.className = 'tlog-card-footer';

      const editBtn = document.createElement('button');
      editBtn.className = 'btn ghost'; editBtn.textContent = 'Edit';
      editBtn.addEventListener('click', () => openEditor(entry));
      footer.appendChild(editBtn);

      if (entry.type === 'encoded' && entry.key_record_id) {
        const studioBtn = document.createElement('button');
        studioBtn.className = 'btn'; studioBtn.textContent = '⚡ Studio';
        studioBtn.title = 'Open in Layout Studio';
        studioBtn.addEventListener('click', () => openEntryInStudio(entry));
        footer.appendChild(studioBtn);
      }
      card.appendChild(footer);

      elTlogGrid.appendChild(card);
    });
  }

  function statusLabel(s) {
    const map = {
      planned: 'Planned', design: 'Design', scheduled: 'Scheduled',
      fresh: 'Fresh', healing: 'Healing', healed: 'Healed',
      touchup_needed: 'Touchup needed', retired: 'Retired',
    };
    return map[s] || s;
  }

  // ── ENTRY EDITOR ───────────────────────────────────────────────────────

  function openEditor(entry) {
    editingId     = entry ? entry.id : null;
    editInkColors = entry ? [...(entry.ink_colors || [])] : [];

    elEditorTitle.textContent = entry ? 'Edit tattoo' : 'New tattoo';
    elEdName.value           = entry ? (entry.name || '') : '';
    // Type radio
    const typeVal = entry ? (entry.type || 'art') : 'art';
    document.querySelectorAll('input[name="tled-type"]').forEach(r => {
      r.checked = (r.value === typeVal);
    });
    elEdPlacement.value      = entry ? (entry.placement || '') : '';
    elEdPlacementNotes.value = entry ? (entry.placement_notes || '') : '';
    elEdArtist.value         = entry ? (entry.artist_name || '') : '';
    elEdStudio.value         = entry ? (entry.studio_name || '') : '';
    elEdStyle.value          = entry ? (entry.style || '') : '';
    elEdStatus.value         = entry ? (entry.status || 'planned') : 'planned';
    elEdDate.value           = entry ? (entry.date_done || '') : '';
    elEdSize.value           = entry && entry.size_cm  != null ? entry.size_cm  : '';
    elEdPrice.value          = entry && entry.price    != null ? entry.price    : '';
    elEdCurrency.value       = entry ? (entry.currency || 'USD') : 'USD';
    elEdNotes.value          = entry ? (entry.notes || '') : '';

    elEdDelete.style.display = entry ? '' : 'none';

    renderInkTags();
    renderPhotos(entry ? (entry.photos || []) : []);
    syncTypeSection();
    populateEditorKeyRecordSection(entry);

    elEditor.classList.remove('hidden');
    requestAnimationFrame(() => elEditor.classList.add('open'));
    elEdName.focus();
  }

  function closeEditor() {
    elEditor.classList.remove('open');
    setTimeout(() => elEditor.classList.add('hidden'), 260);
    editingId = null;
  }

  function syncTypeSection() {
    const type = document.querySelector('input[name="tled-type"]:checked')?.value || 'art';
    elEdEncodedSection.classList.toggle('hidden', type !== 'encoded');
  }

  function populateEditorKeyRecordSection(entry) {
    if (entry && entry.key_record_id) {
      elEdRecordLinked.classList.remove('hidden');
      elEdRecordUnlinked.classList.add('hidden');
      const kr = keyRecords.find(k => k.id === entry.key_record_id);
      elEdRecordLabel.textContent = kr
        ? (kr.label || `Record ${entry.key_record_id}`)
        : entry.key_record_id;
    } else {
      elEdRecordLinked.classList.add('hidden');
      elEdRecordUnlinked.classList.remove('hidden');
      elEdRecordPicker.innerHTML = keyRecords.length
        ? keyRecords.map(k =>
            `<option value="${k.id}">${escapeHtml(k.label || k.id)}</option>`
          ).join('')
        : '<option value="">(no key records)</option>';
    }
  }

  // Ink colors
  function renderInkTags() {
    elEdColorsWrap.innerHTML = '';
    editInkColors.forEach((color, idx) => {
      const tag  = document.createElement('span');
      tag.className = 'ink-tag chip';
      tag.textContent = color + ' ';

      const btn = document.createElement('button');
      btn.type = 'button'; btn.className = 'ink-tag-remove'; btn.textContent = '×';
      btn.addEventListener('click', () => {
        editInkColors.splice(idx, 1);
        renderInkTags();
      });
      tag.appendChild(btn);
      elEdColorsWrap.appendChild(tag);
    });
  }

  function onAddInkColor() {
    const val = elEdColorInput.value.trim();
    if (!val) return;
    if (!editInkColors.includes(val)) editInkColors.push(val);
    elEdColorInput.value = '';
    renderInkTags();
  }

  // Photos
  function renderPhotos(photos) {
    Array.from(elEdPhotosWrap.children).forEach(c => {
      if (c.id !== 'tled-photos-empty') c.remove();
    });
    elEdPhotosEmpty.style.display = photos.length ? 'none' : '';

    photos.forEach((rel, idx) => {
      const wrap = document.createElement('div');
      wrap.className = 'tlog-photo-thumb';

      const name = document.createElement('span');
      name.className = 'tlog-photo-thumb-name';
      name.textContent = rel.split(/[\\/]/).pop();
      wrap.appendChild(name);

      const removeBtn = document.createElement('button');
      removeBtn.className = 'remove-photo-btn'; removeBtn.textContent = '×';
      removeBtn.title = 'Remove photo';
      removeBtn.addEventListener('click', () => onRemovePhoto(idx));
      wrap.appendChild(removeBtn);

      elEdPhotosWrap.insertBefore(wrap, elEdPhotosEmpty);
    });
  }

  async function onAddPhoto() {
    if (!editingId) {
      App.toast('Save the entry first, then add photos', 'info');
      return;
    }
    const dlg = await App.api('open_file_dialog', 'open');
    if (!dlg.ok || !dlg.path) return;
    const r = await App.api('tattoo_log_add_photo', editingId, dlg.path);
    if (r.ok) {
      App.toast('Photo added', 'success');
      renderPhotos(r.entry.photos || []);
      await loadLog();
    } else {
      App.toast('Failed to add photo: ' + r.error, 'error');
    }
  }

  async function onRemovePhoto(idx) {
    if (!editingId) return;
    const ok = await App.confirm('Remove photo?', 'This permanently deletes the photo file from disk.');
    if (!ok) return;
    const r = await App.api('tattoo_log_remove_photo', editingId, idx);
    if (r.ok) {
      App.toast('Photo removed', 'success');
      renderPhotos(r.entry.photos || []);
      await loadLog();
    } else {
      App.toast('Failed to remove photo: ' + r.error, 'error');
    }
  }

  // Save
  async function saveEditor() {
    const type = document.querySelector('input[name="tled-type"]:checked')?.value || 'art';
    const params = {
      name:            elEdName.value.trim(),
      type,
      placement:       elEdPlacement.value,
      placement_notes: elEdPlacementNotes.value.trim(),
      artist_name:     elEdArtist.value.trim(),
      studio_name:     elEdStudio.value.trim(),
      style:           elEdStyle.value.trim(),
      status:          elEdStatus.value,
      date_done:       elEdDate.value || null,
      size_cm:         elEdSize.value  !== '' ? parseFloat(elEdSize.value)  : null,
      price:           elEdPrice.value !== '' ? parseFloat(elEdPrice.value) : null,
      currency:        elEdCurrency.value.trim() || 'USD',
      notes:           elEdNotes.value.trim(),
      ink_colors:      [...editInkColors],
    };

    let r;
    if (editingId) {
      r = await App.api('tattoo_log_update', editingId, params);
    } else {
      r = await App.api('tattoo_log_create', params);
      if (r.ok) editingId = r.entry.id;  // now we have an ID for photos
    }
    if (!r.ok) { App.toast('Save failed: ' + r.error, 'error'); return; }
    App.toast('Saved', 'success');
    closeEditor();
    await loadLog();
  }

  // Delete
  async function onDeleteEntry() {
    if (!editingId) return;
    const entry = logEntries.find(e => e.id === editingId);
    const hasLink = entry && entry.key_record_id;
    const name = entry ? (entry.name || 'this tattoo') : 'this entry';
    const msg = hasLink
      ? `Delete "${name}"?\n\nYour encoded key record (${entry.key_record_id}) will NOT be deleted — only the tattoo log entry and its sidecar photos.`
      : `Delete "${name}"? This cannot be undone.`;
    const ok = await App.confirm('Delete tattoo entry?', msg);
    if (!ok) return;

    const r = await App.api('tattoo_log_delete', editingId);
    if (!r.ok) { App.toast('Delete failed: ' + r.error, 'error'); return; }

    if (r.key_record_unlinked) {
      App.toast(`Entry deleted. Key record "${r.key_record_id}" is still safe in your vault.`, 'info', 6000);
    } else {
      App.toast('Entry deleted', 'success');
    }
    closeEditor();
    await loadLog();
  }

  // Key record linking
  async function onLinkRecord() {
    if (!editingId) { App.toast('Save the entry first, then link a record', 'info'); return; }
    const krId = elEdRecordPicker.value;
    if (!krId) { App.toast('Select a key record to link', 'error'); return; }
    const r = await App.api('tattoo_log_link_record', editingId, krId);
    if (!r.ok) { App.toast('Link failed: ' + r.error, 'error'); return; }
    App.toast('Linked to key record', 'success');
    document.querySelectorAll('input[name="tled-type"]').forEach(rb => {
      rb.checked = (rb.value === 'encoded');
    });
    syncTypeSection();
    populateEditorKeyRecordSection(r.entry);
    await loadLog();
  }

  async function onUnlinkRecord() {
    if (!editingId) return;
    const ok = await App.confirm(
      'Unlink key record?',
      'The key record will NOT be deleted. The tattoo entry type will become "Art".'
    );
    if (!ok) return;
    const r = await App.api('tattoo_log_unlink_record', editingId);
    if (!r.ok) { App.toast('Unlink failed: ' + r.error, 'error'); return; }
    App.toast('Unlinked from key record', 'success');
    document.querySelectorAll('input[name="tled-type"]').forEach(rb => {
      rb.checked = (rb.value === 'art');
    });
    syncTypeSection();
    populateEditorKeyRecordSection(r.entry);
    await loadLog();
  }

  function openEntryInStudio(entry) {
    // Switch to Layout Studio sub-tab
    switchSubTab('studio');
    // Set source radio to logentry
    const radio = document.querySelector('input[name="tattoo-source"][value="logentry"]');
    if (radio) { radio.checked = true; radio.dispatchEvent(new Event('change')); }
    if (elLogEntryPicker) {
      elLogEntryPicker.value = entry.id;
    }
    // Restore saved layout params
    if (entry.layout && catalog.find(l => l.key === entry.layout)) {
      currentLayoutKey = entry.layout;
      currentParams    = Object.assign({}, entry.layout_params || {});
      renderChips();
      renderParamsForm();
    }
    requestRender();
  }

  function onOpenInLayoutStudio() {
    const entry = logEntries.find(e => e.id === editingId);
    if (entry) { openEntryInStudio(entry); closeEditor(); }
  }

  // ── BODY MAP ───────────────────────────────────────────────────────────

  function refreshBodyMap() {
    // Clear old zone state from all SVG zones (both front and back)
    document.querySelectorAll('.bz').forEach(el => {
      el.classList.remove('has-tattoo', 'multi-tattoo');
    });

    // Count tattoos per placement
    const counts = {};
    logEntries.forEach(e => {
      if (e.placement) counts[e.placement] = (counts[e.placement] || 0) + 1;
    });

    // Apply classes to SVG zones (querySelectorAll covers both front and back SVGs)
    Object.entries(counts).forEach(([key, n]) => {
      document.querySelectorAll(`.bz[id="${key}"]`).forEach(el => {
        el.classList.add('has-tattoo');
        if (n > 1) el.classList.add('multi-tattoo');
      });
    });

    // Rebuild the zone list sidebar
    buildZoneList(counts);
  }

  function buildZoneList(counts) {
    elBmapZoneList.innerHTML = '';
    const cats = groupByCat(placements);

    cats.forEach(([cat, ps]) => {
      const catLi = document.createElement('li');
      catLi.className = 'bmap-zone-cat';
      catLi.textContent = cat;
      elBmapZoneList.appendChild(catLi);

      ps.forEach(p => {
        const li = document.createElement('li');
        li.className = 'bmap-zone-row' + (counts[p.key] ? ' has-tattoo' : '');
        li.dataset.zone = p.key;
        if (bodyMapFilter === p.key) li.classList.add('active');
        li.innerHTML =
          `<span class="bmap-zone-label">${escapeHtml(p.label)}</span>` +
          `<span class="bmap-zone-count">${counts[p.key] || ''}</span>`;
        li.addEventListener('click',      () => onZoneClick(p.key));
        li.addEventListener('mouseenter', () => onZoneHover(p.key, true));
        li.addEventListener('mouseleave', () => onZoneHover(p.key, false));
        elBmapZoneList.appendChild(li);
      });
    });
  }

  function onZoneClick(key) {
    if (bodyMapFilter === key) {
      // Second click = clear filter
      bodyMapFilter = null;
      clearZoneSelections();
    } else {
      bodyMapFilter = key;
      clearZoneSelections();
      document.querySelectorAll(`.bz[id="${key}"]`).forEach(el => el.classList.add('active'));
      const listEl = elBmapZoneList.querySelector(`[data-zone="${key}"]`);
      if (listEl) listEl.classList.add('active');
    }
    // Switch to My Tattoos and re-filter
    switchSubTab('log');
    applyFilters();
  }

  function onZoneHover(key, entering) {
    // Use querySelectorAll to cover both front and back SVGs (both share ids on some zones)
    document.querySelectorAll(`.bz[id="${key}"]`).forEach(el =>
      el.classList.toggle('hovered', entering)
    );
    const listEl = elBmapZoneList ? elBmapZoneList.querySelector(`[data-zone="${key}"]`) : null;
    if (listEl) {
      listEl.classList.toggle('hovered', entering);
      if (entering) listEl.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }

  function clearZoneSelections() {
    document.querySelectorAll('.bz.active').forEach(el => el.classList.remove('active'));
    if (elBmapZoneList) {
      elBmapZoneList.querySelectorAll('.bmap-zone-row.active').forEach(el => el.classList.remove('active'));
    }
  }

  // ── LAYOUT STUDIO: source + record helpers ─────────────────────────────

  function maybeRestoreLayoutFromRecord(rec) {
    if (!rec || !rec.tattoo_layout) return;
    if (catalog.find(l => l.key === rec.tattoo_layout)) {
      currentLayoutKey = rec.tattoo_layout;
      currentParams    = Object.assign({}, rec.tattoo_layout_params || {});
      renderChips();
      renderParamsForm();
    }
  }

  function onSourceChange() {
    const mode = document.querySelector('input[name="tattoo-source"]:checked').value;
    elLogEntryPicker.classList.toggle('hidden', mode !== 'logentry');
    elRecordPicker.classList.toggle('hidden',   mode !== 'record');
    elPasteInput.classList.toggle('hidden',     mode !== 'paste');

    if (mode === 'record') {
      refreshImageManager();
    } else {
      // Image manager only works with key-record mode
      elImgEmpty.textContent = mode === 'logentry'
        ? 'Switch to "From key record" mode to manage reference images.'
        : 'Reference images attach to key records. Pick a record above.';
      elImgEmpty.hidden = false;
      elImgThumb.hidden = true; elImgThumb.removeAttribute('src');
      elImgImport.disabled = true;
      elImgRemove.disabled = true;
      elImgRecognize.disabled = true;
      elImgInfo.textContent = '';
    }
    requestRender();
  }

  function currentStudioRecord() {
    const mode = document.querySelector('input[name="tattoo-source"]:checked')?.value;
    if (mode !== 'record') return null;
    const id = elRecordPicker.value;
    return id ? keyRecords.find(r => r.id === id) : null;
  }

  function getEncodedString() {
    const mode = document.querySelector('input[name="tattoo-source"]:checked')?.value;
    if (mode === 'paste') return elPasteInput.value.trim();
    if (mode === 'logentry') {
      const entryId = elLogEntryPicker.value;
      const entry = logEntries.find(e => e.id === entryId);
      if (!entry || !entry.key_record_id) return '';
      const rec = keyRecords.find(r => r.id === entry.key_record_id);
      return rec ? (rec.encoded_string || '') : '';
    }
    // 'record'
    const id = elRecordPicker.value;
    if (!id) return '';
    const rec = keyRecords.find(r => r.id === id);
    return rec ? (rec.encoded_string || '') : '';
  }

  // ── LAYOUT STUDIO: chips + params ──────────────────────────────────────

  function renderChips() {
    elChipRow.innerHTML = '';
    if (!currentLayoutKey && catalog.length) currentLayoutKey = catalog[0].key;
    catalog.forEach(layout => {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'chip' + (layout.key === currentLayoutKey ? ' active' : '');
      chip.textContent = layout.label;
      chip.dataset.key = layout.key;
      chip.addEventListener('click', () => selectLayout(layout.key));
      elChipRow.appendChild(chip);
    });
    renderParamsForm();
  }

  function selectLayout(key) {
    currentLayoutKey = key;
    const layout = catalog.find(l => l.key === key);
    currentParams = Object.assign({}, layout.defaults);
    renderChips();
    renderParamsForm();
    requestRender();
  }

  function renderParamsForm() {
    if (!currentLayoutKey) {
      elParamsForm.innerHTML = '<div class="muted small">Pick a layout to see its parameters.</div>';
      return;
    }
    const layout = catalog.find(l => l.key === currentLayoutKey);
    const schema = layout.param_schema;
    elParamsForm.innerHTML = '';
    Object.entries(schema).forEach(([paramKey, spec]) => {
      const row = document.createElement('div');
      row.className = 'param-row';
      const label = document.createElement('label');
      label.textContent = spec.label || paramKey;
      label.setAttribute('for', 'tattoo-param-' + paramKey);
      row.appendChild(label);

      const inputId = 'tattoo-param-' + paramKey;
      const value   = currentParams[paramKey];

      if (spec.type === 'bool') {
        const input = document.createElement('input');
        input.type = 'checkbox'; input.id = inputId; input.checked = !!value;
        input.addEventListener('change', () => {
          currentParams[paramKey] = input.checked; requestRender();
        });
        row.appendChild(input);
      } else if (spec.type === 'enum') {
        const select = document.createElement('select');
        select.id = inputId;
        spec.values.forEach(v => {
          const opt = document.createElement('option');
          opt.value = v; opt.textContent = v;
          if (v === value) opt.selected = true;
          select.appendChild(opt);
        });
        select.addEventListener('change', () => {
          currentParams[paramKey] = select.value; requestRender();
        });
        row.appendChild(select);
      } else {
        const input = document.createElement('input');
        input.type = 'number'; input.id = inputId;
        if (spec.min  !== undefined) input.min  = spec.min;
        if (spec.max  !== undefined) input.max  = spec.max;
        if (spec.step !== undefined) input.step = spec.step;
        input.value = value;
        input.addEventListener('input', () => {
          const v = spec.type === 'int' ? parseInt(input.value, 10) : parseFloat(input.value);
          if (!isNaN(v)) { currentParams[paramKey] = v; requestRender(); }
        });
        row.appendChild(input);
      }
      elParamsForm.appendChild(row);
    });
  }

  // ── LAYOUT STUDIO: render + export ─────────────────────────────────────

  function requestRender() {
    if (renderDebounceTimer) clearTimeout(renderDebounceTimer);
    renderDebounceTimer = setTimeout(doRender, 150);
  }

  async function doRender() {
    const encoded = getEncodedString();
    if (!encoded) { clearCanvas(); elStats.textContent = '0 chars'; return; }
    if (!currentLayoutKey) return;

    const r = await App.api('tattoo_render_preview', {
      encoded_string: encoded,
      layout: currentLayoutKey,
      layout_params: currentParams,
    });
    if (!r.ok) { App.toast('Render failed: ' + r.error, 'error', 4000); return; }
    drawGlyphs(r.glyphs, r.bbox);
    elStats.textContent = `${r.glyphs.length} chars`;
    elCopyText.disabled = !r.text_exportable;
    elCopyText.title = r.text_exportable
      ? 'Copy as plain text'
      : `${currentLayoutKey} is a path layout — text export not meaningful`;
  }

  function clearCanvas() {
    const ctx = elCanvas.getContext('2d');
    ctx.clearRect(0, 0, elCanvas.width, elCanvas.height);
  }

  function drawGlyphs(glyphs, bbox) {
    const fontSize = parseInt(elFontSize.value, 10) || 20;
    const ctx = elCanvas.getContext('2d');
    const [x0, y0, x1, y1] = bbox;
    const wEm = Math.max(x1 - x0, 0.1);
    const hEm = Math.max(y1 - y0, 0.1);
    const wPx = elCanvas.width, hPx = elCanvas.height;
    const scale = Math.min(wPx * 0.85 / (wEm * fontSize), hPx * 0.85 / (hEm * fontSize)) * fontSize;
    const drawnFont = Math.min(fontSize, Math.max(8, scale));

    ctx.clearRect(0, 0, wPx, hPx);
    ctx.fillStyle    = '#0f172a';
    ctx.textAlign    = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = `${drawnFont}px 'Sovereign Mono', 'DejaVu Sans Mono', 'Consolas', monospace`;

    const offX = wPx / 2 - (wEm * drawnFont) / 2 - x0 * drawnFont;
    const offY = hPx / 2 - (hEm * drawnFont) / 2 - y0 * drawnFont;

    for (const [char, x, y, rot] of glyphs) {
      const px = x * drawnFont + offX;
      const py = y * drawnFont + offY;
      if (Math.abs(rot) < 0.01) {
        ctx.fillText(char, px, py);
      } else {
        ctx.save(); ctx.translate(px, py); ctx.rotate(rot * Math.PI / 180);
        ctx.fillText(char, 0, 0); ctx.restore();
      }
    }
  }

  async function onCopyText() {
    const encoded = getEncodedString();
    if (!encoded || !currentLayoutKey) return;
    const dlg = await App.api('open_file_dialog', 'save', `sv_tattoo_${currentLayoutKey}.txt`);
    if (!dlg.ok || !dlg.path) return;
    const r = await App.api('tattoo_export', {
      encoded_string: encoded, layout: currentLayoutKey,
      layout_params: currentParams, format: 'txt', out_path: dlg.path,
    });
    if (r.ok) App.toast(`Wrote ${r.byte_count} bytes`, 'success');
    else App.toast('Export failed: ' + r.error, 'error');
  }

  async function onSaveSvg() {
    const encoded = getEncodedString();
    if (!encoded || !currentLayoutKey) { App.toast('Pick a source string first', 'error'); return; }
    const dlg = await App.api('open_file_dialog', 'save', `sv_tattoo_${currentLayoutKey}.svg`);
    if (!dlg.ok || !dlg.path) return;
    const r = await App.api('tattoo_export', {
      encoded_string: encoded, layout: currentLayoutKey,
      layout_params: currentParams, format: 'svg', out_path: dlg.path,
      font_size_px: parseInt(elFontSize.value, 10) || 20,
    });
    if (r.ok) App.toast(`Saved SVG (${r.byte_count} bytes)`, 'success');
    else App.toast('SVG save failed: ' + r.error, 'error');
  }

  async function onSavePng() {
    const encoded = getEncodedString();
    if (!encoded || !currentLayoutKey) { App.toast('Pick a source string first', 'error'); return; }
    const dlg = await App.api('open_file_dialog', 'save', `sv_tattoo_${currentLayoutKey}.png`);
    if (!dlg.ok || !dlg.path) return;
    const r = await App.api('tattoo_export', {
      encoded_string: encoded, layout: currentLayoutKey,
      layout_params: currentParams, format: 'png', out_path: dlg.path,
      font_size_px: parseInt(elFontSize.value, 10) || 20,
    });
    if (r.ok) App.toast(`Saved PNG (${r.byte_count} bytes)`, 'success');
    else App.toast('PNG save failed: ' + r.error, 'error');
  }

  // ── LAYOUT STUDIO: image manager ───────────────────────────────────────

  function refreshImageManager() {
    const rec = currentStudioRecord();
    if (!rec) {
      elImgEmpty.textContent = 'Reference images attach to key records. Pick a record above.';
      elImgEmpty.hidden = false; elImgThumb.hidden = true;
      elImgThumb.removeAttribute('src');
      elImgImport.disabled = true; elImgRemove.disabled = true;
      elImgRecognize.disabled = true; elImgInfo.textContent = '';
      return;
    }
    elImgImport.disabled = false;
    if (rec.tattoo_image_abs) {
      const url = 'file:///' + rec.tattoo_image_abs.replace(/\\/g, '/');
      elImgThumb.src = url + '?t=' + Date.now();
      elImgThumb.hidden = false; elImgEmpty.hidden = true;
      elImgRemove.disabled = false; elImgRecognize.disabled = false;
      elImgInfo.textContent = rec.tattoo_image_imported || '';
    } else {
      elImgEmpty.textContent = 'No reference image attached. Import a photo, stencil mockup, or any picture.';
      elImgEmpty.hidden = false; elImgThumb.hidden = true;
      elImgThumb.removeAttribute('src');
      elImgRemove.disabled = true; elImgRecognize.disabled = true;
      elImgInfo.textContent = '';
    }
  }

  async function onImportImage() {
    const rec = currentStudioRecord();
    if (!rec) { App.toast('Pick a record first', 'error'); return; }
    const dlg = await App.api('open_file_dialog', 'open');
    if (!dlg.ok || !dlg.path) return;
    const r = await App.api('tattoo_image_import', rec.id, dlg.path);
    if (r.ok) {
      App.toast('Reference image imported', 'success');
      await loadKeyRecords();
      refreshImageManager();
    } else {
      App.toast('Import failed: ' + r.error, 'error');
    }
  }

  async function onRemoveImage() {
    const rec = currentStudioRecord();
    if (!rec) return;
    const ok = await App.confirm(
      'Remove reference image?',
      'Deletes the file from the vault folder. The key record is preserved.'
    );
    if (!ok) return;
    const r = await App.api('tattoo_image_remove', rec.id);
    if (r.ok) {
      App.toast('Reference image removed', 'success');
      await loadKeyRecords();
      refreshImageManager();
    } else {
      App.toast('Remove failed: ' + r.error, 'error');
    }
  }

  // ── LAYOUT STUDIO: OCR ─────────────────────────────────────────────────

  function populateOcrAdapterSelect() {
    elOcrAdapter.innerHTML = '';
    const preferred = adapters.find(a => a.name === 'tesseract' && a.available)
                   || adapters.find(a => a.available);
    adapters.forEach(a => {
      const opt = document.createElement('option');
      opt.value = a.name;
      opt.textContent = a.label + (a.available ? '' : ' (unavailable)');
      opt.disabled = !a.available && a.name !== 'manual';
      if (preferred && a.name === preferred.name) opt.selected = true;
      elOcrAdapter.appendChild(opt);
    });
    updateOcrAdapterReason();
  }

  function updateOcrAdapterReason() {
    const a = adapters.find(x => x.name === elOcrAdapter.value);
    elOcrReason.textContent = (a && !a.available) ? a.reason : '';
  }

  async function onRecognizeImage() {
    const rec = currentStudioRecord();
    if (!rec || !rec.tattoo_image_abs) { App.toast('Import a reference image first', 'error'); return; }
    elOcrReview.classList.remove('hidden'); elOcrReview.open = true;
    elOcrText.value = 'Recognizing…'; elOcrText.disabled = true;
    const r = await App.api('tattoo_image_recognize', {
      image_path: rec.tattoo_image_abs,
      alphabet_id: rec.alphabet_id,
      adapter: elOcrAdapter.value || 'manual',
    });
    elOcrText.disabled = false;
    if (!r.ok) {
      elOcrText.value = ''; App.toast('Recognize failed: ' + r.error, 'error', 5000);
      elOcrText.focus(); return;
    }
    elOcrText.value = r.text || '';
    const ra = await App.api('tattoo_adapters_list');
    if (ra.ok) adapters = ra.adapters;
    elOcrText.focus(); elOcrText.select();
  }

  function onUseOcrText() {
    const text = elOcrText.value.trim();
    if (!text) { App.toast('Editor is empty', 'error'); return; }
    App.switchTab('decode');
    const el = document.getElementById('decode-paste');
    let injected = false;
    if (el) {
      el.value = text;
      el.dispatchEvent(new Event('input', { bubbles: true }));
      const useBtn = document.getElementById('decode-paste-use');
      if (useBtn) { useBtn.click(); injected = true; }
    }
    if (!injected) {
      App.api('copy_to_clipboard', text).then(r => {
        if (r.ok) App.toast('Decode tab not found — text copied to clipboard', 'success', 4000);
      });
    } else {
      App.toast('Routed to Decode tab', 'success');
    }
    discardOcrReview();
  }

  function discardOcrReview() {
    elOcrText.value = '';
    elOcrReview.classList.add('hidden');
    elOcrReview.open = false;
  }

  async function onSaveLayoutToRecord() {
    const mode = document.querySelector('input[name="tattoo-source"]:checked').value;
    if (mode !== 'record') { App.toast('Switch to "From key record" mode first', 'error'); return; }
    const id = elRecordPicker.value;
    if (!id || !currentLayoutKey) return;
    const r = await App.api('tattoo_save_layout_to_record', id, currentLayoutKey, currentParams);
    if (r.ok) {
      App.toast(`Layout saved to "${r.record.label || id}"`, 'success');
      await loadKeyRecords();
    } else {
      App.toast('Save failed: ' + r.error, 'error');
    }
  }

  // ── UTILITIES ──────────────────────────────────────────────────────────

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
    );
  }

  return { init, onShow };
})();

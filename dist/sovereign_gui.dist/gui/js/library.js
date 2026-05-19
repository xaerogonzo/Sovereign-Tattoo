// ===========================================================
// library.js - Library tab + alphabet management
// ===========================================================

Tabs.library = (() => {

  async function init() {
    document.getElementById('lib-refresh').addEventListener('click', () => refresh());
    document.getElementById('lib-open-editor').addEventListener('click', () => App.switchTab('editor'));
    document.getElementById('lib-import').addEventListener('click', importSvlib);
    await refresh();
  }

  async function onShow() {
    // Refresh on each show to pick up changes from the editor tab
    await refresh();
  }

  async function refresh() {
    const alphabets = await App.getAlphabets(true);
    const tbody = document.querySelector('#lib-table tbody');
    tbody.innerHTML = '';
    alphabets.forEach(a => {
      const tr = document.createElement('tr');
      const builtinBadge = a.builtin
        ? '<span class="badge builtin">builtin</span>'
        : '<span class="badge custom">custom</span>';
      tr.innerHTML = `
        <td class="mono">${a.id}</td>
        <td>${escapeHtml(a.name)}</td>
        <td>${a.base}</td>
        <td class="mono">${a.fingerprint}</td>
        <td>${a.engine}</td>
        <td>${builtinBadge}</td>
        <td><div class="row-actions">
          <button class="btn ghost small" data-action="keycard" data-id="${a.id}">Key card</button>
          ${a.builtin ? '' : `<button class="btn ghost small" data-action="delete" data-id="${a.id}">Delete</button>`}
        </div></td>
      `;
      tbody.appendChild(tr);
    });
    tbody.addEventListener('click', onRowAction);
  }

  async function onRowAction(e) {
    const btn = e.target.closest('button[data-action]');
    if (!btn) return;
    const id = btn.dataset.id;
    const action = btn.dataset.action;
    if (action === 'delete') {
      const ok = await App.confirm('Delete alphabet?', `Remove "${id}" from the library? Encoded files using it will become un-decodable without the key card.`);
      if (!ok) return;
      const r = await App.api('delete_alphabet', id);
      if (r.ok) { App.toast('Deleted', 'success'); App.invalidateAlphabets(); await refresh(); }
      else App.toast('Delete failed: ' + r.error, 'error');
    } else if (action === 'keycard') {
      const settings = await App.getSettings();
      const dlg = await App.api('open_file_dialog', 'save', `${id}.keycard.txt`);
      if (!dlg.ok || !dlg.path) return;
      const r = await App.api('key_card', id, dlg.path);
      if (r.ok) App.toast('Key card saved: ' + r.keycard_path, 'success');
      else App.toast('Key card failed: ' + r.error, 'error');
    }
  }

  async function importSvlib() {
    const dlg = await App.api('open_file_dialog', 'open');
    if (!dlg.ok || !dlg.path) return;
    const r = await App.api('import_svlib', dlg.path);
    if (r.ok) {
      App.toast(`Imported "${r.alphabet.name}"`, 'success');
      App.invalidateAlphabets();
      await refresh();
    } else {
      App.toast('Import failed: ' + r.error, 'error');
    }
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  return { init, onShow, refresh };
})();

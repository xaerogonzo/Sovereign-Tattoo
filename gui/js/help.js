// ===========================================================
// help.js - Help tab — opens documentation files externally
// ===========================================================

Tabs.help = (() => {

  async function init() {
    document.getElementById('help-open-readme').addEventListener('click', openReadme);
    document.getElementById('help-open-architecture').addEventListener('click', openArchitecture);
    document.getElementById('help-open-docs-folder').addEventListener('click', openDocsFolder);
  }

  function onShow() {}

  async function openReadme() {
    const root = await App.api('project_root');
    if (!root.ok) { App.toast('Cannot resolve project root', 'error'); return; }
    const path = root.path + '/docs/README.md';
    const r = await App.api('open_path', path);
    if (!r.ok) App.toast('Cannot open README: ' + r.error, 'error');
  }

  async function openArchitecture() {
    const root = await App.api('project_root');
    if (!root.ok) { App.toast('Cannot resolve project root', 'error'); return; }
    const path = root.path + '/docs/ARCHITECTURE.md';
    const r = await App.api('open_path', path);
    if (!r.ok) App.toast('Cannot open architecture doc: ' + r.error, 'error');
  }

  async function openDocsFolder() {
    const root = await App.api('project_root');
    if (!root.ok) return;
    await App.api('open_folder', root.path + '/docs');
  }

  return { init, onShow };
})();

/* Shared category tabs: switches visibility without rebuilding form fields. */
(() => {
  const selections = new Map();
  function controls(group) { return [...group.querySelectorAll('[data-eco-tab]')].filter(tab => tab.closest('[data-eco-tabs]') === group); }
  function activate(group, id, focus = false) {
    const tabs = controls(group);
    if (!tabs.some(tab => tab.dataset.ecoTab === id)) id = tabs[0]?.dataset.ecoTab;
    for (const tab of tabs) {
      const active = tab.dataset.ecoTab === id;
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
      const panel = document.getElementById(tab.dataset.ecoTab);
      if (panel && panel.closest('[data-eco-tabs]') === group) panel.hidden = !active;
      if (active && focus) tab.focus();
    }
    if (id) selections.set(group.dataset.ecoTabs, id);
  }
  function initialize(group) {
    if (group.dataset.ecoReady) return;
    group.dataset.ecoReady = 'true';
    activate(group, selections.get(group.dataset.ecoTabs));
  }
  function scan(root) {
    if (root.nodeType !== 1 && root !== document) return;
    if (root.matches?.('[data-eco-tabs]')) initialize(root);
    root.querySelectorAll('[data-eco-tabs]').forEach(initialize);
  }
  document.addEventListener('click', event => {
    const tab = event.target.closest?.('[data-eco-tab]');
    if (tab) activate(tab.closest('[data-eco-tabs]'), tab.dataset.ecoTab);
  });
  document.addEventListener('keydown', event => {
    const tab = event.target.closest?.('[data-eco-tab]');
    if (!tab || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    const group = tab.closest('[data-eco-tabs]'), tabs = controls(group), index = tabs.indexOf(tab);
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
    event.preventDefault(); event.stopPropagation();
    activate(group, tabs[next].dataset.ecoTab, true);
  }, true);
  document.addEventListener('invalid', event => {
    const panel = event.target.closest?.('.eco-tab-panel');
    if (panel) activate(panel.closest('[data-eco-tabs]'), panel.id);
  }, true);
  function start() {
    scan(document);
    new MutationObserver(records => records.forEach(record => record.addedNodes.forEach(scan))).observe(document.body, { childList: true, subtree: true });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();

/* Reusable interactions. Applications provide elements and own persistence. */
(() => {
  function setupSidebar({ sidebar, toggle, expanded = true, onPreference = () => {}, onResize = () => {}, destination = 'nav a, [data-view]' }) {
    const document = sidebar.ownerDocument, window = document.defaultView;
    const viewport = window.matchMedia('(max-width: 760px)');
    let mobileExpanded = false;
    const apply = () => {
      const visible = viewport.matches ? mobileExpanded : expanded;
      document.body.classList.toggle('sidebar-collapsed', !visible);
      toggle.setAttribute('aria-expanded', String(visible));
      toggle.setAttribute('aria-label', visible ? 'Collapse sidebar' : 'Expand sidebar');
      toggle.title = toggle.getAttribute('aria-label');
    };
    const collapse = () => { mobileExpanded = false; apply(); };
    toggle.addEventListener('click', () => {
      if (viewport.matches) mobileExpanded = !mobileExpanded;
      else { expanded = !expanded; onPreference(expanded); }
      apply();
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && viewport.matches && mobileExpanded && !document.querySelector('dialog[open]')) {
        collapse(); toggle.focus();
      }
    });
    document.addEventListener('pointerdown', event => {
      if (viewport.matches && mobileExpanded && !document.querySelector('dialog[open]') && !sidebar.contains(event.target)) collapse();
    });
    sidebar.addEventListener('click', event => {
      if (viewport.matches && event.target.closest(destination)) collapse();
    });
    viewport.addEventListener('change', () => { collapse(); onResize(); });
    apply();
    return { viewport };
  }

  function setupDialog(dialog, { onClose = () => {}, fallbackFocus = () => null } = {}) {
    let returnFocus;
    dialog.addEventListener('click', event => {
      if (event.target.closest('[data-eco-close]')) dialog.close();
    });
    dialog.addEventListener('close', () => {
      if (dialog.open) return;
      onClose();
      const target = returnFocus?.isConnected && !returnFocus.closest('[hidden]') ? returnFocus : fallbackFocus();
      if (!dialog.ownerDocument.querySelector('dialog[open]')) target?.focus({ preventScroll: true });
      returnFocus = null;
    });
    return {
      open() {
        if (dialog.open) return;
        returnFocus = dialog.ownerDocument.activeElement;
        dialog.showModal();
      },
      close() { if (dialog.open) dialog.close(); }
    };
  }
  globalThis.EcoUI = { setupSidebar, setupDialog };
})();

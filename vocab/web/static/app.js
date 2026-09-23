'use strict';
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => Array.from(root.querySelectorAll(s));
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const plain = value => String(value ?? '').replace(/\[[^\]]+\]/g, '');

const paths = {
  home: 'M3 10 12 3l9 7v10H3z M9 20v-7h6v7',
  library: 'M4 4h6v16H4z M14 4h6v16h-6z M6 8h2 M16 8h2',
  decks: 'M3 7h18v14H3z M6 3h12 M4 5h16',
  insights: 'M4 20V10 M10 20V4 M16 20v-8 M22 20H2',
  check: 'M8 3h8v3h4v15H4V6h4z M8 3v5h8V3 M8 14l3 3 5-6',
  settings: 'M4 7h16 M4 17h16 M8 4v6 M16 14v6',
  research: 'M4 4h7l1 2 1-2h7v16h-7l-1 1-1-1H4z M12 6v15',
  clock: 'M12 8v5l3 2 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
  flashcard: 'M5 3h14v18H5z M9 8h6 M9 12h6 M9 16h3',
  typing: 'M3 6h18v13H3z M6 10h1 M10 10h1 M14 10h1 M18 10h1 M7 15h10',
  quiz: 'M4 4h6v6H4z M14 4h6v6h-6z M4 14h6v6H4z M14 14h6v6h-6z',
  arrow: 'M4 12h16 M14 6l6 6-6 6',
  flame: 'M12 2c4 5 7 8 7 13a7 7 0 0 1-14 0c0-4 4-5 7-13z',
  plus: 'M12 4v16 M4 12h16',
  speaker: 'M11 5L6 9H2v6h4l5 4V5z M15.54 8.46a5 5 0 0 1 0 7.07 M19.07 4.93a10 10 0 0 1 0 14.14',
  keyboard: 'M2 6h20v12H2zm4 3h2v2H6zm4 0h2v2h-2zm4 0h2v2h-2zm4 0h2v2h-2zm-12 4h12v2H6z'
};
const icon = name => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[name] || paths.library}"/></svg>`;
const nav = [
  ['home', 'Overview'],
  ['library', 'Library'],
  ['decks', 'Decks'],
  ['insights', 'Insights'],
  ['check', 'Vocab check'],
  ['settings', 'Data & settings']
];
const titles = Object.fromEntries([...nav, ['study', 'Study session'], ['research', 'Research & methodology']]);

const S = {
  csrf: '',
  groups: [],
  group: localStorage.getItem('vocab.deck') || '',
  page: 'home',
  offset: 0,
  session: null,
  sid: sessionStorage.getItem('vocab.session'),
  filters: {},
  routeVersion: 0,
  keyboardControls: true,
  threshold: 30,
  // Realtime state
  revision: 0,
  watchingIds: new Set(),
  isLiveSyncRunning: false,
  // Move set cursors
  libraryWords: [],
  libraryCursor: 0,
  decksCursor: 0,
  choiceCursor: 0
};

let toastTimer;
function toast(message, error = false) {
  const el = $('#toast');
  el.textContent = message;
  el.className = `visible${error ? ' error' : ''}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = ''; }, error ? 10000 : 4500);
}

async function api(path, options = {}) {
  const { method = 'GET', data, form } = options;
  const headers = { 'X-CSRF-Token': S.csrf };
  if (data) headers['Content-Type'] = 'application/json';
  const response = await fetch(`/api/${path}`, {
    method,
    headers,
    body: form || (data ? JSON.stringify(data) : undefined)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `Request failed (${response.status}).`);
  return result;
}

function query(values = {}) {
  return new URLSearchParams(Object.entries({ group_id: S.group, ...values }).filter(([, v]) => v !== '' && v != null)).toString();
}

function date(value, brief = false) {
  return value ? new Date(value).toLocaleString(undefined, brief ? { month: 'short', day: 'numeric' } : { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
}

function options(groups = S.groups, chosen = S.group, all = true) {
  return (all ? '<option value="">All decks</option>' : '') + groups.map(g => `<option value="${g.id}" ${String(g.id) === String(chosen) ? 'selected' : ''}>${esc(g.name)}</option>`).join('');
}

function updateScope() {
  if (S.group && !S.groups.some(g => String(g.id) === S.group)) S.group = '';
  $('#deck-scope').innerHTML = options();
  localStorage.setItem('vocab.deck', S.group);
}

async function refreshGroups() {
  S.groups = (await api('groups')).groups;
  updateScope();
}

function heading(title, sub, action = '') {
  return `<div class="page-heading"><div><div class="eyebrow">Your learning workspace</div><h1>${title}</h1><p>${sub}</p></div>${action}</div>`;
}

function metrics(stats) {
  return `<div class="metrics">${[
    ['Due for review', stats.due_count, 'Ready when you are', 'clock'],
    ['Words in library', stats.total_words, `${stats.new_count} new · ${stats.mature_count} mature`, 'library'],
    ['Recall accuracy', stats.total_recent_reviews ? `${stats.retention_rate}%` : '—', 'Last 7 days · recall reviews', 'check'],
    ['Study streak', `${stats.streak_days}<small> days</small>`, 'A little practice, every day', 'flame']
  ].map(([label, value, note, i]) => `<div class="metric"><div class="metric-label">${label}${icon(i)}</div><div class="metric-value">${value}</div><div class="metric-note">${note}</div></div>`).join('')}</div>`;
}

function chart(entries, hourly = false) {
  const max = Math.max(1, ...entries.map(e => Number(e[1])));
  return `<div class="chart${hourly ? ' hourly' : ''}" role="img" aria-label="${esc(entries.map(([k, v]) => `${k}: ${v} reviews`).join(', '))}">${entries.map(([k, v]) => `<div class="chart-col" title="${esc(k)}: ${v}"><b>${v || ''}</b><div class="chart-bar" style="height:${Math.max(2, v / max * 80)}%"></div><span>${esc(k)}</span></div>`).join('')}</div>`;
}

function forecast(data) {
  return `<div class="section-heading"><h2>Review forecast</h2><span>Next 7 days</span></div><p>Scheduled reviews, by due date.</p>${chart(Object.entries(data))}`;
}

function deckRows(groups) {
  return groups.length ? groups.slice(0, 4).map(g => `<div class="deck-row"><div class="deck-dot">${icon('decks')}</div><div class="deck-info"><strong>${esc(g.name)}</strong><small>${g.word_count} words</small></div><span class="due-badge">${g.due_count} due</span><button class="button small ghost" data-action="deck-study" data-id="${g.id}" aria-label="Study ${esc(g.name)}">${icon('arrow')}</button></div>`).join('') : '<p>Your library is empty. Create a deck to get started.</p>';
}

function dashboardKeyGuide() {
  return S.keyboardControls ? '<div class="terminal-shortcuts" aria-label="Dashboard keyboard shortcuts"><span>Move set</span><kbd>1</kbd> Flashcards <kbd>2</kbd> Typing <kbd>3</kbd> Quiz <kbd>4</kbd> Deck <kbd>5</kbd> Add <kbd>6</kbd> Library <kbd>7</kbd> Insights <kbd>8</kbd> Decks <kbd>9</kbd> Data <kbd>t</kbd> Check <kbd>?</kbd> Cheatsheet</div>' : '';
}

/* Audio Pronunciation with SpeechSynthesis */
function speakWord(text) {
  if (!('speechSynthesis' in window) || !text) return;
  try {
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(String(text).trim());
    u.lang = 'en-US';
    u.rate = 0.92;
    const btn = $('.speech-btn');
    if (btn) btn.classList.add('speaking');
    u.onend = () => { if (btn) btn.classList.remove('speaking'); };
    u.onerror = () => { if (btn) btn.classList.remove('speaking'); };
    window.speechSynthesis.speak(u);
  } catch (e) {}
}

/* Realtime Sync Engine */
async function pollSync() {
  if (!S.csrf) return;
  try {
    const watchingParam = Array.from(S.watchingIds).join(',');
    const q = new URLSearchParams({
      since: String(S.revision),
      watching: watchingParam,
      group_id: S.group || ''
    }).toString();
    const data = await api(`sync?${q}`);

    // Update connection indicator
    const dot = $('#live-dot');
    if (dot) { dot.className = 'connection-dot live'; dot.title = 'Realtime sync active'; }
    const label = $('#connection-label');
    if (label) label.textContent = 'Live workspace';

    // Update completed background enrichments in quick-add dialog
    if (data.completed && data.completed.length) {
      for (const item of data.completed) {
        S.watchingIds.delete(item.id);
        const logItem = $(`#quick-add-log li[data-id="${item.id}"]`);
        if (logItem) {
          logItem.classList.add('enriched-active');
          const span = logItem.querySelector('span');
          if (span) {
            span.innerHTML = `<span class="enrich-badge">✓ Enriched</span> ${esc(item.definition || '')} ${item.phonetic ? `<small>${esc(item.phonetic)}</small>` : ''}`;
          }
        }
      }
      const statusSpan = $('#quick-add-status-text');
      if (statusSpan && data.completed.length) {
        statusSpan.textContent = 'Enrichment complete! Definitions and phonetics loaded.';
      }
    }

    // Update state upon mutation
    if (data.changed) {
      S.revision = data.revision;
      S.groups = data.groups || S.groups;
      updateScope();

      // Smoothly update metrics or views without jarring page reload
      if (S.page === 'home') {
        const metricsContainer = $('.metrics');
        if (metricsContainer && data.stats) metricsContainer.outerHTML = metrics(data.stats);
      } else if (S.page === 'library' && !$('#modal').open && document.activeElement?.tagName !== 'INPUT') {
        renderLibraryTable();
      } else if (S.page === 'decks' && !$('#modal').open) {
        const grid = $('.deck-grid');
        if (grid) grid.innerHTML = S.groups.map((g, i) => deckCardHTML(g, i)).join('');
      }
    }
  } catch (err) {
    const dot = $('#live-dot');
    if (dot) { dot.className = 'connection-dot offline'; dot.title = 'Reconnecting…'; }
    const label = $('#connection-label');
    if (label) label.textContent = 'Offline';
  }
}

function startRealtimeSync() {
  if (S.isLiveSyncRunning) return;
  S.isLiveSyncRunning = true;
  const loop = async () => {
    if (document.visibilityState === 'visible') {
      await pollSync();
    }
    const interval = (S.watchingIds.size > 0 || $('#quick-add-form')) ? 1200 : 2800;
    setTimeout(loop, interval);
  };
  setTimeout(loop, 1200);
}

/* Views */
async function home() {
  const d = await api(`dashboard?${query()}`), s = d.stats;
  S.groups = d.groups;
  updateScope();
  return heading('Make every word stick.', 'A focused space to learn, recall, and build lasting vocabulary.', `<span class="date-chip">${new Date().toLocaleDateString(undefined, { weekday: 'short', month: 'long', day: 'numeric' })}</span>`) + metrics(s) + dashboardKeyGuide() + `${S.sid && S.session?.phase !== 'done' ? '<div class="notice">A practice session is in progress. <a href="#study">Resume session →</a></div>' : ''}
    <section class="hero"><div><div class="eyebrow">A little today. Remember tomorrow.</div><h2>${s.due_count ? 'Your next session is ready.' : 'Keep your vocabulary growing.'}</h2><p>${s.due_count ? `${s.due_count} words are ready for practice. Strengthen each memory with a short, focused session.` : 'Add new words or practice upcoming cards. Your progress is saved in the same library as the terminal app.'}</p><div class="hero-actions"><button class="button" data-action="start" data-mode="flashcard">Start review ${icon('arrow')}</button><button class="button ghost" data-action="session-options">Session options</button></div></div>
    <div class="hero-graphic"><svg viewBox="0 0 340 145" aria-label="Illustration of spaced retrieval over time" role="img"><g stroke="#cbd7bc" stroke-width="1"><path d="M20 120H320 M20 80H320 M20 40H320" stroke-dasharray="3 5"/></g><path d="M23 33Q35 95 78 115 M79 30Q110 94 166 106 M166 25Q222 69 317 87" stroke="#6c8b5a" stroke-width="2.5" fill="none"/><path d="M79 114V30 M166 105V25" stroke="#a0b88c" stroke-width="1.5" stroke-dasharray="4 4"/><g fill="#496d3d"><circle cx="23" cy="33" r="4"/><circle cx="79" cy="30" r="4"/><circle cx="166" cy="25" r="4"/></g><g fill="#7d8b70" font-family="Segoe UI,sans-serif" font-size="9"><text x="18" y="141">Learn</text><text x="65" y="141">Recall</text><text x="152" y="141">Recall</text><text x="285" y="141">Time →</text></g></svg><small>Spaced retrieval · Conceptual illustration</small></div></section>
    <div class="section-heading"><h2>Choose your practice</h2><span>Three ways to strengthen recall</span></div><div class="mode-grid">${[
      ['flashcard', 'Flashcards', 'Recall the meaning, reveal the answer, and rate how well you remembered.', 'Spaced repetition'],
      ['typing', 'Typing practice', 'Find the right word from its meaning. Practice precise, active recall.', 'Written recall'],
      ['quiz', 'Recognition quiz', 'Choose the matching word. A quick way to practice your vocabulary.', 'Practice only']
    ].map(([mode, title, description, tag]) => `<button class="mode-card" data-action="start" data-mode="${mode}"><span class="mode-icon">${icon(mode)}</span><h3>${title}</h3><p>${description}</p><span class="mode-tag">${tag}</span><span class="arrow">↗</span></button>`).join('')}</div>
    <div class="grid-two"><section class="panel"><div class="section-heading"><h2>Your decks</h2><a class="button small ghost" href="#decks">View all ↗</a></div>${deckRows(d.groups.filter(g => !S.group || String(g.id) === S.group))}</section><section class="panel">${forecast(d.forecast)}</section></div>`;
}

function renderLibraryTableRows(words) {
  if (!words.length) return '';
  return words.map((w, i) => `
    <tr data-index="${i}" data-id="${w.id}" class="${i === S.libraryCursor ? 'keyboard-focused' : ''}">
      <td><strong>${esc(w.word)}</strong><small>${esc(w.phonetic)} ${esc(w.pos)}</small></td>
      <td><span class="word-definition">${esc(w.definition)}</span></td>
      <td>${esc(w.group_name)}</td>
      <td><span class="pill ${esc(w.state)}">${w.state === 'mastered' ? 'retired' : esc(w.state)}</span></td>
      <td>${w.state === 'mastered' ? 'Retired' : date(w.due_date, true)}</td>
      <td><button class="button small secondary" data-action="edit-word" data-id="${w.id}">Edit</button></td>
    </tr>`).join('');
}

async function renderLibraryTable() {
  const data = await api(`words?${query({ ...S.filters, offset: S.offset, limit: 30 })}`);
  S.libraryWords = data.words;
  if (S.libraryCursor >= S.libraryWords.length) S.libraryCursor = Math.max(0, S.libraryWords.length - 1);
  const container = $('#library-table-container');
  if (container) {
    container.innerHTML = data.words.length ? `
      <div class="table-wrap">
        <table>
          <thead>
            <tr><th>Word</th><th>Meaning</th><th>Deck</th><th>State</th><th>Next review</th><th></th></tr>
          </thead>
          <tbody>${renderLibraryTableRows(data.words)}</tbody>
        </table>
      </div>` : `<div class="panel empty"><h2>No matching words</h2><p>Add a word or adjust your filters to see more of your library.</p><button class="button" data-action="add-word">Add a word</button></div>`;
  }
  const pagination = $('#library-pagination');
  if (pagination) {
    pagination.innerHTML = `<span>${data.total ? `${S.offset + 1}–${Math.min(S.offset + 30, data.total)} of ${data.total}` : '0 words'}</span><div><button class="button small secondary" data-action="previous" ${S.offset === 0 ? 'disabled' : ''}>Previous <kbd>h</kbd></button><button class="button small secondary" data-action="next-page" ${S.offset + 30 >= data.total ? 'disabled' : ''}>Next <kbd>l</kbd></button></div>`;
  }
}

async function library() {
  const data = await api(`words?${query({ ...S.filters, offset: S.offset, limit: 30 })}`);
  S.libraryWords = data.words;
  if (S.libraryCursor >= S.libraryWords.length) S.libraryCursor = Math.max(0, S.libraryWords.length - 1);
  return heading('Your word library.', 'Collect, organize, and refine the words you want to remember.', '<button class="button" data-action="add-word">+ Add word <kbd>n</kbd></button>') + `
    <form id="filters" class="toolbar">
      <input aria-label="Search words" name="search" type="search" placeholder="Search words or definitions… (/)" value="${esc(S.filters.search)}" class="grow" autocomplete="off">
      <select name="state" aria-label="Card state">${[['', 'All states'], ['new', 'New'], ['learning', 'Learning'], ['review', 'Review'], ['relearning', 'Relearning'], ['mastered', 'Retired']].map(([v, n]) => `<option value="${v}" ${S.filters.state === v ? 'selected' : ''}>${n}</option>`).join('')}</select>
      <input name="pos" placeholder="Part of speech" aria-label="Part of speech" size="12" value="${esc(S.filters.pos)}">
      <input name="tag" placeholder="Tag" aria-label="Tag" size="10" value="${esc(S.filters.tag)}">
      <select name="sort" aria-label="Sort by">${['word', 'due', 'state', 'ease', 'interval', 'reps', 'lapses', 'created', 'deck'].map(v => `<option ${S.filters.sort === v ? 'selected' : ''}>${v}</option>`).join('')}</select>
      <select name="order" aria-label="Sort order"><option value="asc">Ascending</option><option value="desc" ${S.filters.order === 'desc' ? 'selected' : ''}>Descending</option></select>
      <label class="check-label"><input type="checkbox" name="due_only" ${S.filters.due_only === 'true' ? 'checked' : ''}>Due only</label>
      <button class="button small">Apply</button>
    </form>
    ${S.keyboardControls ? '<div class="terminal-shortcuts" style="margin:-10px 0 14px;justify-content:flex-start"><span>Move set</span><kbd>j</kbd>/<kbd>k</kbd> navigate <kbd>Enter</kbd> edit <kbd>m</kbd> retire <kbd>x</kbd> delete <kbd>h</kbd>/<kbd>l</kbd> page <kbd>/</kbd> search</div>' : ''}
    <div id="library-table-container">
      ${data.words.length ? `<div class="table-wrap"><table><thead><tr><th>Word</th><th>Meaning</th><th>Deck</th><th>State</th><th>Next review</th><th></th></tr></thead><tbody>${renderLibraryTableRows(data.words)}</tbody></table></div>` : `<div class="panel empty"><h2>No matching words</h2><p>Add a word or adjust your filters to see more of your library.</p><button class="button" data-action="add-word">Add a word</button></div>`}
    </div>
    <div class="pagination" id="library-pagination">
      <span>${data.total ? `${S.offset + 1}–${Math.min(S.offset + 30, data.total)} of ${data.total}` : '0 words'}</span>
      <div>
        <button class="button small secondary" data-action="previous" ${S.offset === 0 ? 'disabled' : ''}>Previous <kbd>h</kbd></button>
        <button class="button small secondary" data-action="next-page" ${S.offset + 30 >= data.total ? 'disabled' : ''}>Next <kbd>l</kbd></button>
      </div>
    </div>`;
}

function updateLibraryCursor(index) {
  if (!S.libraryWords.length) return;
  S.libraryCursor = Math.max(0, Math.min(S.libraryWords.length - 1, index));
  $$('#library-table-container tbody tr').forEach((tr, i) => {
    tr.classList.toggle('keyboard-focused', i === S.libraryCursor);
    if (i === S.libraryCursor) tr.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  });
}

function deckCardHTML(g, i = 0) {
  return `<section class="panel deck-card ${i === S.decksCursor ? 'keyboard-focused' : ''}" data-deck-index="${i}" data-id="${g.id}">
    <div class="deck-dot">${icon('decks')}</div>
    <h2 style="margin-top:17px">${esc(g.name)}</h2>
    <p>${esc(g.description) || 'Your personal vocabulary collection.'}</p>
    <div class="counts"><span><b>${g.word_count}</b> words</span><span><b>${g.due_count}</b> due</span></div>
    <div class="actions">
      <button class="button small" data-action="deck-study" data-id="${g.id}">Study deck <kbd>s</kbd></button>
      <button class="button small secondary" data-action="browse-deck" data-id="${g.id}">Browse <kbd>b</kbd></button>
      <button class="button small secondary" data-action="edit-deck" data-id="${g.id}">Edit <kbd>e</kbd></button>
    </div>
  </section>`;
}

async function decks() {
  await refreshGroups();
  return heading('A place for every word.', 'Build a collection around a subject, a book, or your next goal.', '<button class="button" data-action="new-deck">+ Create deck <kbd>c</kbd></button>') +
    (S.keyboardControls ? '<div class="terminal-shortcuts" style="margin:-16px 0 18px;justify-content:flex-start"><span>Move set</span><kbd>j</kbd>/<kbd>k</kbd> select deck <kbd>s</kbd> study <kbd>Enter</kbd> browse <kbd>e</kbd> edit <kbd>c</kbd> new</div>' : '') +
    (S.groups.length ? `<div class="deck-grid">${S.groups.map((g, i) => deckCardHTML(g, i)).join('')}</div>` : '<div class="panel empty"><h2>Your first collection starts here.</h2><p>Create a deck or load the curated starter decks in Data & settings.</p><button class="button" data-action="new-deck">Create a deck</button></div>');
}

function updateDecksCursor(index) {
  if (!S.groups.length) return;
  S.decksCursor = Math.max(0, Math.min(S.groups.length - 1, index));
  $$('.deck-card').forEach((card, i) => {
    card.classList.toggle('keyboard-focused', i === S.decksCursor);
    if (i === S.decksCursor) card.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  });
}

function analyticsMeter(label, count, total, color = 'green') {
  const value = Number(count || 0), denominator = Math.max(1, Number(total || 0));
  return `<div class="analytics-meter"><div><span>${label}</span><strong>${value}</strong></div><div class="meter-track"><span class="meter-fill ${color}" style="width:${Math.min(100, value / denominator * 100)}%"></span></div></div>`;
}

async function insights() {
  const d = await api(`dashboard?${query()}`), s = d.stats, l = d.latency;
  const timed = Number(l.total_timed_reviews || 0);
  const periodRows = (d.periods || []).map(p => `<tr><td><strong>${esc(p.icon || '')} ${esc(p.name)}</strong><small>${esc(plain(p.state_label || ''))}</small></td><td>${p.active_minutes} min</td><td>${p.reviews}<small>${p.new_learning_revs || 0} new · ${p.review_revs || 0} review</small></td><td>${p.avg_thought_time ? `${Number(p.avg_thought_time).toFixed(1)}s` : '—'}</td><td>${p.reviews ? `${Number(p.retention_rate).toFixed(1)}%` : '—'}${p.review_retention_rate != null ? `<small>${Number(p.review_retention_rate).toFixed(1)}% established</small>` : ''}</td><td>${esc(plain(p.state_label || '—'))}</td></tr>`).join('');
  const latencyRows = [['Up to 3 seconds', l.count_fluent, 'green'], ['3 to 7 seconds', l.count_steady, 'blue'], ['Over 7 seconds', l.count_hesitant, 'gold']].map(([label, count, color]) => analyticsMeter(label, count, timed, color)).join('');
  const stages = [['New cards', s.new_count, 'blue'], ['Learning / lapsed', s.learning_count, 'gold'], ['Young review (<21 days)', s.young_count, 'green'], ['Mature review (≥21 days)', s.mature_count, 'green'], ['Retired', s.mastered_count, 'muted']];
  const stageRows = stages.map(([label, count, color]) => analyticsMeter(label, count, s.total_words, color)).join('');
  const deckRows = (d.groups || []).map(g => { const ratio = g.word_count ? Math.round((g.word_count - g.due_count) / g.word_count * 100) : 100; return `<tr><td><strong>${esc(g.name)}</strong></td><td>${g.word_count}</td><td>${g.due_count}</td><td><div class="mini-meter"><span style="width:${ratio}%"></span></div><small>${ratio}% not due</small></td></tr>`; }).join('');
  return heading('Observe your progress.', 'The full learning dashboard from the terminal app, with counts, timing, retention, and library structure.') + metrics(s) + `
    <section class="metrics insight-metrics">${[['Review attempts', s.total_review_attempts, 'All-time rated recall attempts', 'check'], ['Attempts · 7 days', s.total_recent_reviews, 'Excludes quizzes and introductions', 'clock'], ['Learning cards', s.learning_count, 'New + lapsed cards still consolidating', 'typing'], ['Average response', l.overall_avg_thought_time ? `${Number(l.overall_avg_thought_time).toFixed(1)}<small> sec</small>` : '—', `${l.total_timed_reviews || 0} timed responses`, 'clock']].map(([label, value, note, i]) => `<div class="metric"><div class="metric-label">${label}${icon(i)}</div><div class="metric-value">${value}</div><div class="metric-note">${note}</div></div>`).join('')}</section>
    <div class="grid-two"><section class="panel">${forecast(d.forecast)}</section><section class="panel"><div class="section-heading"><h2>Library composition</h2><span>${s.total_words} words</span></div>${stageRows}</section></div>
    <section class="panel"><div class="section-heading"><h2>Activity by time of day</h2><span>Last 30 days · local time</span></div><p>These are observed review patterns. They do not establish an optimal study time or diagnose focus or fatigue.</p><div class="table-wrap analytics-table"><table><thead><tr><th>Period</th><th>Active time</th><th>Attempts</th><th>Avg latency</th><th>Recall</th><th>Sample</th></tr></thead><tbody>${periodRows || '<tr><td colspan="6">No review activity yet.</td></tr>'}</tbody></table></div></section>
    <section class="panel"><div class="section-heading"><h2>24-hour review distribution</h2><span>Last 30 days</span></div>${chart((d.hourly || []).map(h => [`${h.hour}:00`, h.reviews]), true)}</section>
    <div class="grid-two"><section class="panel"><div class="section-heading"><h2>Recorded response times</h2><span>${timed} timed responses</span></div><p>Valid response times are grouped descriptively; values above ${l.max_thought_time_threshold || 30}s are excluded from averages.</p>${timed ? latencyRows : '<div class="empty">Complete recall sessions to see timing bands.</div>'}<div class="notice">${l.count_outliers || 0} timing outlier(s) excluded from latency averages. Response time does not change SM-2 intervals.</div></section><section class="panel"><h2>Words that need a moment</h2><p>Terms with the longest recorded average retrieval times.</p>${(l.hesitant_words || []).slice(0, 6).map(w => `<div class="deck-row"><strong class="grow">${esc(w.word)}</strong><small>${Number(w.avg_thought_time).toFixed(1)}s</small><button class="button small ghost" data-action="edit-word" data-id="${w.id}">View</button></div>`).join('') || '<div class="empty">Complete a few recall sessions to see patterns here.</div>'}</section></div>
    <section class="panel"><div class="section-heading"><h2>Vocabulary decks</h2><span>Words and current workload</span></div><div class="table-wrap analytics-table"><table><thead><tr><th>Deck</th><th>Words</th><th>Due now</th><th>Not due</th></tr></thead><tbody>${deckRows || '<tr><td colspan="4">No decks yet.</td></tr>'}</tbody></table></div></section>
    <div class="notice">Recall accuracy is Hard, Good, or Easy divided by rated recall attempts in the last 7 days. Quizzes and introductions are excluded. Mature means an interval of at least 21 days; it is not a claim of permanent mastery.</div>`;
}

async function checkPage() {
  const data = await api('checks');
  return heading('Check what you know.', 'A short vocabulary exercise to find useful directions for your next practice.') + `
    <div class="grid-two"><section class="panel"><div class="eyebrow">Vocabulary check</div><h2>A fresh set of questions.</h2><p>Choose curated offline questions, book trivia, or synonym practice.</p><form id="check-options" class="form-grid"><label class="field full">Question source<select name="source"><option value="benchmark">Curated vocabulary · offline</option><option value="opentdb">OpenTDB · books & general trivia</option><option value="datamuse">Datamuse · synonyms</option></select></label><label class="field">Questions<input name="limit" type="number" min="1" max="100" value="12" required></label><label class="field">Curated item level<select name="level"><option value="">Mixed A1–C2</option>${['A1', 'A2', 'B1', 'B2', 'C1', 'C2'].map(l => `<option>${l}</option>`).join('')}</select></label><div class="full"><button class="button">Begin vocabulary check ${icon('arrow')}</button></div></form></section><section class="panel"><div class="eyebrow">Interpreting your score</div><h2>Useful feedback, with context.</h2><p>Your score describes accuracy on the questions you answered. The result includes a 95% Wilson interval and a breakdown by the question bank’s level labels.</p><p>These questions are not calibrated to certify a CEFR level or estimate vocabulary size. Guessing and item selection affect the results.</p><p>Online sources fall back to curated questions when unavailable. Each question displays its actual category.</p><a class="button ghost" href="#research">Read the methodology ↗</a></section></div>
    <div class="section-heading"><h2>Previous checks</h2><span>Latest 100 results</span></div>${data.history.length ? `<div class="table-wrap"><table><thead><tr><th>Date</th><th>Source</th><th>Accuracy</th><th>Responses</th><th></th></tr></thead><tbody>${data.history.map(t => `<tr><td>${date(t.tested_at)}</td><td>${esc(t.test_type)}</td><td><strong>${t.score_pct}%</strong></td><td>${t.correct_count} / ${t.total_questions}</td><td><button class="button small secondary" data-action="check-detail" data-id="${t.id}">Details</button> <button class="button small danger" data-action="delete-check" data-id="${t.id}">Delete</button></td></tr>`).join('')}</tbody></table></div>` : '<div class="panel empty">Your completed checks will appear here.</div>'}`;
}

async function settings() {
  const boot = await api('bootstrap');
  S.keyboardControls = boot.keyboard_controls;
  S.threshold = boot.threshold || 30;
  return heading('Your data, in your hands.', 'The browser and terminal use the same local SQLite library.') + `
    <div class="grid-two"><section class="panel"><h2>Export vocabulary</h2><p>Download the selected deck or your entire library. Files are compatible with terminal imports.</p><form id="export-form" class="form-grid"><label class="field full">Deck<select name="group_id">${options()}</select></label><label class="field">Format<select name="format"><option value="json">JSON</option><option value="csv">CSV</option></select></label><div class="full"><button class="button secondary">Download export ↓</button></div></form><div class="notice">Vocabulary imports start with new schedules. For a complete backup including review history, copy the database file while the apps are closed.</div></section>
    <section class="panel"><h2>Import vocabulary</h2><p>Upload a UTF-8 CSV or JSON file, up to 5 MB. Existing words in the same deck are skipped.</p><form id="import-form"><label class="field">Vocabulary file<input name="file" type="file" accept=".csv,.json" required></label><div class="form-actions"><button class="button">Import words</button></div></form><p style="margin-top:22px">CSV columns: <code>group, word, definition, phonetic, pos, example, mnemonic, tags</code>. Only word and definition are required.</p></section></div>
    <section class="panel"><h2>Learning preferences & maintenance</h2><div class="settings-row"><div><h3>Terminal-style keyboard controls & move set</h3><p id="keyboard-help">Use fluid keyboard shortcuts: 1–4, arrows, j/k cursor navigation, Space to flip, p to pronounce, and vim commands.</p></div><label class="switch"><input id="keyboard-controls" type="checkbox" role="switch" aria-describedby="keyboard-help" ${S.keyboardControls ? 'checked' : ''}><span class="switch-track" aria-hidden="true"></span><span class="switch-label">${S.keyboardControls ? 'On' : 'Off'}</span></label></div><div class="settings-row"><div><h3>Response-time threshold</h3><p>Exclude slower responses from timing summaries. Raw history remains saved until you explicitly clean it.</p></div><form id="threshold-form" class="toolbar" style="margin:0"><input aria-label="Response-time threshold in seconds" name="value" type="number" min="1" max="3600" value="${boot.threshold}" style="width:85px" required><span class="subtle">sec</span><button class="button small secondary">Save</button></form></div>
    <div class="settings-row"><div><h3>Curated starter decks</h3><p>Add the bundled vocabulary collections. Existing starter words are preserved.</p></div><button class="button small secondary" data-action="maintenance" data-op="seed">Load starter decks</button></div>
    <div class="settings-row"><div><h3>Rebuild schedules from review history</h3><p>Replay your saved review events through the shared scheduler. This replaces stored schedules.</p></div><button class="button small secondary" data-action="maintenance" data-op="sync">Rebuild schedules</button></div>
    <div class="settings-row"><div><h3>Clean response-time outliers</h3><p>Clear timing values above your threshold and recalculate word averages. This changes saved timing history.</p></div><button class="button small danger" data-action="maintenance" data-op="cleanup">Clean timing history</button></div></section>`;
}

async function research() {
  const d = await api('research');
  return `<div class="research">${heading('Grounded in retrieval.', 'The research, implementation choices, and limits behind this workspace.')}<section class="panel"><h2>Core references</h2><a class="paper-link" href="https://www.super-memory.org/archive/english/ol/sm2.htm" target="_blank" rel="noopener">Woźniak · The original SM-2 algorithm ↗</a><a class="paper-link" href="https://learninglab.psych.purdue.edu/downloads/2008/2008_Karpicke_Roediger_Science.pdf" target="_blank" rel="noopener">Karpicke & Roediger (2008) · Retrieval practice ↗</a><a class="paper-link" href="https://doi.org/10.1080/01621459.1927.10502953" target="_blank" rel="noopener">Wilson (1927) · Score intervals ↗</a></section><section class="panel"><pre>${esc(d.content)}</pre></section></div>`;
}

function dialog(title, content) {
  const el = $('#modal');
  el.innerHTML = `<div class="modal-heading"><h2>${title}</h2><button class="close" data-action="close" aria-label="Close dialog">×</button></div>${content}<div class="error-message" id="modal-error" role="alert"></div>`;
  if (!el.open) el.showModal();
}

/* Move Set Cheatsheet Modal */
function showShortcutsModal() {
  const content = `
    <div class="shortcuts-dialog">
      <p style="margin-bottom:14px;color:var(--muted)">Master your vocabulary workspace with fluid keyboard navigation and tactile shortcuts.</p>
      <div class="shortcuts-grid">
        <div class="shortcuts-card">
          <h3><span>🌍 Navigation & Global</span></h3>
          <ul class="shortcuts-list">
            <li class="shortcuts-row"><span>Jump to Views</span><div class="shortcut-keys"><kbd>1</kbd>–<kbd>4</kbd>, <kbd>6</kbd>–<kbd>9</kbd>, <kbd>t</kbd></div></li>
            <li class="shortcuts-row"><span>Quick Search</span><div class="shortcut-keys"><kbd>/</kbd></div></li>
            <li class="shortcuts-row"><span>Move Set Help</span><div class="shortcut-keys"><kbd>?</kbd></div></li>
            <li class="shortcuts-row"><span>Close / Dismiss</span><div class="shortcut-keys"><kbd>Esc</kbd></div></li>
          </ul>
        </div>
        <div class="shortcuts-card">
          <h3><span>📇 Library Move Set</span></h3>
          <ul class="shortcuts-list">
            <li class="shortcuts-row"><span>Navigate Rows</span><div class="shortcut-keys"><kbd>j</kbd> / <kbd>k</kbd> or <kbd>↓</kbd> / <kbd>↑</kbd></div></li>
            <li class="shortcuts-row"><span>Edit Focused Word</span><div class="shortcut-keys"><kbd>Enter</kbd> or <kbd>e</kbd></div></li>
            <li class="shortcuts-row"><span>Toggle Mastery / Retire</span><div class="shortcut-keys"><kbd>Space</kbd> or <kbd>m</kbd></div></li>
            <li class="shortcuts-row"><span>Delete Word</span><div class="shortcut-keys"><kbd>x</kbd> or <kbd>Del</kbd></div></li>
            <li class="shortcuts-row"><span>Previous / Next Page</span><div class="shortcut-keys"><kbd>h</kbd> / <kbd>l</kbd> or <kbd>←</kbd> / <kbd>→</kbd></div></li>
            <li class="shortcuts-row"><span>Continuous Add</span><div class="shortcut-keys"><kbd>n</kbd> or <kbd>+</kbd></div></li>
          </ul>
        </div>
        <div class="shortcuts-card">
          <h3><span>🃏 Study Move Set</span></h3>
          <ul class="shortcuts-list">
            <li class="shortcuts-row"><span>Flip / Reveal Answer</span><div class="shortcut-keys"><kbd>Space</kbd>, <kbd>Enter</kbd>, <kbd>f</kbd>, <kbd>↓</kbd></div></li>
            <li class="shortcuts-row"><span>Rate Card (Again/Hard/Good/Easy)</span><div class="shortcut-keys"><kbd>1</kbd>–<kbd>4</kbd> or <kbd>a</kbd>/<kbd>h</kbd>/<kbd>g</kbd>/<kbd>e</kbd></div></li>
            <li class="shortcuts-row"><span>Arrow Key Rating</span><div class="shortcut-keys"><kbd>←</kbd> <kbd>↓</kbd> <kbd>↑</kbd> <kbd>→</kbd></div></li>
            <li class="shortcuts-row"><span>Pronounce Word (Audio)</span><div class="shortcut-keys"><kbd>p</kbd> or <kbd>r</kbd></div></li>
            <li class="shortcuts-row"><span>Shuffle Queue</span><div class="shortcut-keys"><kbd>s</kbd></div></li>
            <li class="shortcuts-row"><span>Edit / Delete Word</span><div class="shortcut-keys"><kbd>e</kbd> / <kbd>d</kbd></div></li>
            <li class="shortcuts-row"><span>Finish Session</span><div class="shortcut-keys"><kbd>q</kbd></div></li>
          </ul>
        </div>
        <div class="shortcuts-card">
          <h3><span>⌨️ Typing & Quiz Moves</span></h3>
          <ul class="shortcuts-list">
            <li class="shortcuts-row"><span>Choose Option (Quiz/Check)</span><div class="shortcut-keys"><kbd>1</kbd>–<kbd>4</kbd> or <kbd>j</kbd>/<kbd>k</kbd> + <kbd>Enter</kbd></div></li>
            <li class="shortcuts-row"><span>Peek Word Hint (Typing)</span><div class="shortcut-keys"><kbd>Tab</kbd></div></li>
            <li class="shortcuts-row"><span>Submit Answer</span><div class="shortcut-keys"><kbd>Enter</kbd></div></li>
            <li class="shortcuts-row"><span>Typing Commands</span><div class="shortcut-keys"><kbd>:s</kbd> shuffle · <kbd>:q</kbd> quit</div></li>
          </ul>
        </div>
      </div>
      <div class="form-actions"><button class="button secondary" type="button" data-action="close">Close (Esc)</button></div>
    </div>
  `;
  dialog('Workspace Move Set & Shortcuts', content);
}

function sessionOptions(mode = 'flashcard') {
  dialog('Set up your session', `<form id="session-options" class="form-grid"><label class="field full">Practice mode<select name="mode">${[['flashcard', 'Flashcards'], ['typing', 'Typing practice'], ['quiz', 'Recognition quiz']].map(([v, n]) => `<option value="${v}" ${mode === v ? 'selected' : ''}>${n}</option>`).join('')}</select></label><label class="field">Deck<select name="group_id">${options()}</select></label><label class="field">Maximum words<input type="number" name="limit" min="1" max="100" value="20" required></label>${[['shuffle', 'Mix card order', true], ['fill_placeholders', 'Fill short sessions with upcoming cards', true], ['force_all', 'Cram: include words before their due date', false]].map(([key, label, checked]) => `<label class="check-label full"><input type="checkbox" name="${key}" ${checked ? 'checked' : ''}>${label}</label>`).join('')}<div class="notice full">Each session uses a fixed batch within your workload budget. Difficult words may repeat; start another session for more words. Successful early reviews preserve their schedule. Quizzes record practice without changing SM-2 intervals.</div><div class="full form-actions"><button class="button">Begin session ${icon('arrow')}</button></div></form>`);
}

async function startSession(data) {
  if (S.sid && S.session?.phase !== 'done' && !confirm('Start a new session? Completed reviews are already saved.')) return;
  const d = await api('sessions', { method: 'POST', data: { group_id: S.group || null, limit: 20, ...data } });
  S.sid = d.id;
  S.session = d;
  sessionStorage.setItem('vocab.session', S.sid);
  $('#modal').close();
  if (location.hash === '#study') renderStudy(d); else location.hash = 'study';
}

function resultPanel(r) {
  const ci = r.accuracy_interval;
  return `<div class="eyebrow">Practice result</div><h2>A snapshot of your vocabulary.</h2><div class="result-score">${r.score_pct}%</div><p>${r.correct_count} correct out of ${r.total_questions} responses</p>${ci ? `<p>95% Wilson interval: ${(ci[0] * 100).toFixed(1)}–${(ci[1] * 100).toFixed(1)}%</p>` : ''}<div class="notice">${esc(r.sample_warning)}</div><div class="table-wrap"><table><thead><tr><th>Item level</th><th>Correct</th><th>Answered</th></tr></thead><tbody>${Object.entries(r.level_breakdown || {}).filter(([, v]) => v.total).map(([level, v]) => `<tr><td>${esc(level)}</td><td>${v.correct}</td><td>${v.total}</td></tr>`).join('')}</tbody></table></div>`;
}

function key(label) { return S.keyboardControls ? ` <kbd>${label}</kbd>` : ''; }

function keyboardGuide(d) {
  if (!S.keyboardControls) return '<p class="keyboard-note muted-keys">Terminal-style keyboard controls are off. Buttons remain active.</p>';
  if (d.mode === 'check') return '<p class="keyboard-note"><kbd>1–4</kbd> choose · <kbd>Enter</kbd> continue · <kbd>q</kbd> finish · <kbd>?</kbd> move set</p>';
  if (d.mode === 'quiz') return '<p class="keyboard-note"><kbd>1–4</kbd> or <kbd>j</kbd>/<kbd>k</kbd> choose · <kbd>s</kbd> shuffle · <kbd>p</kbd> audio · <kbd>q</kbd> finish</p>';
  if (d.mode === 'typing') return '<p class="keyboard-note">Type answer · <kbd>Tab</kbd> hint · <kbd>:s</kbd> shuffle · <kbd>skip</kbd> reveal · <kbd>:q</kbd> finish</p>';
  return '<p class="keyboard-note"><kbd>Space</kbd>/<kbd>Enter</kbd> reveal · <kbd>1–4</kbd> or <kbd>a</kbd>/<kbd>h</kbd>/<kbd>g</kbd>/<kbd>e</kbd> or <kbd>←</kbd><kbd>↓</kbd><kbd>↑</kbd><kbd>→</kbd> rate · <kbd>p</kbd> audio · <kbd>s</kbd> shuffle · <kbd>q</kbd> finish</p>';
}

function studyHTML(d) {
  if (d.phase === 'done') {
    return `<div class="study-container"><section class="panel" style="text-align:center">${d.mode === 'check' ? resultPanel(d.result) : `<div class="eyebrow">Session complete</div><h1>A little progress, well earned.</h1><p>Every completed review has been saved to your library.</p><div class="result-score">${d.reviews}<small> reviews</small></div><div class="metrics" style="grid-template-columns:repeat(2,1fr)"><div class="metric"><div class="metric-label">${d.mode === 'quiz' ? 'Recognition accuracy' : 'Recall accuracy'}</div><div class="metric-value">${d.reviews ? `${d.retention.toFixed(0)}%` : '—'}</div></div><div class="metric"><div class="metric-label">Average response time</div><div class="metric-value">${d.average_seconds}<small> sec</small></div></div></div><p>${Object.entries(d.grades).map(([k, v]) => `${k}: ${v}`).join(' · ')}</p>`}<div class="form-actions" style="justify-content:center"><a class="button secondary" href="#home">Back to overview</a><button class="button" data-action="${d.mode === 'check' ? 'another-check' : 'session-options'}">Practice again</button></div></section></div>`;
  }
  const check = d.mode === 'check', c = d.card || {}, q = d.question || {}, f = d.feedback;
  const progress = check ? d.answered / Math.max(1, d.total) : d.completed / Math.max(1, d.total_added);
  const label = check ? 'Vocabulary check' : { flashcard: 'Flashcards', typing: 'Typing practice', quiz: 'Recognition quiz' }[d.mode];
  const wordToSpeak = check ? '' : (c.word || '');

  return `<div class="study-container"><div class="study-top">
    <span>${label} <span class="slash">/</span>${check ? `${d.answered} of ${d.total} answered` : `${d.remaining} remaining · ${d.reviews} reviews`}</span>
    <button class="button small secondary" data-action="study" data-op="end">Finish session${key('q')}</button>
  </div><div class="progress" role="progressbar" aria-label="Session words completed" aria-valuemin="0" aria-valuemax="${check ? d.total : d.total_added}" aria-valuenow="${check ? d.answered : d.completed}"><span style="width:${Math.min(100, progress * 100)}%"></span></div>
    <section class="study-card ${d.phase === 'revealed' ? 'revealed' : ''} ${d.phase}"><div class="state-line">
      <span>${check ? `${esc(q.category)} · item ${esc(q.level)}` : `${esc(c.group_name)} · ${d.phase === 'introduction' ? 'First look' : esc(c.state)}`}</span>
      ${wordToSpeak ? `<button class="speech-btn" data-action="speak" data-word="${esc(wordToSpeak)}" aria-label="Pronounce word (p or r)" title="Pronounce word (p or r)"><svg class="icon" viewBox="0 0 24 24"><path d="${paths.speaker}"/></svg></button>` : ''}
    </div><div class="prompt">${esc(check ? q.prompt : d.mode === 'flashcard' ? c.word : c.definition)}</div>
      ${!check && c.word ? `
        <div class="card-body">
          ${d.mode === 'flashcard' ? (c.definition ? `<div class="answer meaning">${esc(c.definition)}</div>` : '<div class="answer meaning placeholder"><span class="subtle">Recall the definition, context, and usage.</span></div>') : `<div class="answer">${esc(c.word)}</div>`}
          ${c.phonetic || c.pos ? `<p class="phonetic">${esc(c.phonetic || '')} ${esc(c.pos || '')}</p>` : ''}
          ${c.example ? `<p class="example">${esc(c.example)}</p>` : ''}
          ${c.mnemonic ? `<p class="mnemonic">Memory cue: ${esc(c.mnemonic)}</p>` : ''}
        </div>` : ''}
      ${d.phase === 'question' && (check || d.mode === 'quiz') ? `<div class="choices">${(check ? q.choices : d.choices).map((choice, i) => `<button class="choice ${i === S.choiceCursor ? 'keyboard-focused' : ''}" data-action="choice" data-index="${i}"><span>${i + 1}</span>${esc(choice)}</button>`).join('')}</div>` : ''}
      ${d.phase === 'question' && d.mode === 'typing' ? `<form id="typing-answer" class="typing-form"><input name="answer" aria-label="Type the matching word" placeholder="Type the matching word… (Tab for hint)" autocomplete="off" autocapitalize="off" spellcheck="false" maxlength="500" ${S.keyboardControls ? '' : 'required'} autofocus><button class="button">Check answer</button></form>` : ''}
    </section>
    ${f ? `<div class="feedback ${f.grade === 'Again' || f.correct === false ? 'missed' : ''}" role="status"><strong>${check ? (f.correct ? 'Correct' : 'Keep this one in mind') : f.introduced ? 'Ready for recall' : f.grade === 'Hard' && d.mode === 'typing' ? 'Close spelling · Hard' : esc(f.grade)}</strong><p>${check ? `${esc(f.answer)} — ${esc(f.explanation)}` : esc(f.message)}</p></div>` : ''}
    <div class="study-actions">
      ${d.phase === 'introduction' ? `<button class="button" data-action="study" data-op="introduce">Learn this word · continue${key('Enter')}</button>` : ''}
      ${d.phase === 'question' && d.mode === 'flashcard' ? `<button class="button" data-action="study" data-op="reveal">Reveal answer${key('Space / Enter')}</button>` : ''}
      ${d.phase === 'revealed' ? ['Again', 'Hard', 'Good', 'Easy'].map((g, i) => {
        const arrowKey = ['←', '↓', '↑', '→'][i];
        const letterKey = ['a', 'h', 'g', 'e'][i];
        return `<button class="grade-button ${g.toLowerCase()}" data-action="grade" data-grade="${i + 1}"><b>${g}${S.keyboardControls ? ` <kbd>${i + 1}</kbd> <kbd>${letterKey}</kbd> <kbd>${arrowKey}</kbd>` : ''}</b><small>${esc(d.intervals[String(i + 1)])}</small></button>`;
      }).join('') : ''}
      ${d.phase === 'feedback' ? `<button class="button" data-action="study" data-op="next">Continue →${key('Enter')}</button>` : ''}
    </div>${!check ? `<div class="study-bottom"><button class="button ghost" data-action="study" data-op="shuffle">Shuffle${key('s')}</button><button class="button ghost" data-action="edit-word" data-id="${c.id}">Edit${key('e')}</button><button class="button ghost" data-action="delete-word" data-id="${c.id}">Delete${key('d')}</button><button class="button ghost" data-action="study" data-op="skip">Skip card</button></div>` : ''}
    ${keyboardGuide(d)}</div>`;
}

function updateChoiceCursor(index) {
  const choices = $$('.choice');
  if (!choices.length) return;
  S.choiceCursor = Math.max(0, Math.min(choices.length - 1, index));
  choices.forEach((btn, i) => btn.classList.toggle('keyboard-focused', i === S.choiceCursor));
}

function renderStudy(d) {
  S.session = d;
  S.choiceCursor = 0;
  $('#content').innerHTML = studyHTML(d);
  $('#content').focus({ preventScroll: true });
  $('#typing-answer input')?.focus();
}

async function studyAction(data) {
  const d = await api(`sessions/${S.sid}`, { method: 'POST', data: { token: S.session.token, ...data } });
  renderStudy(d);
  if (data.action === 'shuffle') toast('Queue shuffled.');
}

async function wordEditor(id, chosenGroup = S.group) {
  await refreshGroups();
  if (!S.groups.length) { deckEditor(null); toast('Create a deck first, then add your words.'); return; }
  const detail = id ? await api(`words/${id}`) : { word: { group_id: chosenGroup || S.groups[0].id }, reviews: [] }, w = detail.word;
  dialog(id ? 'Edit vocabulary' : 'Add a word', `<form id="word-editor" data-id="${id || ''}" class="form-grid"><label class="field">Word<input name="word" value="${esc(w.word)}" maxlength="500" required autofocus></label><label class="field">Deck<select name="group_id">${options(S.groups, w.group_id, false)}</select></label><div class="full"><button type="button" class="button small secondary" data-action="lookup">Look up dictionary & Chinese</button><span class="subtle" id="lookup-status"></span></div><label class="field full">Definition<textarea name="definition" required>${esc(w.definition)}</textarea></label>${[['phonetic', 'Phonetic'], ['pos', 'Part of speech'], ['example', 'Example'], ['mnemonic', 'Memory cue'], ['tags', 'Tags (comma-separated)']].map(([key, label]) => `<label class="field ${['example', 'mnemonic', 'tags'].includes(key) ? 'full' : ''}">${label}<input name="${key}" value="${esc(w[key])}"></label>`).join('')}${id ? `<label class="check-label full"><input type="checkbox" name="retired" ${w.state === 'mastered' ? 'checked' : ''}>Retire this word from scheduled study</label>` : '<label class="check-label full"><input type="checkbox" name="another">Keep adding words</label>'}<div class="form-actions full">${id ? `<button class="button danger" type="button" data-action="delete-word" data-id="${id}">Delete word</button>` : ''}<span class="spacer"></span><button class="button secondary" type="button" data-action="close">Cancel</button><button class="button">Save word</button></div></form>${detail.reviews.length ? `<details class="history"><summary>Review history · ${detail.reviews.length} events</summary><ul>${detail.reviews.slice(-30).reverse().map(r => `<li>${date(r.reviewed_at)} · ${esc(r.review_mode)} · ${['', 'Again', 'Hard', 'Good', 'Easy'][r.grade]} · ${Number(r.thought_time_seconds).toFixed(1)}s</li>`).join('')}</ul></details>` : ''}`);
}

async function quickAddDialog(chosenGroup = S.group) {
  await refreshGroups();
  if (!S.groups.length) { deckEditor(null); toast('Create a deck first, then add your words.'); return; }
  const gid = S.groups.some(g => String(g.id) === String(chosenGroup)) ? chosenGroup : S.groups[0].id;
  dialog('Add words continuously', `<form id="quick-add-form" class="quick-add"><label class="field">Deck<select name="group_id">${options(S.groups, gid, false)}</select></label><label class="field">Word or word with definition<input name="entry" maxlength="10503" placeholder="e.g. salient: most noticeable" autocomplete="off" autocapitalize="off" spellcheck="false" autofocus></label><p class="subtle">Press Enter after every word. Use <code>word: definition</code>, <code>word = definition</code>, or <code>word - definition</code> for custom meanings. Words without one enrich in realtime.</p><div class="quick-add-status" aria-live="polite"><strong id="quick-add-count">0 words added</strong><span id="quick-add-status-text">Ready for your first word.</span></div><ol id="quick-add-log" class="quick-add-log" aria-label="Words added in this session"></ol><div class="form-actions"><button class="button secondary" type="button" data-action="detailed-add">Detailed editor</button><span class="spacer"></span><button class="button secondary" type="button" data-action="close">Done (Esc)</button><button class="button">Add</button></div></form>`);
  $('#quick-add-form [name=entry]').focus();
}

function deckEditor(id) {
  const g = S.groups.find(g => g.id === Number(id)) || {};
  dialog(id ? 'Edit deck' : 'Create a deck', `<form id="deck-editor" data-id="${id || ''}" class="form-grid"><label class="field full">Deck name<input name="name" maxlength="100" required value="${esc(g.name)}"></label><label class="field full">Description<textarea name="description">${esc(g.description)}</textarea></label><label class="field full">Terminal accent color<select name="color">${['cyan', 'green', 'blue', 'magenta', 'yellow', 'red', 'white'].map(c => `<option ${g.color === c ? 'selected' : ''}>${c}</option>`).join('')}</select></label><div class="form-actions full">${id ? `<button class="button danger" type="button" data-action="delete-deck" data-id="${id}">Delete deck</button>` : ''}<span class="spacer"></span><button class="button">Save deck</button></div></form>`);
}

async function route() {
  const version = ++S.routeVersion;
  S.page = location.hash.slice(1) || 'home';
  if (!titles[S.page]) S.page = 'home';
  $('#page-label').textContent = titles[S.page];
  document.title = `${titles[S.page]} · Vocab`;
  $('#navigation').innerHTML = nav.map(([key, title]) => `<a href="#${key}" class="nav-item ${S.page === key ? 'active' : ''}" data-page="${key}" ${S.page === key ? 'aria-current="page"' : ''} title="${title}">${icon(key)}<span>${title}</span></a>`).join('');
  $('#deck-scope').disabled = S.page === 'study';
  $('#content').innerHTML = '<div class="loading" role="status">Loading your workspace…</div>';
  try {
    if (S.page === 'study') {
      if (!S.sid) { location.hash = 'home'; return; }
      const d = await api(`sessions/${S.sid}`);
      if (version === S.routeVersion) renderStudy(d);
    } else {
      const html = await ({ home, library, decks, insights, check: checkPage, settings, research }[S.page])();
      if (version === S.routeVersion) $('#content').innerHTML = html;
    }
  } catch (error) {
    if (version !== S.routeVersion) return;
    $('#content').innerHTML = `<div class="panel empty"><h2>We couldn’t load this view.</h2><p>${esc(error.message)}</p><button class="button" data-action="retry">Try again</button> <a class="button secondary" href="#home">Overview</a></div>`;
    if (S.page === 'study') { S.sid = null; S.session = null; sessionStorage.removeItem('vocab.session'); }
  }
}

let busy = false;
async function runAction(fn, target) {
  if (busy) return;
  busy = true;
  const button = target?.closest('button');
  if (button) button.disabled = true;
  try {
    await fn();
  } catch (error) {
    toast(error.message, true);
    if ($('#modal').open) $('#modal-error').textContent = error.message;
  } finally {
    busy = false;
    if (button?.isConnected) button.disabled = false;
  }
}

/* Tactile keypress feedback helper */
function flashButtonFeedback(selector) {
  const btn = $(selector);
  if (btn) {
    btn.classList.add('keyboard-active');
    setTimeout(() => btn.classList.remove('keyboard-active'), 180);
  }
}

/* Global Click Handlers */
document.addEventListener('click', event => {
  if (event.target.closest('.skip-link')) { event.preventDefault(); $('#content').focus(); return; }
  const b = event.target.closest('[data-action]');
  if (!b) return;
  const { action, id, mode, op, grade, word } = b.dataset;

  runAction(async () => {
    if (action === 'close') $('#modal').close();
    else if (action === 'retry') await route();
    else if (action === 'shortcuts-help') showShortcutsModal();
    else if (action === 'speak') speakWord(word || S.session?.card?.word);
    else if (action === 'add-word') await quickAddDialog();
    else if (action === 'edit-word') await wordEditor(id);
    else if (action === 'detailed-add') await wordEditor(null, $('#quick-add-form')?.elements.group_id.value);
    else if (action === 'new-deck' || action === 'edit-deck') deckEditor(id);
    else if (action === 'session-options') sessionOptions();
    else if (action === 'start') await startSession({ mode });
    else if (action === 'deck-study' || action === 'browse-deck') {
      S.group = String(id);
      updateScope();
      if (action === 'deck-study') sessionOptions();
      else { S.offset = 0; S.filters = {}; location.hash = 'library'; }
    }
    else if (action === 'previous' || action === 'next-page') {
      S.offset += action === 'previous' ? -30 : 30;
      await renderLibraryTable();
    }
    else if (action === 'study') {
      if (op === 'end' && !confirm('Finish this session? Completed responses are saved.')) return;
      await studyAction({ action: op });
    }
    else if (action === 'grade') await studyAction({ action: 'grade', grade: Number(grade) });
    else if (action === 'choice') await studyAction({ action: 'answer', choice: Number(b.dataset.index) });
    else if (action === 'another-check') location.hash = 'check';
    else if (action === 'delete-word') {
      if (!confirm('Delete this word and its review history?')) return;
      await api(`words/${id}`, { method: 'DELETE' });
      $('#modal').close();
      toast('Word deleted.');
      if (S.page === 'study' && id && Number(id) === S.session?.card?.id) await studyAction({ action: 'skip' });
      else if (S.page === 'library') await renderLibraryTable();
      else if (S.page !== 'study') await route();
    }
    else if (action === 'delete-deck') {
      if (!confirm('Delete this deck, all its words, and their review history?')) return;
      await api(`groups/${id}`, { method: 'DELETE' });
      $('#modal').close();
      await refreshGroups();
      await route();
      toast('Deck deleted.');
    }
    else if (action === 'lookup') {
      const form = $('#word-editor'), wordVal = form.elements.word.value.trim();
      if (!wordVal) throw new Error('Enter a word first.');
      $('#lookup-status').textContent = ' Looking up…';
      const d = await api('dictionary', { method: 'POST', data: { word: wordVal } });
      if (form !== $('#word-editor') || form.elements.word.value.trim() !== wordVal) return;
      for (const key of ['definition', 'phonetic', 'pos', 'example']) {
        if (!form.elements[key].value && d.entry[key]) form.elements[key].value = d.entry[key];
      }
      if (d.chinese) form.elements.definition.value = [form.elements.definition.value, d.chinese].filter(Boolean).join('\n');
      $('#lookup-status').textContent = d.valid ? ' Dictionary details loaded.' : ` No verified match.${d.suggestion ? ` Try “${d.suggestion}”.` : ''} You can add the word manually.`;
    }
    else if (action === 'maintenance') {
      const messages = {
        seed: 'Add the curated starter decks to your library?',
        sync: 'Rebuild all schedules from saved reviews? This replaces stored schedules.',
        cleanup: 'Clear response-time values above your threshold? This changes saved timing history.'
      };
      if (!confirm(messages[op])) return;
      const r = await api('maintenance', { method: 'POST', data: { action: op } });
      await refreshGroups();
      await route();
      toast(Object.entries(r).map(([k, v]) => `${k.replaceAll('_', ' ')}: ${v}`).join(' · '));
    }
    else if (action === 'delete-check') {
      if (!confirm('Delete this vocabulary-check result?')) return;
      await api(`checks/${id}`, { method: 'DELETE' });
      await route();
    }
    else if (action === 'check-detail') {
      const history = (await api('checks')).history, t = history.find(t => t.id === Number(id));
      let details;
      try { details = JSON.parse(t.details_json); } catch { details = null; }
      dialog('Vocabulary-check result', details?.level_breakdown ? resultPanel(details) : `<p>${esc(t.score_pct)}% · ${t.correct_count} of ${t.total_questions} correct</p><p class="subtle">This historical result has no detailed breakdown.</p>`);
    }
  }, b);
});

/* Global Submit Handlers */
document.addEventListener('submit', event => {
  event.preventDefault();
  const form = event.target, values = Object.fromEntries(new FormData(form));
  runAction(async () => {
    if (form.id === 'filters') {
      S.filters = { ...values, due_only: form.elements.due_only.checked ? 'true' : '' };
      S.offset = 0;
      await renderLibraryTable();
    }
    else if (form.id === 'session-options') {
      for (const key of ['shuffle', 'fill_placeholders', 'force_all']) values[key] = form.elements[key].checked;
      values.limit = Number(values.limit);
      await startSession(values);
    }
    else if (form.id === 'check-options') {
      await startSession({ ...values, limit: Number(values.limit), mode: 'check' });
    }
    else if (form.id === 'typing-answer') {
      const answer = String(values.answer || '').trim(), command = answer.toLowerCase();
      if (S.keyboardControls && [':q', 'quit', 'exit'].includes(command)) await studyAction({ action: 'end' });
      else if (S.keyboardControls && [':s', ':shuffle', 'shuffle'].includes(command)) await studyAction({ action: 'shuffle' });
      else await studyAction({ action: 'answer', answer: S.keyboardControls && ['', '?', 'skip'].includes(command) ? 'skip' : answer });
    }
    else if (form.id === 'word-editor') {
      const id = form.dataset.id, another = form.elements.another?.checked;
      delete values.another;
      if (id) values.retired = form.elements.retired.checked;
      await api(id ? `words/${id}` : 'words', { method: id ? 'PATCH' : 'POST', data: values });
      toast('Word saved.');
      if (another) {
        await wordEditor();
        $('#word-editor [name=group_id]').value = values.group_id;
        $('#word-editor [name=another]').checked = true;
      } else {
        $('#modal').close();
        if (S.page === 'study' && id && Number(id) === S.session?.card?.id) await studyAction({ action: 'skip' });
        else if (S.page === 'library') await renderLibraryTable();
        else if (S.page !== 'study') await route();
      }
    }
    else if (form.id === 'quick-add-form') {
      const input = form.elements.entry, entry = input.value.trim(), command = entry.toLowerCase();
      if (!entry) { input.focus(); return; }
      if ([':q', 'quit', 'exit', ':quit', ':exit'].includes(command)) { $('#modal').close(); return; }
      const result = await api('words/quick', { method: 'POST', data: { group_id: values.group_id, entry } });
      if (result.quit) { $('#modal').close(); return; }
      const count = $('#quick-add-count'), log = $('#quick-add-log'), statusText = $('#quick-add-status-text');
      let added = Number(form.dataset.added || 0);
      if (!result.duplicate) {
        added += 1;
        form.dataset.added = String(added);
      }
      count.textContent = `${added} ${added === 1 ? 'word' : 'words'} added`;
      if (statusText) statusText.textContent = result.duplicate ? 'Duplicate skipped.' : result.enriching ? 'Saved · fetching definitions in background…' : 'Saved to deck.';

      if (result.enriching && result.word?.id) {
        S.watchingIds.add(result.word.id);
      }

      log.insertAdjacentHTML('afterbegin', `<li data-id="${result.word.id}"><strong>${esc(result.word.word)}</strong><span>${result.duplicate ? 'Already in this deck' : result.enriching ? '<span class="enrich-spinner"></span>Fetching meaning…' : esc(result.word.definition || 'Saved')}</span></li>`);
      input.value = '';
      input.focus();
    }
    else if (form.id === 'deck-editor') {
      const id = form.dataset.id;
      await api(id ? `groups/${id}` : 'groups', { method: id ? 'PATCH' : 'POST', data: values });
      $('#modal').close();
      await refreshGroups();
      await route();
      toast('Deck saved.');
    }
    else if (form.id === 'export-form') {
      const a = document.createElement('a');
      a.href = `/api/export?${new URLSearchParams(values)}`;
      a.download = '';
      a.click();
    }
    else if (form.id === 'import-form') {
      const r = await api('import', { method: 'POST', form: new FormData(form) });
      await refreshGroups();
      await route();
      toast(`Imported ${r.words_added} words into ${r.groups_added} new decks.`);
    }
    else if (form.id === 'threshold-form') {
      const r = await api('maintenance', { method: 'POST', data: { action: 'threshold', value: Number(values.value) } });
      S.threshold = r.threshold;
      toast(`Timing threshold saved: ${r.threshold} seconds.`);
    }
  }, event.submitter);
});

/* Realtime debounced search & filter inputs in Library */
let searchDebounceTimer;
document.addEventListener('input', event => {
  if (event.target.closest('#filters') && event.target.name === 'search') {
    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(async () => {
      const form = $('#filters');
      if (!form) return;
      const values = Object.fromEntries(new FormData(form));
      S.filters = { ...values, due_only: form.elements.due_only.checked ? 'true' : '' };
      S.offset = 0;
      await renderLibraryTable();
    }, 240);
  }
});

/* Instant Filter Changes */
document.addEventListener('change', event => {
  const form = event.target.closest('#filters');
  if (form && ['state', 'pos', 'tag', 'sort', 'order', 'due_only'].includes(event.target.name)) {
    const values = Object.fromEntries(new FormData(form));
    S.filters = { ...values, due_only: form.elements.due_only.checked ? 'true' : '' };
    S.offset = 0;
    renderLibraryTable();
  }
});

/* Keyboard Move Set & Shortcuts */
document.addEventListener('keydown', event => {
  // Global Esc key closes modal or blurs search
  if (event.key === 'Escape') {
    if ($('#modal').open) {
      $('#modal').close();
      event.preventDefault();
      return;
    }
    if (document.activeElement?.tagName === 'INPUT') {
      document.activeElement.blur();
      event.preventDefault();
      return;
    }
  }

  // Handle typing practice hint peek on Tab
  if (S.page === 'study' && S.session?.mode === 'typing' && event.key === 'Tab' && event.target.name === 'answer') {
    event.preventDefault();
    const input = event.target;
    const targetWord = S.session?.card?.word || '';
    if (targetWord) {
      const current = input.value;
      if (!current) {
        input.value = targetWord.slice(0, 1);
      } else if (targetWord.toLowerCase().startsWith(current.toLowerCase()) && current.length < targetWord.length) {
        input.value = targetWord.slice(0, current.length + 1);
      }
      toast(`Hint: ${input.value}…`);
    }
    return;
  }

  // Ignore shortcuts when editing text or when controls are disabled
  if (!S.keyboardControls || $('#modal').open || busy || event.repeat || event.ctrlKey || event.altKey || event.metaKey || ['INPUT', 'TEXTAREA', 'SELECT'].includes(event.target.tagName)) return;

  const pressed = event.key.toLowerCase();

  // Move set help modal (?)
  if (event.key === '?' || (pressed === 'h' && event.shiftKey)) {
    event.preventDefault();
    showShortcutsModal();
    return;
  }

  // Global quick search trigger (/)
  if (event.key === '/') {
    event.preventDefault();
    if (S.page !== 'library') {
      location.hash = 'library';
      setTimeout(() => {
        const searchInput = $('#filters [name=search]');
        searchInput?.focus();
        searchInput?.select();
      }, 150);
    } else {
      const searchInput = $('#filters [name=search]');
      searchInput?.focus();
      searchInput?.select();
    }
    return;
  }

  // Top-level Navigation Keys: 1-9, t
  if (['home', 'library', 'decks', 'insights'].includes(S.page)) {
    const destinations = { '6': 'library', '7': 'insights', '8': 'decks', '9': 'settings', 't': 'check' };
    if (destinations[pressed]) {
      event.preventDefault();
      location.hash = destinations[pressed];
      return;
    }
  }

  // Overview / Home Shortcuts
  if (S.page === 'home') {
    const dashboardActions = {
      '1': '[data-action="start"][data-mode="flashcard"]',
      '2': '[data-action="start"][data-mode="typing"]',
      '3': '[data-action="start"][data-mode="quiz"]',
      '5': '[data-action="add-word"]',
      'n': '[data-action="add-word"]',
      '+': '[data-action="add-word"]'
    };
    if (dashboardActions[pressed] && $(dashboardActions[pressed])) {
      event.preventDefault();
      $(dashboardActions[pressed]).click();
      return;
    }
    if (pressed === '4') {
      event.preventDefault();
      $('#deck-scope').focus();
      toast('Choose a deck with arrow keys, then press Enter.');
      return;
    }
  }

  // Library Move Set
  if (S.page === 'library') {
    if (pressed === 'j' || event.key === 'ArrowDown') {
      event.preventDefault();
      updateLibraryCursor(S.libraryCursor + 1);
      return;
    }
    if (pressed === 'k' || event.key === 'ArrowUp') {
      event.preventDefault();
      updateLibraryCursor(S.libraryCursor - 1);
      return;
    }
    if (pressed === 'enter' || pressed === 'e') {
      event.preventDefault();
      const currentWord = S.libraryWords[S.libraryCursor];
      if (currentWord) wordEditor(currentWord.id);
      return;
    }
    if (pressed === 'm' || event.code === 'Space') {
      event.preventDefault();
      const currentWord = S.libraryWords[S.libraryCursor];
      if (currentWord) {
        const newMastery = currentWord.state !== 'mastered';
        runAction(async () => {
          await api(`words/${currentWord.id}`, { method: 'PATCH', data: { retired: newMastery } });
          currentWord.state = newMastery ? 'mastered' : 'review';
          toast(`"${currentWord.word}" is now ${newMastery ? 'retired' : 'active'}.`);
          renderLibraryTable();
        });
      }
      return;
    }
    if (pressed === 'x' || event.key === 'Delete') {
      event.preventDefault();
      const currentWord = S.libraryWords[S.libraryCursor];
      if (currentWord && confirm(`Delete "${currentWord.word}" from your library?`)) {
        runAction(async () => {
          await api(`words/${currentWord.id}`, { method: 'DELETE' });
          toast(`"${currentWord.word}" deleted.`);
          renderLibraryTable();
        });
      }
      return;
    }
    if (pressed === 'h' || event.key === 'ArrowLeft') {
      if (S.offset > 0) {
        event.preventDefault();
        S.offset = Math.max(0, S.offset - 30);
        renderLibraryTable();
      }
      return;
    }
    if (pressed === 'l' || event.key === 'ArrowRight') {
      event.preventDefault();
      S.offset += 30;
      renderLibraryTable();
      return;
    }
    if (pressed === 'n' || pressed === '+') {
      event.preventDefault();
      quickAddDialog();
      return;
    }
  }

  // Decks Move Set
  if (S.page === 'decks') {
    if (pressed === 'j' || event.key === 'ArrowDown' || event.key === 'ArrowRight') {
      event.preventDefault();
      updateDecksCursor(S.decksCursor + 1);
      return;
    }
    if (pressed === 'k' || event.key === 'ArrowUp' || event.key === 'ArrowLeft') {
      event.preventDefault();
      updateDecksCursor(S.decksCursor - 1);
      return;
    }
    const currentDeck = S.groups[S.decksCursor];
    if (pressed === 's' && currentDeck) {
      event.preventDefault();
      S.group = String(currentDeck.id);
      updateScope();
      sessionOptions();
      return;
    }
    if ((pressed === 'enter' || pressed === 'b') && currentDeck) {
      event.preventDefault();
      S.group = String(currentDeck.id);
      updateScope();
      S.offset = 0;
      S.filters = {};
      location.hash = 'library';
      return;
    }
    if (pressed === 'e' && currentDeck) {
      event.preventDefault();
      deckEditor(currentDeck.id);
      return;
    }
    if (pressed === 'c') {
      event.preventDefault();
      deckEditor(null);
      return;
    }
  }

  // Study Session Move Set
  if (S.page !== 'study') return;

  // Speech pronunciation (p or r)
  if (pressed === 'p' || pressed === 'r') {
    event.preventDefault();
    speakWord(S.session?.card?.word);
    return;
  }

  let selector;

  // Reveal / Continue on Space or Enter or f or ArrowDown
  if (event.code === 'Space' || pressed === 'f') {
    selector = '[data-op="reveal"]';
  }
  if (event.key === 'Enter') {
    selector = S.session?.phase === 'introduction' ? '[data-op="introduce"]' : S.session?.phase === 'question' && S.session?.mode === 'flashcard' ? '[data-op="reveal"]' : '[data-op="next"]';
  }
  if (event.key === 'ArrowDown' && S.session?.phase === 'question' && S.session?.mode === 'flashcard') {
    selector = '[data-op="reveal"]';
  }

  // Arrow key ratings when revealed
  if (S.session?.phase === 'revealed') {
    if (event.key === 'ArrowLeft') { selector = '[data-grade="1"]'; flashButtonFeedback(selector); }
    else if (event.key === 'ArrowDown') { selector = '[data-grade="2"]'; flashButtonFeedback(selector); }
    else if (event.key === 'ArrowUp') { selector = '[data-grade="3"]'; flashButtonFeedback(selector); }
    else if (event.key === 'ArrowRight') { selector = '[data-grade="4"]'; flashButtonFeedback(selector); }
  }

  // Letter key ratings: a (Again), h (Hard), g (Good), e (Easy)
  if (S.session?.phase === 'revealed') {
    if (pressed === 'a') { selector = '[data-grade="1"]'; flashButtonFeedback(selector); }
    else if (pressed === 'h') { selector = '[data-grade="2"]'; flashButtonFeedback(selector); }
    else if (pressed === 'g') { selector = '[data-grade="3"]'; flashButtonFeedback(selector); }
    else if (pressed === 'e') { selector = '[data-grade="4"]'; flashButtonFeedback(selector); }
  }

  // Number keys 1-4
  if (/^[1-4]$/.test(event.key)) {
    if (S.session?.phase === 'revealed') {
      selector = `[data-grade="${event.key}"]`;
      flashButtonFeedback(selector);
    } else if (S.session?.phase === 'question' && ['quiz', 'check'].includes(S.session?.mode)) {
      selector = `[data-index="${Number(event.key) - 1}"]`;
    }
  }

  // Choice navigation in Quiz / Check with j/k or up/down
  if (S.session?.phase === 'question' && ['quiz', 'check'].includes(S.session?.mode)) {
    if (pressed === 'j' || event.key === 'ArrowDown') {
      event.preventDefault();
      updateChoiceCursor(S.choiceCursor + 1);
      return;
    }
    if (pressed === 'k' || event.key === 'ArrowUp') {
      event.preventDefault();
      updateChoiceCursor(S.choiceCursor - 1);
      return;
    }
    if (pressed === 'enter') {
      selector = `[data-index="${S.choiceCursor}"]`;
    }
  }

  // Study actions
  if (pressed === 's' && ['flashcard', 'quiz'].includes(S.session?.mode)) selector = '[data-op="shuffle"]';
  if (pressed === 'e' && S.session?.mode === 'flashcard' && S.session?.phase !== 'revealed') selector = '[data-action="edit-word"]';
  if (pressed === 'd' && S.session?.mode === 'flashcard' && S.session?.phase !== 'revealed') selector = '[data-action="delete-word"]';
  if (pressed === 'q') selector = '[data-op="end"]';

  if (selector && $(selector)) {
    event.preventDefault();
    $(selector).click();
  }
});

/* Settings Toggle */
document.addEventListener('change', event => {
  if (event.target.id !== 'keyboard-controls') return;
  runAction(async () => {
    const previous = S.keyboardControls;
    const enabled = event.target.checked;
    try {
      const result = await api('maintenance', { method: 'POST', data: { action: 'keyboard', enabled } });
      S.keyboardControls = result.keyboard_controls;
      $('.switch-label').textContent = S.keyboardControls ? 'On' : 'Off';
      toast(`Keyboard controls & move set are ${S.keyboardControls ? 'on' : 'off'}.`);
    } catch (error) {
      event.target.checked = previous;
      throw error;
    }
  }, event.target);
});

$('#deck-scope').addEventListener('change', async event => {
  S.group = event.target.value;
  S.offset = 0;
  updateScope();
  await route();
});

window.addEventListener('hashchange', () => {
  $('#modal').close();
  route();
});

/* Boot App */
async function boot() {
  try {
    const d = await api('bootstrap');
    S.csrf = d.csrf;
    S.groups = d.groups;
    S.keyboardControls = d.keyboard_controls;
    S.threshold = d.threshold || 30;
    updateScope();
    if (S.sid) {
      try { S.session = await api(`sessions/${S.sid}`); }
      catch { S.sid = null; S.session = null; sessionStorage.removeItem('vocab.session'); }
    }
    await route();
    startRealtimeSync();
  } catch (error) {
    $('#content').innerHTML = `<div class="panel empty"><h2>Connection unavailable</h2><p>${esc(error.message)}</p><p>Start the local server with <code>python main.py web</code>, then reload this page.</p></div>`;
  }
}
boot();

/* MegaMail — Frontend */
'use strict';

// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  results:         [],
  config:          {},
  criteriaColumns: [],
  sort:            { col: null, asc: true },
  excelRunning:    false,
  emailBatchRunning: false,
  emailRunning:    false,
  uploadedFile:    null,
  resultSource:    'all',   // 'all' | 'excel' | 'email' | 'uploaded'
};

let _detailResult = null;

// ── Helpers ───────────────────────────────────────────────────────────────────

function customKey(name) {
  if (!name) return '';
  return name.charAt(0).toUpperCase() + name.slice(1).toLowerCase();
}

function getCustomCols() {
  return state.criteriaColumns.filter(c => !c.builtin);
}

/** Ensure every result has _batch_source so source-tab counts work. */
function normalizeResult(r) {
  if (r._batch_source) return r;
  // Infer from fields: email results have Subject/Sender
  const src = (r.Subject !== undefined || r.Sender !== undefined) ? 'email' : 'excel';
  return { ...r, _batch_source: src };
}

function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function typBadge(typ) { return `<span class="badge badge-${typ||'unclear'}">${typ||'unclear'}</span>`; }

function confBar(n) {
  const pct = Math.round(((n||0)/10)*100);
  const col = n>=7 ? 'var(--green)' : n>=4 ? 'var(--yellow)' : 'var(--red)';
  return `<div title="Confidence: ${n}/10" style="display:inline-flex;align-items:center;gap:6px">
    <div style="width:44px;height:5px;background:#dee2e6">
      <div style="width:${pct}%;height:100%;background:${col}"></div></div>
    <span style="font-size:10px;color:var(--muted)">${n}/10</span>
  </div>`;
}

let toastTimer = null;
function showToast(msg) {
  const t = document.getElementById('toast-el');
  t.textContent = msg; t.style.display = 'block';
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.style.display = 'none'; }, 2500);
}

async function api(method, url, body) {
  try {
    const opts = { method, headers: {} };
    if (body) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    const res = await fetch(url, opts);
    if (!res.ok && res.status !== 404) return null;
    return await res.json();
  } catch (_) { return null; }
}

// ── WebSocket ─────────────────────────────────────────────────────────────────
let ws = null;
let wsTimer = null;

function connectWS() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onopen = () => {
    document.getElementById('ws-badge').className = 'badge bg-success';
    document.getElementById('ws-badge').innerHTML = '<i class="bi bi-wifi me-1"></i>WS';
    if (wsTimer) { clearTimeout(wsTimer); wsTimer = null; }
    setInterval(() => { if (ws.readyState === WebSocket.OPEN) ws.send('ping'); }, 20000);
  };
  ws.onmessage = (e) => { try { handleWsMessage(JSON.parse(e.data)); } catch (_) {} };
  ws.onclose = () => {
    document.getElementById('ws-badge').className = 'badge bg-warning text-dark';
    document.getElementById('ws-badge').innerHTML = '<i class="bi bi-wifi-off me-1"></i>WS';
    wsTimer = setTimeout(connectWS, 3000);
  };
}

function handleWsMessage(data) {
  switch (data.type) {
    case 'batch_start':          onBatchStart(data);          break;
    case 'progress':             onBatchProgress(data);       break;
    case 'batch_done':           onBatchDone(data);           break;
    case 'batch_error':
      logBatch(`ERROR: ${data.error}`, 'log-err');
      setBatchStatus('Error', 'bg-danger');
      state.excelRunning = false;
      document.getElementById('btn-start-batch').disabled = false;
      document.getElementById('btn-stop-excel').classList.add('d-none');
      break;
    case 'excel_queued':
      document.getElementById('excel-queue-msg').classList.remove('d-none');
      setBatchStatus('Queued', 'bg-warning text-dark');
      break;
    case 'email_classified':     onEmailClassified(data.result);    break;
    case 'email_error':          addEmailFeedItem({ error: data.error }); break;
    case 'email_batch_start':    onEmailBatchStart(data);      break;
    case 'email_batch_progress': onEmailBatchProgress(data);   break;
    case 'email_batch_done':     onEmailBatchDone(data);       break;
    case 'email_batch_error':
      logEmailBatch(`ERROR: ${data.error}`, 'log-err');
      setEmailBatchStatus('Error', 'bg-danger');
      state.emailBatchRunning = false;
      document.getElementById('btn-em-fetch').disabled = false;
      document.getElementById('btn-stop-email-batch').classList.add('d-none');
      break;
    case 'email_queued':
      document.getElementById('email-queue-msg').classList.remove('d-none');
      setEmailBatchStatus('Queued', 'bg-warning text-dark');
      break;
  }
}

// ── Batch events ──────────────────────────────────────────────────────────────
function onBatchStart(data) {
  state.excelRunning = true;
  setBatchStatus('Running…', 'bg-primary');
  logBatch(`Started: ${data.new} new + ${data.skipped} from checkpoint (total ${data.total})`, 'log-ok');
  document.getElementById('batch-progress').style.width = '0%';
  document.getElementById('btn-stop-excel').classList.remove('d-none');
  document.getElementById('excel-queue-msg').classList.add('d-none');
}
function onBatchProgress(data) {
  const pct = Math.round((data.done / data.total) * 100);
  document.getElementById('batch-progress').style.width = pct + '%';
  document.getElementById('batch-eta').textContent = `${data.done}/${data.total} — ETA ${data.eta}s`;
  const r = normalizeResult(data.result);
  logBatch(`[${r._source}] ID=${r.ID} | ${r.Typ} | ${r.Priorytet} | ${r.Serwis}${r.Email_alert?'  📧':''}`,
    r.Email_alert ? 'log-email' : 'log-ok');
  state.results.push(r);
  updateResultsCount();
  updateSourceCounts();
}
function onBatchDone(data) {
  const stopped = data.stopped;
  setBatchStatus(stopped ? 'Stopped' : 'Done', stopped ? 'bg-warning text-dark' : 'bg-success');
  document.getElementById('batch-progress').style.width = stopped ? '' : '100%';
  document.getElementById('batch-eta').textContent = stopped ? 'Stopped.' : 'Complete.';
  logBatch(stopped ? '⏹ Batch stopped.' : `✓ Finished. Total: ${data.results.length}`, 'log-ok');
  state.results = (data.results || state.results).map(normalizeResult);
  state.excelRunning = false;
  document.getElementById('btn-start-batch').disabled = false;
  document.getElementById('btn-stop-excel').classList.add('d-none');
  document.getElementById('btn-download').disabled    = false;
  document.getElementById('btn-dl-results').disabled  = false;
  updateDashboard();
  updateSourceCounts();
  renderCustomFilters();
  renderResultsTable();
}

// ── Email batch (fetch & classify) ───────────────────────────────────────────

function setEmailBatchStatus(text, cls) {
  const el = document.getElementById('em-batch-badge');
  el.className = `badge ${cls}`; el.textContent = text;
}
function logEmailBatch(msg, cls = '') {
  const wrap = document.getElementById('em-fetch-progress-wrap');
  wrap.classList.remove('d-none');
  const el = document.getElementById('em-fetch-log');
  const line = document.createElement('div');
  if (cls) line.className = cls;
  line.textContent = msg; el.appendChild(line); el.scrollTop = el.scrollHeight;
}
function onEmailBatchStart(data) {
  state.emailBatchRunning = true;
  document.getElementById('btn-em-fetch').disabled = true;
  document.getElementById('btn-stop-email-batch').classList.remove('d-none');
  document.getElementById('em-fetch-progress-wrap').classList.remove('d-none');
  document.getElementById('em-fetch-progress').style.width = '0%';
  document.getElementById('em-fetch-log').innerHTML = '';
  document.getElementById('email-queue-msg').classList.add('d-none');
  setEmailBatchStatus('Running…', 'bg-primary');
  logEmailBatch(`Fetching ${data.total} emails…`, 'log-ok');
}
function onEmailBatchProgress(data) {
  const pct = Math.round((data.done / data.total) * 100);
  document.getElementById('em-fetch-progress').style.width = pct + '%';
  document.getElementById('em-fetch-eta').textContent = `${data.done}/${data.total} — ETA ${data.eta}s`;
  const r = normalizeResult(data.result);
  logEmailBatch(`[${r._source}] ${r.Subject||r.ID} | ${r.Typ} | ${r.Priorytet}${r.Email_alert ? '  📧' : ''}`,
    r.Email_alert ? 'log-email' : 'log-ok');
  state.results.push(r);
  updateResultsCount();
  updateSourceCounts();
}
function onEmailBatchDone(data) {
  const stopped = data.stopped;
  setEmailBatchStatus(stopped ? 'Stopped' : 'Done', stopped ? 'bg-warning text-dark' : 'bg-success');
  document.getElementById('em-fetch-progress').style.width = stopped ? '' : '100%';
  document.getElementById('em-fetch-eta').textContent = stopped ? 'Stopped.' : 'Complete.';
  logEmailBatch(stopped ? '⏹ Batch stopped.' : `✓ Finished. Total results: ${data.results.length}`, 'log-ok');
  state.results = (data.results || state.results).map(normalizeResult);
  state.emailBatchRunning = false;
  document.getElementById('btn-em-fetch').disabled = false;
  document.getElementById('btn-stop-email-batch').classList.add('d-none');
  document.getElementById('btn-dl-results').disabled = false;
  updateDashboard();
  updateSourceCounts();
  renderCustomFilters();
  renderResultsTable();
}

document.getElementById('btn-em-fetch').addEventListener('click', async () => {
  const form = getEmailForm();
  if (!form.host || !form.username) {
    const msg = document.getElementById('em-status-msg');
    msg.classList.remove('d-none', 'text-success'); msg.classList.add('text-danger');
    msg.textContent = 'Fill in Host and Username above first.';
    return;
  }
  const limit     = parseInt(document.getElementById('em-fetch-limit').value) || 200;
  const date_from = document.getElementById('em-date-from').value || null;
  const date_to   = document.getElementById('em-date-to').value   || null;
  setEmailBatchStatus('Fetching…', 'bg-warning text-dark');
  try {
    const httpRes = await fetch('/api/email/classify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...form, limit, date_from, date_to }),
    });
    const res = await httpRes.json();
    if (!httpRes.ok || !res?.ok) {
      logEmailBatch(`Error (HTTP ${httpRes.status}): ${res?.error || 'Unknown error'}`, 'log-err');
      setEmailBatchStatus('Error', 'bg-danger');
    } else if (res.queued) {
      document.getElementById('email-queue-msg').classList.remove('d-none');
      setEmailBatchStatus('Queued', 'bg-warning text-dark');
    }
  } catch (e) {
    logEmailBatch(`Network error: ${e.message}`, 'log-err');
    setEmailBatchStatus('Error', 'bg-danger');
  }
});

document.getElementById('btn-stop-email-batch').addEventListener('click', async () => {
  await api('POST', '/api/email/classify/stop');
  document.getElementById('email-queue-msg').classList.add('d-none');
});

// ── Email events ──────────────────────────────────────────────────────────────
function onEmailClassified(result) {
  state.results.push(normalizeResult(result));
  addEmailFeedItem(result);
  updateResultsCount();
  updateSourceCounts();
  updateDashboard();
  renderCustomFilters();
}
function addEmailFeedItem(item) {
  const feed = document.getElementById('email-feed');
  const ph = feed.querySelector('.text-muted');
  if (ph) ph.remove();
  if (item.error) {
    const d = document.createElement('div');
    d.className = 'email-item text-danger'; d.textContent = `⚠ ${item.error}`;
    feed.prepend(d); return;
  }
  const d = document.createElement('div');
  d.className = 'email-item';
  d.innerHTML = `
    <div class="d-flex justify-content-between">
      <strong class="text-truncate" style="max-width:300px">${esc(item.Subject||'(no subject)')}</strong>
      ${typBadge(item.Typ||item.typ)}
    </div>
    <div class="text-muted" style="font-size:11px">${esc(item.Sender||'')} · ${esc(item.Created||'')}</div>
    <div class="mt-1">${esc((item.Streszczenie||'').substring(0,120))}</div>`;
  feed.prepend(d);
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
function updateDashboard() {
  const r = state.results;
  document.getElementById('stat-total').textContent = r.length;
  document.getElementById('stat-open').textContent  = r.filter(x=>(x.Status||x.status)==='open').length;
  document.getElementById('stat-email').textContent = r.filter(x=>x.Email_alert||x.email_alert).length;
  document.getElementById('stat-cache').textContent = r.filter(x=>(x._source||'')==='cache').length;

  const counts = {};
  for (const x of r) { const t=x.Typ||x.typ||'unclear'; counts[t]=(counts[t]||0)+1; }
  const mx = Math.max(1,...Object.values(counts));
  document.getElementById('chart-typ').innerHTML = Object.entries(counts)
    .sort((a,b)=>b[1]-a[1])
    .map(([t,n])=>`<div class="bar-row">
      <span class="bar-label">${t}</span>
      <div class="bar-fill" style="width:${Math.round((n/mx)*200)}px"></div>
      <span class="bar-count">${n}</span></div>`).join('')
    || '<span class="text-muted small">No data.</span>';

  const recent = [...r].reverse().slice(0,8);
  document.getElementById('recent-list').innerHTML = recent.length
    ? recent.map(x=>`<li class="list-group-item py-2 px-3">
        <div class="d-flex justify-content-between align-items-center">
          <span class="fw-semibold small">ID ${x.ID}</span>${typBadge(x.Typ||x.typ)}
        </div>
        <div class="text-muted" style="font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:400px">
          ${esc((x.Streszczenie||'').substring(0,100))}</div></li>`).join('')
    : '<li class="list-group-item text-muted small">No results yet.</li>';
}
function updateResultsCount() { document.getElementById('results-count').textContent = state.results.length; }

function updateSourceCounts() {
  const all      = state.results.length;
  const excel    = state.results.filter(r => r._batch_source === 'excel').length;
  const email    = state.results.filter(r => r._batch_source === 'email').length;
  const uploaded = state.results.filter(r => r._batch_source === 'uploaded').length;
  document.getElementById('src-count-all').textContent      = all;
  document.getElementById('src-count-excel').textContent    = excel;
  document.getElementById('src-count-email').textContent    = email;
  document.getElementById('src-count-uploaded').textContent = uploaded;
}

// Source tab switching
document.querySelectorAll('[data-src]').forEach(a => {
  a.addEventListener('click', e => {
    e.preventDefault();
    document.querySelectorAll('[data-src]').forEach(x => x.classList.remove('active'));
    a.classList.add('active');
    state.resultSource = a.dataset.src;
    renderResultsTable();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// RESULTS TABLE
// ─────────────────────────────────────────────────────────────────────────────

const BUILT_IN_COLS = [
  { key: 'ID',         label: 'ID' },
  { key: 'Created',    label: 'Date' },
  { key: '_batch_source', label: 'Source', render: r => {
    const s = r._batch_source || '';
    const col = {excel:'success', email:'primary', uploaded:'secondary'}[s] || 'secondary';
    return `<span class="badge bg-${col}">${s||'?'}</span>`;
  }},
  { key: 'Typ',        label: 'Type',     render: r => typBadge(r.Typ||r.typ||'') },
  { key: 'Priorytet',  label: 'Priority', render: r => `<span class="badge badge-${r.Priorytet||r.priorytet||''}">${r.Priorytet||r.priorytet||''}</span>` },
  { key: 'Serwis',     label: 'Service' },
  { key: 'Akcja',      label: 'Action',   render: r => `<span class="badge bg-secondary">${esc(r.Akcja||r.akcja||'')}</span>` },
  { key: 'Status',     label: 'Status',   render: r => `<span class="badge badge-${r.Status||r.status||''}">${r.Status||r.status||''}</span>` },
  { key: 'Confidence', label: 'Conf.',    render: r => confBar(r.Confidence||r.confidence||0) },
  { key: 'Streszczenie', label: 'Summary', cls: 'summary-cell' },
];

function getActiveCols() {
  const customCols = getCustomCols().map(c => ({
    key:    customKey(c.name),
    label:  c.name,
    custom: true,
  }));
  const idx = BUILT_IN_COLS.findIndex(c => c.key === 'Status');
  return [
    ...BUILT_IN_COLS.slice(0, idx),
    ...customCols,
    ...BUILT_IN_COLS.slice(idx),
  ];
}

function getFilteredSorted() {
  const typF  = document.getElementById('filter-typ')?.value || '';
  const priF  = document.getElementById('filter-priorytet')?.value || '';
  const stF   = document.getElementById('filter-status')?.value || '';
  const serF  = document.getElementById('filter-serwis')?.value || '';
  const srch  = (document.getElementById('filter-search')?.value||'').toLowerCase();

  const customFilters = {};
  for (const col of getCustomCols()) {
    const el = document.getElementById(`filter-custom-${col.key}`);
    if (el && el.value) customFilters[customKey(col.name)] = el.value;
  }

  let list = state.results.filter(r => {
    // Source tab filter
    if (state.resultSource !== 'all' && r._batch_source !== state.resultSource) return false;

    const typ = r.Typ||r.typ||''; const pri = r.Priorytet||r.priorytet||'';
    const st  = r.Status||r.status||''; const ser = r.Serwis||r.serwis||'';
    const sum = (r.Streszczenie||r.streszczenie||'').toLowerCase();
    if (typF && typ !== typF) return false;
    if (priF && pri !== priF) return false;
    if (stF  && st  !== stF)  return false;
    if (serF && ser !== serF) return false;
    if (srch && !sum.includes(srch) && !String(r.ID).includes(srch)) return false;
    for (const [k, v] of Object.entries(customFilters)) {
      if (v && r[k] !== v) return false;
    }
    return true;
  });

  if (state.sort.col) {
    const k = state.sort.col;
    list = [...list].sort((a, b) => {
      let va = a[k] ?? ''; let vb = b[k] ?? '';
      if (typeof va === 'number' && typeof vb === 'number')
        return state.sort.asc ? va - vb : vb - va;
      va = String(va).toLowerCase(); vb = String(vb).toLowerCase();
      return state.sort.asc ? va.localeCompare(vb) : vb.localeCompare(va);
    });
  }

  return list;
}

function renderResultsTable() {
  const cols   = getActiveCols();
  const list   = getFilteredSorted();
  const thead  = document.getElementById('results-thead-row');
  const tbody  = document.getElementById('results-tbody');
  const empty  = document.getElementById('results-empty');

  thead.innerHTML = cols.map(col => {
    const isSorted = state.sort.col === col.key;
    const sortCls  = isSorted ? (state.sort.asc ? 'sort-asc' : 'sort-desc') : '';
    const arrow    = isSorted ? (state.sort.asc ? '↑' : '↓') : '↕';
    return `<th data-sortkey="${col.key}" class="${sortCls}" title="Sort by ${col.label}">
      ${col.label}<span class="sort-arrow">${arrow}</span>
    </th>`;
  }).join('') + '<th class="correct-btn-cell" style="cursor:default"></th>';

  thead.querySelectorAll('th[data-sortkey]').forEach(th => {
    th.addEventListener('click', () => {
      const k = th.dataset.sortkey;
      if (state.sort.col === k) state.sort.asc = !state.sort.asc;
      else { state.sort.col = k; state.sort.asc = true; }
      renderResultsTable();
    });
  });

  empty.classList.toggle('d-none', list.length > 0);
  if (!list.length) { tbody.innerHTML = ''; return; }

  tbody.innerHTML = list.map(r => {
    const cells = cols.map(col => {
      let val;
      if (col.render) {
        val = col.render(r);
      } else {
        const raw = r[col.key] ?? r[col.key?.toLowerCase()] ?? '';
        val = esc(String(raw).substring(0, col.cls === 'summary-cell' ? 80 : 200));
      }
      const title = col.cls === 'summary-cell' ? `title="${esc(r.Streszczenie||r.streszczenie||'')}"` : '';
      return `<td class="${col.cls||''}" ${title}>${val}</td>`;
    }).join('');

    const rJson = esc(JSON.stringify(r));
    return `<tr data-result='${rJson.replace(/'/g,"&#39;")}' style="cursor:pointer">
      ${cells}
      <td class="correct-btn-cell" onclick="event.stopPropagation()">
        <button class="btn btn-outline-secondary btn-sm py-0 px-1"
          onclick="openDetailModal(getResultById('${esc(String(r.ID))}'), true)" title="Correct (RL)">✏</button>
      </td>
    </tr>`;
  }).join('');

  // Row click → open in new tab
  tbody.querySelectorAll('tr').forEach(tr => {
    tr.addEventListener('click', () => {
      try {
        const r = JSON.parse(tr.dataset.result || '{}');
        openMessageInNewTab(r);
      } catch (_) {}
    });
  });
}

function getResultById(id) {
  return state.results.find(r => String(r.ID) === String(id)) || {};
}

function openMessageInNewTab(r) {
  window.open(`/message?id=${encodeURIComponent(String(r.ID))}`, '_blank');
}

// ─────────────────────────────────────────────────────────────────────────────
// DETAIL MODAL (for corrections)
// ─────────────────────────────────────────────────────────────────────────────

function openDetailModal(r, showCorrection) {
  _detailResult = r;

  document.getElementById('dm-id').textContent = r.ID || '';
  document.getElementById('dm-date').textContent = r.Created || '';
  const srcBadge = document.getElementById('dm-source-badge');
  srcBadge.textContent = r._source || 'ai';
  srcBadge.className = 'badge ms-2 ' + ({rules:'bg-info',cache:'bg-secondary',fallback:'bg-danger'}[r._source] || 'bg-primary');

  const stdFields = [
    ['Type',        (r.Typ||r.typ) ? typBadge(r.Typ||r.typ) : '—'],
    ['Priority',    `<span class="badge badge-${r.Priorytet||r.priorytet||''}">${r.Priorytet||r.priorytet||'—'}</span>`],
    ['Service',     esc(r.Serwis||r.serwis||'—')],
    ['Action',      `<span class="badge bg-secondary">${esc(r.Akcja||r.akcja||'—')}</span>`],
    ['Status',      `<span class="badge badge-${r.Status||r.status||''}">${r.Status||r.status||'—'}</span>`],
    ['Confidence',  confBar(r.Confidence||r.confidence||0)],
    ['Deadline',    esc(r.Data_wazna||r.data_wazna||'—')],
    ['Email Alert', (r.Email_alert||r.email_alert) ? `<span class="badge" style="background:var(--yellow);color:#222">YES</span>` : `<span class="badge bg-secondary">no</span>`],
  ];

  if (r.Subject) stdFields.push(['Subject', esc(r.Subject)]);
  if (r.Sender)  stdFields.push(['Sender',  esc(r.Sender)]);

  for (const col of getCustomCols()) {
    const key = customKey(col.name);
    stdFields.push([col.name, esc(r[key] || '—')]);
  }

  document.getElementById('dm-fields-grid').innerHTML = stdFields.map(([lbl, val]) => `
    <div class="col-6 col-md-3">
      <div class="dm-field">
        <div class="dm-field-label">${esc(lbl)}</div>
        <div class="dm-field-val">${val}</div>
      </div>
    </div>`).join('');

  document.getElementById('dm-summary').textContent = r.Streszczenie || r.streszczenie || '—';

  if (r._source === 'ai' && r.Subject !== undefined) {
    document.getElementById('dm-attachments').textContent = 'Attachment storage not supported yet — only message body is captured.';
  } else {
    document.getElementById('dm-attachments').textContent = 'N/A — Excel source.';
  }

  document.getElementById('dm-message').textContent = r.FullMessage || '(message body not stored)';

  if (showCorrection) {
    _openCorrectionForm(r);
  } else {
    document.getElementById('dm-correction').classList.add('d-none');
  }

  bootstrap.Modal.getOrCreateInstance(document.getElementById('detailModal')).show();
}

function _openCorrectionForm(r) {
  const correction = document.getElementById('dm-correction');
  correction.classList.remove('d-none');
  const typSel = document.getElementById('dm-typ');
  const serSel = document.getElementById('dm-serwis');
  typSel.innerHTML = (state.config.typ_values||[]).map(v =>
    `<option ${v===(r.Typ||r.typ)?'selected':''}>${v}</option>`).join('');
  serSel.innerHTML = (state.config.serwis_values||[]).map(v =>
    `<option ${v===(r.Serwis||r.serwis)?'selected':''}>${v}</option>`).join('');
  document.getElementById('dm-priorytet').value = r.Priorytet||r.priorytet||'medium';
  document.getElementById('dm-akcja').value     = r.Akcja||r.akcja||'none';
  correction.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

document.getElementById('btn-dm-correct').addEventListener('click', () => {
  if (_detailResult) _openCorrectionForm(_detailResult);
});

document.getElementById('btn-dm-newtab').addEventListener('click', () => {
  if (_detailResult) openMessageInNewTab(_detailResult);
});

document.getElementById('btn-dm-save-correction').addEventListener('click', async () => {
  const r = _detailResult;
  if (!r) return;
  await api('POST', '/api/feedback', {
    id:        r.ID,
    text:      r.FullMessage || r.Streszczenie || '',
    original:  { typ: r.Typ||r.typ, priorytet: r.Priorytet||r.priorytet, serwis: r.Serwis||r.serwis, akcja: r.Akcja||r.akcja },
    corrected: {
      typ:      document.getElementById('dm-typ').value,
      priorytet:document.getElementById('dm-priorytet').value,
      serwis:   document.getElementById('dm-serwis').value,
      akcja:    document.getElementById('dm-akcja').value,
    },
  });
  document.getElementById('dm-correction').classList.add('d-none');
  showToast('Correction saved — RL feedback recorded.');
  loadFeedback();
});

// ─────────────────────────────────────────────────────────────────────────────
// CUSTOM FILTERS
// ─────────────────────────────────────────────────────────────────────────────

function renderCustomFilters() {
  const container = document.getElementById('custom-filters-container');
  if (!container) return;
  const customCols = getCustomCols();

  container.querySelectorAll('select').forEach(sel => {
    const stillExists = customCols.some(c => `filter-custom-${c.key}` === sel.id);
    if (!stillExists) sel.remove();
  });

  for (const col of customCols) {
    const filterId = `filter-custom-${col.key}`;
    const key      = customKey(col.name);
    const vals     = [...new Set(state.results.map(r => r[key]).filter(v => v != null && v !== ''))];

    let sel = document.getElementById(filterId);
    const prev = sel?.value || '';

    if (!sel) {
      sel = document.createElement('select');
      sel.id = filterId;
      sel.className = 'form-select form-select-sm w-auto';
      sel.addEventListener('change', renderResultsTable);
      container.appendChild(sel);
    }

    sel.innerHTML = `<option value="">All ${esc(col.name)}</option>` +
      vals.map(v => `<option ${v===prev?'selected':''}>${esc(v)}</option>`).join('');
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// SETTINGS — CRITERIA TABLE
// ─────────────────────────────────────────────────────────────────────────────

function renderCriteriaTable() {
  const cols = state.criteriaColumns;
  if (!cols.length) return;
  const maxRows = Math.max(...cols.map(c => c.values.length), 0);

  let html = '<table class="criteria-tbl"><thead><tr>';
  for (const col of cols) {
    const cls = col.builtin ? 'builtin-th' : 'custom-th';
    html += `<th class="${cls}">
      <div class="th-inner">
        ${col.builtin
          ? `<span class="col-name">${esc(col.name)}</span>`
          : `<input class="col-name-input" data-key="${col.key}" value="${esc(col.name)}">`
        }
        ${!col.builtin ? `<div class="th-actions"><button class="btn-del-col" data-key="${col.key}" title="Remove column">✕</button></div>` : ''}
      </div>
    </th>`;
  }
  html += `<th class="add-col-th"><button id="btn-add-col-th" class="btn-add-col">＋ Column</button></th>`;
  html += '</tr></thead><tbody>';

  for (let r = 0; r < maxRows; r++) {
    html += '<tr>';
    for (const col of cols) {
      const val = col.values[r];
      if (val !== undefined) {
        html += `<td><div class="val-row">
          <input class="val-input" data-key="${col.key}" data-idx="${r}" value="${esc(val)}">
          <button class="btn-del-val" data-key="${col.key}" data-idx="${r}" title="Remove">✕</button>
        </div></td>`;
      } else {
        html += '<td class="empty-cell"></td>';
      }
    }
    html += '<td></td></tr>';
  }

  html += '<tr class="add-val-row">';
  for (const col of cols) {
    html += `<td><button class="btn-add-val" data-key="${col.key}">＋ add value</button></td>`;
  }
  html += '<td></td></tr>';
  html += '</tbody></table>';

  const container = document.getElementById('criteria-table-container');
  container.innerHTML = html;

  container.querySelectorAll('.btn-del-col').forEach(btn => {
    btn.addEventListener('click', () => {
      state.criteriaColumns = state.criteriaColumns.filter(c => c.key !== btn.dataset.key);
      renderCriteriaTable();
    });
  });

  container.querySelectorAll('.btn-del-val').forEach(btn => {
    btn.addEventListener('click', () => {
      const col = state.criteriaColumns.find(c => c.key === btn.dataset.key);
      if (col) { col.values.splice(parseInt(btn.dataset.idx), 1); renderCriteriaTable(); }
    });
  });

  container.querySelectorAll('.val-input').forEach(input => {
    input.addEventListener('change', () => {
      const col = state.criteriaColumns.find(c => c.key === input.dataset.key);
      if (col) col.values[parseInt(input.dataset.idx)] = input.value;
    });
    input.addEventListener('focus', () => { const b=input.closest('.val-row')?.querySelector('.btn-del-val'); if(b) b.style.opacity='1'; });
    input.addEventListener('blur',  () => { const b=input.closest('.val-row')?.querySelector('.btn-del-val'); if(b) b.style.opacity=''; });
  });

  container.querySelectorAll('.col-name-input').forEach(input => {
    input.addEventListener('change', () => {
      const col = state.criteriaColumns.find(c => c.key === input.dataset.key);
      if (col) col.name = input.value;
    });
  });

  container.querySelectorAll('.btn-add-val').forEach(btn => {
    btn.addEventListener('click', () => {
      const col = state.criteriaColumns.find(c => c.key === btn.dataset.key);
      if (col) {
        col.values.push('');
        renderCriteriaTable();
        const all = container.querySelectorAll(`.val-input[data-key="${col.key}"]`);
        if (all.length) all[all.length-1].focus();
      }
    });
  });

  document.getElementById('btn-add-col-th').addEventListener('click', () => {
    const key = `custom_${Date.now()}`;
    state.criteriaColumns.push({ key, name: 'New Column', values: [], builtin: false });
    renderCriteriaTable();
    const inputs = container.querySelectorAll('.col-name-input');
    if (inputs.length) { inputs[inputs.length-1].focus(); inputs[inputs.length-1].select(); }
  });
}

async function saveCriteria() {
  const active = document.activeElement;
  if (active && (active.classList.contains('val-input') || active.classList.contains('col-name-input'))) {
    active.blur();
    await new Promise(r => setTimeout(r, 50));
  }
  const cols = state.criteriaColumns;
  const get  = key => cols.find(c => c.key === key)?.values.filter(v => v !== '') || [];
  await api('POST', '/api/config', {
    typ_values:       get('typ'),
    priorytet_values: get('priorytet'),
    serwis_values:    get('serwis'),
    akcja_values:     get('akcja'),
    custom_criteria:  cols.filter(c => !c.builtin).map(c => ({
      name: c.name, values: c.values.filter(v => v !== ''),
    })),
  });
  await loadConfig();
  renderCustomFilters();
  showToast('Criteria saved.');
}

document.getElementById('btn-save-criteria').addEventListener('click', saveCriteria);

// ─────────────────────────────────────────────────────────────────────────────
// SETTINGS — Model / Extra AI
// ─────────────────────────────────────────────────────────────────────────────

async function loadConfig() {
  const cfg = await api('GET', '/api/config');
  if (!cfg) return;
  state.config = cfg;

  document.getElementById('cfg-model').value   = cfg.model || 'gemma3';
  document.getElementById('cfg-workers').value = cfg.workers || 2;
  document.getElementById('cfg-timeout').value = cfg.request_timeout || 180;
  document.getElementById('cfg-extra').value   = cfg.extra_criteria || '';

  state.criteriaColumns = [
    { key:'typ',       name:'Type',     values:[...(cfg.typ_values      ||[])], builtin:true },
    { key:'priorytet', name:'Priority', values:[...(cfg.priorytet_values||[])], builtin:true },
    { key:'serwis',    name:'Service',  values:[...(cfg.serwis_values   ||[])], builtin:true },
    { key:'akcja',     name:'Action',   values:[...(cfg.akcja_values    ||[])], builtin:true },
    ...(cfg.custom_criteria||[]).map(c=>({
      key: `custom_${c.name}`, name: c.name, values:[...c.values], builtin:false,
    })),
  ];

  document.getElementById('filter-typ').innerHTML =
    '<option value="">All Types</option>' + (cfg.typ_values||[]).map(v=>`<option>${v}</option>`).join('');
  document.getElementById('filter-serwis').innerHTML =
    '<option value="">All Services</option>' + (cfg.serwis_values||[]).map(v=>`<option>${v}</option>`).join('');

  renderCriteriaTable();
  renderCustomFilters();
}

document.getElementById('btn-save-cfg').addEventListener('click', async () => {
  await api('POST', '/api/config', {
    model:           document.getElementById('cfg-model').value,
    workers:         parseInt(document.getElementById('cfg-workers').value),
    request_timeout: parseInt(document.getElementById('cfg-timeout').value),
  });
  showToast('Model settings saved.');
});

document.getElementById('btn-save-extra').addEventListener('click', async () => {
  await api('POST', '/api/config', { extra_criteria: document.getElementById('cfg-extra').value });
  showToast('AI instructions saved.');
});

// ─────────────────────────────────────────────────────────────────────────────
// FEEDBACK (RL)
// ─────────────────────────────────────────────────────────────────────────────

async function loadFeedback() {
  const entries = await api('GET', '/api/feedback') || [];
  const ul = document.getElementById('feedback-list');
  ul.innerHTML = entries.length
    ? entries.map(e=>`<li class="list-group-item py-2 px-3">
        <div class="d-flex justify-content-between">
          <span class="small fw-semibold">ID ${e.id}</span>
          <button class="btn btn-sm btn-outline-danger py-0 px-1" onclick="deleteFeedback(${e.id})">✕</button>
        </div>
        <div class="text-muted" style="font-size:11px">${esc((e.snippet||'').substring(0,80))}</div>
        <div class="small mt-1">
          Was: <span class="badge bg-secondary">${e.original?.typ||'?'}</span>
          → <span class="badge bg-primary">${e.corrected?.typ||'?'}</span>
        </div></li>`).join('')
    : '<li class="list-group-item text-muted small">No corrections recorded.</li>';
}

async function deleteFeedback(id) {
  await api('DELETE', `/api/feedback/${id}`);
  loadFeedback();
}

// ─────────────────────────────────────────────────────────────────────────────
// EXCEL UPLOAD + BATCH
// ─────────────────────────────────────────────────────────────────────────────

const dropZone  = document.getElementById('drop-zone');
const fileInput = document.getElementById('excel-file-input');
dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => { e.preventDefault(); dropZone.classList.remove('dragover'); if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]); });
fileInput.addEventListener('change', () => { if (fileInput.files[0]) setFile(fileInput.files[0]); });

function setFile(f) {
  state.uploadedFile = f;
  document.getElementById('file-name').textContent = `Selected: ${f.name} (${(f.size/1024).toFixed(1)} KB)`;
  document.getElementById('btn-start-batch').disabled = false;
}

document.getElementById('btn-start-batch').addEventListener('click', async () => {
  if (!state.uploadedFile) return;
  const fd = new FormData();
  fd.append('file', state.uploadedFile);
  const df = document.getElementById('excel-date-from').value;
  const dt = document.getElementById('excel-date-to').value;
  const lm = document.getElementById('row-limit').value;
  if (df) fd.append('date_from', df);
  if (dt) fd.append('date_to', dt);
  if (lm) fd.append('limit', lm);

  document.getElementById('btn-start-batch').disabled = true;
  document.getElementById('batch-log').innerHTML = '';
  setBatchStatus('Uploading…', 'bg-warning text-dark');
  const res  = await fetch('/api/classify/excel', { method: 'POST', body: fd });
  const data = await res.json();
  if (!res.ok) {
    logBatch(`Upload error: ${data.error}`, 'log-err');
    setBatchStatus('Error', 'bg-danger');
    document.getElementById('btn-start-batch').disabled = false;
  } else if (data.queued) {
    document.getElementById('excel-queue-msg').classList.remove('d-none');
    setBatchStatus('Queued', 'bg-warning text-dark');
  }
});

document.getElementById('btn-stop-excel').addEventListener('click', async () => {
  await api('POST', '/api/classify/excel/stop');
  document.getElementById('excel-queue-msg').classList.add('d-none');
  setBatchStatus('Stopping…', 'bg-warning text-dark');
});

document.getElementById('btn-download').addEventListener('click',   () => { window.location = '/api/classify/excel/download'; });
document.getElementById('btn-dl-results').addEventListener('click', () => { window.location = '/api/classify/excel/download'; });

document.getElementById('btn-clear-results').addEventListener('click', async () => {
  if (!confirm('Clear all results and checkpoint?')) return;
  await api('DELETE', '/api/results');
  state.results = [];
  updateResultsCount(); updateSourceCounts(); renderResultsTable(); updateDashboard(); renderCustomFilters();
});

function setBatchStatus(text, cls) { const el=document.getElementById('batch-status'); el.className=`badge ${cls}`; el.textContent=text; }
function logBatch(msg, cls='') {
  const el=document.getElementById('batch-log');
  const line=document.createElement('div');
  if (cls) line.className=cls;
  line.textContent=msg; el.appendChild(line); el.scrollTop=el.scrollHeight;
}

// ─────────────────────────────────────────────────────────────────────────────
// UPLOAD PRE-CLASSIFIED RESULTS
// ─────────────────────────────────────────────────────────────────────────────

document.getElementById('btn-toggle-upload').addEventListener('click', () => {
  const body = document.getElementById('upload-results-body');
  const btn  = document.getElementById('btn-toggle-upload');
  body.classList.toggle('d-none');
  btn.innerHTML = body.classList.contains('d-none')
    ? '<i class="bi bi-chevron-down"></i>'
    : '<i class="bi bi-chevron-up"></i>';
});

const resultsDropZone  = document.getElementById('results-drop-zone');
const resultsFileInput = document.getElementById('results-file-input');
let _resultsUploadFile = null;

resultsDropZone.addEventListener('click', () => resultsFileInput.click());
resultsDropZone.addEventListener('dragover', e => { e.preventDefault(); resultsDropZone.classList.add('dragover'); });
resultsDropZone.addEventListener('dragleave', () => resultsDropZone.classList.remove('dragover'));
resultsDropZone.addEventListener('drop', e => {
  e.preventDefault(); resultsDropZone.classList.remove('dragover');
  if (e.dataTransfer.files[0]) setResultsFile(e.dataTransfer.files[0]);
});
resultsFileInput.addEventListener('change', () => { if (resultsFileInput.files[0]) setResultsFile(resultsFileInput.files[0]); });

function setResultsFile(f) {
  _resultsUploadFile = f;
  document.getElementById('results-upload-name').textContent = `Selected: ${f.name} (${(f.size/1024).toFixed(1)} KB)`;
  document.getElementById('btn-upload-results').disabled = false;
}

document.getElementById('btn-upload-results').addEventListener('click', async () => {
  if (!_resultsUploadFile) return;
  const fd = new FormData();
  fd.append('file', _resultsUploadFile);
  const msgEl = document.getElementById('results-upload-msg');
  msgEl.textContent = 'Uploading…';
  msgEl.className = 'small mt-2 text-muted';
  const res  = await fetch('/api/results/upload', { method: 'POST', body: fd });
  const data = await res.json();
  if (!res.ok || !data.ok) {
    msgEl.textContent = `Error: ${data.error || 'Unknown error'}`;
    msgEl.className = 'small mt-2 text-danger';
  } else {
    msgEl.textContent = `✓ Added ${data.added} new result(s) from ${data.total} rows.`;
    msgEl.className = 'small mt-2 text-success';
    // Reload all results from server
    const results = await api('GET', '/api/results');
    if (results) {
      state.results = results.map(normalizeResult);
      updateResultsCount();
      updateSourceCounts();
      updateDashboard();
      renderCustomFilters();
      renderResultsTable();
      document.getElementById('btn-dl-results').disabled = false;
    }
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// EMAIL MONITOR
// ─────────────────────────────────────────────────────────────────────────────

document.getElementById('btn-em-test').addEventListener('click', async () => {
  const res = await api('POST', '/api/email/test', getEmailForm());
  const msg = document.getElementById('em-status-msg');
  msg.classList.remove('d-none','text-success','text-danger');
  msg.classList.add(res?.ok ? 'text-success' : 'text-danger');
  msg.textContent = res?.message || 'Request failed';
});

document.getElementById('btn-em-start').addEventListener('click', async () => {
  const res = await api('POST', '/api/email/start', getEmailForm());
  if (res?.ok) {
    state.emailRunning = true;
    document.getElementById('btn-em-start').classList.add('d-none');
    document.getElementById('btn-em-stop').classList.remove('d-none');
    document.getElementById('em-monitor-badge').className = 'badge bg-success';
    document.getElementById('em-monitor-badge').textContent = 'Running';
  }
});

document.getElementById('btn-em-stop').addEventListener('click', async () => {
  await api('POST', '/api/email/stop');
  state.emailRunning = false;
  document.getElementById('btn-em-start').classList.remove('d-none');
  document.getElementById('btn-em-stop').classList.add('d-none');
  document.getElementById('em-monitor-badge').className = 'badge bg-secondary';
  document.getElementById('em-monitor-badge').textContent = 'Stopped';
});

function getEmailForm() {
  return {
    protocol: document.getElementById('em-protocol').value,
    host: document.getElementById('em-host').value,
    port: parseInt(document.getElementById('em-port').value),
    username: document.getElementById('em-user').value,
    password: document.getElementById('em-pass').value,
    folder: document.getElementById('em-folder').value || 'INBOX',
    poll_interval: parseInt(document.getElementById('em-interval').value),
    ssl: document.getElementById('em-ssl').checked,
  };
}

document.getElementById('em-protocol').addEventListener('change', function () {
  const isPop3 = this.value === 'pop3';
  const portEl = document.getElementById('em-port');
  const folderRow = document.getElementById('em-folder-row');
  if (portEl.value === '993' || portEl.value === '995') {
    portEl.value = isPop3 ? '995' : '993';
  }
  folderRow.style.display = isPop3 ? 'none' : '';
});

// ─────────────────────────────────────────────────────────────────────────────
// TAB SWITCHING
// ─────────────────────────────────────────────────────────────────────────────

document.querySelectorAll('[data-tab]').forEach(a => {
  a.addEventListener('click', e => {
    e.preventDefault();
    const id = a.dataset.tab;
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.add('d-none'));
    document.getElementById(`tab-${id}`).classList.remove('d-none');
    document.querySelectorAll('[data-tab]').forEach(l => l.classList.remove('active'));
    a.classList.add('active');
    if (id === 'results')  { updateSourceCounts(); renderCustomFilters(); renderResultsTable(); }
    if (id === 'settings') { renderCriteriaTable(); loadFeedback(); }
  });
});

['filter-typ','filter-priorytet','filter-status','filter-serwis','filter-search']
  .forEach(id => document.getElementById(id).addEventListener('input', renderResultsTable));

// ─────────────────────────────────────────────────────────────────────────────
// STATUS POLLING
// ─────────────────────────────────────────────────────────────────────────────

async function pollStatus() {
  const s = await api('GET', '/api/status');
  if (!s) return;
  const badge = document.getElementById('ollama-badge');
  if (s.ollama) {
    badge.className = 'badge bg-success';
    badge.innerHTML = `<i class="bi bi-circle-fill me-1"></i>${s.model}`;
  } else {
    badge.className = 'badge bg-danger';
    badge.innerHTML = '<i class="bi bi-exclamation-circle me-1"></i>Ollama Offline';
  }
  document.getElementById('stat-cache').textContent = s.cache_hits || 0;
  if (s.email?.running && !state.emailRunning) {
    state.emailRunning = true;
    document.getElementById('btn-em-start').classList.add('d-none');
    document.getElementById('btn-em-stop').classList.remove('d-none');
    document.getElementById('em-monitor-badge').className = 'badge bg-success';
    document.getElementById('em-monitor-badge').textContent = 'Running';
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// FIRST-RUN SETUP
// ─────────────────────────────────────────────────────────────────────────────

let _setupEs = null;

function _setupLog(msg, cls) {
  const el = document.getElementById('setup-log');
  const line = document.createElement('div');
  if (cls) line.className = cls;
  line.textContent = msg;
  el.appendChild(line);
  el.scrollTop = el.scrollHeight;
  while (el.children.length > 80) el.removeChild(el.firstChild);
}

function _setupProgress(pct, label) {
  const bar = document.getElementById('setup-progress-bar');
  const lbl = document.getElementById('setup-pct-label');
  bar.style.width = pct + '%';
  bar.textContent = pct + '%';
  if (label) lbl.textContent = label;
}

function _startSetupSSE() {
  if (_setupEs) { _setupEs.close(); _setupEs = null; }
  document.getElementById('setup-msg').textContent = 'Starting setup...';
  _setupLog('Connecting to setup service...', 'text-info');

  _setupEs = new EventSource('/api/setup/run');

  _setupEs.onmessage = (e) => {
    let data;
    try { data = JSON.parse(e.data); } catch (_) { return; }

    if (data.type === 'status') {
      document.getElementById('setup-msg').textContent = data.msg;
      _setupLog(data.msg, 'text-info');
      if (data.step === 1) _setupProgress(10, '');
      if (data.step === 2) _setupProgress(15, 'Downloading...');
    } else if (data.type === 'pull') {
      if (data.pct !== null && data.pct !== undefined) {
        const pct = Math.max(15, Math.round(data.pct * 0.85 + 15));
        _setupProgress(pct, data.pct + '% downloaded');
      }
      _setupLog(data.msg, '');
    } else if (data.type === 'done') {
      _setupProgress(100, 'Complete!');
      document.getElementById('setup-progress-bar').classList.remove('progress-bar-animated');
      document.getElementById('setup-msg').textContent = data.msg;
      _setupLog(data.msg, 'text-success fw-bold');
      _setupEs.close(); _setupEs = null;
      setTimeout(() => {
        document.getElementById('setup-screen').style.display = 'none';
        document.getElementById('setup-screen').classList.add('d-none');
        document.getElementById('main-app').classList.remove('d-none');
        _initApp();
      }, 1500);
    } else if (data.type === 'error') {
      document.getElementById('setup-msg').textContent = 'Error: ' + data.msg;
      _setupLog('ERROR: ' + data.msg, 'text-danger fw-bold');
      _setupLog('You can retry by restarting the app (close and reopen the shortcut).', 'text-warning');
      _setupEs.close(); _setupEs = null;
    }
  };

  _setupEs.onerror = () => {
    _setupLog('Connection lost. Retrying in 5s...', 'text-warning');
    if (_setupEs) { _setupEs.close(); _setupEs = null; }
    setTimeout(_startSetupSSE, 5000);
  };
}

async function _checkAndShowSetup() {
  let status = null;
  try { status = await fetch('/api/setup/status').then(r => r.json()); } catch (_) {}
  if (!status || status.model_ready) return false;

  // Model not ready — show setup screen
  document.getElementById('main-app').classList.add('d-none');
  const ss = document.getElementById('setup-screen');
  ss.classList.remove('d-none');
  ss.style.display = '';

  const msg = !status.ollama_running
    ? 'Starting Ollama server and downloading AI model...'
    : 'Downloading AI model ' + (status.model || 'gemma3') + '...';
  document.getElementById('setup-msg').textContent = msg;
  _startSetupSSE();
  return true;
}

// ─────────────────────────────────────────────────────────────────────────────
// INIT
// ─────────────────────────────────────────────────────────────────────────────

// Set default date_to = today for both pickers
(function setDefaultDates() {
  const today = new Date().toISOString().split('T')[0];
  document.getElementById('excel-date-to').value   = today;
  document.getElementById('em-date-to').value      = today;
})();

async function _initApp() {
  connectWS();
  await loadConfig();

  const results = await api('GET', '/api/results');
  if (results?.length) {
    state.results = results.map(normalizeResult);
    updateResultsCount();
    updateSourceCounts();
    updateDashboard();
    renderCustomFilters();
    document.getElementById('btn-download').disabled   = false;
    document.getElementById('btn-dl-results').disabled = false;
  }

  pollStatus();
  setInterval(pollStatus, 10000);
}

(async function init() {
  const setupNeeded = await _checkAndShowSetup();
  if (setupNeeded) return;
  await _initApp();
})();

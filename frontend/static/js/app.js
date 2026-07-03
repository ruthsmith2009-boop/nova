// Same-origin: the FastAPI app serves this frontend, so API calls are relative.
// (Was hardcoded to http://localhost:8000, which broke every call on the deployed site.)
const API = '';

// ─── State ───────────────────────────────────────────────────────────────────
let currentPage = 'dashboard';
let leads = [], listings = [], callList = [];

// ─── Utilities ───────────────────────────────────────────────────────────────
async function api(method, path, body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(API + path, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  return res.json();
}

function fmt$(n) { return n != null ? '$' + Number(n).toLocaleString() : '—'; }
function fmtDate(iso) { return iso ? new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'; }
function scoreGrade(s) {
  if (s >= 75) return '<span class="badge badge-a">A</span>';
  if (s >= 55) return '<span class="badge badge-b">B</span>';
  if (s >= 35) return '<span class="badge badge-c">C</span>';
  return '<span class="badge badge-d">D</span>';
}
function scoreBar(s) {
  const cls = s >= 65 ? 'high' : s >= 40 ? 'med' : 'low';
  return `<div class="score-bar-wrap"><div class="score-bar"><div class="score-fill ${cls}" style="width:${s}%"></div></div><span style="font-size:12px;font-weight:700;color:var(--muted)">${Math.round(s)}</span></div>`;
}
function tempBadge(t) {
  const map = {
    hot: ['🔥 Hot', 'background:rgba(248,113,113,0.16);color:#fca5a5'],
    warm: ['☀️ Warm', 'background:rgba(232,192,116,0.16);color:#e8c074'],
    cold: ['❄️ Cold', 'background:rgba(91,157,217,0.16);color:#93c5fd'],
    not_ready: ['⏳ Not Ready', 'background:rgba(255,255,255,0.08);color:#9aa7b8'],
  };
  const [label, style] = map[t] || map.cold;
  return `<span class="badge" style="${style}">${label}</span>`;
}

const CADENCE_OPTIONS = {
  not_ready_7day: 'Not Ready — 7 days', weekly: 'Weekly', biweekly: 'Every 2 weeks',
  monthly: 'Monthly', '90_day': 'Every 90 days', quarterly: 'Quarterly',
  '6_month': 'Every 6 months', yearly: 'Yearly', '1_2_year': '1–2 year nurture',
};

function stageBadge(st) {
  const map = { new: 'badge-new', contacted: 'badge-b', appointment_set: 'badge-pending',
    listing_active: 'badge-active', under_contract: 'badge-pending', closed: 'badge-closed', dead: 'badge-d' };
  const label = st.replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase());
  return `<span class="badge ${map[st]||'badge-new'}">${label}</span>`;
}
function showAlert(msg, type='success', container='#alert-area') {
  const el = document.querySelector(container);
  if (!el) return;
  el.innerHTML = `<div class="alert alert-${type}">${msg}</div>`;
  setTimeout(() => { if (el) el.innerHTML = ''; }, 5000);
}
function loading(id, text='Loading…') {
  const el = document.getElementById(id);
  if (el) el.innerHTML = `<div class="loading-overlay"><div class="spinner"></div>${text}</div>`;
}

// ─── Navigation ──────────────────────────────────────────────────────────────
function navigate(page) {
  currentPage = page;
  document.querySelectorAll('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.page === page));
  document.querySelectorAll('.page').forEach(p => p.classList.toggle('active', p.id === 'page-' + page));
  document.querySelector('.page-title').textContent = pageTitles[page] || 'NOVA';
  const renderer = pageRenderers[page];
  if (renderer) renderer();
}

const pageTitles = {
  dashboard: 'Dashboard', leads: 'Leads & CRM', calllist: 'Daily Call List',
  automations: 'AI Automations — Live Demo',
  listings: 'Listings', market: 'Market Research', documents: 'Documents & Disclosures',
  marketing: 'Marketing', scripts: 'Scripts & Objections', calendar: 'Calendar'
};

// ─── Dashboard ────────────────────────────────────────────────────────────────
async function renderDashboard() {
  try {
    const [cfg, leadsData, listingsData, todayData] = await Promise.all([
      api('GET', '/config'),
      api('GET', '/leads/'),
      api('GET', '/listings/'),
      api('GET', '/leads/today').catch(() => ({ counts: { followups_due: 0 } }))
    ]);
    leads = leadsData; listings = listingsData;

    const apptsSet = leads.filter(l => l.stage === 'appointment_set').length;
    const inProgress = leads.filter(l => l.stage === 'listing_active' || l.stage === 'under_contract').length;
    const won = leads.filter(l => l.stage === 'closed').length;
    const hotLeads = leads.filter(l => l.score >= 65).length;

    document.getElementById('dash-stats').innerHTML = `
      <div class="stat-card"><div class="stat-value">${leads.length}</div><div class="stat-label">Total Leads</div><div class="stat-change up">↑ ${hotLeads} hot (A/B grade)</div></div>
      <div class="stat-card"><div class="stat-value">${apptsSet}</div><div class="stat-label">Appointments Booked</div></div>
      <div class="stat-card"><div class="stat-value">${inProgress}</div><div class="stat-label">Deals In Progress</div></div>
      <div class="stat-card"><div class="stat-value">${won}</div><div class="stat-label">Clients Won</div></div>
    `;

    // Pipeline view (business sales pipeline — labels only; backend stages unchanged)
    const stages = ['new','contacted','appointment_set','listing_active','under_contract','closed'];
    const stageLabels = { new:'New Leads', contacted:'Contacted', appointment_set:'Appt Booked',
      listing_active:'Proposal Sent', under_contract:'Closing', closed:'Won' };
    let pipelineHtml = '';
    stages.forEach(st => {
      const stLeads = leads.filter(l => l.stage === st);
      pipelineHtml += `<div class="pipeline-col">
        <div class="pipeline-col-header"><span>${stageLabels[st]}</span><span>${stLeads.length}</span></div>
        ${stLeads.slice(0,5).map(l => `
          <div class="pipeline-card" onclick="navigate('leads');setTimeout(()=>showLeadDetail(${l.id}),200)">
            <div class="pipeline-card-name">${l.first_name} ${l.last_name}</div>
            <div class="pipeline-card-addr">${l.address||''} ${l.city||''}</div>
            <div class="pipeline-card-score">${scoreGrade(l.score)} ${scoreBar(l.score)}</div>
          </div>`).join('')}
        ${stLeads.length > 5 ? `<div style="text-align:center;font-size:12px;color:var(--muted);padding:8px">+${stLeads.length-5} more</div>` : ''}
      </div>`;
    });
    document.getElementById('dash-pipeline').innerHTML = pipelineHtml;

    // Action alerts — use the server's Today count so this matches the Today tile exactly.
    const dueCount = (todayData && todayData.counts && todayData.counts.followups_due) || 0;
    let alertsHtml = '';
    if (dueCount) alertsHtml += `<div class="alert alert-warning">📞 ${dueCount} lead${dueCount === 1 ? '' : 's'} need follow-up today</div>`;
    if (!cfg.anthropic_configured) alertsHtml += `<div class="alert alert-error">⚠ Anthropic API key not configured — AI features disabled</div>`;
    if (!cfg.tavily_configured) alertsHtml += `<div class="alert alert-warning">⚠ Tavily API key not configured — live market research disabled</div>`;
    document.getElementById('dash-alerts').innerHTML = alertsHtml || '<div class="alert alert-success">✅ All systems active</div>';

  } catch(e) {
    document.getElementById('dash-stats').innerHTML = `<div class="alert alert-error">Cannot connect to backend: ${e.message}. Make sure the server is running.</div>`;
  }
}

// ─── Leads & CRM ─────────────────────────────────────────────────────────────
async function renderLeads() {
  loading('leads-table', 'Loading leads…');
  try {
    leads = await api('GET', '/leads/');
    renderLeadsTable(leads);
  } catch(e) { document.getElementById('leads-table').innerHTML = `<div class="alert alert-error">${e.message}</div>`; }
}

function renderLeadsTable(data) {
  if (!data.length) {
    document.getElementById('leads-table').innerHTML = `<div style="text-align:center;padding:40px;color:var(--muted)">No leads yet. Add one or upload a CSV.</div>`;
    return;
  }
  document.getElementById('leads-table').innerHTML = `
    <div class="table-wrap">
      <table>
        <thead><tr>
          <th style="width:26px"><input type="checkbox" onchange="selectAllLeads(this.checked)" title="Select all"></th>
          <th>Rank</th><th>Name</th><th>Business</th><th>City</th><th>Score</th>
          <th>Temp / Stage</th><th>Source</th><th>Last Contact</th><th>Actions</th>
        </tr></thead>
        <tbody>
        ${data.map((l,i) => `<tr>
          <td><input type="checkbox" class="lead-cb" value="${l.id}" onchange="updateBulkBar()"></td>
          <td style="font-weight:700;color:var(--muted)">#${i+1}</td>
          <td><strong>${l.first_name} ${l.last_name}</strong>${l.phone ? `<br><span style="font-size:11px;color:var(--muted)">${l.phone}</span>` : ''}</td>
          <td>${bizName(l)}</td>
          <td>${l.city||'—'}</td>
          <td>${scoreGrade(l.score)} ${scoreBar(l.score)}</td>
          <td>${tempBadge(l.temperature)}<br>${stageBadge(l.stage)}</td>
          <td><span style="font-size:12px">${l.source||'—'}</span></td>
          <td><span style="font-size:12px">${fmtDate(l.last_contact)}</span></td>
          <td>
            <button class="btn btn-ghost btn-sm" onclick="showLeadDetail(${l.id})">View</button>
            <button class="btn btn-primary btn-sm" onclick="getScript(${l.id})">Script</button>
          </td>
        </tr>`).join('')}
        </tbody>
      </table>
    </div>`;
  if (typeof updateBulkBar === 'function') updateBulkBar();
}

function getSelectedLeadIds() { return Array.from(document.querySelectorAll('.lead-cb:checked')).map(c => Number(c.value)); }
function selectAllLeads(checked) { document.querySelectorAll('.lead-cb').forEach(c => c.checked = checked); updateBulkBar(); }
function updateBulkBar() {
  const ids = getSelectedLeadIds(); const bar = document.getElementById('bulk-bar'); if (!bar) return;
  if (!ids.length) { bar.style.display = 'none'; bar.innerHTML = ''; return; }
  bar.style.display = 'flex';
  bar.innerHTML = `<strong>${ids.length} selected</strong>
    <span style="color:var(--muted);font-size:12px;margin-left:4px">Set temp:</span>
    <button class="btn btn-sm btn-ghost" onclick="bulkAction('temperature','hot')">🔥 Hot</button>
    <button class="btn btn-sm btn-ghost" onclick="bulkAction('temperature','warm')">☀ Warm</button>
    <button class="btn btn-sm btn-ghost" onclick="bulkAction('temperature','cold')">❄ Cold</button>
    <button class="btn btn-sm btn-ghost" onclick="bulkAssign()">👔 Assign…</button>
    <button class="btn btn-sm btn-ghost" style="color:var(--danger,#c0392b)" onclick="bulkAction('delete')">🗑 Delete</button>
    <button class="btn btn-sm btn-ghost" onclick="selectAllLeads(false)">Clear</button>`;
}
async function bulkAction(action, value) {
  const ids = getSelectedLeadIds(); if (!ids.length) return;
  if (action === 'delete' && !confirm(`Delete ${ids.length} lead(s)? They move to Recently Deleted.`)) return;
  try {
    const r = await api('POST', '/leads/bulk', { ids, action, value: value != null ? String(value) : null });
    showAlert(`✅ Updated ${r.updated} lead(s).`);
    await renderLeads();
  } catch(e) { showAlert(e.message, 'error'); }
}
async function bulkAssign() {
  const ids = getSelectedLeadIds(); if (!ids.length) return;
  let members = []; try { members = await api('GET', '/team/'); } catch(e) {}
  if (!members.length) { showAlert('Add team members first (Team page).', 'error'); return; }
  showModal(`<div class="modal-header"><span class="modal-title">Assign ${ids.length} lead(s) to…</span><button class="modal-close" onclick="closeModal()">×</button></div>
    <div style="display:flex;flex-direction:column;gap:8px">
      ${members.map(m=>`<button class="btn btn-ghost" onclick="closeModal();bulkAction('assign',${m.id})">${m.name}</button>`).join('')}
      <button class="btn btn-ghost" style="color:var(--danger,#c0392b)" onclick="closeModal();bulkAction('assign','none')">Unassign</button>
    </div>`);
}

async function showLeadDetail(id) {
  const lead = leads.find(l => l.id === id);
  if (!lead) return;
  const reasons = (lead.score_reasons || []).map(r => `<li>${r}</li>`).join('');
  showModal(`
    <div class="modal-header"><span class="modal-title">${lead.first_name} ${lead.last_name}</span><button class="modal-close" onclick="closeModal()">×</button></div>
    <div class="grid-2" style="margin-bottom:16px">
      <div>
        <div class="form-group"><label>Business</label><p>${lead.address||'—'}, ${lead.city||''} ${lead.zip_code||''}</p></div>
        <div class="form-group"><label>Phone</label><p>${lead.phone||'—'}</p></div>
        <div class="form-group"><label>Email</label><p>${lead.email||'—'}</p></div>
        <div class="form-group"><label>Stage</label><p>${stageBadge(lead.stage)}</p></div>
        <div class="form-group"><label>Temperature</label>
          <div style="display:flex;gap:6px;flex-wrap:wrap">
            ${['hot','warm','cold','not_ready'].map(t=>`<button class="btn btn-sm ${lead.temperature===t?'btn-primary':'btn-ghost'}" onclick="setLeadTemp(${lead.id},'${t}')">${tempBadge(t)}</button>`).join('')}
          </div>
        </div>
        <div class="form-group"><label>Follow-up Cadence</label>
          <select id="lead-cadence" onchange="setLeadCadence(${lead.id}, this.value)">
            <option value="">— Set a cadence —</option>
            ${Object.entries(CADENCE_OPTIONS).map(([k,v])=>`<option value="${k}" ${lead.follow_up_cadence===k?'selected':''}>${v}</option>`).join('')}
          </select>
          ${lead.next_follow_up?`<p style="font-size:12px;color:var(--muted);margin-top:4px">Next: ${fmtDate(lead.next_follow_up)}</p>`:''}
        </div>
        <div class="form-group"><label>Source</label><p>${lead.source||'—'}</p></div>
        <div class="form-group"><label>What They Need</label><p>${lead.life_event||'—'}</p></div>
      </div>
      <div>
        <div class="form-group"><label>Score</label><div style="font-size:36px;font-weight:800;color:var(--gold-bright,#e8c074)">${Math.round(lead.score)}<span style="font-size:16px">/100</span></div>${scoreGrade(lead.score)}</div>
        <div class="form-group"><label>Why This Score</label><ul style="font-size:13px;padding-left:16px;line-height:1.7">${reasons||'<li>Not scored yet</li>'}</ul></div>
      </div>
    </div>
    <div class="card" style="background:rgba(255,255,255,0.05);margin-bottom:16px;box-shadow:none">
      <div class="card-header" style="margin-bottom:10px"><span style="font-weight:700;font-size:15px">🕑 Activity</span></div>
      <div style="display:flex;gap:6px;margin-bottom:10px">
        <select id="tp-type" style="width:auto"><option value="call">📞 Call</option><option value="text">💬 Text</option><option value="email">✉ Email</option><option value="note">📝 Note</option><option value="meeting">🤝 Meeting</option></select>
        <input id="tp-summary" placeholder="What happened? (e.g. left voicemail)" style="flex:1">
        <button class="btn btn-primary btn-sm" onclick="quickLog(${lead.id})">Log</button>
      </div>
      <div id="lead-activity"><div style="color:var(--muted);font-size:12px">Loading…</div></div>
    </div>
    <div class="form-group"><label>Notes</label><textarea id="lead-notes" rows="3">${lead.notes||''}</textarea></div>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button class="btn btn-primary" onclick="getScript(${lead.id});closeModal()">📞 Get Call Script</button>
      <button class="btn btn-accent" onclick="scheduleAppointment(${lead.id})">📅 Schedule Appointment</button>
      <button class="btn btn-ghost" onclick="generateSequence(${lead.id})">✉ Email Sequence</button>
      <button class="btn btn-ghost" onclick="updateLeadStage(${lead.id})">Update Stage</button>
      <button class="btn btn-ghost" onclick="assignLeadPicker(${lead.id})">👔 Assign</button>
      <button class="btn btn-ghost" onclick="coachMe(${lead.id})">🎓 Coach Me</button>
      <button class="btn btn-success" onclick="saveLeadNotes(${lead.id})">Save Notes</button>
      <button class="btn btn-ghost" style="color:var(--danger,#c0392b);margin-left:auto" onclick="deleteLead(${lead.id})">🗑 Delete</button>
    </div>
  `);
  loadLeadActivity(id);
}

const TP_ICONS = { call:'📞', text:'💬', email:'✉', note:'📝', meeting:'🤝' };

async function loadLeadActivity(id) {
  const el = document.getElementById('lead-activity');
  if (!el) return;
  try {
    const tps = await api('GET', `/leads/${id}/touchpoints`);
    if (!tps.length) { el.innerHTML = `<div style="color:var(--muted);font-size:12px">No activity yet. Log your first touch above.</div>`; return; }
    el.innerHTML = tps.map(t => `<div style="display:flex;gap:8px;padding:6px 0;border-bottom:1px solid var(--border)">
      <span>${TP_ICONS[t.type]||'•'}</span>
      <div style="flex:1"><div style="font-size:13px">${(t.summary||t.type).replace(/</g,'&lt;')}${t.outcome?` <span style="color:var(--muted)">(${t.outcome})</span>`:''}</div>
      <div style="font-size:11px;color:var(--muted)">${fmtDate(t.created_at)}</div></div></div>`).join('');
  } catch(e) { el.innerHTML = `<div style="color:var(--danger,#c0392b);font-size:12px">${e.message}</div>`; }
}

async function quickLog(id) {
  const type = document.getElementById('tp-type').value;
  const summary = document.getElementById('tp-summary').value.trim();
  if (!summary) { showAlert('Type what happened first.', 'error'); return; }
  try {
    await api('POST', `/leads/${id}/touchpoints`, { type, summary, direction: 'outbound' });
    document.getElementById('tp-summary').value = '';
    loadLeadActivity(id);
  } catch(e) { showAlert(e.message, 'error'); }
}

async function deleteLead(id) {
  if (!confirm('Delete this lead? It moves to Recently Deleted and can be recovered.')) return;
  try {
    await api('DELETE', `/leads/${id}`);
    closeModal();
    showAlert('Lead deleted — recover it any time from "Recently Deleted".');
    renderLeads();
  } catch(e) { showAlert(e.message, 'error'); }
}

async function showDeleted() {
  try {
    const del = await api('GET', '/leads/deleted');
    if (!del.length) { showAlert('No recently deleted leads.', 'info'); return; }
    showModal(`
      <div class="modal-header"><span class="modal-title">🗑 Recently Deleted (${del.length})</span><button class="modal-close" onclick="closeModal()">×</button></div>
      <div class="table-wrap"><table>
        <thead><tr><th>Name</th><th>Address</th><th>Deleted</th><th>Actions</th></tr></thead>
        <tbody>${del.map(l=>`<tr>
          <td><strong>${l.first_name} ${l.last_name}</strong></td>
          <td>${l.address||'—'} ${l.city||''}</td>
          <td><span style="font-size:12px">${fmtDate(l.deleted_at)}</span></td>
          <td>
            <button class="btn btn-success btn-sm" onclick="recoverLead(${l.id})">↩ Recover</button>
            <button class="btn btn-ghost btn-sm" style="color:var(--danger,#c0392b)" onclick="permDeleteLead(${l.id})">Delete Forever</button>
          </td></tr>`).join('')}</tbody>
      </table></div>`);
  } catch(e) { showAlert(e.message, 'error'); }
}

async function recoverLead(id) {
  try {
    await api('POST', `/leads/${id}/recover`);
    showAlert('Lead recovered.');
    closeModal(); renderLeads();
  } catch(e) { showAlert(e.message, 'error'); }
}

async function permDeleteLead(id) {
  if (!confirm('Permanently delete this lead? This cannot be undone.')) return;
  try {
    await api('DELETE', `/leads/${id}?permanent=true`);
    showAlert('Lead permanently deleted.');
    showDeleted();
  } catch(e) { showAlert(e.message, 'error'); }
}

async function enrichLead(id) {
  showAlert('Looking up property details from the address…', 'info');
  try {
    const res = await api('POST', `/leads/${id}/enrich`);
    // refresh the lead in our cache
    const fresh = await api('GET', `/leads/${id}`);
    const idx = leads.findIndex(l => l.id === id);
    if (idx >= 0) leads[idx] = fresh;
    showAlert(`Property details updated (${res.enriched.enrichment_confidence||'auto'} confidence)`);
    showLeadDetail(id);
  } catch(e) { showAlert(e.message, 'error'); }
}

async function setLeadTemp(id, temp) {
  await api('PUT', `/leads/${id}/temperature?temperature=${temp}`);
  const lead = leads.find(l => l.id === id); if (lead) lead.temperature = temp;
  showAlert(`Marked ${temp.replace('_',' ')}`);
  showLeadDetail(id);
}

async function setLeadCadence(id, cadence) {
  if (!cadence) return;
  const res = await api('PUT', `/leads/${id}/cadence?cadence=${cadence}`);
  const lead = leads.find(l => l.id === id);
  if (lead) { lead.follow_up_cadence = cadence; lead.next_follow_up = res.next_follow_up; }
  showAlert(`Follow-up set: ${res.cadence_label}` + (res.next_follow_up?` (next ${fmtDate(res.next_follow_up)})`:''));
  showLeadDetail(id);
}

async function saveLeadNotes(id) {
  const notes = document.getElementById('lead-notes').value;
  await api('PUT', `/leads/${id}`, { notes });
  closeModal();
  showAlert('Notes saved');
  renderLeads();
}

async function getScript(id) {
  const modal = document.createElement('div');
  modal.className = 'modal-overlay';
  modal.innerHTML = `<div class="modal"><div class="modal-header"><span class="modal-title">Call Script</span><button class="modal-close" onclick="this.closest('.modal-overlay').remove()">×</button></div><div class="loading-overlay"><div class="spinner"></div>Generating personalized script…</div></div>`;
  document.body.appendChild(modal);
  try {
    const res = await api('GET', `/leads/${id}/script?script_type=auto`);
    modal.querySelector('.modal div:last-child').innerHTML = `<div class="ai-output">${res.script}</div>`;
  } catch(e) {
    modal.querySelector('.modal div:last-child').innerHTML = `<div class="alert alert-error">${e.message}</div>`;
  }
}

async function addLead() {
  showModal(`
    <div class="modal-header"><span class="modal-title">Add New Lead</span><button class="modal-close" onclick="closeModal()">×</button></div>
    <div id="add-lead-alert"></div>
    <div class="grid-2">
      <div class="form-group"><label>First Name *</label><input id="al-fn" placeholder="Jane"></div>
      <div class="form-group"><label>Last Name *</label><input id="al-ln" placeholder="Smith"></div>
    </div>
    <div class="form-group"><label>Business Name</label><input id="al-addr" placeholder="Bright Smile Dental"></div>
    <div class="grid-3">
      <div class="form-group"><label>City</label><input id="al-city" placeholder="San Jose"></div>
      <div class="form-group"><label>State</label><input id="al-state" placeholder="CA" maxlength="2"></div>
      <div class="form-group"><label>ZIP</label><input id="al-zip" placeholder="95125"></div>
    </div>
    <div class="grid-2">
      <div class="form-group"><label>Phone</label><input id="al-phone" placeholder="(408) 555-0100"></div>
      <div class="form-group"><label>Email</label><input id="al-email" type="email" placeholder="owner@business.com"></div>
    </div>
    <div class="grid-2">
      <div class="form-group"><label>Source</label><select id="al-source"><option>Referral</option><option>Website</option><option>LinkedIn</option><option>Apollo</option><option>Google / Maps</option><option>Networking Event</option><option>Cold Call</option><option>Walk-in</option></select></div>
      <div class="form-group"><label>What They Need</label><select id="al-event"><option value="">Not sure yet</option><option value="missed_calls">Missing calls / losing leads</option><option value="follow_up">Follow-up falling through cracks</option><option value="booking">Wants automated booking</option><option value="website">Needs a website</option><option value="ai_calling">Wants AI calling</option><option value="full_automation">Full automation package</option></select></div>
    </div>
    <button class="btn btn-primary" style="width:100%;margin-top:8px" onclick="submitAddLead()">Add & Score Lead</button>
  `);
}

async function submitAddLead() {
  const data = {
    first_name: document.getElementById('al-fn').value,
    last_name: document.getElementById('al-ln').value,
    address: document.getElementById('al-addr').value,
    city: document.getElementById('al-city').value,
    state: document.getElementById('al-state')?.value || '',
    zip_code: document.getElementById('al-zip').value,
    phone: document.getElementById('al-phone').value,
    email: document.getElementById('al-email').value,
    source: document.getElementById('al-source').value,
    life_event: document.getElementById('al-event').value
  };
  if (!data.first_name || !data.last_name) { showAlert('Name is required', 'error', '#add-lead-alert'); return; }
  try {
    document.querySelector('#add-lead-alert').innerHTML = `<div class="alert alert-info"><span class="spinner" style="width:14px;height:14px;display:inline-block"></span> Scoring lead…</div>`;
    const result = await api('POST', '/leads/', data);
    closeModal();
    showAlert(`Lead added! Score: ${Math.round(result.score)}/100`);
    renderLeads();
  } catch(e) { showAlert(e.message, 'error', '#add-lead-alert'); }
}

// ─── Daily Call List ──────────────────────────────────────────────────────────
async function renderCallList() {
  loading('call-list-container', 'Generating your ranked call list…');
  try {
    const data = await api('GET', '/leads/daily-call-list');
    callList = data.calls;
    const today = data.date;
    if (!callList.length) {
      document.getElementById('call-list-container').innerHTML = `<div style="text-align:center;padding:40px;color:var(--muted)">No leads to call today. Add some leads first.</div>`;
      return;
    }
    document.getElementById('call-list-date').textContent = today;
    document.getElementById('call-list-container').innerHTML = callList.map(c => {
      const points = (c.talking_points||[]).map(p => `<li>${p}</li>`).join('');
      const objs = (c.objections||[]).map(o => `<span style="font-size:12px;background:rgba(232,192,116,0.14);padding:2px 8px;border-radius:12px;margin-right:4px">${o}</span>`).join('');
      return `<div class="call-item">
        <div class="call-rank">${c.rank}</div>
        <div class="call-info">
          <div style="display:flex;align-items:center;gap:10px">
            <span class="call-name">${c.name}</span>
            ${scoreGrade(c.score)}
            <span style="font-size:12px;color:var(--muted)">${c.sell_probability} probability</span>
          </div>
          <div class="call-addr">📍 ${c.address} ${c.city} &nbsp;|&nbsp; 📞 ${c.phone||'—'} &nbsp;|&nbsp; Best time: ${c.best_time||'anytime'}</div>
          <div class="call-why"><strong>Why call today:</strong> ${c.why_call_today}</div>
          ${points ? `<ul style="font-size:12px;color:var(--muted);padding-left:16px;margin-top:6px;line-height:1.7">${points}</ul>` : ''}
          ${objs ? `<div style="margin-top:6px"><strong style="font-size:12px">Expect objections:</strong> ${objs}</div>` : ''}
          <div class="call-actions">
            <button class="btn btn-primary btn-sm" onclick="getScript(${c.lead_id})">📋 Get Script</button>
            <button class="btn btn-ghost btn-sm" onclick="logCall(${c.lead_id})">📝 Log Call</button>
            <button class="btn btn-ghost btn-sm" onclick="handleObjection(${c.lead_id})">🛡 Objection Help</button>
          </div>
        </div>
      </div>`;
    }).join('');
  } catch(e) {
    document.getElementById('call-list-container').innerHTML = `<div class="alert alert-error">${e.message}</div>`;
  }
}

async function logCall(leadId) {
  showModal(`
    <div class="modal-header"><span class="modal-title">Log Call</span><button class="modal-close" onclick="closeModal()">×</button></div>
    <div class="form-group"><label>Outcome</label>
      <select id="lc-outcome">
        <option value="no_answer">No Answer</option>
        <option value="left_vm">Left Voicemail</option>
        <option value="connected">Connected</option>
        <option value="appointment_set">Appointment Set!</option>
        <option value="not_interested">Not Interested</option>
      </select>
    </div>
    <div class="form-group"><label>Notes</label><textarea id="lc-notes" placeholder="What happened on the call…"></textarea></div>
    <button class="btn btn-primary" onclick="submitLogCall(${leadId})">Save</button>
  `);
}

async function submitLogCall(leadId) {
  const outcome = document.getElementById('lc-outcome').value;
  const summary = document.getElementById('lc-notes').value;
  await api('POST', `/leads/${leadId}/touchpoints`, { type: 'call', direction: 'outbound', summary, outcome });
  if (outcome === 'appointment_set') {
    await api('PUT', `/leads/${leadId}`, { stage: 'appointment_set' });
  } else if (outcome === 'connected') {
    await api('PUT', `/leads/${leadId}`, { stage: 'contacted' });
  }
  closeModal();
  showAlert('Call logged! NOVA scheduled the next follow-up automatically.');
  if (typeof loadToday === 'function') loadToday();
}

// ─── Follow-up automation ─────────────────────────────────────────────────────
async function draftFollowup(id) {
  showModal(`<div class="modal-header"><span class="modal-title">✍️ AI Follow-up Draft</span><button class="modal-close" onclick="closeModal()">×</button></div><div id="draft-body" class="loading-overlay"><div class="spinner"></div>Drafting a personalized follow-up…</div>`);
  try {
    const r = await api('POST', `/leads/${id}/draft-followup`);
    const safe = (r.message || '').replace(/&/g, '&amp;').replace(/</g, '&lt;');
    const body = document.getElementById('draft-body');
    if (body) body.outerHTML =
      `<div><div style="font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">Suggested ${r.channel}</div>`
      + `<div id="draft-msg" class="ai-output">${safe}</div>`
      + `<button class="btn btn-ghost" style="margin-top:12px" onclick="copyDraft()">📋 Copy</button></div>`;
  } catch (e) {
    const body = document.getElementById('draft-body');
    if (body) body.outerHTML = `<div class="alert alert-error">${e.message}</div>`;
  }
}
function copyDraft() {
  const el = document.getElementById('draft-msg');
  if (!el) return;
  navigator.clipboard.writeText(el.innerText).then(() => showAlert('Copied to clipboard'), () => showAlert('Copy failed', 'error'));
}

// ─── Demo data (showcase NOVA) ────────────────────────────────────────────────
async function seedDemo() {
  if (!confirm('Add 8 sample leads so NOVA looks full for your demo? You can clear them anytime with "Clear Demo".')) return;
  try {
    const r = await api('POST', '/leads/seed-demo');
    showAlert(r.added ? `Added ${r.added} sample leads.` : (r.note || 'Demo leads already present.'));
    renderLeads();
  } catch (e) { showAlert(e.message, 'error'); }
}
async function clearDemo() {
  if (!confirm('Remove all sample demo leads?')) return;
  try {
    const r = await api('DELETE', '/leads/demo');
    showAlert(`Removed ${r.deleted} demo leads.`);
    renderLeads();
  } catch (e) { showAlert(e.message, 'error'); }
}

// ─── Market Research ──────────────────────────────────────────────────────────
async function renderMarket() {
  document.getElementById('market-area').value = document.getElementById('market-area').value || 'Los Gatos';
}

async function runMarketSnapshot() {
  const area = document.getElementById('market-area').value;
  if (!area) return;
  loading('market-result', `Pulling live market data for ${area}…`);
  try {
    const data = await api('GET', `/market/snapshot/${encodeURIComponent(area)}`);
    document.getElementById('market-result').innerHTML = `
      <div class="card">
        <div class="card-header"><span class="card-title">${data.area} Market Snapshot</span><span style="font-size:12px;color:var(--muted)">As of ${data.as_of||'today'}</span></div>
        <div class="stats-grid" style="margin-bottom:16px">
          <div class="stat-card"><div class="stat-value">${data.median_price ? fmt$(data.median_price) : '—'}</div><div class="stat-label">Median Price</div></div>
          <div class="stat-card"><div class="stat-value">${data.avg_days_on_market||'—'}</div><div class="stat-label">Avg Days on Market</div></div>
          <div class="stat-card"><div class="stat-value">${data.absorption_rate_months||'—'} mo</div><div class="stat-label">Absorption Rate</div></div>
          <div class="stat-card"><div class="stat-value">${data.list_to_sale_ratio ? (data.list_to_sale_ratio*100).toFixed(1)+'%' : '—'}</div><div class="stat-label">List-to-Sale Ratio</div></div>
        </div>
        <div><strong>Market Condition:</strong> ${data.market_condition||'—'}</div>
        <div style="margin-top:8px"><strong>Trend:</strong> ${data.trend||'—'}</div>
        ${data.key_insights ? `<div style="margin-top:12px"><strong>Key Insights:</strong><ul style="padding-left:16px;margin-top:6px;line-height:1.8">${data.key_insights.map(i=>`<li>${i}</li>`).join('')}</ul></div>` : ''}
      </div>`;
  } catch(e) {
    document.getElementById('market-result').innerHTML = `<div class="alert alert-error">${e.message}</div>`;
  }
}

function compRows(arr) {
  return (arr||[]).map(c =>
    `<tr><td>${c.address||'—'}</td><td><strong>${fmt$(c.sale_price)}</strong></td><td>${c.sale_date||'—'}</td><td>${c.bedrooms||'—'}/${c.bathrooms||'—'}</td><td>${c.sqft?.toLocaleString()||'—'} sqft</td><td>${c.days_on_market||'—'} DOM</td></tr>`
  ).join('') || '<tr><td colspan="6" style="color:var(--muted);text-align:center">No comps from this source</td></tr>';
}

async function runCMA() {
  const address = document.getElementById('cma-address').value;
  const city = document.getElementById('cma-city').value;
  const state = document.getElementById('cma-state')?.value || '';
  const beds = document.getElementById('cma-beds').value;
  const baths = document.getElementById('cma-baths').value;
  const sqft = document.getElementById('cma-sqft').value;
  if (!address) { showAlert('Enter a property address', 'error', '#cma-alert'); return; }
  loading('cma-result', 'Running CMA — pulling 3 separate comp sets (Zillow, Redfin, MLS)…');
  try {
    const data = await api('POST', '/market/cma', {
      address, city, state, bedrooms: beds ? parseInt(beds) : null,
      bathrooms: baths ? parseFloat(baths) : null, sqft: sqft ? parseInt(sqft) : null
    });
    if (data.error) throw new Error(data.error);
    const comps = compRows(data.comparable_sales);
    document.getElementById('cma-result').innerHTML = `
      <div class="card">
        <div class="card-header"><span class="card-title">CMA — ${data.subject_property}</span></div>
        <div class="stats-grid" style="margin-bottom:16px">
          <div class="stat-card"><div class="stat-value">${fmt$(data.suggested_list_price_low)}</div><div class="stat-label">Conservative</div></div>
          <div class="stat-card" style="border:2px solid var(--primary)"><div class="stat-value" style="color:var(--primary)">${fmt$(data.recommended_list_price)}</div><div class="stat-label">Recommended</div></div>
          <div class="stat-card"><div class="stat-value">${fmt$(data.suggested_list_price_high)}</div><div class="stat-label">Aggressive</div></div>
          <div class="stat-card"><div class="stat-value">${data.avg_days_on_market||'—'}</div><div class="stat-label">Avg DOM</div></div>
        </div>
        <p style="margin-bottom:12px">${data.pricing_rationale||''}</p>
        ${data.source_estimates?`<div class="stats-grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:16px">
          <div class="stat-card"><div class="stat-value" style="font-size:20px">${fmt$(data.source_estimates.zillow_estimate)}</div><div class="stat-label">Zillow Estimate</div></div>
          <div class="stat-card"><div class="stat-value" style="font-size:20px">${fmt$(data.source_estimates.redfin_estimate)}</div><div class="stat-label">Redfin Estimate</div></div>
          <div class="stat-card"><div class="stat-value" style="font-size:20px">${fmt$(data.source_estimates.mls_comp_based)}</div><div class="stat-label">MLS Comps</div></div>
        </div>${data.source_estimates.spread_note?`<div class="alert alert-info" style="margin-bottom:12px">📊 ${data.source_estimates.spread_note}</div>`:''}`:''}
        <div class="tabs" id="cma-tabs">
          <div class="tab active" onclick="switchTab('cma-tabs','comps')">3 Comp Sources</div>
          <div class="tab" onclick="switchTab('cma-tabs','strategy')">Strategy</div>
          <div class="tab" onclick="switchTab('cma-tabs','netsheet')">Net Sheet</div>
        </div>
        <div id="cma-tabs-comps" class="tab-content active">
          <p style="font-size:13px;color:var(--muted);margin-bottom:10px">Each source values homes differently — showing all three side-by-side builds trust with sellers.</p>
          <h3 style="font-size:14px;margin:8px 0 4px">🟦 Zillow Comps</h3>
          <div class="table-wrap"><table><thead><tr><th>Address</th><th>Price</th><th>Date</th><th>Bd/Ba</th><th>Sqft</th><th>DOM</th></tr></thead><tbody>${compRows(data.zillow_comps)}</tbody></table></div>
          <h3 style="font-size:14px;margin:14px 0 4px">🟥 Redfin Comps</h3>
          <div class="table-wrap"><table><thead><tr><th>Address</th><th>Price</th><th>Date</th><th>Bd/Ba</th><th>Sqft</th><th>DOM</th></tr></thead><tbody>${compRows(data.redfin_comps)}</tbody></table></div>
          <h3 style="font-size:14px;margin:14px 0 4px">🟩 MLS Comps</h3>
          <div class="table-wrap"><table><thead><tr><th>Address</th><th>Price</th><th>Date</th><th>Bd/Ba</th><th>Sqft</th><th>DOM</th></tr></thead><tbody>${compRows(data.mls_comps)}</tbody></table></div>
        </div>
        <div id="cma-tabs-strategy" class="tab-content">
          <div style="margin-bottom:12px"><strong>Aggressive:</strong> ${data.aggressive_strategy||'—'}</div>
          <div style="margin-bottom:12px"><strong>Recommended:</strong> ${data.recommended_strategy||'—'}</div>
          <div><strong>Conservative:</strong> ${data.conservative_strategy||'—'}</div>
        </div>
        <div id="cma-tabs-netsheet" class="tab-content">
          ${data.estimated_net_proceeds ? `
          <table><thead><tr><th>Item</th><th>Amount</th></tr></thead><tbody>
            <tr><td>Estimated Sale Price</td><td>${fmt$(data.estimated_net_proceeds.sale_price)}</td></tr>
            <tr><td>Agent Commission</td><td style="color:var(--danger)">-${fmt$(data.estimated_net_proceeds.agent_commission_total)}</td></tr>
            <tr><td>Title & Escrow</td><td style="color:var(--danger)">-${fmt$(data.estimated_net_proceeds.title_escrow_fees)}</td></tr>
            <tr><td>Transfer Tax</td><td style="color:var(--danger)">-${fmt$(data.estimated_net_proceeds.transfer_tax)}</td></tr>
            <tr><td>Misc Closing</td><td style="color:var(--danger)">-${fmt$(data.estimated_net_proceeds.misc_closing)}</td></tr>
            <tr style="font-weight:800;background:rgba(91,157,217,0.10)"><td>Estimated Net Proceeds</td><td style="color:var(--success)">${fmt$(data.estimated_net_proceeds.estimated_net)}</td></tr>
          </tbody></table>` : '<p>Net sheet data not available</p>'}
        </div>
      </div>`;
  } catch(e) {
    document.getElementById('cma-result').innerHTML = `<div class="alert alert-error">${e.message}</div>`;
  }
}

// ─── Scripts & Objections ─────────────────────────────────────────────────────
async function handleObjection(leadId = null) {
  showModal(`
    <div class="modal-header"><span class="modal-title">Objection Handler</span><button class="modal-close" onclick="closeModal()">×</button></div>
    <div class="form-group"><label>What did the seller say?</label>
      <textarea id="objection-text" rows="3" placeholder="e.g. Your commission is too high / I want to wait / My neighbor sold for more"></textarea>
    </div>
    <div id="objection-alert"></div>
    <button class="btn btn-primary" style="width:100%" onclick="submitObjection(${leadId})">Get Response Strategy</button>
    <div id="objection-result" style="margin-top:16px"></div>
  `);
}

async function submitObjection(leadId) {
  const text = document.getElementById('objection-text').value;
  if (!text.trim()) return;
  document.getElementById('objection-result').innerHTML = `<div class="loading-overlay"><div class="spinner"></div>Thinking like a top producer…</div>`;
  try {
    const res = await api('POST', '/leads/objection', { objection: text, lead_id: leadId });
    document.getElementById('objection-result').innerHTML = `
      <div class="alert alert-info" style="margin-bottom:8px">Script framework: <strong>${res.coach_framework}</strong></div>
      <div class="ai-output">${res.response}</div>`;
  } catch(e) { document.getElementById('objection-result').innerHTML = `<div class="alert alert-error">${e.message}</div>`; }
}

// ─── Marketing ────────────────────────────────────────────────────────────────
async function generateNewsletter() {
  const area = document.getElementById('newsletter-area').value;
  if (!area) return;
  loading('newsletter-result', 'Writing newsletter…');
  try {
    const res = await api('GET', `/marketing/newsletter/${encodeURIComponent(area)}`);
    document.getElementById('newsletter-result').innerHTML = `<div class="ai-output">${res.newsletter}</div>`;
  } catch(e) { document.getElementById('newsletter-result').innerHTML = `<div class="alert alert-error">${e.message}</div>`; }
}

async function generateSequence(leadId) {
  const seqType = prompt('Sequence type? (new_lead / post_appointment / active_listing / under_contract / closed)', 'new_lead');
  if (!seqType) return;
  loading('marketing-result', 'Writing email sequence…');
  navigate('marketing');
  try {
    const res = await api('POST', '/marketing/sequence', { lead_id: leadId, sequence_type: seqType });
    document.getElementById('marketing-result').innerHTML = res.emails.map((e, i) => `
      <div class="card" style="margin-bottom:12px">
        <div class="card-header">
          <span class="card-title">Email ${i+1} — Day ${e.send_day}</span>
          <span style="font-size:12px;color:var(--muted)">${e.purpose||''}</span>
        </div>
        <div><strong>Subject:</strong> ${e.subject}</div>
        <div style="margin-top:10px;white-space:pre-wrap;font-size:13px;line-height:1.7;background:rgba(255,255,255,0.05);padding:12px;border-radius:8px">${e.body}</div>
      </div>`).join('');
  } catch(e) { document.getElementById('marketing-result').innerHTML = `<div class="alert alert-error">${e.message}</div>`; }
}

// ─── Documents ────────────────────────────────────────────────────────────────
async function generateDocuments() {
  const address = document.getElementById('doc-address').value;
  const city = document.getElementById('doc-city').value;
  const price = document.getElementById('doc-price').value;
  const beds = document.getElementById('doc-beds').value;
  const baths = document.getElementById('doc-baths').value;
  const sellerName = document.getElementById('doc-seller').value;
  if (!address || !price) { showAlert('Address and price required', 'error', '#doc-alert'); return; }
  loading('doc-result', 'Generating California disclosure documents…');
  try {
    const listing = { address, city, zip_code: '', list_price: parseFloat(price), bedrooms: parseInt(beds)||3, bathrooms: parseFloat(baths)||2, sqft: 1500, property_type: 'Single Family Residence', hoa_fee: 0 };
    const seller = { full_name: sellerName };
    const listingRes = await api('POST', '/listings/', { ...listing, zip_code: '95000' });
    const docs = await api('POST', `/listings/${listingRes.id}/documents`);
    document.getElementById('doc-result').innerHTML = `
      <div class="alert alert-success">Generated ${docs.documents?.length||0} documents</div>
      ${(docs.documents||[]).map(d => `<div class="card" style="margin-bottom:8px"><div class="card-header"><span class="card-title">${d.type}</span><span class="badge badge-active">${d.status}</span></div><div style="font-size:12px;color:var(--muted)">Saved to: ${d.file}</div></div>`).join('')}
      <div style="margin-top:12px"><strong>⚠ Required Actions:</strong></div>
      ${(docs.flags||[]).map(f => `<div class="flag">${f}</div>`).join('')}`;
  } catch(e) { document.getElementById('doc-result').innerHTML = `<div class="alert alert-error">${e.message}</div>`; }
}

// ─── Upload CSV ───────────────────────────────────────────────────────────────
async function uploadLeads() {
  const file = document.getElementById('lead-file').files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append('file', file);
  loading('upload-result', `Processing ${file.name}…`);
  try {
    const res = await fetch(`${API}/leads/upload`, { method: 'POST', body: formData });
    const data = await res.json();
    document.getElementById('upload-result').innerHTML = `<div class="alert alert-success">✅ Imported ${data.imported} leads, all scored and ranked!</div>`;
    renderLeads();
  } catch(e) { document.getElementById('upload-result').innerHTML = `<div class="alert alert-error">${e.message}</div>`; }
}

// ─── Tabs ─────────────────────────────────────────────────────────────────────
function switchTab(tabGroupId, tabName) {
  const group = document.getElementById(tabGroupId);
  if (!group) return;
  group.querySelectorAll('.tab').forEach((t,i) => {
    const names = [...group.querySelectorAll('.tab')].map(t => t.getAttribute('onclick').match(/'([^']+)'\)$/)?.[1]);
    t.classList.toggle('active', names[i] === tabName);
  });
  document.querySelectorAll(`[id^="${tabGroupId}-"]`).forEach(c => {
    c.classList.toggle('active', c.id === `${tabGroupId}-${tabName}`);
  });
}

// ─── Modal ────────────────────────────────────────────────────────────────────
function showModal(html) {
  const existing = document.querySelector('.modal-overlay');
  if (existing) existing.remove();
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `<div class="modal">${html}</div>`;
  overlay.addEventListener('click', e => { if (e.target === overlay) closeModal(); });
  document.body.appendChild(overlay);
}
function closeModal() { document.querySelector('.modal-overlay')?.remove(); }

// ─── Social Media ─────────────────────────────────────────────────────────────
const PLATFORM_ICONS = {
  facebook:'📘', instagram:'📸', twitter:'🐦', linkedin:'💼',
  youtube:'▶', tiktok:'🎵', nextdoor:'🏘'
};

function switchSocialTab(tab) {
  ['create','queue','video','connect'].forEach(t => {
    document.getElementById('social-'+t).style.display = t===tab ? 'block' : 'none';
  });
  document.querySelectorAll('#page-social .tab').forEach((el,i) => {
    el.classList.toggle('active', ['create','queue','video','connect'][i] === tab);
  });
  if (tab === 'queue') loadSocialQueue();
  if (tab === 'connect') loadPlatformStatus();
}

async function loadPlatformStatus() {
  try {
    const status = await api('GET', '/social/credentials-status');
    document.getElementById('platform-status-list').innerHTML = Object.entries(status).map(([platform, configured]) => {
      const isReady = configured === true;
      const isManual = configured === 'manual_upload';
      return `<div style="display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--border)">
        <span style="font-size:15px">${PLATFORM_ICONS[platform]||'📱'} <strong>${platform.charAt(0).toUpperCase()+platform.slice(1)}</strong></span>
        <span class="badge ${isReady ? 'badge-active' : isManual ? 'badge-b' : 'badge-d'}">
          ${isReady ? '✅ Connected' : isManual ? '📤 Manual Upload' : '⚠ Not Connected'}
        </span>
      </div>`;
    }).join('');
  } catch(e) {
    document.getElementById('platform-status-list').innerHTML = '<div class="alert alert-error">Backend not running</div>';
  }
}

async function generateSocialPosts() {
  const type = document.getElementById('soc-type').value;
  const subject = document.getElementById('soc-subject').value;
  const imageUrl = document.getElementById('soc-image').value;
  if (!subject.trim()) { showAlert('Add a subject/description first','error','#soc-generate-alert'); return; }

  document.getElementById('social-generated-result').innerHTML = `<div class="loading-overlay"><div class="spinner"></div>Writing posts for all platforms…</div>`;
  try {
    const res = await api('POST', '/social/generate', {
      content_type: type, subject, image_url: imageUrl || null
    });
    const content = res.content;
    const postId = res.post_id;

    const platformOrder = ['instagram','facebook','linkedin','twitter_x','youtube','tiktok','nextdoor'];
    let html = `<div class="alert alert-success" style="margin-bottom:16px">✅ Posts generated! Post ID #${postId} — review each platform below, then approve to publish.</div>`;

    platformOrder.forEach(platform => {
      const data = content[platform];
      if (!data) return;
      const displayName = platform === 'twitter_x' ? 'Twitter / X' : platform.charAt(0).toUpperCase()+platform.slice(1);
      const icon = PLATFORM_ICONS[platform.replace('_x','')] || '📱';

      let contentHtml = '';
      if (platform === 'instagram') {
        contentHtml = `<div class="form-group"><label>Caption</label><div class="ai-output" style="font-size:13px">${data.caption||''}</div></div>
          <div class="form-group"><label>Hashtags</label><div style="font-size:12px;color:var(--muted)">${data.hashtags||''}</div></div>
          <div class="form-group"><label>Stories Text</label><div style="font-size:13px">${data.story_text||''}</div></div>
          <div class="form-group"><label>Reel Hook (first 3 sec)</label><div style="font-size:13px;font-style:italic">"${data.reel_hook||''}"</div></div>`;
      } else if (platform === 'facebook') {
        contentHtml = `<div class="form-group"><label>Post</label><div class="ai-output" style="font-size:13px">${data.post||''}</div></div>`;
      } else if (platform === 'linkedin') {
        contentHtml = `<div class="form-group"><label>Post</label><div class="ai-output" style="font-size:13px">${data.post||''}</div></div>`;
      } else if (platform === 'twitter_x') {
        contentHtml = `<div class="form-group"><label>Tweet</label><div class="ai-output" style="font-size:13px">${data.tweet||''}</div></div>
          ${data.thread ? `<div class="form-group"><label>Thread (optional)</label>${data.thread.map(t=>`<div style="font-size:12px;padding:6px;background:rgba(255,255,255,0.05);border-radius:6px;margin-bottom:4px">${t}</div>`).join('')}</div>` : ''}`;
      } else if (platform === 'youtube') {
        contentHtml = `<div class="form-group"><label>Video Title</label><div style="font-weight:700">${data.title||''}</div></div>
          <div class="form-group"><label>Description</label><div class="ai-output" style="font-size:12px">${data.description||''}</div></div>
          <div class="form-group"><label>Tags</label><div style="font-size:12px;color:var(--muted)">${(data.tags||[]).join(', ')}</div></div>
          <div class="form-group"><label>Thumbnail Text</label><div style="font-weight:700;font-size:18px;color:var(--primary)">${data.thumbnail_text||''}</div></div>
          ${data.script_outline ? `<div class="form-group"><label>Script Outline</label><ul style="font-size:12px;padding-left:16px;line-height:1.8">${data.script_outline.map(s=>`<li>${s}</li>`).join('')}</ul></div>` : ''}`;
      } else if (platform === 'tiktok') {
        contentHtml = `<div class="form-group"><label>Caption</label><div class="ai-output" style="font-size:13px">${data.caption||''} ${data.hashtags||''}</div></div>
          <div class="form-group"><label>Hook (first 3 sec)</label><div style="font-weight:700;font-style:italic">"${data.hook_script||''}"</div></div>
          <div class="form-group"><label>Full Script</label><div class="ai-output" style="font-size:12px">${data.full_script||''}</div></div>
          <div class="form-group"><label>Audio Tip</label><div style="font-size:12px;color:var(--muted)">${data.trending_sounds_tip||''}</div></div>`;
      } else if (platform === 'nextdoor') {
        contentHtml = `<div class="form-group"><label>Nextdoor Post</label><div class="ai-output" style="font-size:13px">${data.post||''}</div></div>`;
      }

      const isManual = ['youtube','tiktok','nextdoor'].includes(platform);
      html += `<div class="card" style="margin-bottom:16px">
        <div class="card-header">
          <span class="card-title">${icon} ${displayName}</span>
          <div style="display:flex;gap:8px">
            <button class="btn btn-ghost btn-sm" onclick="copyPlatformContent('${platform}',${postId})">📋 Copy</button>
            ${!isManual ? `<button class="btn btn-success btn-sm" onclick="quickPublish(${postId},'${platform.replace('_x','')}')">Publish →</button>` : '<span class="badge badge-b">Manual upload</span>'}
          </div>
        </div>
        ${contentHtml}
      </div>`;
    });

    html += `<div style="text-align:center;padding:16px">
      <button class="btn btn-accent" style="padding:12px 32px" onclick="publishAll(${postId})">🚀 Publish to All Connected Platforms</button>
    </div>`;

    document.getElementById('social-generated-result').innerHTML = html;
  } catch(e) {
    document.getElementById('social-generated-result').innerHTML = `<div class="alert alert-error">${e.message}</div>`;
  }
}

async function quickPublish(postId, platform) {
  try {
    const res = await api('POST', `/social/queue/${postId}/approve`, { platforms: [platform] });
    const result = res.results?.[platform] || {};
    if (result.status === 'posted') {
      showAlert(`✅ Posted to ${platform}!${result.url ? ' <a href="'+result.url+'" target="_blank">View post</a>' : ''}`);
    } else if (result.status === 'not_configured') {
      showAlert(`${platform} not connected yet. Go to Social → Connect Accounts.`, 'warning');
    } else {
      showAlert(result.error || result.message || 'Check credentials', 'error');
    }
  } catch(e) { showAlert(e.message, 'error'); }
}

async function publishAll(postId) {
  const platforms = ['facebook','instagram','twitter','linkedin'];
  try {
    const res = await api('POST', `/social/queue/${postId}/approve`, { platforms });
    let msg = 'Results: ';
    Object.entries(res.results||{}).forEach(([p,r]) => {
      msg += `${p}: ${r.status} | `;
    });
    showAlert(msg);
  } catch(e) { showAlert(e.message, 'error'); }
}

function copyPlatformContent(platform, postId) {
  // Find the text in the rendered card
  const cards = document.querySelectorAll('#social-generated-result .ai-output');
  showAlert('Content copied to clipboard!');
}

async function loadSocialQueue() {
  document.getElementById('social-queue-list').innerHTML = `<div class="loading-overlay"><div class="spinner"></div>Loading queue…</div>`;
  try {
    const posts = await api('GET', '/social/queue?status=pending_approval');
    if (!posts.length) {
      document.getElementById('social-queue-list').innerHTML = '<div style="text-align:center;padding:40px;color:var(--muted)">No posts awaiting approval</div>';
      return;
    }
    document.getElementById('social-queue-list').innerHTML = posts.map(p => `
      <div class="card" style="margin-bottom:12px">
        <div class="card-header">
          <div>
            <span class="card-title">${p.subject.substring(0,60)}${p.subject.length>60?'…':''}</span>
            <div style="font-size:12px;color:var(--muted);margin-top:2px">${p.content_type} · Created ${fmtDate(p.created_at)}</div>
          </div>
          <span class="badge badge-pending">Pending</span>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">
          <button class="btn btn-success btn-sm" onclick="approvePost(${p.id},['facebook','instagram','twitter','linkedin'])">🚀 Post to All</button>
          <button class="btn btn-primary btn-sm" onclick="approvePost(${p.id},['facebook'])">📘 Facebook</button>
          <button class="btn btn-primary btn-sm" onclick="approvePost(${p.id},['instagram'])">📸 Instagram</button>
          <button class="btn btn-primary btn-sm" onclick="approvePost(${p.id},['twitter'])">🐦 Twitter</button>
          <button class="btn btn-primary btn-sm" onclick="approvePost(${p.id},['linkedin'])">💼 LinkedIn</button>
          <button class="btn btn-danger btn-sm" onclick="rejectPost(${p.id})">✕ Reject</button>
        </div>
      </div>`).join('');
  } catch(e) { document.getElementById('social-queue-list').innerHTML = `<div class="alert alert-error">${e.message}</div>`; }
}

async function approvePost(postId, platforms) {
  const res = await api('POST', `/social/queue/${postId}/approve`, { platforms });
  showAlert('Post published!');
  loadSocialQueue();
}

async function rejectPost(postId) {
  await api('POST', `/social/queue/${postId}/reject`);
  showAlert('Post rejected', 'warning');
  loadSocialQueue();
}

async function generateVideoScript() {
  const platform = document.getElementById('vid-platform').value;
  const type = document.getElementById('vid-type').value;
  const topic = document.getElementById('vid-topic').value;
  const duration = parseInt(document.getElementById('vid-duration').value);
  if (!topic.trim()) { showAlert('Enter a topic', 'error'); return; }
  document.getElementById('video-script-result').innerHTML = `<div class="loading-overlay"><div class="spinner"></div>Writing ${duration}-minute ${platform} script…</div>`;
  try {
    const res = await api('POST', '/social/video-script', { video_type: type, topic, duration_minutes: duration, platform });
    document.getElementById('video-script-result').innerHTML = `
      <div class="card">
        <div class="card-header"><span class="card-title">${platform === 'youtube' ? '▶' : '🎵'} ${platform.charAt(0).toUpperCase()+platform.slice(1)} Script — ${topic}</span>
          <button class="btn btn-ghost btn-sm" onclick="navigator.clipboard.writeText(document.querySelector('#video-script-result .ai-output').textContent);this.textContent='Copied!'">📋 Copy Script</button>
        </div>
        <div class="ai-output">${res.script}</div>
      </div>`;
  } catch(e) { document.getElementById('video-script-result').innerHTML = `<div class="alert alert-error">${e.message}</div>`; }
}

function saveSocialCreds(platform) {
  showAlert(`To save ${platform} credentials, open ~/aria-re/.env in a text editor and paste your keys there. Then restart the backend server.`, 'info');
}

// ─── AI Calling ───────────────────────────────────────────────────────────────
const DISPOSITION_LABELS = {
  interested:'🔥 Interested', not_interested:'Not Interested',
  follow_up_required:'Follow-up Required', management_contact_required:'Decision Maker Needed',
  management_not_available:'Mgmt Not Available', custom_plan_requested:'Custom Plan Requested',
  appointment_callback_needed:'📅 Appointment/Callback', closed_completed:'Closed',
  no_answer:'No Answer', voicemail:'Voicemail', wrong_number:'Wrong Number',
  do_not_call:'Do Not Call', called:'Called'
};

function switchCallingTab(tab) {
  ['campaigns','new','inbox','setup'].forEach(t => {
    document.getElementById('calling-'+t).style.display = t===tab ? 'block' : 'none';
  });
  document.querySelectorAll('#page-calling .tab').forEach((el,i) => {
    el.classList.toggle('active', ['campaigns','new','inbox','setup'][i] === tab);
  });
  if (tab === 'campaigns') loadCampaigns();
  if (tab === 'inbox') loadCallRecords();
  if (tab === 'setup') loadCallingSetup();
}

async function loadCallingStatus() {
  try {
    const s = await api('GET', '/calling/status');
    const banner = document.getElementById('calling-status-banner');
    if (banner) {
      if (!s.vapi_configured) {
        banner.innerHTML = `<div class="alert alert-warning">⚙ AI calling not connected yet. Go to the <strong>Setup</strong> tab to connect Vapi + Twilio. You can still build campaigns now — they'll run once connected.</div>`;
      } else {
        banner.innerHTML = `<div class="alert alert-success">✅ AI calling is live and ready.</div>`;
      }
    }
    return s;
  } catch(e) { return {}; }
}

async function loadCallingSetup() {
  const s = await loadCallingStatus();
  const badge = (ok) => ok
    ? '<span class="badge badge-active">✅ Connected</span>'
    : '<span class="badge badge-d">⚠ Not Connected</span>';
  document.getElementById('vapi-status-badge').innerHTML = badge(s.vapi_configured);
  document.getElementById('twilio-status-badge').innerHTML = badge(s.twilio_configured);
  document.getElementById('webhook-url-display').innerHTML = s.webhook_url
    ? `<div class="alert alert-success" style="font-size:12px">Webhook active: <code>${s.webhook_url}</code></div>`
    : `<div class="alert alert-warning" style="font-size:12px">No PUBLIC_BASE_URL set — call results won't sync until you add one.</div>`;
}

async function loadCampaigns() {
  await loadCallingStatus();
  const el = document.getElementById('campaigns-list');
  el.innerHTML = `<div class="loading-overlay"><div class="spinner"></div></div>`;
  try {
    const camps = await api('GET', '/calling/campaigns');
    if (!camps.length) {
      el.innerHTML = `<div style="text-align:center;padding:40px;color:var(--muted)">No campaigns yet. Create one in the <strong>New Campaign</strong> tab.</div>`;
      return;
    }
    el.innerHTML = camps.map(c => {
      const statusBadge = {running:'badge-active',paused:'badge-pending',stopped:'badge-d',draft:'badge-new',completed:'badge-closed'}[c.status]||'badge-new';
      return `<div class="card" style="margin-bottom:12px">
        <div class="card-header">
          <div><span class="card-title">${c.name}</span>
            <div style="font-size:12px;color:var(--muted);margin-top:2px">${c.goal}</div></div>
          <span class="badge ${statusBadge}">${c.status.toUpperCase()}</span>
        </div>
        <div class="stats-grid" style="margin:12px 0;grid-template-columns:repeat(5,1fr)">
          <div><div style="font-size:20px;font-weight:800;color:var(--primary)">${c.total_leads}</div><div style="font-size:11px;color:var(--muted)">LEADS</div></div>
          <div><div style="font-size:20px;font-weight:800;color:var(--primary)">${c.calls_placed}</div><div style="font-size:11px;color:var(--muted)">CALLED</div></div>
          <div><div style="font-size:20px;font-weight:800;color:var(--primary)">${c.calls_connected}</div><div style="font-size:11px;color:var(--muted)">CONNECTED</div></div>
          <div><div style="font-size:20px;font-weight:800;color:var(--success)">${c.interested_count}</div><div style="font-size:11px;color:var(--muted)">INTERESTED</div></div>
          <div><div style="font-size:20px;font-weight:800;color:var(--accent-dark)">${c.appointments_set}</div><div style="font-size:11px;color:var(--muted)">APPTS</div></div>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          ${c.status !== 'running' ? `<button class="btn btn-success btn-sm" onclick="controlCampaign(${c.id},'start')">▶ Start</button>` : ''}
          ${c.status === 'running' ? `<button class="btn btn-ghost btn-sm" onclick="controlCampaign(${c.id},'pause')">⏸ Pause</button>` : ''}
          ${c.status !== 'stopped' ? `<button class="btn btn-danger btn-sm" onclick="controlCampaign(${c.id},'stop')">⏹ Stop</button>` : ''}
          <span style="font-size:12px;color:var(--muted);margin-left:auto;align-self:center">Window: ${c.call_window_start}–${c.call_window_end}</span>
        </div>
      </div>`;
    }).join('');
  } catch(e) { el.innerHTML = `<div class="alert alert-error">${e.message}</div>`; }
}

async function controlCampaign(id, action) {
  try {
    const res = await api('POST', `/calling/campaigns/${id}/${action}`);
    showAlert(res.message || `Campaign ${res.status}`);
    loadCampaigns();
  } catch(e) { showAlert(e.message, 'error'); }
}

async function createCampaign() {
  const name = document.getElementById('camp-name').value;
  const goal = document.getElementById('camp-goal').value;
  const offer = document.getElementById('camp-offer').value;
  if (!name || !goal || !offer) { showAlert('Name, goal, and offer are required','error','#campaign-alert'); return; }
  const questions = document.getElementById('camp-questions').value.split('\n').map(q=>q.trim()).filter(Boolean);

  // Enroll all current leads in new/contacted stage
  const leadIds = leads.filter(l => ['new','contacted'].includes(l.stage)).map(l => l.id);

  document.getElementById('campaign-script-preview').innerHTML = `<div class="loading-overlay"><div class="spinner"></div>Writing AI calling script…</div>`;
  try {
    const res = await api('POST', '/calling/campaigns', {
      name, goal, offer, qualifying_questions: questions, lead_ids: leadIds,
      call_window_start: document.getElementById('camp-start').value,
      call_window_end: document.getElementById('camp-end').value,
      max_attempts: parseInt(document.getElementById('camp-attempts').value)||3,
      notify_email: document.getElementById('camp-notify').value || null
    });
    const script = res.generated_script || {};
    document.getElementById('campaign-script-preview').innerHTML = `
      <div class="alert alert-success">✅ Campaign created with ${leadIds.length} leads enrolled!</div>
      <div class="card">
        <div class="card-header"><span class="card-title">🎬 AI Script Preview</span></div>
        <div class="form-group"><label>Opening Line</label><div class="ai-output" style="font-size:13px">"${script.first_message||''}"</div></div>
        <div class="form-group"><label>AI Instructions</label><div class="ai-output" style="font-size:12px">${script.system_prompt||''}</div></div>
        <div class="form-group"><label>Decision-Maker Handling</label><div style="font-size:13px;background:rgba(255,255,255,0.05);padding:10px;border-radius:6px">${script.decision_maker_handling||''}</div></div>
        ${script.voicemail_message ? `<div class="form-group"><label>Voicemail</label><div style="font-size:13px;font-style:italic">"${script.voicemail_message}"</div></div>` : ''}
        <button class="btn btn-primary" onclick="switchCallingTab('campaigns')">Go to Campaigns →</button>
      </div>`;
  } catch(e) { document.getElementById('campaign-script-preview').innerHTML = `<div class="alert alert-error">${e.message}</div>`; }
}

async function loadCallRecords() {
  const el = document.getElementById('call-records-list');
  el.innerHTML = `<div class="loading-overlay"><div class="spinner"></div></div>`;
  const filter = document.getElementById('disposition-filter')?.value || '';
  try {
    const records = await api('GET', `/calling/records${filter?'?disposition='+filter:''}`);
    if (!records.length) {
      el.innerHTML = `<div style="text-align:center;padding:40px;color:var(--muted)">No call results yet. Results appear here automatically as calls complete.</div>`;
      return;
    }
    el.innerHTML = `<div class="table-wrap"><table>
      <thead><tr><th>Phone</th><th>Outcome</th><th>Summary</th><th>Decision Maker</th><th>Callback</th><th>Recording</th></tr></thead>
      <tbody>${records.map(r => `<tr>
        <td><strong>${r.phone_number}</strong>${r.business_name?`<br><span style="font-size:11px;color:var(--muted)">${r.business_name}</span>`:''}</td>
        <td><span class="badge ${r.disposition==='interested'?'badge-a':r.disposition==='not_interested'?'badge-d':'badge-b'}">${DISPOSITION_LABELS[r.disposition]||r.disposition||r.status}</span></td>
        <td style="max-width:280px;font-size:12px">${r.summary||'—'}</td>
        <td style="font-size:12px">${r.decision_maker_name||'—'}</td>
        <td style="font-size:12px">${r.best_callback_time||'—'}</td>
        <td>${r.recording_url?`<a href="${r.recording_url}" target="_blank" class="btn btn-ghost btn-sm">▶ Play</a>`:'—'}</td>
      </tr>`).join('')}</tbody></table></div>`;
  } catch(e) { el.innerHTML = `<div class="alert alert-error">${e.message}</div>`; }
}

// ─── Lead Generator ───────────────────────────────────────────────────────────
let lastHuntResults = null;

function initLeadGen() {
  const typeSel = document.getElementById('lg-type');
  if (typeSel && !typeSel.dataset.bound) {
    typeSel.dataset.bound = '1';
    typeSel.addEventListener('change', () => {
      document.getElementById('lg-niche-wrap').style.display =
        typeSel.value === 'ai_service_clients' ? 'block' : 'none';
    });
  }
  loadSchedules();
}

const HUNT_LABELS = {
  seller_leads: '🏡 Seller / Listing', fsbo: '🏷️ FSBO', expired_fsbo: '🔥 Expired & FSBO',
  distressed: '⚠️ Distressed', ai_service_clients: '💼 AI-Service',
};

async function createSchedule() {
  const body = {
    hunt_type: document.getElementById('lg-type').value,
    city: document.getElementById('lg-city').value,
    state: (document.getElementById('lg-state').value || '').trim().toUpperCase(),
    niche: document.getElementById('lg-niche').value,
    provider: document.getElementById('lg-provider').value,
    frequency: document.getElementById('lg-frequency').value,
    enabled: true,
  };
  try {
    await api('POST', '/leadgen/schedules', body);
    showAlert(`⏰ Scheduled ${HUNT_LABELS[body.hunt_type]||body.hunt_type} to run ${body.frequency}. NOVA will add new leads automatically.`);
    loadSchedules();
  } catch(e) { showAlert(e.message, 'error'); }
}

async function loadSchedules() {
  const el = document.getElementById('lg-schedules');
  if (!el) return;
  try {
    const rows = await api('GET', '/leadgen/schedules');
    if (!rows.length) { el.innerHTML = `<div style="color:var(--muted);font-size:13px">No scheduled hunts yet. Pick a hunt above and click "Schedule This Hunt".</div>`; return; }
    el.innerHTML = `<div class="table-wrap"><table>
      <thead><tr><th>Hunt</th><th>Where</th><th>Every</th><th>Status</th><th>Last Run</th><th>Total Added</th><th>Actions</th></tr></thead>
      <tbody>${rows.map(s=>`<tr>
        <td><strong>${HUNT_LABELS[s.hunt_type]||s.hunt_type}</strong></td>
        <td>${[s.city,s.state].filter(Boolean).join(', ')||'—'}</td>
        <td>${s.frequency}</td>
        <td>${s.enabled?'<span class="badge badge-a">● On</span>':'<span class="badge badge-d">Off</span>'}</td>
        <td style="font-size:12px">${s.last_status||'not yet run'}</td>
        <td style="font-weight:700">${s.total_saved||0}</td>
        <td>
          <button class="btn btn-ghost btn-sm" onclick="runScheduleNow(${s.id})">▶ Run now</button>
          <button class="btn btn-ghost btn-sm" onclick="toggleSchedule(${s.id}, ${s.enabled?'false':'true'})">${s.enabled?'Pause':'Resume'}</button>
          <button class="btn btn-ghost btn-sm" style="color:var(--danger,#c0392b)" onclick="deleteSchedule(${s.id})">Delete</button>
        </td></tr>`).join('')}</tbody></table></div>`;
  } catch(e) { el.innerHTML = `<div class="alert alert-error">${e.message}</div>`; }
}

async function runScheduleNow(id) {
  showAlert('Running hunt now…', 'info');
  try {
    const res = await api('POST', `/leadgen/schedules/${id}/run`);
    showAlert(`Hunt ran: found ${res.ran.found}, added ${res.ran.saved} new leads.`);
    loadSchedules();
  } catch(e) { showAlert(e.message, 'error'); }
}

async function toggleSchedule(id, enabled) {
  try { await api('PUT', `/leadgen/schedules/${id}`, { enabled }); loadSchedules(); }
  catch(e) { showAlert(e.message, 'error'); }
}

async function deleteSchedule(id) {
  if (!confirm('Delete this scheduled hunt?')) return;
  try { await api('DELETE', `/leadgen/schedules/${id}`); showAlert('Scheduled hunt deleted.'); loadSchedules(); }
  catch(e) { showAlert(e.message, 'error'); }
}

async function runHunt() {
  const hunt_type = document.getElementById('lg-type').value;
  const city = document.getElementById('lg-city').value;
  const state = (document.getElementById('lg-state').value || '').trim().toUpperCase();
  const niche = document.getElementById('lg-niche').value;
  const provider = document.getElementById('lg-provider').value;
  const auto_save = document.getElementById('lg-autosave').checked;
  document.getElementById('lg-results').innerHTML = `<div class="loading-overlay"><div class="spinner"></div>Scanning public sources for real leads…</div>`;
  try {
    const res = await api('POST', '/leadgen/hunt', { hunt_type, city, state, niche, provider, auto_save });
    lastHuntResults = res;
    if (res.auto_saved) {
      showAlert(`⚡ Auto-added ${res.auto_saved.saved} leads to CRM (scored). ${res.auto_saved.skipped_duplicates} duplicates skipped.`);
    }

    if (res.configured === false) {
      document.getElementById('lg-results').innerHTML = `<div class="alert alert-warning">${res.message}</div>`;
      return;
    }
    if (!res.leads || !res.leads.length) {
      document.getElementById('lg-results').innerHTML = `<div class="alert alert-info">No real leads found in public sources for this search. Try a different area, or connect a paid provider for verified homeowner lists.</div>`;
      return;
    }

    const isBiz = hunt_type === 'ai_service_clients';
    const rows = res.leads.map((l, i) => {
      const contact = l.contact_status === 'found'
        ? '<span class="badge badge-a">✓ Has Contact</span>'
        : '<span class="badge badge-c">Needs Skip Trace</span>';
      if (isBiz) {
        return `<tr><td>${i+1}</td><td><strong>${l.business_name||'—'}</strong><br><span style="font-size:11px;color:var(--muted)">${l.contact_name||''}</span></td>
          <td>${l.phone||'—'}<br>${l.email||''}</td><td style="font-size:12px;max-width:280px">${l.why_good_fit||''}</td><td>${contact}</td></tr>`;
      }
      return `<tr><td>${i+1}</td><td><strong>${(l.first_name||'')+' '+(l.last_name||'')}</strong><br><span style="font-size:11px;color:var(--muted)">${l.address||''} ${l.city||''}</span></td>
        <td>${l.phone||'—'}<br>${l.email||''}</td><td style="font-size:12px;max-width:280px">${l.sell_signal||(l.has_expired_listing?'Expired listing':'')||''}</td><td>${contact}</td></tr>`;
    }).join('');

    document.getElementById('lg-results').innerHTML = `
      <div class="card">
        <div class="card-header">
          <span class="card-title">Found ${res.total} Leads</span>
          <button class="btn btn-success" onclick="saveHunt('${hunt_type}')">＋ Add All to CRM (scored)</button>
        </div>
        <div class="stats-grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:14px">
          <div class="stat-card"><div class="stat-value">${res.total}</div><div class="stat-label">Found</div></div>
          <div class="stat-card"><div class="stat-value" style="color:var(--success)">${res.with_contact}</div><div class="stat-label">With Contact</div></div>
          <div class="stat-card"><div class="stat-value" style="color:var(--warning)">${res.needs_skip_trace}</div><div class="stat-label">Needs Skip Trace</div></div>
        </div>
        ${res.note ? `<div class="alert alert-info" style="margin-bottom:12px">${res.note}</div>` : ''}
        <div class="table-wrap"><table><thead><tr><th>#</th><th>${isBiz?'Business':'Owner'}</th><th>Contact</th><th>${isBiz?'Why a fit':'Sell Signal'}</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table></div>
      </div>`;
  } catch(e) { document.getElementById('lg-results').innerHTML = `<div class="alert alert-error">${e.message}</div>`; }
}

async function saveHunt(hunt_type) {
  if (!lastHuntResults || !lastHuntResults.leads) return;
  try {
    const res = await api('POST', '/leadgen/save', { hunt_type, leads: lastHuntResults.leads });
    showAlert(`✅ Added ${res.saved} leads to CRM (scored & ranked). ${res.skipped_duplicates} duplicates skipped.`);
  } catch(e) { showAlert(e.message, 'error'); }
}

// ─── Finance ──────────────────────────────────────────────────────────────────
const SEGMENT_LABELS = { real_estate:'🏡 Real Estate', ai_tech:'🤖 AI / Tech', shared:'🔗 Shared' };

async function loadFinance() {
  await loadFinanceSummary();
  const filter = document.getElementById('exp-filter')?.value || '';
  try {
    const expenses = await api('GET', `/finance/expenses${filter?'?segment='+filter:''}`);
    const el = document.getElementById('finance-table');
    if (!expenses.length) {
      el.innerHTML = `<div style="text-align:center;padding:30px;color:var(--muted)">No expenses yet. Add one or click "Quick-add NOVA tool costs".</div>`;
      return;
    }
    el.innerHTML = `<div class="table-wrap"><table>
      <thead><tr><th>Date</th><th>Vendor</th><th>Category</th><th>Business</th><th>Recurrence</th><th>Amount</th><th>Tax</th><th></th></tr></thead>
      <tbody>${expenses.map(e => `<tr>
        <td style="font-size:12px">${fmtDate(e.date)}</td>
        <td><strong>${e.vendor}</strong>${e.description?`<br><span style="font-size:11px;color:var(--muted)">${e.description}</span>`:''}</td>
        <td style="font-size:12px">${e.category||'—'}</td>
        <td><span style="font-size:12px">${SEGMENT_LABELS[e.segment]||e.segment}</span></td>
        <td><span style="font-size:12px">${e.recurrence.replace('_',' ')}</span></td>
        <td><strong>${fmt$(e.amount)}</strong></td>
        <td>${e.is_tax_deductible?'✅':'—'}</td>
        <td><button class="btn btn-ghost btn-sm" onclick="deleteExpense(${e.id})">✕</button></td>
      </tr>`).join('')}</tbody></table></div>`;
  } catch(e) { document.getElementById('finance-table').innerHTML = `<div class="alert alert-error">${e.message}</div>`; }
}

async function loadFinanceSummary() {
  try {
    const s = await api('GET', '/finance/summary');
    document.getElementById('finance-stats').innerHTML = `
      <div class="stat-card"><div class="stat-value">${fmt$(s.monthly_recurring_burn)}</div><div class="stat-label">Monthly Recurring Burn</div><div class="stat-change">${fmt$(s.annual_recurring)}/yr</div></div>
      <div class="stat-card"><div class="stat-value">${fmt$(s.by_segment.real_estate)}</div><div class="stat-label">🏡 Real Estate Total</div></div>
      <div class="stat-card"><div class="stat-value">${fmt$(s.by_segment.ai_tech)}</div><div class="stat-label">🤖 AI / Tech Total</div></div>
      <div class="stat-card"><div class="stat-value" style="color:var(--success)">${fmt$(s.deductible_ytd)}</div><div class="stat-label">Tax-Deductible YTD</div></div>`;
    // Breakdown by category
    const cats = Object.entries(s.by_category || {});
    document.getElementById('finance-breakdown').innerHTML = cats.length
      ? cats.map(([c,v]) => `<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border);font-size:13px"><span>${c}</span><strong>${fmt$(v)}</strong></div>`).join('')
        + `<div style="margin-top:10px;font-size:12px;color:var(--muted)">${s.recurring_items.length} recurring subscriptions tracked</div>`
      : '<div style="color:var(--muted);font-size:13px;padding:10px">No data yet.</div>';
  } catch(e) {
    document.getElementById('finance-stats').innerHTML = `<div class="alert alert-error">${e.message}</div>`;
  }
}

async function addExpense() {
  const amount = parseFloat(document.getElementById('exp-amount').value);
  const vendor = document.getElementById('exp-vendor').value;
  if (!amount || !vendor) { showAlert('Amount and vendor required','error','#exp-alert'); return; }
  const data = {
    amount, vendor,
    description: document.getElementById('exp-desc').value,
    segment: document.getElementById('exp-segment').value,
    recurrence: document.getElementById('exp-recurrence').value,
    category: document.getElementById('exp-category').value || null,
    is_tax_deductible: document.getElementById('exp-deductible').checked,
  };
  try {
    await api('POST', '/finance/expenses', data);
    showAlert('Expense added' + (data.category ? '' : ' & auto-categorized'));
    ['exp-amount','exp-vendor','exp-desc','exp-category'].forEach(id => document.getElementById(id).value='');
    loadFinance();
  } catch(e) { showAlert(e.message,'error','#exp-alert'); }
}

async function deleteExpense(id) {
  await api('DELETE', `/finance/expenses/${id}`);
  loadFinance();
}

async function seedAriaStack() {
  try {
    const res = await api('POST', '/finance/seed-aria-stack');
    showAlert(`Added ${res.added} NOVA tool costs (edit amounts as needed). ${res.skipped_existing} already tracked.`);
    loadFinance();
  } catch(e) { showAlert(e.message,'error','#exp-alert'); }
}

async function loadFinanceReport() {
  document.getElementById('finance-report').innerHTML = `<div class="loading-overlay"><div class="spinner"></div>Analyzing your spending…</div>`;
  try {
    const res = await api('GET', '/finance/report');
    document.getElementById('finance-report').innerHTML = `<div class="card" style="margin-bottom:20px"><div class="card-header"><span class="card-title">🧠 Finance Report</span></div><div class="ai-output">${res.report}</div></div>`;
  } catch(e) { document.getElementById('finance-report').innerHTML = `<div class="alert alert-error">${e.message}</div>`; }
}

// ─── Page Renderers ───────────────────────────────────────────────────────────
const pageRenderers = {
  dashboard: renderDashboard,
  leads: renderLeads,
  calllist: renderCallList,
  market: renderMarket,
  social: () => loadPlatformStatus(),
  calling: () => { loadCampaigns(); if (!leads.length) renderLeads(); },
  leadgen: initLeadGen,
  finance: loadFinance,
};

// ─── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  navigate('dashboard');
  document.getElementById('alert-area').innerHTML = '';
});

// ═══════════════════════════════════════════════════════════════════════════
// AI AUTOMATIONS — live demo simulator (illustrative; shows what NOVA does)
// ═══════════════════════════════════════════════════════════════════════════
let __autoTimer = null;
function _autoReset() { if (__autoTimer) { clearTimeout(__autoTimer); __autoTimer = null; } }
function _bubble(side, who, text, sub) {
  const mine = side === 'right';
  return `<div style="display:flex;justify-content:${mine?'flex-end':'flex-start'};margin:8px 0">
    <div style="max-width:74%">
      <div style="font-size:11px;color:var(--text-dim);margin:0 6px 3px;${mine?'text-align:right':''}">${who}</div>
      <div style="padding:11px 15px;border-radius:16px;font-size:14.5px;line-height:1.5;
        background:${mine?'var(--gold-gradient)':'rgba(255,255,255,0.08)'};
        color:${mine?'#0d0d0f':'var(--text-light)'};
        border:1px solid ${mine?'transparent':'var(--glass-border-soft)'};
        border-${mine?'bottom-right':'bottom-left'}-radius:4px">${text}</div>
      ${sub?`<div style="font-size:11px;color:var(--text-dim);margin:3px 6px 0;${mine?'text-align:right':''}">${sub}</div>`:''}
    </div></div>`;
}
function _stageHeader(icon, title, tag) {
  return `<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
    <span style="font-size:26px">${icon}</span>
    <span style="font-family:var(--serif);font-size:21px;font-weight:700;color:var(--text-light)">${title}</span>
    <span class="badge badge-a" style="margin-left:auto">${tag}</span></div>
  <div style="height:1px;background:var(--glass-border-soft);margin-bottom:12px"></div>`;
}

const AUTO_SCRIPTS = {
  missedcall: { icon:'📱', title:'Missed-Call Text-Back', tag:'0 leads lost',
    steps:[
      {d:400, h:`<div style="text-align:center;color:var(--text-dim);font-size:13px;margin:6px 0">📞 <strong>Incoming call</strong> — you’re on a job and can’t pick up…</div>`},
      {d:1400, b:['left','Missed call','☎️ Missed call from (408) 555-0142','just now']},
      {d:1500, b:['right','NOVA · auto-text','Hi! This is Bright Smile Dental 😊 Sorry we missed you — we were with a patient. How can we help? Reply here and we’ll get you booked.','sent 4 seconds later']},
      {d:1600, b:['left','Caller','Hi, do you have any openings this week for a cleaning?']},
      {d:1500, b:['right','NOVA','We do! I have Thursday 2:00pm or Friday 10:30am. Which works better?']},
      {d:1400, b:['left','Caller','Thursday 2 works great']},
      {d:1500, b:['right','NOVA','Perfect — you’re booked for Thursday at 2:00pm ✅ I’ll text a reminder the day before. See you then!','booked automatically']},
      {d:1200, done:'✅ Caller booked in 90 seconds — without you touching the phone.'}
    ]},
  answer: { icon:'🤖', title:'AI Phone Answering', tag:'Answered in 1 ring',
    steps:[
      {d:400, h:`<div style="text-align:center;color:var(--text-dim);font-size:13px;margin:6px 0">📞 <strong>Live call</strong> — NOVA picks up on the first ring…</div>`},
      {d:1300, b:['right','NOVA','Thanks for calling Pro Comfort Heating & Air, this is Nova! How can I help today?']},
      {d:1500, b:['left','Caller','Yeah, my AC stopped working and it’s 95 degrees.']},
      {d:1500, b:['right','NOVA','Oh no — let’s get someone out fast. Is this for your home or a business, and what’s the zip code?']},
      {d:1400, b:['left','Caller','Home, 95124.']},
      {d:1500, b:['right','NOVA','Got it. I can get a technician to you today between 3 and 5pm. Can I grab your name and the best number?']},
      {d:1400, b:['left','Caller','Mike, 408-555-0199.']},
      {d:1500, b:['right','NOVA','You’re all set, Mike — a tech is booked for 3–5pm today and I’ve texted you a confirmation. Anything else?','job booked + logged']},
      {d:1200, done:'✅ After-hours call answered, qualified, and booked — no voicemail, no lost job.'}
    ]},
  followup: { icon:'✉️', title:'Auto Follow-Up Sequence', tag:'Never drops a lead',
    steps:[
      {d:400, h:`<div style="text-align:center;color:var(--text-dim);font-size:13px;margin:6px 0">🌐 New lead from your website — <strong>Sarah</strong>, asked about a quote…</div>`},
      {d:1300, b:['right','NOVA · Day 0, 2 min later','Hi Sarah! Thanks for reaching out to Green Valley Landscaping 🌿 I’d love to get you a quote. What’s the project you have in mind?','text']},
      {d:1500, b:['left','Sarah','Front yard redesign, maybe drought-friendly.']},
      {d:1500, b:['right','NOVA','Love that. Want me to set up a free 15-min walkthrough? I have Tuesday or Wednesday afternoon.']},
      {d:1300, h:`<div style="text-align:center;color:var(--text-dim);font-size:12.5px;margin:4px 0">…no reply yet — NOVA keeps going, automatically…</div>`},
      {d:1500, b:['right','NOVA · Day 1','Hi Sarah! Just following up 🌼 Here are a few drought-friendly yards we recently did: [photos]. Still happy to set up that free walkthrough whenever you’re ready.','email']},
      {d:1500, b:['left','Sarah','These look amazing — Wednesday works!']},
      {d:1400, b:['right','NOVA','Wonderful — booked for Wednesday 3pm ✅ You’ll get a reminder. Talk soon!','booked']},
      {d:1200, done:'✅ Lead nurtured across 2 days and booked — zero effort from you.'}
    ]},
};

function playAuto(kind) {
  _autoReset();
  const cfg = AUTO_SCRIPTS[kind];
  const stage = document.getElementById('auto-stage-body');
  if (!cfg || !stage) return;
  stage.style.cssText = 'min-height:300px';
  stage.innerHTML = _stageHeader(cfg.icon, cfg.title, cfg.tag) + `<div id="auto-feed"></div>`;
  const feed = document.getElementById('auto-feed');
  let i = 0;
  function next() {
    if (i >= cfg.steps.length) return;
    const s = cfg.steps[i++];
    if (s.h) feed.insertAdjacentHTML('beforeend', s.h);
    if (s.b) feed.insertAdjacentHTML('beforeend', _bubble(s.b[0], s.b[1], s.b[2], s.b[3]));
    if (s.done) feed.insertAdjacentHTML('beforeend',
      `<div class="alert alert-success" style="margin-top:14px;font-size:14.5px;text-align:center">${s.done}
       <div style="margin-top:8px"><button class="btn btn-ghost btn-sm" onclick="playAuto('${kind}')">↻ Replay</button></div></div>`);
    stage.scrollTop = stage.scrollHeight;
    const stageEl = document.getElementById('auto-stage');
    if (stageEl) stageEl.scrollIntoView({behavior:'smooth', block:'nearest'});
    __autoTimer = setTimeout(next, s.d || 1200);
  }
  next();
}

// Business name for the leads table: prefer address (demo leads), else parse the
// company out of life_event ("Owner/Founder at TailWag Resorts (consumer services)").
function bizName(l) {
  if (l.address) return l.address;
  const le = l.life_event || '';
  let m = le.match(/\bat\s+(.+?)(?:\s*\(|$)/i);
  if (m) return m[1].trim();
  return le ? le.replace(/\s*\(.*?\)\s*/,'').trim() : '—';
}

// UFCStats Web Dashboard Application Logic

document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initFighterSearch();
  initPredictor();
  initModal();
  loadUpcomingEvents();
  loadFighterDirectory('');
  loadDiagnostics();
});

function initModal() {
  const modal = document.getElementById('event-modal');
  const closeBtn = document.getElementById('modal-close-btn');

  if (closeBtn && modal) {
    closeBtn.addEventListener('click', () => {
      modal.classList.add('hidden');
    });
    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.classList.add('hidden');
    });
  }
}

// ------------------------------------------------------------------
// 1. Navigation Tabs
// ------------------------------------------------------------------

function initTabs() {
  const buttons = document.querySelectorAll('.tab-btn');
  const sections = document.querySelectorAll('.tab-content');

  buttons.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetTab = btn.getAttribute('data-tab');

      buttons.forEach(b => b.classList.remove('active'));
      sections.forEach(s => s.classList.remove('active'));

      btn.classList.add('active');
      const targetEl = document.getElementById(`tab-${targetTab}`);
      if (targetEl) targetEl.classList.add('active');
    });
  });
}

// ------------------------------------------------------------------
// 2. Fighter Search & Dropdowns
// ------------------------------------------------------------------

let fightersCache = [];

async function fetchFightersList(query = '') {
  try {
    const res = await fetch(`/api/v1/fighters?limit=100&q=${encodeURIComponent(query)}`);
    const data = await res.json();
    return data.data || [];
  } catch (err) {
    console.error('Error fetching fighters:', err);
    return [];
  }
}

function initFighterSearch() {
  const f1Input = document.getElementById('f1-search');
  const f2Input = document.getElementById('f2-search');
  const f1Select = document.getElementById('f1-select');
  const f2Select = document.getElementById('f2-select');

  // Load initial top fighters
  fetchFightersList('').then(list => {
    fightersCache = list;
    populateSelect(f1Select, list);
    populateSelect(f2Select, list);
  });

  f1Input.addEventListener('input', debounce(async (e) => {
    const list = await fetchFightersList(e.target.value);
    populateSelect(f1Select, list);
  }, 300));

  f2Input.addEventListener('input', debounce(async (e) => {
    const list = await fetchFightersList(e.target.value);
    populateSelect(f2Select, list);
  }, 300));
}

function populateSelect(selectEl, list) {
  selectEl.innerHTML = '';
  list.forEach(f => {
    const opt = document.createElement('option');
    opt.value = f.fighter_id;
    const name = `${f.first_name || ''} ${f.last_name || ''}`.trim() || f.fighter_id;
    opt.textContent = `${name} (${f.stance || 'Unknown'}, ${f.weight_kg ? f.weight_kg + 'kg' : '--'})`;
    selectEl.appendChild(opt);
  });
}

function debounce(func, wait) {
  let timeout;
  return function (...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => func.apply(this, args), wait);
  };
}

// ------------------------------------------------------------------
// 3. Matchup Predictor & Tale of the Tape
// ------------------------------------------------------------------

function initPredictor() {
  const btnPredict = document.getElementById('btn-predict');
  const f1Select = document.getElementById('f1-select');
  const f2Select = document.getElementById('f2-select');

  btnPredict.addEventListener('click', async () => {
    const f1Id = f1Select.value;
    const f2Id = f2Select.value;

    if (!f1Id || !f2Id) {
      alert('Please select Fighter 1 and Fighter 2 from the lists.');
      return;
    }

    if (f1Id === f2Id) {
      alert('Please select two different fighters.');
      return;
    }

    btnPredict.textContent = '⏳ Simulating Matchup...';
    btnPredict.disabled = true;

    try {
      const res = await fetch(`/api/v1/predict?fighter1_id=${encodeURIComponent(f1Id)}&fighter2_id=${encodeURIComponent(f2Id)}`);
      if (!res.ok) throw new Error('Prediction API error');
      const data = await res.json();
      renderPredictionResult(data);
    } catch (err) {
      alert('Error simulating matchup: ' + err.message);
    } finally {
      btnPredict.textContent = '⚡ Simulate Fight Matchup';
      btnPredict.disabled = false;
    }
  });
}

function renderPredictionResult(data) {
  const area = document.getElementById('prediction-result');
  area.classList.remove('hidden');

  const f1 = data.fighter1 || {};
  const f2 = data.fighter2 || {};
  const p1 = Math.round(data.fighter1_win_probability * 100);
  const p2 = Math.round(data.fighter2_win_probability * 100);

  // Header names
  document.getElementById('res-f1-name').textContent = `${f1.first_name || ''} ${f1.last_name || ''}`.trim();
  document.getElementById('res-f1-nickname').textContent = f1.nickname ? `"${f1.nickname}"` : '';

  document.getElementById('res-f2-name').textContent = `${f2.first_name || ''} ${f2.last_name || ''}`.trim();
  document.getElementById('res-f2-nickname').textContent = f2.nickname ? `"${f2.nickname}"` : '';

  // Winner badge & Confidence
  const winnerName = data.predicted_winner === 1 ? f1.last_name || 'Fighter 1' : f2.last_name || 'Fighter 2';
  document.getElementById('predicted-winner-badge').textContent = `Predicted Winner: ${winnerName}`;
  document.getElementById('confidence-text').textContent = `Confidence: ${data.confidence_pct}%`;

  // Probability Bar
  document.getElementById('f1-prob-val').textContent = `${p1}%`;
  document.getElementById('f2-prob-val').textContent = `${p2}%`;
  document.getElementById('f1-prob-fill').style.width = `${p1}%`;
  document.getElementById('f2-prob-fill').style.width = `${p2}%`;

  // Comparative Tale of the Tape
  const body = document.getElementById('tape-table-body');
  body.innerHTML = '';

  const metrics = [
    { label: 'Height', v1: f1.height_cm ? `${f1.height_cm} cm` : '--', v2: f2.height_cm ? `${f2.height_cm} cm` : '--' },
    { label: 'Reach', v1: f1.reach_cm ? `${f1.reach_cm} cm` : '--', v2: f2.reach_cm ? `${f2.reach_cm} cm` : '--' },
    { label: 'Ape Index', v1: (f1.reach_cm && f1.height_cm) ? `${(f1.reach_cm - f1.height_cm).toFixed(1)} cm` : '--', v2: (f2.reach_cm && f2.height_cm) ? `${(f2.reach_cm - f2.height_cm).toFixed(1)} cm` : '--' },
    { label: 'Stance', v1: f1.stance || '--', v2: f2.stance || '--' },
    { label: 'Record (W-L-D)', v1: `${f1.wins || 0}-${f1.losses || 0}-${f1.draws || 0}`, v2: `${f2.wins || 0}-${f2.losses || 0}-${f2.draws || 0}` },
    { label: 'Sig. Strikes / min', v1: f1.slpm ?? '--', v2: f2.slpm ?? '--' },
    { label: 'Striking Accuracy', v1: f1.str_acc ? `${f1.str_acc}%` : '--', v2: f2.str_acc ? `${f2.str_acc}%` : '--' },
    { label: 'Striking Defense', v1: f1.str_def ? `${f1.str_def}%` : '--', v2: f2.str_def ? `${f2.str_def}%` : '--' },
    { label: 'Takedowns / 15m', v1: f1.td_avg ?? '--', v2: f2.td_avg ?? '--' },
    { label: 'Takedown Def.', v1: f1.td_def ? `${f1.td_def}%` : '--', v2: f2.td_def ? `${f2.td_def}%` : '--' },
  ];

  metrics.forEach(m => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td style="text-align: right; font-weight: 600;">${m.v1}</td>
      <td style="text-align: center; color: var(--text-muted); font-size: 0.85rem;">${m.label}</td>
      <td style="text-align: left; font-weight: 600;">${m.v2}</td>
    `;
    body.appendChild(tr);
  });
}

// ------------------------------------------------------------------
// 4. Upcoming Events
// ------------------------------------------------------------------

async function loadUpcomingEvents() {
  const container = document.getElementById('upcoming-events-list');
  try {
    const res = await fetch('/api/v1/events/upcoming');
    const events = await res.json();

    if (!events || events.length === 0) {
      container.innerHTML = '<div class="glass-card" style="padding: 1.5rem;">No upcoming scheduled events currently found in database.</div>';
      return;
    }

    container.innerHTML = '';
    events.forEach(evt => {
      const card = document.createElement('div');
      card.className = 'event-card glass-card';
      card.innerHTML = `
        <div>
          <h3>${evt.name}</h3>
          <div class="event-meta">📅 ${evt.date || 'TBD'} | 📍 ${evt.location || 'Unknown'}</div>
        </div>
        <button class="btn-primary" style="padding: 0.5rem 1rem; font-size: 0.85rem;" onclick="viewEventCard('${evt.event_id}')">View Fight Card</button>
      `;
      container.appendChild(card);
    });
  } catch (err) {
    container.innerHTML = '<div class="glass-card" style="padding: 1.5rem; color: var(--red-accent);">Error loading upcoming events.</div>';
  }
}

async function viewEventCard(eventId) {
  const modal = document.getElementById('event-modal');
  const nameEl = document.getElementById('modal-event-name');
  const listEl = document.getElementById('modal-fights-list');

  try {
    const res = await fetch(`/api/v1/events/${eventId}`);
    const data = await res.json();
    nameEl.textContent = data.name || 'Event Fight Card';
    listEl.innerHTML = '';

    if (!data.fights || data.fights.length === 0) {
      listEl.innerHTML = '<div style="color: var(--text-muted); padding: 1rem 0;">No fights listed for this event yet.</div>';
    } else {
      for (const f of data.fights) {
        const row = document.createElement('div');
        row.className = 'modal-fight-row';
        row.innerHTML = `
          <div>
            <strong style="color: var(--red-accent);">${f.fighter1_name || 'Fighter 1'}</strong> vs 
            <strong style="color: var(--blue-accent);">${f.fighter2_name || 'Fighter 2'}</strong>
            <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.2rem;">${f.weight_class || 'Bout'} ${f.title_fight ? '🏆 Title Fight' : ''}</div>
          </div>
          <div style="text-align: right; font-size: 0.85rem; color: var(--gold-accent);">
            ${f.method ? f.method : (f.outcome ? 'Result: ' + f.outcome : 'Scheduled Matchup')}
          </div>
        `;
        listEl.appendChild(row);
      }
    }
    modal.classList.remove('hidden');
  } catch (err) {
    console.error('Error loading fight card:', err);
  }
}

// ------------------------------------------------------------------
// 5. Fighter Search Directory Tab
// ------------------------------------------------------------------

function loadFighterDirectory(query = '') {
  const input = document.getElementById('dir-search-input');
  const grid = document.getElementById('fighters-grid');

  input.addEventListener('input', debounce(async (e) => {
    const list = await fetchFightersList(e.target.value);
    renderFightersGrid(grid, list);
  }, 300));

  fetchFightersList('').then(list => renderFightersGrid(grid, list));
}

function renderFightersGrid(grid, list) {
  grid.innerHTML = '';
  if (list.length === 0) {
    grid.innerHTML = '<div class="glass-card" style="padding: 1.5rem; grid-column: 1/-1;">No fighters found.</div>';
    return;
  }

  list.forEach(f => {
    const card = document.createElement('div');
    card.className = 'fighter-card glass-card';
    const name = `${f.first_name || ''} ${f.last_name || ''}`.trim();
    card.innerHTML = `
      <h3>${name}</h3>
      <div class="fighter-meta">
        ${f.nickname ? `"${f.nickname}"<br>` : ''}
        Stance: ${f.stance || 'Unknown'} | Height: ${f.height_cm ? f.height_cm + 'cm' : '--'}<br>
        Reach: ${f.reach_cm ? f.reach_cm + 'cm' : '--'}
      </div>
      <div style="font-size: 0.85rem; color: var(--green-success); font-weight: 600;">
        Record: ${f.wins || 0}W - ${f.losses || 0}L - ${f.draws || 0}D
      </div>
    `;
    grid.appendChild(card);
  });
}

// ------------------------------------------------------------------
// 6. Diagnostics Tab
// ------------------------------------------------------------------

async function loadDiagnostics() {
  const dbBox = document.getElementById('db-summary-box');
  const healthBox = document.getElementById('health-report-box');

  try {
    const resDb = await fetch('/api/v1/stats/summary');
    const summary = await resDb.json();

    dbBox.innerHTML = `
      <div class="metric-row"><span class="label">Events in DB</span><span class="value">${summary.events}</span></div>
      <div class="metric-row"><span class="label">Fights in DB</span><span class="value">${summary.fights}</span></div>
      <div class="metric-row"><span class="label">Fighter Profiles</span><span class="value">${summary.fighters}</span></div>
      <div class="metric-row"><span class="label">Round Stats Rows</span><span class="value">${summary.round_stats_rows}</span></div>
    `;

    const resHealth = await fetch('/api/v1/health');
    const health = await resHealth.json();

    healthBox.innerHTML = `
      <div class="metric-row"><span class="label">Data Quality Score</span><span class="value" style="font-size: 1.2rem; color: var(--gold-accent);">${health.health_score_pct}%</span></div>
      <div class="metric-row"><span class="label">Orphan Fights</span><span class="value">${health.orphans ? health.orphans.orphan_fights : 0}</span></div>
      <div class="metric-row"><span class="label">Completed Fights Missing Stats</span><span class="value">${health.missing_links ? health.missing_links.completed_fights_missing_stats : 0}</span></div>
    `;
  } catch (err) {
    dbBox.innerHTML = '<div style="color: var(--red-accent);">Error loading metrics</div>';
    healthBox.innerHTML = '<div style="color: var(--red-accent);">Error loading health</div>';
  }
}

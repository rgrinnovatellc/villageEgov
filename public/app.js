async function loadDashboard() {
  const response = await fetch('./village_governance_dashboard_data.json');
  if (!response.ok) {
    throw new Error('Failed to load dashboard bundle');
  }
  return response.json();
}

const dashboardState = {
  selectedNeed: '',
  selectedNodeId: ''
};

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function renderSummary(summary) {
  const pluralize = (label) => label.endsWith('s') ? label : `${label}s`;
  const scopeCards = (summary.scope_level_counts || []).map(level => [
    pluralize(level.name),
    level.count
  ]);
  const cards = [
    ['Needs', summary.need_count],
    ...scopeCards,
    ['Village Scope', summary.scope],
    ['Completeness', summary.completeness]
  ];
  document.getElementById('summary-cards').innerHTML = cards.map(([label, value]) => `
    <article class="card">
      <div class="label">${label}</div>
      <div class="value">${value}</div>
    </article>
  `).join('');
}

function renderInterventions(rows) {
  const html = `
    <table class="table">
      <thead>
        <tr>
          <th>Need</th>
          <th>Target</th>
          <th>Save</th>
          <th>Investment</th>
          <th>Priority</th>
          <th>Confidence</th>
        </tr>
      </thead>
      <tbody>
        ${rows.map(row => `
          <tr>
            <td>
              <strong>${row.need}</strong><br>
              <span class="meta">${row.time_horizon}</span>
            </td>
            <td>${row.target_scope}</td>
            <td>${row.total_hop_savings}</td>
            <td>${row.investment}</td>
            <td>${row.savings_per_effort.toFixed(2)}</td>
            <td><span class="pill">${row.confidence}</span></td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
  document.getElementById('interventions').innerHTML = html;
}

function renderScenarios(scenarios) {
  document.getElementById('scenarios').innerHTML = scenarios.map(scenario => `
    <article class="scenario">
      <h3>${scenario.name}</h3>
      <p>${scenario.notes || ''}</p>
      <div class="meta">Budget band: ${scenario.budget_band} | Hop savings: ${scenario.total_hop_savings} | Cost used: ${scenario.total_investment_cost}</div>
      <ul>
        ${scenario.selected.map(item => `<li>${item.need} -> ${item.target_scope} (save ${item.total_hop_savings}, inv ${item.investment})</li>`).join('')}
      </ul>
    </article>
  `).join('');
}

function renderGraphDetails(graph, edges, selectedNodeId) {
  const node = (graph.nodes || []).find(item => item.id === selectedNodeId);
  const target = document.getElementById('graph-details');
  if (!node) {
    target.innerHTML = '<article class="graph-detail-card"><h3>Graph Details</h3><p class="meta">Select a node to inspect its dependencies and responsibilities.</p></article>';
    return;
  }

  const incoming = edges.filter(edge => edge.target === selectedNodeId);
  const outgoing = edges.filter(edge => edge.source === selectedNodeId);
  const routedNeeds = [...new Set([...incoming, ...outgoing].flatMap(edge => edge.needs))].sort();

  target.innerHTML = `
    <article class="graph-detail-card">
      <h3>${escapeHtml(node.label)}</h3>
      <div class="meta">${escapeHtml(node.id)} | Scope ${escapeHtml(node.type)}</div>
      <div style="margin-top:10px;">
        <span class="pill">Satisfies ${(node.satisfies || []).length}</span>
        <span class="pill">Provides ${(node.provides || []).length}</span>
        <span class="pill">Requires ${(node.requires || []).length}</span>
      </div>
      <div style="margin-top:12px;">
        ${(node.satisfies || []).slice(0, 12).map(need => `<span class="pill">${escapeHtml(need)}</span>`).join('') || '<span class="meta">No local satisfies listed.</span>'}
      </div>
    </article>
    <article class="graph-detail-card">
      <h4>Incoming Dependencies</h4>
      <ul>
        ${incoming.length ? incoming.map(edge => `<li><strong>${escapeHtml(edge.source)}</strong> requests ${escapeHtml(edge.needs.join(', '))}</li>`).join('') : '<li>No incoming dependencies in this view.</li>'}
      </ul>
    </article>
    <article class="graph-detail-card">
      <h4>Outgoing Dependencies</h4>
      <ul>
        ${outgoing.length ? outgoing.map(edge => `<li>Depends on <strong>${escapeHtml(edge.target)}</strong> for ${escapeHtml(edge.needs.join(', '))}</li>`).join('') : '<li>No outgoing dependencies in this view.</li>'}
      </ul>
      <div style="margin-top:10px;">
        ${routedNeeds.map(need => `<span class="pill">${escapeHtml(need)}</span>`).join('') || '<span class="meta">No routed needs in this view.</span>'}
      </div>
    </article>
  `;
}

function renderGraph(graph, selectedNeed = '', selectedNodeId = '') {
  const filter = selectedNeed.trim();
  const edges = (graph.edges || []).filter(edge => !filter || edge.needs.includes(filter));

  if (!edges.length) {
    document.getElementById('graph-stats').innerHTML = '<span class="pill">No routes for this filter</span>';
    document.getElementById('graph').innerHTML = '<p class="meta">No dependency edges match the current need filter.</p>';
    document.getElementById('graph-details').innerHTML = '<article class="graph-detail-card"><h3>Graph Details</h3><p class="meta">No graph details available for this filter.</p></article>';
    return;
  }

  const activeIds = new Set();
  edges.forEach(edge => {
    activeIds.add(edge.source);
    activeIds.add(edge.target);
  });

  const columns = ['H', 'N', 'W', 'V'];
  const nodes = (graph.nodes || []).filter(node => activeIds.has(node.id));
  const grouped = Object.fromEntries(columns.map(type => [type, []]));
  nodes.forEach(node => grouped[node.type]?.push(node));
  columns.forEach(type => grouped[type].sort((a, b) => a.label.localeCompare(b.label)));

  const width = 1120;
  const columnWidth = 220;
  const leftPad = 80;
  const topPad = 80;
  const boxWidth = 130;
  const boxHeight = 42;
  const rowGap = 62;
  const maxRows = Math.max(...columns.map(type => grouped[type].length), 1);
  const height = Math.max(360, topPad + maxRows * rowGap + 60);
  const positions = new Map();

  columns.forEach((type, colIndex) => {
    grouped[type].forEach((node, rowIndex) => {
      const x = leftPad + colIndex * columnWidth;
      const y = topPad + rowIndex * rowGap;
      positions.set(node.id, { x, y, type, label: node.label });
    });
  });

  const paths = edges.map(edge => {
    const source = positions.get(edge.source);
    const target = positions.get(edge.target);
    if (!source || !target) {
      return '';
    }
    const x1 = source.x + boxWidth;
    const y1 = source.y + boxHeight / 2;
    const x2 = target.x;
    const y2 = target.y + boxHeight / 2;
    const midX = x1 + (x2 - x1) / 2;
    const thickness = 1.5 + edge.weight * 0.7;
    const title = `${edge.source} -> ${edge.target} | ${edge.needs.join(', ')}`;
    return `
      <path class="graph-edge" d="M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}" stroke-width="${thickness}">
        <title>${escapeHtml(title)}</title>
      </path>
    `;
  }).join('');

  const labels = columns.map((type, colIndex) => `
    <text class="graph-column-label" x="${leftPad + colIndex * columnWidth + 8}" y="34">${type}</text>
  `).join('');

  const activeNodeId = nodes.some(node => node.id === selectedNodeId) ? selectedNodeId : nodes[0].id;
  dashboardState.selectedNodeId = activeNodeId;

  const boxes = nodes.map(node => {
    const pos = positions.get(node.id);
    return `
      <g class="graph-node graph-node-${node.type} ${node.id === activeNodeId ? 'active' : ''}" data-node-id="${escapeHtml(node.id)}">
        <rect x="${pos.x}" y="${pos.y}" width="${boxWidth}" height="${boxHeight}" rx="12" ry="12"></rect>
        <text x="${pos.x + 12}" y="${pos.y + 25}">${escapeHtml(node.label)}</text>
        <title>${escapeHtml(`${node.id} (${node.type})`)}</title>
      </g>
    `;
  }).join('');

  const routedNeedCount = new Set(edges.flatMap(edge => edge.needs)).size;
  document.getElementById('graph-stats').innerHTML = [
    `<span class="pill">Edges ${edges.length}</span>`,
    `<span class="pill">Active nodes ${nodes.length}</span>`,
    `<span class="pill">Needs ${routedNeedCount}</span>`,
    filter ? `<span class="pill">Filter ${escapeHtml(filter)}</span>` : '<span class="pill">Showing all routed needs</span>'
  ].join('');

  document.getElementById('graph').innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Dependency route graph">
      ${labels}
      ${paths}
      ${boxes}
    </svg>
  `;

  document.querySelectorAll('[data-node-id]').forEach(element => {
    element.addEventListener('click', () => {
      dashboardState.selectedNodeId = element.getAttribute('data-node-id') || '';
      renderGraph(graph, dashboardState.selectedNeed, dashboardState.selectedNodeId);
    });
  });

  renderGraphDetails(graph, edges, activeNodeId);
}

function renderNeeds(needs, query = '') {
  const normalized = query.trim().toLowerCase();
  const filtered = needs.filter(need => {
    const haystack = [need.id, need.name, need.category].join(' ').toLowerCase();
    return haystack.includes(normalized);
  });

  document.getElementById('needs').innerHTML = `
    <div class="need-grid">
      ${filtered.map(need => `
        <article class="need-card">
          <h3>${need.name}</h3>
          <div class="meta">${need.id}</div>
          <div class="meta">Category: ${need.category}</div>
          <div class="meta">Confidence: ${need.confidence}</div>
          <div class="meta">Evidence: ${(need.evidence || []).length}</div>
          <div style="margin-top:10px;">
            ${(need.scope_options || []).map(scope => `<span class="pill">${scope}</span>`).join('')}
          </div>
          <div style="margin-top:10px;">
            ${(need.barriers || []).map(barrier => `<span class="pill">${barrier.type}</span>`).join('')}
          </div>
        </article>
      `).join('')}
    </div>
  `;
}

async function main() {
  try {
    const data = await loadDashboard();
    renderSummary(data.summary);
    renderInterventions(data.top_interventions || []);
    renderScenarios(data.budget_scenarios || []);
    renderGraph(data.graph || {}, dashboardState.selectedNeed, dashboardState.selectedNodeId);
    renderNeeds(data.needs || []);
    document.getElementById('graph-filter').innerHTML = ['<option value="">All routed needs</option>']
      .concat((data.graph?.need_options || []).map(need => `<option value="${need}">${need}</option>`))
      .join('');
    document.getElementById('need-search').addEventListener('input', (event) => {
      renderNeeds(data.needs || [], event.target.value);
    });
    document.getElementById('graph-filter').addEventListener('change', (event) => {
      dashboardState.selectedNeed = event.target.value;
      renderGraph(data.graph || {}, dashboardState.selectedNeed, dashboardState.selectedNodeId);
    });
  } catch (error) {
    document.body.innerHTML = `<main class="shell"><section class="panel"><h2>Dashboard Load Error</h2><p>${error.message}</p><p>Run <strong>make export-public-data</strong> and serve the workspace over HTTP.</p></section></main>`;
  }
}

main();
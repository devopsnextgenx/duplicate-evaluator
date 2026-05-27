/* ============================================================
   Duplicate Evaluator — Main Application JavaScript
   ============================================================ */

'use strict';

// ── State ──────────────────────────────────────────────────────
const state = {
  activeTab: 'within',
  selectedNode: null,       // { path, name, type, language, quality, actress }
  selectedNodes: new Map(), // multi-select folder scan targets
  lastSelectedPath: null,   // for shift-range selection
  currentReport: {
    within: null,
    cross: null,
  },
  scanJobId: {
    within: null,
    cross: null,
  },
  saveTimers: {
    within: null,
    cross: null,
  },
  expandedPaths: new Set(), // Track expanded tree node paths
  scanProgress: { total: 0, completed: 0 },
};

let terminalAutoScroll = true;

// ── localStorage Tree State Persistence ──────────────────────────
const TREE_STATE_KEY = 'treeState';

function saveTreeState() {
  const treeState = {
    expandedPaths: Array.from(state.expandedPaths),
    selectedNodePath: state.selectedNode ? state.selectedNode.path : null,
    selectedNodePaths: Array.from(state.selectedNodes.keys()),
    lastSelectedPath: state.lastSelectedPath,
    activeTab: state.activeTab,
  };
  localStorage.setItem(TREE_STATE_KEY, JSON.stringify(treeState));
}

function loadTreeState() {
  try {
    const raw = localStorage.getItem(TREE_STATE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function restoreTreeState(treeData) {
  const saved = loadTreeState();
  if (!saved) return;

  // 1. Restore expanded paths in state
  if (saved.expandedPaths && Array.isArray(saved.expandedPaths)) {
    saved.expandedPaths.forEach(p => state.expandedPaths.add(p));
  }

  // 2. Restore active tab
  if (saved.activeTab) {
    state.activeTab = saved.activeTab;
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.style.display = 'none');
    const targetTab = document.querySelector(`.tab[data-tab="${saved.activeTab}"]`);
    if (targetTab) {
      targetTab.classList.add('active');
      document.getElementById(`pane-${saved.activeTab}`).style.display = 'flex';
    }
  }

  // 3. Restore selected node in state
  if (saved.selectedNodePath) {
    const node = findNodeByPath(treeData, saved.selectedNodePath);
    if (node) {
      state.selectedNode = node;
      state.lastSelectedPath = saved.lastSelectedPath || node.path;

      // Force parent structures to be added to open list
      ensurePathExpanded(node.path);
    }
  }

  // 4. Restore multi-selection map records
  if (saved.selectedNodePaths && Array.isArray(saved.selectedNodePaths)) {
    saved.selectedNodePaths.forEach(path => {
      const node = findNodeByPath(treeData, path);
      if (node) {
        state.selectedNodes.set(path, node);
        ensurePathExpanded(path);
      }
    });
  }
}

function findNodeByPath(nodes, targetPath) {
  if (!nodes) return null;
  // If passed the root element object instead of child array
  const nodesArray = Array.isArray(nodes) ? nodes : (nodes.children || [nodes]);
  
  for (const node of nodesArray) {
    if (node.path === targetPath) return node;
    if (node.children && node.children.length > 0) {
      const found = findNodeByPath(node.children, targetPath);
      if (found) return found;
    }
  }
  return null;
}

function ensurePathExpanded(nodePath) {
  const parts = nodePath.split('/');
  let currentPath = '';
  for (let i = 0; i < parts.length - 1; i++) {
    currentPath = currentPath ? `${currentPath}/${parts[i]}` : parts[i];
    state.expandedPaths.add(currentPath);
  }
}

// ── API Helpers ─────────────────────────────────────────────────
const api = {
  async get(path) {
    const r = await fetch(path);
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }));
      throw new Error(err.detail || r.statusText);
    }
    return r.json();
  },

  async post(path, body) {
    const r = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }));
      throw new Error(err.detail || r.statusText);
    }
    return r.json();
  },
};

// ── Toast ────────────────────────────────────────────────────────
function toast(message, type = 'info', duration = 3500) {
  const icons = { success: '✓', error: '✕', info: 'ℹ' };
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `<span>${icons[type] || 'ℹ'}</span> ${escHtml(message)}`;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => el.remove(), duration);
}

// ── Utility ──────────────────────────────────────────────────────
function escHtml(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

function refreshTreeUI() {
  const treeEl = document.getElementById('folder-tree');
  if (!_cachedTreeData || !treeEl) return;

  treeEl.innerHTML = '';
  renderTree(_cachedTreeData.children || [], treeEl, 0);
  updateSelectionSummary();
  updateScanButton();
}

function humanSize(bytes) {
  if (!bytes) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let v = bytes;
  let u = 0;
  while (v >= 1024 && u < units.length - 1) { v /= 1024; u++; }
  return `${v.toFixed(1)} ${units[u]}`;
}

function confClass(score) {
  if (score >= 0.8) return 'high';
  if (score >= 0.5) return 'med';
  if (score > 0)    return 'low';
  return 'none';
}

function confLabel(score) {
  if (!score) return '—';
  return `${Math.round(score * 100)}%`;
}

// ── Tab switching ────────────────────────────────────────────────
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    const target = tab.dataset.tab;
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.style.display = 'none');
    tab.classList.add('active');
    document.getElementById(`pane-${target}`).style.display = 'flex';
    state.activeTab = target;
    updateScanButton();
    saveTreeState();
    syncPaneParentMargin();
  });
});

// ── Health / Connection check ────────────────────────────────────
async function checkHealth() {
  try {
    const data = await api.get('/health');
    const dot = document.getElementById('conn-dot');
    const label = document.getElementById('conn-label');
    dot.className = 'connection-dot connected';
    label.textContent = `${data.llm_provider} · ${data.llm_model}`;
  } catch {
    document.getElementById('conn-dot').className = 'connection-dot error';
    document.getElementById('conn-label').textContent = 'Server offline';
  }
}

// ── Folder Tree ──────────────────────────────────────────────────
let _cachedTreeData = null;

async function loadTree() {
  const treeEl = document.getElementById('folder-tree');
  treeEl.innerHTML = '<li style="padding:1rem;color:var(--text-muted);font-size:0.78rem"><span class="spinner"></span> Loading…</li>';
  try {
    const tree = await api.get('/api/tree');
    _cachedTreeData = tree;
    treeEl.innerHTML = '';
    if (tree.error) {
      treeEl.innerHTML = `<li style="padding:1rem;color:var(--accent-red);font-size:0.78rem">⚠ ${escHtml(tree.error)}</li>`;
      return;
    }

    restoreTreeState(tree);

    renderTree(tree.children || [], treeEl, 0);
    updateSelectionSummary();
    updateScanButton();

    if (state.selectedNode) {
      if (state.selectedNode.has_report) {
        loadReport(state.selectedNode.path, state.activeTab);
      } else {
        showEmptyReport(state.activeTab, `No report found. Click "Scan Selected Folder" to analyse.`);
      }
    }
  } catch (e) {
    treeEl.innerHTML = `<li style="padding:1rem;color:var(--accent-red);font-size:0.78rem">⚠ ${escHtml(e.message)}</li>`;
  }
}

function renderTree(nodes, parentEl, depth) {
  nodes.forEach(node => {
    const li = document.createElement('li');
    li.className = `tree-node tree-level-${node.type}`;

    const label = document.createElement('div');
    label.className = 'tree-label';
    label.style.paddingLeft = `${0.75 + depth * 1}rem`;

    if (state.selectedNode && node.path === state.selectedNode.path) {
      label.classList.add('active');
      state.selectedNode = node;
    }

    if (state.selectedNodes.has(node.path)) {
      label.classList.add('selected');
      state.selectedNodes.set(node.path, node);
    }

    const icon = getIcon(node);
    const hasChildren = node.children && node.children.length > 0;

    let dotHtml = '';
    let rescanHtml = '';
    if (node.type === 'actress') {
      const status = node.scan_status || 'none';
      dotHtml = `<span class="scan-status-dot ${status}" title="Status: ${status}"></span>`;
      rescanHtml = `<button class="rescan-btn" title="Rescan folder">🔄</button>`;
    }

    label.innerHTML = `
      ${dotHtml}
      <span class="icon">${icon}</span>
      <span class="name" title="${escHtml(node.path)}">${escHtml(node.name)}</span>
      ${node.type === 'actress' ? `<span class="tree-badge ${node.has_report ? 'has-report' : ''}">${node.mp4_count ?? 0}</span>` : ''}
      ${rescanHtml}
    `;

    if (hasChildren) {
      const chevron = document.createElement('span');
      chevron.className = 'tree-chevron';
      chevron.textContent = '▶';
      label.prepend(chevron);
    }

    li.appendChild(label);

    label.addEventListener('click', (e) => {
      if (e.target.closest('.tree-chevron')) return;
      e.stopPropagation();

      if (node.type === 'actress') {
        if (e.target.classList && e.target.classList.contains('rescan-btn')) {
          selectNode(node, label);
          startScan(true, node);
          return;
        }

        if (e.ctrlKey || e.metaKey) {
          const path = node.path;
          if (state.selectedNodes.has(path)) {
            state.selectedNodes.delete(path);
            label.classList.remove('selected');
          } else {
            state.selectedNodes.set(path, node);
            label.classList.add('selected');
          }
          state.lastSelectedPath = path;
          updateSelectionSummary();
          updateScanButton();
          saveTreeState();
          return;
        }

        if (e.shiftKey && state.lastSelectedPath) {
          const allLabels = Array.from(document.querySelectorAll('.tree-label'));
          const actressLabels = allLabels.filter(lbl => {
            const li = lbl.closest('li');
            return li && li.classList.contains('tree-level-actress');
          });

          const paths = actressLabels.map(lbl => lbl.querySelector('.name')?.getAttribute('title') || '');
          const a = paths.indexOf(state.lastSelectedPath);
          const b = paths.indexOf(node.path);

          if (a !== -1 && b !== -1) {
            const [start, end] = a < b ? [a, b] : [b, a];
            for (let i = start; i <= end; i++) {
              const otherLabel = actressLabels[i];
              const otherNode = getNodeFromLabel(otherLabel);
              if (otherNode) {
                state.selectedNodes.set(otherNode.path, otherNode);
                otherLabel.classList.add('selected');
              }
            }
          }
          state.lastSelectedPath = node.path;
          updateSelectionSummary();
          updateScanButton();
          saveTreeState();
          return;
        }

        document.querySelectorAll('.tree-label.active').forEach(el => el.classList.remove('active'));
        label.classList.add('active');

        document.querySelectorAll('.tree-label.selected').forEach(el => el.classList.remove('selected'));
        state.selectedNodes.clear();

        state.selectedNode = node;
        state.lastSelectedPath = node.path;
        updateScanButton();
        saveTreeState();

        if (node.has_report) {
          loadReport(node.path, state.activeTab);
        } else {
          showEmptyReport(state.activeTab, `No report found. Click "Scan Selected Folder" to analyse.`);
        }
        return;
      }

      if (e.ctrlKey || e.metaKey) {
        const descendantActresses = collectDescendantActressNodes(node);
        descendantActresses.forEach((actressNode) => state.selectedNodes.set(actressNode.path, actressNode));
        state.selectedNode = null;
        state.lastSelectedPath = descendantActresses[descendantActresses.length - 1]?.path || state.lastSelectedPath;
        updateSelectionSummary();
        updateScanButton();
        updateTreeSelectionUI();
        saveTreeState();
        return;
      }

      document.querySelectorAll('.tree-label.active').forEach(el => el.classList.remove('active'));
      label.classList.add('active');

      document.querySelectorAll('.tree-label.selected').forEach(el => el.classList.remove('selected'));
      state.selectedNodes.clear();

      state.selectedNode = node;
      updateSelectionSummary();
      updateScanButton();
      saveTreeState();

      showEmptyReport(state.activeTab, `Ready to scan all folders under ${node.name}.`);
    });

    if (hasChildren) {
      const childUl = document.createElement('ul');
      childUl.className = 'tree-children';

      const shouldBeOpen = state.expandedPaths.has(node.path);
      if (shouldBeOpen) {
        childUl.classList.add('open');
        label.classList.add('expanded');
      }

      renderTree(node.children, childUl, depth + 1);
      li.appendChild(childUl);

      const chevron = label.querySelector('.tree-chevron');
      if (chevron) {
        chevron.addEventListener('click', (e) => {
          e.stopPropagation();
          const isOpen = childUl.classList.contains('open');
          const nextOpen = !isOpen;
          childUl.classList.toggle('open', nextOpen);
          label.classList.toggle('expanded', nextOpen);

          if (nextOpen) {
            state.expandedPaths.add(node.path);
          } else {
            state.expandedPaths.delete(node.path);
          }
          saveTreeState();
        });
      }
    }

    parentEl.appendChild(li);
  });
}

function getNodeFromLabel(label) {
  const nameSpan = label.querySelector('.name');
  const path = nameSpan?.getAttribute('title');
  if (!path) return null;
  const node = findNodeByPath(_cachedTreeData, path);
  if (node) return node;
  return { path, name: nameSpan?.textContent || '' };
}

function getIcon(node) {
  if (node.type === 'language') return '🌐';
  if (node.type === 'quality')  {
    const icons = { xhd: '⬆', hd: '▲', sd: '▼' };
    return icons[node.tier] || '📂';
  }
  if (node.type === 'actress')  return '👤';
  return '📁';
}

// ── Selection helpers ───────────────────────────────────────────
function selectNode(node, labelEl) {
  document.querySelectorAll('.tree-label.active').forEach(el => el.classList.remove('active'));
  labelEl.classList.add('active');

  document.querySelectorAll('.tree-label.selected').forEach(el => el.classList.remove('selected'));
  state.selectedNodes.clear();

  state.selectedNode = node;
  state.lastSelectedPath = node.path;
  updateScanButton();
  saveTreeState();
}

function updateScanButton() {
  const scanBtn = document.getElementById('btn-scan-folder');
  const clearBtn = document.getElementById('btn-clear-reports');
  if (state.activeTab === 'lang') {
    if (scanBtn) {
      scanBtn.disabled = true;
      scanBtn.innerHTML = `<span>🔍</span> Scan Selected Folder`;
    }
    if (clearBtn) {
      clearBtn.disabled = true;
      clearBtn.innerHTML = `<span>🧹</span> Clear Report Files`;
    }
    return;
  }

  const selectedCount = state.selectedNodes.size;

  if (scanBtn) {
    if (selectedCount > 0) {
      scanBtn.disabled = false;
      scanBtn.innerHTML = `<span>🔍</span> Scan Selected Folders (${selectedCount})`;
    } else {
      scanBtn.disabled = !state.selectedNode;
      scanBtn.innerHTML = state.selectedNode
        ? `<span>🔍</span> Scan: ${escHtml(state.selectedNode.name)}`
        : `<span>🔍</span> Scan Selected Folder`;
    }
  }

  if (clearBtn) {
    if (selectedCount > 0) {
      clearBtn.disabled = false;
      clearBtn.innerHTML = `<span>🧹</span> Clear Reports (${selectedCount})`;
    } else {
      clearBtn.disabled = !state.selectedNode;
      clearBtn.innerHTML = state.selectedNode
        ? `<span>🧹</span> Clear Reports`
        : `<span>🧹</span> Clear Report Files`;
    }
  }
}

// ── Terminal Management ──────────────────────────────────────────
function appendTerminal(message, type = 'info') {
  const output = document.getElementById('terminal-output-global');
  if (!output) return;
  const isAtBottom = output.scrollHeight - output.scrollTop <= output.clientHeight + 4;
  const timestamp = new Date().toLocaleTimeString();
  let formatted = `[${timestamp}] ${message}`;

  output.textContent += `${formatted}\n`;

  if (terminalAutoScroll && isAtBottom) {
    output.scrollTop = output.scrollHeight;
  }
}

// Explicitly clean up text streams without altering DOM attributes
function clearTerminal() {
  const output = document.getElementById('terminal-output-global');
  if (!output) return;
  output.textContent = '';
}

function getSelectedFolders() {
  if (state.selectedNodes.size > 0) {
    return Array.from(state.selectedNodes.values());
  }
  return state.selectedNode ? [state.selectedNode] : [];
}

// Sync bulk choices context descriptions
function updateSelectionSummary() {
  const summary = document.getElementById('selection-summary');
  if (!summary) return;
  const count = state.selectedNodes.size;
  if (count === 0) {
    if (state.selectedNode && state.selectedNode.type === 'quality') {
      summary.textContent = `Selected quality tier: ${state.selectedNode.name}. Scan will submit all child folders.`;
    } else if (state.selectedNode && state.selectedNode.type === 'language') {
      summary.textContent = `Selected language group: ${state.selectedNode.name}. Scan will submit all child folders.`;
    } else {
      summary.textContent = 'Select one or more actress folders to scan.';
    }
  } else if (count === 1) {
    summary.textContent = '1 folder selected for bulk scan.';
  } else {
    summary.textContent = `${count} folders selected for bulk scan.`;
  }
}

function isAlreadyScanned(node) {
  return Boolean(node && node.scan_status && node.scan_status !== 'none');
}

function collectDescendantActressNodes(node) {
  if (!node) return [];
  if (node.type === 'actress') return [node];
  if (!node.children || node.children.length === 0) return [];
  return node.children.flatMap((child) => collectDescendantActressNodes(child));
}

function updateTreeSelectionUI() {
  document.querySelectorAll('.tree-label').forEach((label) => {
    const nameSpan = label.querySelector('.name');
    if (!nameSpan) return;
    const path = nameSpan.getAttribute('title');
    if (state.selectedNodes.has(path)) {
      label.classList.add('selected');
    } else {
      label.classList.remove('selected');
    }
  });
}

function getScanTargetsFromNodes(nodes, isRescan = false) {
  const seen = new Set();
  const targets = [];

  function walk(current) {
    if (!current || !current.path) return;
    if (current.type === 'actress') {
      if (seen.has(current.path)) return;
      seen.add(current.path);
      if (!isRescan && isAlreadyScanned(current)) return;
      targets.push(current);
      return;
    }
    if (current.children && current.children.length) {
      current.children.forEach(walk);
    }
  }

  nodes.forEach(walk);
  return targets;
}

function updateProgressBar(completed, total, label = '') {
  const fill = document.getElementById('progress-fill');
  const text = document.getElementById('progress-label');
  const percent = total ? Math.round((completed / total) * 100) : 0;
  if (fill) fill.style.width = `${percent}%`;
  if (text) text.textContent = label || `${percent}% (${completed}/${total})`;
}

function resetProgressBar() {
  state.scanProgress = { total: 0, completed: 0 };
  updateProgressBar(0, 0, '');
}

// ── Auto-Save & Manual Execution Helpers ─────────────────────────
function updateAutoSaveStatus(tab, stateText, customText = '') {
  const el = document.getElementById(`auto-save-status-${tab}`);
  if (!el) return;

  el.className = 'auto-save-status';

  if (stateText === 'draft') {
    el.classList.add('show', 'draft');
    el.innerHTML = `<span>⏳</span> ${customText || 'Saving in 5s...'}`;
  } else if (stateText === 'saving') {
    el.classList.add('show', 'saving');
    el.innerHTML = `<span class="spinner" style="margin-right:4px"></span> Saving...`;
  } else if (stateText === 'saved') {
    el.classList.add('show', 'saved');
    el.innerHTML = `<span>✓</span> All changes saved`;
    setTimeout(() => {
      if (el.classList.contains('saved')) {
        el.classList.remove('show');
      }
    }, 3000);
  } else if (stateText === 'error') {
    el.classList.add('show', 'draft');
    el.style.borderColor = 'var(--accent-red)';
    el.style.color = 'var(--accent-red)';
    el.style.background = 'var(--accent-red-bg)';
    el.innerHTML = `<span>✕</span> Save failed`;
  } else {
    el.classList.remove('show');
  }
}

function queueAutoSave(tab) {
  if (state.saveTimers[tab]) {
    clearTimeout(state.saveTimers[tab]);
  }

  updateAutoSaveStatus(tab, 'draft');

  state.saveTimers[tab] = setTimeout(() => {
    state.saveTimers[tab] = null;
    performAutoSave(tab);
  }, 5000);
}

async function performAutoSave(tab) {
  const report = state.currentReport[tab];
  if (!report || !report.folder_path) {
    updateAutoSaveStatus(tab, 'none');
    return;
  }

  updateAutoSaveStatus(tab, 'saving');

  const tbody = document.getElementById(`report-tbody-${tab}`);
  if (!tbody) {
    updateAutoSaveStatus(tab, 'none');
    return;
  }

  const actions = [];
  tbody.querySelectorAll('tr').forEach(tr => {
    const checked = tr.querySelector('input[type="radio"]:checked');
    const path = tr.dataset.path;
    if (checked && path) {
      actions.push({
        path: path,
        action: checked.value
      });
    }
  });

  if (actions.length === 0) {
    updateAutoSaveStatus(tab, 'none');
    return;
  }

  try {
    await api.post('/api/report/actions', {
      folder_path: report.folder_path,
      actions: actions
    });

    const actionMap = {};
    actions.forEach(a => { actionMap[a.path] = a.action; });
    if (report.entries) {
      report.entries.forEach(entry => {
        if (actionMap[entry.file.path]) {
          entry.suggested_action = actionMap[entry.file.path];
        }
      });
    }

    updateAutoSaveStatus(tab, 'saved');
  } catch (e) {
    console.error('Auto-save failed:', e);
    updateAutoSaveStatus(tab, 'error');
    toast(`Failed to auto-save actions: ${e.message}`, 'error');
  }
}

async function markFolderExecuted(tab) {
  const report = state.currentReport[tab];
  if (!report || !report.folder_path) {
    toast('No folder loaded to mark as executed', 'info');
    return;
  }

  // TODO
  // if (!confirm(`Are you sure you want to mark "${report.actress || report.folder_path}" as executed manually?`)) {
  //   return;
  // }

  try {
    await api.post('/api/execute/mark-executed', {
      folder_path: report.folder_path
    });
    toast('Folder marked as executed successfully', 'success');

    const cachedNode = findNodeByPath(_cachedTreeData, report.folder_path);
    if (cachedNode) {
      cachedNode.scan_status = 'executed';
    }
    refreshTreeUI();
  } catch (e) {
    toast(`Failed to mark executed: ${e.message}`, 'error');
  }
}

// ── Load Report ──────────────────────────────────────────────────
async function loadReport(folderPath, tab) {
  try {
    const report = await api.get(`/api/report?folder_path=${encodeURIComponent(folderPath)}`);
    state.currentReport[tab] = report;
    renderReport(report, tab);
    toast('Report loaded', 'success');
  } catch (e) {
    showEmptyReport(tab, e.message);
  }
}

// CRITICAL FIX: showEmptyReport now leaves toolbars, action bars, headers, and terminals 100% visible.
function showEmptyReport(tab, msg) {
  const wrapper = document.getElementById(`table-wrapper-${tab}`);
  const toolbarEl = document.getElementById(`toolbar-${tab}`);
  const titleEl = document.getElementById(`report-title-${tab}`);
  const metaEl  = document.getElementById(`report-meta-${tab}`);
  
  if (wrapper) {
    wrapper.innerHTML = `
      <div class="empty-state">
        <div class="icon">${tab === 'cross' ? '🔀' : '🎬'}</div>
        <p>${escHtml(msg)}</p>
      </div>`;
  }

  // Ensure toolbars remain visible so actions and text layout contexts don't collapse
  if (toolbarEl) toolbarEl.style.display = 'flex';
  if (titleEl) titleEl.textContent = state.selectedNode ? `${state.selectedNode.name}` : 'No Folder Selected';
  if (metaEl) metaEl.innerHTML = `<span class="stat-chip total">⚠️ Unscanned</span>`;

  // Explicitly protect layout visibility boundaries 
  syncPaneParentMargin();
}

// ── Render Report Table ──────────────────────────────────────────
function renderReport(report, tab) {
  const wrapper = document.getElementById(`table-wrapper-${tab}`);
  const toolbar = document.getElementById(`toolbar-${tab}`);
  const actionBar = document.getElementById('action-bar');
  const actionBarWrapper = actionBar ? actionBar.parentElement : null;
  const titleEl = document.getElementById(`report-title-${tab}`);
  const metaEl  = document.getElementById(`report-meta-${tab}`);

  if (!wrapper || !toolbar) return;

  if (!report) {
    showEmptyReport(tab, 'No report found.');
    return;
  }

  if (state.saveTimers[tab]) {
    clearTimeout(state.saveTimers[tab]);
    state.saveTimers[tab] = null;
  }
  updateAutoSaveStatus(tab, 'none');

  toolbar.style.display = 'flex';
  if (actionBarWrapper) actionBarWrapper.style.display = 'flex';
  if (titleEl) titleEl.textContent = `${report.actress || report.folder_path} · ${report.mode}`;
  if (metaEl) {
    metaEl.innerHTML = `
      <span class="stat-chip total">📁 ${report.total_files_scanned} scanned</span>
      <span class="stat-chip dup">🔴 ${report.duplicate_count || 0} duplicates</span>
      <span class="stat-chip rename">✏ ${report.rename_count || 0} to rename</span>
      <span class="stat-chip total" title="LLM model used">🤖 ${escHtml(report.llm_model || '—')}</span>
    `;
  }

  if (!report.entries || report.entries.length === 0) {
    wrapper.innerHTML = `<div class="empty-state"><div class="icon">${tab === 'cross' ? '🔀' : '🎬'}</div><p>No flagged files found in this folder. All files appear clean.</p></div>`;
    syncPaneParentMargin();
    return;
  }

  const table = document.createElement('table');
  table.className = 'report-table';
  table.innerHTML = `
    <thead>
      <tr>
        <th style="width:30px">#</th>
        <th>File Name</th>
        <th style="width:75px">Play</th>
        <th style="width:90px">Size</th>
        <th style="width:90px">Confidence</th>
        <th style="width:100px">Duplicate</th>
        <th style="width:100px">Rename</th>
        <th style="width:180px">Action</th>
      </tr>
    </thead>
    <tbody id="report-tbody-${tab}"></tbody>
  `;

  wrapper.innerHTML = '';
  wrapper.appendChild(table);

  const tbody = document.getElementById(`report-tbody-${tab}`);

  report.entries.forEach((entry, idx) => {
    const file = entry.file;
    const isDup = entry.is_duplicate;
    const needsRename = entry.needs_rename;
    const isDeleted = entry.deleted || false;

    let rowClasses = [];
    if (isDup) rowClasses.push('is-duplicate');
    else if (needsRename) rowClasses.push('needs-rename');
    if (isDeleted) rowClasses.push('row-deleted');

    let rowClass = rowClasses.join(' ');

    let defAction = entry.suggested_action || 'keep';
    if (isDeleted) defAction = 'keep';

    const uid = `${tab}-${idx}`;

    let playBtnHtml = '';
    if (isDeleted) {
      playBtnHtml = `<button class="play-btn" disabled title="File is deleted">▶ Play</button>`;
    } else {
      playBtnHtml = `<button class="play-btn btn-play-video" data-path="${escHtml(file.path)}" data-filename="${escHtml(file.filename)}" title="Stream Video">▶ Play</button>`;
    }

    let filenameHtml = '';
    if (isDeleted) {
      filenameHtml = `<span class="file-deleted"><del>${escHtml(file.filename)}</del></span> <span class="badge" style="color:var(--accent-red);font-size:0.65rem;border:1px solid var(--accent-red);padding:0.05rem 0.2rem;border-radius:3px;margin-left:0.3rem;font-weight:600">DELETED</span>`;
    } else {
      filenameHtml = escHtml(file.filename);
    }

    const tr = document.createElement('tr');
    tr.className = rowClass;
    tr.title = `${escHtml(entry.similar_files?.map(f => f.filename).join('\n') || 'No similar files')}`;
    tr.dataset.path = file.path;
    tr.dataset.filename = file.filename;
    tr.innerHTML = `
      <td style="color:var(--text-muted);font-size:0.7rem" title="${escHtml(file.filename)}">${idx + 1}</td>
      <td class="td-filename">${filenameHtml}</td>
      <td>${playBtnHtml}</td>
      <td class="td-size">${humanSize(file.size_bytes)}</td>
      <td>
        <span class="conf-badge ${confClass(entry.confidence)}" title="${escHtml(entry.similar_files?.map(f => f.filename).join('\n') || 'No similar files')}" style="font-weight:600">
          ${confLabel(entry.confidence)}
        </span>
      </td>
      <td>
        ${isDup
          ? `<span class="bool-badge yes-dup" title="${escHtml(entry.similar_files?.map(f => f.filename).join('\n') || 'No similar files')}">✓ Yes</span>`
          : `<span class="bool-badge no">— No</span>`}
      </td>
      <td>
        ${needsRename
          ? `<span class="bool-badge yes-rename">✓ Yes</span>`
          : `<span class="bool-badge no">— No</span>`}
      </td>
      <td>
        <div class="action-group">
          <input class="action-radio" type="radio" name="action-${uid}" id="del-${uid}" value="delete" ${defAction === 'delete' ? 'checked' : ''} ${isDeleted ? 'disabled' : ''}>
          <label class="action-label" for="del-${uid}" style="${isDeleted ? 'opacity:0.3;cursor:not-allowed' : ''}">Delete</label>

          <input class="action-radio" type="radio" name="action-${uid}" id="ren-${uid}" value="rename" ${defAction === 'rename' ? 'checked' : ''} ${isDeleted ? 'disabled' : ''}>
          <label class="action-label" for="ren-${uid}" style="${isDeleted ? 'opacity:0.3;cursor:not-allowed' : ''}">Rename</label>

          <input class="action-radio" type="radio" name="action-${uid}" id="keep-${uid}" value="keep" ${defAction === 'keep' ? 'checked' : ''} ${isDeleted ? 'disabled' : ''}>
          <label class="action-label" for="keep-${uid}" style="${isDeleted ? 'opacity:0.3;cursor:not-allowed' : ''}">Keep</label>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  });

  tbody.querySelectorAll('.btn-play-video').forEach(btn => {
    btn.addEventListener('click', () => {
      const path = btn.dataset.path;
      const filename = btn.dataset.filename;
      openVideo(path, filename);
    });
  });

  tbody.addEventListener('change', (e) => {
    if (e.target.classList.contains('action-radio')) {
      queueAutoSave(tab);
    }
  });

  if (actionBar) actionBar.style.display = 'flex';
  
  syncPaneParentMargin();
}

function collectActions(tab) {
  const tbody = document.getElementById(`report-tbody-${tab}`);
  if (!tbody) return [];
  const actions = [];
  tbody.querySelectorAll('tr').forEach(tr => {
    const checked = tr.querySelector('input[type="radio"]:checked');
    if (!checked || checked.value === 'keep') return;
    actions.push({
      filename: tr.dataset.filename,
      path: tr.dataset.path,
      action: checked.value,
    });
  });
  return actions;
}

async function runExecute(tab, dryRun, actionFilter = null) {
  const allActions = collectActions(tab);
  const actions = actionFilter
    ? allActions.filter(a => a.action === actionFilter)
    : allActions;

  if (actions.length === 0) {
    toast('No actions selected', 'info');
    return;
  }

  appendTerminal(dryRun
    ? `Running DRY RUN for ${actions.length} action(s)…`
    : `Executing ${actions.length} action(s)…`
  );

  try {
    const result = await api.post('/api/execute', { actions, dry_run: dryRun });
    appendTerminal(result.lines.join('\n'));
    if (!dryRun) {
      toast(`Executed ${actions.length} action(s)`, 'success');
      
      const tree = await api.get('/api/tree');
      _cachedTreeData = tree;
      restoreTreeState(tree);
      refreshTreeUI();
    }
  } catch (e) {
    appendTerminal(`❌ Error: ${e.message}`, 'error');
    toast(e.message, 'error');
  }
}

function selectAllRadio(tab, value) {
  const tbody = document.getElementById(`report-tbody-${tab}`);
  if (!tbody) return;
  let changed = false;
  tbody.querySelectorAll('tr').forEach((tr) => {
    const radio = tr.querySelector(`input[value="${value}"]`);
    if (radio && !radio.disabled) {
      if (!radio.checked) {
        radio.checked = true;
        changed = true;
      }
    }
  });
  if (changed) {
    queueAutoSave(tab);
  }
}

async function clearReports() {
  const selectedFolders = getSelectedFolders();
  if (selectedFolders.length === 0) {
    toast('No folder selected to clear reports.', 'info');
    return;
  }

  const clearTargets = getScanTargetsFromNodes(selectedFolders, true);
  if (clearTargets.length === 0) {
    toast('No valid folders found to clear reports.', 'info');
    return;
  }

  if (!confirm(`Clear report metadata for ${clearTargets.length} selected folder(s)? This will recursively remove only _report.json and _executed.json files.`)) {
    return;
  }

  appendTerminal(`=== Clearing report files for ${clearTargets.length} folder(s) ===`, 'info');
  try {
    const result = await api.post('/api/report/clear', {
      folder_paths: clearTargets.map(node => node.path),
      recursive: true,
    });

    appendTerminal(`Cleared ${result.total_deleted} report files.`, 'info');
    toast(`Removed ${result.total_deleted} report files`, 'success', 5000);
    await loadTree();
  } catch (e) {
    appendTerminal(`❌ Error: ${e.message}`, 'error');
    toast(`Failed to clear report files: ${e.message}`, 'error');
  }
}

async function startScan(isRescan = false, targetNode = null) {
  const selectedFolders = targetNode ? [targetNode] : getSelectedFolders();
  if (selectedFolders.length === 0) {
    toast('No folder selected to scan', 'info');
    return;
  }

  const scanTargets = getScanTargetsFromNodes(selectedFolders, isRescan);
  if (scanTargets.length === 0) {
    const hasAnyTargets = getScanTargetsFromNodes(selectedFolders, true).length > 0;
    if (hasAnyTargets) {
      toast('All selected folders were already scanned. Use Rescan to re-run them.', 'info');
    } else {
      toast('No valid folders found to scan.', 'info');
    }
    return;
  }

  const tab = state.activeTab;
  const mode = tab === 'cross' ? 'cross_quality' : 'within_folder';
  const actionLabel = isRescan ? 'Rescan' : 'Scan';

  const scanBtn = document.getElementById('btn-scan-folder');
  if (scanBtn) scanBtn.disabled = true;
  appendTerminal(`=== ${actionLabel} started for ${scanTargets.length} folder(s) (${tab}) ===`, 'info');

  if (!targetNode && selectedFolders.length > 1) {
    showEmptyReport(tab, `Scanning ${scanTargets.length} selected folders…`);
  } else {
    showEmptyReport(tab, 'Analyzing folders…');
  }

  const wrapper = document.getElementById(`table-wrapper-${tab}`);
  if (wrapper) {
    wrapper.innerHTML = `
      <div class="empty-state">
        <span class="spinner" style="width:24px;height:24px"></span>
        <p>Agent is analysing files…</p>
      </div>`;
  }

  state.scanProgress = { total: scanTargets.length, completed: 0 };
  updateProgressBar(0, scanTargets.length, `0 / ${scanTargets.length} folders scanned`);
  syncPaneParentMargin();

  for (const node of scanTargets) {
    await runFolderScan(node, isRescan, mode);
    state.scanProgress.completed += 1;
    updateProgressBar(state.scanProgress.completed, state.scanProgress.total, `${state.scanProgress.completed} / ${state.scanProgress.total} folders scanned`);
  }

  if (scanBtn) scanBtn.disabled = false;
  appendTerminal(`=== ${actionLabel} finished: ${state.scanProgress.completed}/${state.scanProgress.total} folders scanned ===`, 'info');
  updateProgressBar(state.scanProgress.completed, state.scanProgress.total, `Finished ${state.scanProgress.completed} / ${state.scanProgress.total}`);
  setTimeout(() => {
    if (state.scanProgress.completed === state.scanProgress.total) {
      resetProgressBar();
    }
  }, 5000);

  refreshTreeUI();
}

async function runFolderScan(node, isRescan, mode) {
  const endpoint = isRescan ? '/api/rescan' : '/api/scan';
  appendTerminal(`${isRescan ? 'Rescanning' : 'Scanning'} ${node.path}...`, 'info');

  try {
    const job = await api.post(endpoint, {
      folder_path: node.path,
      mode,
      language: node.language || '',
      quality: node.quality || null,
      actress: node.actress || node.name || '',
    });

    return new Promise((resolve) => {
      let finished = false;
      const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/progress/${job.job_id}`);

      const finish = (message) => {
        if (finished) return;
        finished = true;
        appendTerminal(message);
        ws.close();
        resolve();
      };

      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.type === 'progress') {
          appendTerminal(`[${node.name}] ${msg.messages.join('\n[' + node.name + '] ')}`);
        }
        if (msg.type === 'done') {
          if (msg.status === 'done') {
            finish(`✅ Scan complete for ${node.path}`);
            
            const cachedNode = findNodeByPath(_cachedTreeData, node.path);
            if (cachedNode) {
              cachedNode.has_report = true;
              cachedNode.scan_status = 'completed';
            }

            if (state.selectedNode && state.selectedNode.path === node.path) {
              loadReport(node.path, state.activeTab);
              toast(`Scan complete: ${node.name}`, 'success');
            }
          } else {
            finish(`❌ Scan failed for ${node.path}: ${msg.error || 'Unknown error'}`);
            
            const cachedNode = findNodeByPath(_cachedTreeData, node.path);
            if (cachedNode) {
              cachedNode.scan_status = 'failed';
            }
            toast(msg.error || 'Scan failed', 'error');
          }
        }
      };

      ws.onerror = () => { finish(`⚠ WebSocket error for ${node.path}`); };
      ws.onclose = () => { if (!finished) { finish(`⚠ WebSocket closed for ${node.path}`); } };
    });
  } catch (e) {
    appendTerminal(`❌ Failed to start scan for ${node.path}: ${e.message}`, 'error');
    return Promise.resolve();
  }
}

// ── Config Modal ──────────────────────────────────────────────────
const configModal = document.getElementById('config-modal');

document.getElementById('btn-config').addEventListener('click', () => {
  configModal.classList.add('open');
});
document.getElementById('btn-modal-cancel').addEventListener('click', () => {
  configModal.classList.remove('open');
});
configModal.addEventListener('click', (e) => {
  if (e.target === configModal) configModal.classList.remove('open');
});

document.getElementById('btn-modal-test').addEventListener('click', async () => {
  try {
    const data = await api.get('/health');
    toast(`✓ Connected: ${data.llm_provider} · ${data.llm_model}`, 'success');
  } catch (e) {
    toast(`✕ Connection failed: ${e.message}`, 'error');
  }
});

document.getElementById('btn-modal-save').addEventListener('click', () => {
  toast('Config changes require a server restart to take effect. Edit config.yml and restart.', 'info', 5000);
  configModal.classList.remove('open');
});

// ── Event Bindings ────────────────────────────────────────────────
document.getElementById('btn-refresh-tree').addEventListener('click', () => {
  loadTree();
  toast('Tree refreshed from server', 'info');
});

document.getElementById('btn-scan-folder').addEventListener('click', startScan);
document.getElementById('btn-clear-reports').addEventListener('click', clearReports);
document.getElementById('btn-dry-run').addEventListener('click', () => runExecute('within', true));
document.getElementById('btn-exec-delete').addEventListener('click', () => {
  if (!confirm('Execute DELETE on selected files? This cannot be undone.')) return;
  runExecute('within', false, 'delete');
});
document.getElementById('btn-exec-rename').addEventListener('click', () => {
  if (!confirm('Execute RENAME on selected files?')) return;
  runExecute('within', false, 'rename');
});
document.getElementById('btn-rescan-within').addEventListener('click', () => {
  if (state.selectedNode) {
    startScan(true, state.selectedNode);
  } else {
    toast('No folder selected to rescan', 'info');
  }
});
document.getElementById('btn-mark-executed-within').addEventListener('click', () => markFolderExecuted('within'));
document.getElementById('btn-clear-terminal-global').addEventListener('click', clearTerminal);

const terminalOutput = document.getElementById('terminal-output-global');
if (terminalOutput) {
  terminalOutput.addEventListener('scroll', () => {
    terminalAutoScroll = terminalOutput.scrollHeight - terminalOutput.scrollTop <= terminalOutput.clientHeight + 4;
  });
}

document.getElementById('btn-rescan-cross').addEventListener('click', () => {
  if (state.selectedNode) {
    startScan(true, state.selectedNode);
  } else {
    toast('No folder selected to rescan', 'info');
  }
});
document.getElementById('btn-cross-mark-executed').addEventListener('click', () => markFolderExecuted('cross'));

// ── Custom Video Player Controls ──────────────────────────────────
const videoOverlay = document.getElementById('video-overlay');
const videoEl = document.getElementById('custom-video-element');
const videoCloseBtn = document.getElementById('video-close-btn');
const videoPlayBtn = document.getElementById('video-play-btn');
const videoTimeDisplay = document.getElementById('video-time-display');
const videoVolumeBtn = document.getElementById('video-volume-btn');
const videoVolumeSlider = document.getElementById('video-volume-slider');
const videoFullscreenBtn = document.getElementById('video-fullscreen-btn');
const videoProgressBar = document.getElementById('video-progress-bar');
const videoProgressHandle = document.getElementById('video-progress-handle');
const videoProgressContainer = document.getElementById('video-progress-container');
const videoPlayerTitle = document.getElementById('video-player-title');

function updateVideoStats() {
  if (!videoEl) return;
  const origResEl = document.getElementById('video-orig-res');
  const dispResEl = document.getElementById('video-disp-res');

  if (origResEl) {
    if (videoEl.videoWidth && videoEl.videoHeight) {
      origResEl.textContent = `${videoEl.videoWidth}x${videoEl.videoHeight}`;
    } else {
      origResEl.textContent = 'Loading...';
    }
  }

  if (dispResEl) {
    const rect = videoEl.getBoundingClientRect();
    const w = Math.round(rect.width);
    const h = Math.round(rect.height);
    if (w && h) {
      dispResEl.textContent = `${w}x${h}`;
    } else {
      dispResEl.textContent = '—';
    }
  }
}

function openVideo(path, filename) {
  if (!videoOverlay || !videoEl) return;
  videoPlayerTitle.textContent = filename || 'Video Player';

  const origResEl = document.getElementById('video-orig-res');
  const dispResEl = document.getElementById('video-disp-res');
  if (origResEl) origResEl.textContent = 'Loading...';
  if (dispResEl) dispResEl.textContent = '—';

  videoEl.src = `/api/video?path=${encodeURIComponent(path)}`;
  videoOverlay.style.display = 'flex';
  videoEl.play().catch(() => {});
  videoPlayBtn.textContent = '⏸';

  setTimeout(updateVideoStats, 300);
}

function closeVideo() {
  if (!videoOverlay || !videoEl) return;
  videoEl.pause();
  videoEl.removeAttribute('src');
  videoEl.load();
  videoOverlay.style.display = 'none';
}

if (videoCloseBtn) videoCloseBtn.addEventListener('click', closeVideo);
if (videoOverlay) {
  videoOverlay.addEventListener('click', (e) => {
    if (e.target === videoOverlay) closeVideo();
  });
}

if (videoPlayBtn && videoEl) {
  videoPlayBtn.addEventListener('click', () => {
    if (videoEl.paused) {
      videoEl.play().catch(() => {});
      videoPlayBtn.textContent = '⏸';
    } else {
      videoEl.pause();
      videoPlayBtn.textContent = '⏵';
    }
  });
}

if (videoEl) {
  videoEl.addEventListener('timeupdate', () => {
    const cur = videoEl.currentTime;
    const dur = videoEl.duration || 0;
    const pct = dur > 0 ? (cur / dur) * 100 : 0;

    if (videoProgressBar) videoProgressBar.style.width = pct + '%';
    if (videoProgressHandle) videoProgressHandle.style.left = pct + '%';

    const fmt = (secs) => {
      const m = Math.floor(secs / 60).toString().padStart(2, '0');
      const s = Math.floor(secs % 60).toString().padStart(2, '0');
      return `${m}:${s}`;
    };
    if (videoTimeDisplay) {
      videoTimeDisplay.textContent = `${fmt(cur)} / ${fmt(dur)}`;
    }
  });

  videoEl.addEventListener('loadedmetadata', updateVideoStats);
  videoEl.addEventListener('playing', updateVideoStats);

  window.addEventListener('resize', () => {
    if (videoOverlay && videoOverlay.style.display === 'flex') {
      updateVideoStats();
    }
  });
}

if (videoProgressContainer && videoEl) {
  const setVideoProgress = (e) => {
    const rect = videoProgressContainer.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const pct = Math.max(0, Math.min(1, clickX / rect.width));
    if (videoEl.duration) {
      videoEl.currentTime = pct * videoEl.duration;
    }
  };

  videoProgressContainer.addEventListener('mousedown', (e) => {
    setVideoProgress(e);
    const onMouseMove = (moveEvent) => setVideoProgress(moveEvent);
    const onMouseUp = () => {
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    };
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  });
}

if (videoVolumeSlider && videoEl) {
  videoVolumeSlider.addEventListener('input', () => {
    videoEl.volume = videoVolumeSlider.value;
    if (videoEl.volume === 0) videoVolumeBtn.textContent = '🔇';
    else if (videoEl.volume < 0.5) videoVolumeBtn.textContent = '🔉';
    else videoVolumeBtn.textContent = '🔊';
  });
}

let lastVolume = 1;
if (videoVolumeBtn && videoEl && videoVolumeSlider) {
  videoVolumeBtn.addEventListener('click', () => {
    if (videoEl.volume > 0) {
      lastVolume = videoEl.volume;
      videoEl.volume = 0;
      videoVolumeSlider.value = 0;
      videoVolumeBtn.textContent = '🔇';
    } else {
      videoEl.volume = lastVolume;
      videoVolumeSlider.value = lastVolume;
      videoVolumeBtn.textContent = lastVolume < 0.5 ? '🔉' : '🔊';
    }
  });
}

if (videoFullscreenBtn && videoEl) {
  videoFullscreenBtn.addEventListener('click', () => {
    if (videoEl.requestFullscreen) videoEl.requestFullscreen();
    else if (videoEl.webkitRequestFullscreen) videoEl.webkitRequestFullscreen();
  });
}

document.addEventListener('keydown', (e) => {
  if (videoOverlay && videoOverlay.style.display === 'flex') {
    if (e.key === 'Escape') {
      closeVideo();
    } else if (e.key === ' ') {
      e.preventDefault();
      if (videoPlayBtn) videoPlayBtn.click();
    }
  }
});

// ── Resizer handles initialization ────────────────────────────────
function initResizers() {
  const terminalResizer = document.getElementById('terminal-resizer');
  const terminalGlobal = document.getElementById('terminal-global');

  if (terminalResizer && terminalGlobal) {
    // Explicitly guarantee position rule boundaries upfront
    terminalGlobal.style.display = 'block';
    terminalGlobal.style.position = 'fixed';
    terminalGlobal.style.bottom = '30px';
    terminalGlobal.style.left = 'var(--sidebar-width, 260px)';
    terminalGlobal.style.right = '0px';
    terminalGlobal.style.zIndex = '999';

    terminalResizer.style.display = 'block';
    terminalResizer.style.position = 'fixed';
    terminalResizer.style.left = 'var(--sidebar-width, 260px)';
    terminalResizer.style.right = '0px';
    terminalResizer.style.zIndex = '1000';

    const initialHeight = localStorage.getItem('terminal-preferred-height') || '220';
    terminalGlobal.style.height = `${initialHeight}px`;
    terminalResizer.style.bottom = `${initialHeight + 30}px`;
    document.documentElement.style.setProperty('--terminal-height', `${initialHeight}px`);

    terminalResizer.addEventListener('mousedown', (e) => {
      e.preventDefault();
      terminalResizer.classList.add('active');
      document.body.style.cursor = 'row-resize';
      document.body.style.userSelect = 'none';

      const startHeight = terminalGlobal.getBoundingClientRect().height;
      const startY = e.clientY;

      const doDrag = (moveEvent) => {
        const deltaY = startY - moveEvent.clientY;
        let newHeight = startHeight + deltaY;
        
        const minHeight = 100;
        const maxHeight = window.innerHeight - 150;

        if (newHeight < minHeight) newHeight = minHeight;
        if (newHeight > maxHeight) newHeight = maxHeight;

        terminalGlobal.style.height = `${newHeight}px`;
        terminalResizer.style.bottom = `${newHeight + 30}px`;
        document.documentElement.style.setProperty('--terminal-height', `${newHeight}px`);
        localStorage.setItem('terminal-preferred-height', newHeight);
        syncPaneParentMargin();
      };

      const stopDrag = () => {
        terminalResizer.classList.remove('active');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        document.removeEventListener('mousemove', doDrag);
        document.removeEventListener('mouseup', stopDrag);
      };

      document.addEventListener('mousemove', doDrag);
      document.addEventListener('mouseup', stopDrag);
    });
  }
}

// Strictly locks element rendering states so UI components can never drop below view folds
function syncPaneParentMargin() {
  const terminalGlobal = document.getElementById('terminal-global');
  const terminalResizer = document.getElementById('terminal-resizer');
  const paneParent = document.querySelector('.pane-parent');
  const terminalOutput = document.getElementById('terminal-output-global');
  const actionBar = document.getElementById('action-bar');
  const terminalHeader = document.querySelector('.terminal-header');
  
  if (terminalGlobal && terminalGlobal.style.display !== 'none') {
    const currentHeight = terminalGlobal.getBoundingClientRect().height || 220;
    const headerHeight = terminalHeader ? terminalHeader.getBoundingClientRect().height : 0;
    const actionBarHeight = actionBar && actionBar.style.display !== 'none'
      ? actionBar.getBoundingClientRect().height
      : 0;
    const outputHeight = Math.max(0, currentHeight - headerHeight - actionBarHeight);

    terminalGlobal.style.display = 'block';
    terminalGlobal.style.position = 'fixed';
    terminalGlobal.style.bottom = '30px';
    
    if (terminalResizer) {
      terminalResizer.style.display = 'block';
      terminalResizer.style.position = 'fixed';
      terminalResizer.style.bottom = `${currentHeight+30}px`;
    }

    if (terminalOutput) {
      terminalOutput.style.height = `${outputHeight}px`;
    }
    
    if (paneParent) {
      paneParent.style.paddingBottom = `${currentHeight + 20}px`;
      paneParent.style.marginBottom = '0px';
    }
  }
}

// ── Init ──────────────────────────────────────────────────────────
async function init() {
  await checkHealth();
  initResizers();
  await loadTree();
  syncPaneParentMargin();
  setInterval(checkHealth, 30_000);
}

window.addEventListener('resize', syncPaneParentMargin);

// Ensure init runs after DOM is ready (handles reloads reliably)
window.addEventListener('DOMContentLoaded', init);
let torrentsMap = new Map();
let domRows = new Map(); 
let selectedHashes = new Set();
let currentFilter = 'All';
let currentProfileId = null;
let lastFocusedHash = null;
let lastUserActivity = 0;

// Virtual Scrolling Config
const ROW_HEIGHT = 40;
const VIEWPORT_BUFFER = 10; 
let visibleTorrents = []; 

// Throttling
let lastProfileFetch = 0;
let detailsTimeout = null;

const els = {
    tbody: () => document.getElementById('torrentTableBody'),
    table: () => document.getElementById('torrentTable'),
    container: () => document.getElementById('tableScrollContainer'),
    contextMenu: () => document.getElementById('contextMenu'),
    selectAll: () => document.getElementById('selectAllCheck'),
    aria: () => document.getElementById('aria-announcer'),
    stretcher: () => document.getElementById('tableStretcher'),
    sidebarNav: () => document.getElementById('sidebarNav')
};

// Initialization
window.addEventListener('DOMContentLoaded', () => {
    const container = els.container();
    if (container) {
        container.addEventListener('scroll', () => {
            window.requestAnimationFrame(renderVirtualRows);
        });
    }

    refreshData();

    document.addEventListener('mousedown', (e) => {
        lastUserActivity = Date.now();
        const menu = els.contextMenu();
        if (menu && menu.style.display === 'block') {
            if (!menu.contains(e.target) && e.button === 0) {
                hideContextMenu();
            }
        }
    });

    const selectAll = els.selectAll();
    if (selectAll) {
        selectAll.onchange = (e) => {
            if (e.target.checked) {
                visibleTorrents.forEach(t => selectedHashes.add(t.hash));
            } else {
                selectedHashes.clear();
            }
            updateSelectionVisuals();
            updateDetailsDebounced();
        };
    }

    // Global Click Handler for Sidebar (Mouse Support)
    document.addEventListener('click', (e) => {
        const link = e.target.closest('.sidebar-link');
        if (!link) return;
        e.preventDefault();
        activateSidebarLink(link, e);
    });

    document.addEventListener('keydown', (e) => {
        const menu = els.contextMenu();
        const isMenuOpen = menu && menu.style.display === 'block';

        if (isMenuOpen) {
            handleMenuNavigation(e, menu);
            return;
        }

        if (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'TEXTAREA') return;

        // Check if focus is in sidebar
        const sidebarNav = els.sidebarNav();
        if (sidebarNav && sidebarNav.contains(document.activeElement)) {
            handleSidebarNavigation(e);
            return;
        }

        lastUserActivity = Date.now();
        if (visibleTorrents.length === 0) return;

        let currentIndex = -1;
        if (lastFocusedHash) {
            currentIndex = visibleTorrents.findIndex(t => t.hash === lastFocusedHash);
        } else if (selectedHashes.size > 0) {
            currentIndex = visibleTorrents.indexOf(Array.from(selectedHashes)[0]);
        }

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            navigateToIndex(Math.min(currentIndex + 1, visibleTorrents.length - 1));
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            navigateToIndex(Math.max(currentIndex - 1, 0));
        } else if (e.key === 'Home') {
            e.preventDefault();
            navigateToIndex(0);
        } else if (e.key === 'End') {
            e.preventDefault();
            navigateToIndex(visibleTorrents.length - 1);
        } else if (e.key === 'a' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            visibleTorrents.forEach(t => selectedHashes.add(t.hash));
            updateSelectionVisuals();
            updateDetailsDebounced();
        }
    });
});

// Sidebar navigation logic (Roving tabindex)
function handleSidebarNavigation(e) {
    const links = Array.from(document.querySelectorAll('.sidebar-link'));
    const currentIndex = links.indexOf(document.activeElement);
    let nextIndex = -1;

    if (e.key === 'ArrowDown') {
        e.preventDefault();
        nextIndex = (currentIndex + 1) % links.length;
    } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        nextIndex = (currentIndex - 1 + links.length) % links.length;
    } else if (e.key === 'Home') {
        e.preventDefault();
        nextIndex = 0;
    } else if (e.key === 'End') {
        e.preventDefault();
        nextIndex = links.length - 1;
    } else if (e.key === 'Enter') {
        e.preventDefault();
        activateSidebarLink(document.activeElement, e);
    }

    if (nextIndex !== -1) {
        links.forEach(l => l.tabIndex = -1);
        links[nextIndex].tabIndex = 0;
        links[nextIndex].focus();
    }
}

async function refreshData() {
    if (Date.now() - lastUserActivity < 2000) return;
    try {
        const res = await fetch('/api/v2/torrents/info');
        if (res.status === 403) { window.location.href = '/login.html'; return; }
        const data = await res.json();
        
        const isFirstLoad = torrentsMap.size === 0;
        const torrentsList = data.torrents || [];
        
        syncTorrentsMap(torrentsList);
        updateFilteredList();
        renderVirtualRows();
        updateSidebarStats(data.stats, data.trackers);
        
        const now = Date.now();
        if (now - lastProfileFetch > 30000) { fetchProfiles(); lastProfileFetch = now; }

        if (isFirstLoad && visibleTorrents.length > 0) {
            // Set focus but NOT selection on load
            focusRow(visibleTorrents[0].hash, true);
        } else if (lastFocusedHash) {
            focusRow(lastFocusedHash, false);
        }
    } catch (e) { console.error("Refresh error", e); }
}

function syncTorrentsMap(newData) {
    const newHashes = new Set(newData.map(t => t.hash));
    for (const h of torrentsMap.keys()) {
        if (!newHashes.has(h)) {
            torrentsMap.delete(h);
            const tr = domRows.get(h);
            if (tr) { tr.remove(); domRows.delete(h); }
            selectedHashes.delete(h);
        }
    }
    newData.forEach(t => torrentsMap.set(t.hash, t));
}

function updateFilteredList() {
    visibleTorrents = Array.from(torrentsMap.values()).filter(t => {
        if (currentFilter === 'All') return true;
        if (currentFilter === 'RSS') return false;
        const pct = t.size > 0 ? (t.done / t.size * 100) : 0;
        if (currentFilter === 'Downloading') return t.state === 1 && (pct < 100);
        if (currentFilter === 'Seeding') return t.state === 1 && (pct >= 100);
        if (currentFilter === 'Finished') return pct >= 100;
        if (currentFilter === 'Stopped') return t.state === 0;
        if (currentFilter === 'Failed') {
            const msg = (t.message || '').toLowerCase();
            return msg && !msg.includes('success') && !msg.includes('ok');
        }
        if (t.tracker_domain === currentFilter) return true;
        return false;
    });
    visibleTorrents.sort((a, b) => a.name.localeCompare(b.name));
    const stretcher = els.stretcher();
    if (stretcher) stretcher.style.height = (visibleTorrents.length * ROW_HEIGHT) + 'px';
}

function renderVirtualRows() {
    const container = els.container();
    const tbody = els.tbody();
    if (!container || !tbody) return;
    const startIndex = Math.max(0, Math.floor(container.scrollTop / ROW_HEIGHT) - VIEWPORT_BUFFER);
    const endIndex = Math.min(visibleTorrents.length - 1, Math.ceil((container.scrollTop + container.clientHeight) / ROW_HEIGHT) + VIEWPORT_BUFFER);
    const visibleSubList = visibleTorrents.slice(startIndex, endIndex + 1);
    const visibleHashes = new Set(visibleSubList.map(t => t.hash));
    const allFilteredHashes = new Set(visibleTorrents.map(t => t.hash));

    tbody.style.transform = `translateY(${startIndex * ROW_HEIGHT}px)`;

    for (const [hash, tr] of domRows.entries()) {
        if (!visibleHashes.has(hash)) {
            const isFocusedAndValid = (hash === lastFocusedHash && allFilteredHashes.has(hash));
            if (!isFocusedAndValid) { tr.remove(); domRows.delete(hash); }
        }
    }
    visibleSubList.forEach((t, i) => {
        let tr = domRows.get(t.hash);
        if (!tr) { tr = createRowElement(t); domRows.set(t.hash, tr); }
        else { updateRowData(tr, t); }
        if (tbody.children[i] !== tr) tbody.insertBefore(tr, tbody.children[i] || null);
    });
    updateSelectionVisuals();
}

function createRowElement(t) {
    const tr = document.createElement('tr');
    tr.dataset.hash = t.hash;
    tr.style.height = ROW_HEIGHT + 'px';
    tr.setAttribute('role', 'row');
    tr.tabIndex = -1;
    tr.onclick = (e) => { if (e.ctrlKey || e.metaKey) toggleSelection(t.hash); else selectByHash(t.hash); };
    tr.addEventListener('contextmenu', (e) => { e.preventDefault(); e.stopPropagation(); if (!selectedHashes.has(t.hash)) selectByHash(t.hash); showContextMenu(e); });
    updateRowData(tr, t);
    return tr;
}

function updateRowData(tr, t) {
    const progress = t.size > 0 ? (t.done / t.size * 100).toFixed(1) : 0;
    const isSelected = selectedHashes.has(t.hash);
    const ariaLabel = `${t.name}, ${fmtSize(t.size)}, ${t.state === 1 ? (progress >= 100 ? 'Seeding' : 'Downloading') : 'Paused'}, ${progress}% complete, DL: ${fmtSize(t.down_rate)} per second`;
    if (tr.getAttribute('aria-label') !== ariaLabel) tr.setAttribute('aria-label', ariaLabel);
    const statusText = t.state === 1 ? (progress >= 100 ? 'Seeding' : 'Downloading') : 'Paused';
    const speedText = `DL: ${fmtSize(t.down_rate)}/s`;
    if (!tr.innerHTML || tr.dataset.lastSnapshot !== `${t.state}|${progress}|${t.down_rate}|${isSelected}`) {
        tr.innerHTML = `<td role="gridcell" style="width:40px"><input type="checkbox" class="row-check" ${isSelected ? 'checked' : ''} onclick="event.stopPropagation(); toggleSelection('${t.hash}')"></td><td role="gridcell" class="col-name" title="${t.name}">${t.name}</td><td role="gridcell" style="width:100px">${fmtSize(t.size)}</td><td role="gridcell" style="width:120px">${statusText}</td><td role="gridcell" style="width:150px"><div class="progress" aria-hidden="true"><div class="progress-bar" style="width: ${progress}%">${progress}%</div></div></td><td role="gridcell" style="width:120px">${speedText}</td>`;
        tr.dataset.lastSnapshot = `${t.state}|${progress}|${t.down_rate}|${isSelected}`;
    }
}

function navigateToIndex(index) {
    if (index < 0 || index >= visibleTorrents.length) return;
    const t = visibleTorrents[index];
    selectedHashes.clear(); selectedHashes.add(t.hash);
    lastFocusedHash = t.hash;
    scrollToRow(t.hash, index);
    renderVirtualRows();
    focusRow(t.hash);
    updateDetailsDebounced();
}

function selectByHash(hash) {
    selectedHashes.clear(); selectedHashes.add(hash);
    lastFocusedHash = hash;
    renderVirtualRows();
    focusRow(hash);
    updateDetailsDebounced();
}

function toggleSelection(hash) {
    if (selectedHashes.has(hash)) selectedHashes.delete(hash);
    else selectedHashes.add(hash);
    lastFocusedHash = hash;
    updateSelectionVisuals();
    updateDetailsDebounced();
}

function focusRow(hash, shouldPerformFocus = true) {
    lastFocusedHash = hash;
    const row = domRows.get(hash) || document.querySelector(`tr[data-hash="${hash}"]`);
    document.querySelectorAll('#torrentTableBody tr').forEach(tr => tr.tabIndex = -1);
    if (row) {
        row.tabIndex = 0;
        if (shouldPerformFocus && document.activeElement !== row) row.focus();
    }
}

function scrollToRow(hash, index) {
    const container = els.container();
    const targetTop = index * ROW_HEIGHT;
    if (targetTop < container.scrollTop) container.scrollTop = targetTop;
    else if (targetTop + ROW_HEIGHT > container.scrollTop + container.clientHeight) {
        container.scrollTop = targetTop - container.clientHeight + ROW_HEIGHT;
    }
}

function updateSelectionVisuals() {
    domRows.forEach((tr, hash) => {
        const isSelected = selectedHashes.has(hash);
        tr.classList.toggle('selected', isSelected);
        tr.setAttribute('aria-selected', isSelected);
        const check = tr.querySelector('.row-check');
        if (check) check.checked = isSelected;
    });
    const allSelected = visibleTorrents.length > 0 && visibleTorrents.every(t => selectedHashes.has(t.hash));
    const selectAll = els.selectAll();
    if (selectAll) { selectAll.checked = allSelected; selectAll.indeterminate = !allSelected && selectedHashes.size > 0; }
}

function updateSidebarStats(stats, trackers) {
    if (!stats) return;
    for (const cat in stats) {
        const badge = document.getElementById(`count-${cat}`);
        if (badge) badge.textContent = stats[cat];
    }
    const trackerList = document.getElementById('trackerList');
    if (trackerList && trackers) {
        trackerList.innerHTML = '';
        Object.entries(trackers).sort((a,b)=>b[1]-a[1]).forEach(([domain, count]) => {
            const div = document.createElement('div');
            div.setAttribute('role', 'row');
            const isActive = currentFilter === domain;
            div.innerHTML = `<div role="gridcell"><a href="#" class="sidebar-link ${isActive ? 'active' : ''}" data-filter="${domain}" role="link" tabindex="-1">${domain} (${count})</a></div>`;
            trackerList.appendChild(div);
        });
    }
}

function activateSidebarLink(link, event) {
    const profileId = link.dataset.profileId;
    const filter = link.dataset.filter;
    if (profileId) switchProfile(profileId, event);
    else if (filter) setFilter(filter, event);
}

function setFilter(f, event) {
    if (event) event.preventDefault();
    currentFilter = f;
    selectedHashes.clear();
    lastFocusedHash = null;
    const links = document.querySelectorAll('.sidebar-link');
    links.forEach(l => {
        const isMatch = l.dataset.filter === f;
        l.classList.toggle('active', isMatch);
        const row = l.closest('[role="row"]');
        if (row) row.classList.toggle('active', isMatch);
    });
    updateFilteredList();
    
    // Reset scroll to top for new view
    const container = els.container();
    if (container) container.scrollTop = 0;
    
    renderVirtualRows();

    // Automatically focus the first torrent if available, so Shift-Tab works correctly
    if (visibleTorrents.length > 0) {
        focusRow(visibleTorrents[0].hash, true);
    }
}

async function fetchProfiles() {
    try {
        const res = await fetch('/api/v2/profiles');
        const data = await res.json();
        const list = document.getElementById('profileList');
        if (!list) return;
        list.innerHTML = '';
        currentProfileId = data.current_id;
        for (const id in data.profiles) {
            const p = data.profiles[id];
            const div = document.createElement('div');
            div.setAttribute('role', 'row');
            const isActive = id === data.current_id;
            div.innerHTML = `<div role="gridcell"><a href="#" class="sidebar-link ${isActive ? 'active' : ''}" data-profile-id="${id}" role="link" tabindex="-1">${p.name} (${p.type})</a></div>`;
            list.appendChild(div);
        }
    } catch (e) {}
}

async function switchProfile(id, event) {
    if (event) event.preventDefault();
    if (id === currentProfileId) return;
    announceToSR("Switching client profile...");
    const fd = new FormData(); fd.append('id', id);
    const res = await fetch('/api/v2/profiles/switch', { method: 'POST', body: fd });
    if (res.ok) { selectedHashes.clear(); lastFocusedHash = null; lastUserActivity = 0; refreshData(); }
}

function updateDetailsDebounced() { if (detailsTimeout) clearTimeout(detailsTimeout); detailsTimeout = setTimeout(updateDetails, 200); }

async function updateDetails() {
    const detailPane = document.getElementById('details-general');
    if (selectedHashes.size === 0) { detailPane.innerHTML = '<p>Select a torrent.</p>'; return; }
    if (selectedHashes.size > 1) { detailPane.innerHTML = `<p>${selectedHashes.size} torrents selected.</p><p class="text-muted small">Right-click to manage selection.</p>`; return; }
    const hash = Array.from(selectedHashes)[0];
    const t = torrentsMap.get(hash);
    if (!t) return;
    detailPane.innerHTML = `<h3 class="fs-5">${t.name}</h3><p>Size: ${fmtSize(t.size)}<br>Hash: ${t.hash}<br>Path: ${t.save_path || 'N/A'}</p>`;
    const activeTab = document.querySelector('#detailTabs .nav-link.active').id;
    if (activeTab === 'files-tab') fetchFiles(hash);
    else if (activeTab === 'peers-tab') fetchPeers(hash);
    else if (activeTab === 'trackers-tab') fetchTrackers(hash);
}

async function fetchFiles(hash) {
    const filesPane = document.getElementById('details-files');
    try {
        const res = await fetch(`/api/v2/torrents/files?hash=${hash}`);
        const files = await res.json();
        let html = '<div class="table-responsive"><table class="table table-sm table-striped"><thead><tr><th>Name</th><th>Size</th><th>Progress</th></tr></thead><tbody>';
        files.forEach(f => html += `<tr><td>${f.name}</td><td>${fmtSize(f.size)}</td><td>${(f.progress*100).toFixed(1)}%</td></tr>`);
        html += '</tbody></table></div>'; filesPane.innerHTML = html;
    } catch (e) {}
}

async function fetchPeers(hash) {
    const pane = document.getElementById('details-peers');
    try {
        const res = await fetch(`/api/v2/torrents/peers?hash=${hash}`);
        const peers = await res.json();
        let html = '<div class="table-responsive"><table class="table table-sm table-striped"><thead><tr><th>Address</th><th>Client</th><th>Progress</th><th>Speed</th></tr></thead><tbody>';
        peers.forEach(p => html += `<tr><td>${p.address}</td><td>${p.client}</td><td>${(p.progress*100).toFixed(1)}%</td><td>${fmtSize(p.down_rate)}/s</td></tr>`);
        html += '</tbody></table></div>'; pane.innerHTML = html;
    } catch (e) {}
}

async function fetchTrackers(hash) {
    const pane = document.getElementById('details-trackers');
    try {
        const res = await fetch(`/api/v2/torrents/trackers?hash=${hash}`);
        const trackers = await res.json();
        let html = '<div class="table-responsive"><table class="table table-sm table-striped"><thead><tr><th>URL</th><th>Status</th><th>Peers</th><th>Message</th></tr></thead><tbody>';
        trackers.forEach(t => html += `<tr><td class="text-truncate" style="max-width:200px" title="${t.url}">${t.url}</td><td>${t.status}</td><td>${t.peers}</td><td class="small">${t.message}</td></tr>`);
        html += '</tbody></table></div>'; pane.innerHTML = html;
    } catch (e) {}
}

document.addEventListener('shown.bs.tab', (e) => {
    if (selectedHashes.size === 1) {
        const hash = Array.from(selectedHashes)[0];
        if (e.target.id === 'peers-tab') fetchPeers(hash);
        else if (e.target.id === 'trackers-tab') fetchTrackers(hash);
        else if (e.target.id === 'files-tab') fetchFiles(hash);
    }
});

async function doAction(action, deleteFiles = false) {
    if (selectedHashes.size === 0) return;
    const formData = new FormData();
    formData.append('hashes', Array.from(selectedHashes).join('|'));
    if (deleteFiles) formData.append('deleteFiles', 'true');
    const res = await fetch(`/api/v2/torrents/${action}`, { method: 'POST', body: formData });
    if (res.ok) { hideContextMenu(); refreshData(); }
}

function fmtSize(bytes) {
    if (!bytes || bytes === 0) return "0 B";
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return parseFloat((bytes / Math.pow(1024, i)).toFixed(2)) + ' ' + units[i];
}

async function logout() { await fetch('/api/v2/auth/logout', { method: 'POST' }); window.location.href = '/login.html'; }
function announceToSR(m) { const a = els.aria(); if (a) a.textContent = m; }

function applyTheme(theme) {
    if (theme === 'dark') { document.body.classList.add('dark-mode'); localStorage.setItem('web-theme', 'dark'); }
    else { document.body.classList.remove('dark-mode'); localStorage.setItem('web-theme', 'light'); }
}

function copyToClipboard(type) {
    if (selectedHashes.size === 0) return;
    let text = type === 'hash' ? Array.from(selectedHashes).join('\n') : Array.from(selectedHashes).map(h => `magnet:?xt=urn:btih:${h}`).join('\n');
    navigator.clipboard.writeText(text); hideContextMenu();
}

async function renderRSSView() {
    const pane = document.getElementById('rss-view');
    pane.innerHTML = `<div class="d-flex justify-content-between align-items-center mb-3"><h2>RSS Downloader</h2><div class="btn-group"><button class="btn btn-sm btn-outline-primary" onclick="refreshRSSData()">Update Feeds</button><button class="btn btn-sm btn-outline-secondary" onclick="document.getElementById('flexgetImport').click()">Import FlexGet</button><input type="file" id="flexgetImport" style="display:none" onchange="importFlexGet(this)"></div></div><div class="row"><div class="col-md-4"><div class="card mb-3"><div class="card-header d-flex justify-content-between align-items-center"><span>Feeds</span><button class="btn btn-sm btn-primary" onclick="addRSSFeed()" style="width: 24px; height: 24px; padding: 0;">+</button></div><div class="list-group list-group-flush" id="rssFeedList"></div></div></div><div class="col-md-8"><div class="card mb-3"><div class="card-header d-flex justify-content-between align-items-center"><span>Auto-Download Rules</span><button class="btn btn-sm btn-primary" onclick="addRSSRule()" style="padding: 2px 10px;">Add Rule</button></div><div class="card-body" id="rssRulesList"></div></div></div></div>`;
    refreshRSSData();
}

async function refreshRSSData() {
    const [fRes, rRes] = await Promise.all([fetch('/api/v2/rss/feeds'), fetch('/api/v2/rss/rules')]);
    const feeds = await fRes.json(); const rules = await rRes.json();
    const fList = document.getElementById('rssFeedList'); if (!fList) return;
    fList.innerHTML = '';
    for (const url in feeds) {
        const li = document.createElement('div'); li.className = 'list-group-item d-flex justify-content-between align-items-center';
        li.innerHTML = `<span class="text-truncate">${feeds[url].alias || url}</span><button class="btn btn-sm text-danger" onclick="removeRSSFeed('${url}')">&times;</button>`;
        fList.appendChild(li);
    }
    const rList = document.getElementById('rssRulesList'); rList.innerHTML = '';
    rules.forEach((r, i) => {
        const div = document.createElement('div'); div.className = `alert alert-${r.type === 'accept' ? 'success' : 'warning'} py-1 mb-2 d-flex justify-content-between`;
        div.innerHTML = `<span><strong>${r.type.toUpperCase()}:</strong> <code>${r.pattern}</code></span><button class="btn-close" onclick="removeRSSRule(${i})"></button>`;
        rList.appendChild(div);
    });
}

async function importFlexGet(input) { 
    if (!input.files.length) return; announceToSR("Importing FlexGet configuration...");
    const fd = new FormData(); fd.append('config', input.files[0]);
    try {
        const res = await fetch('/api/v2/rss/import_flexget', { method: 'POST', body: fd });
        if (res.ok) { const result = await res.json(); alert(`Successfully imported ${result.feeds} feeds and ${result.rules} rules.`); refreshRSSData(); }
        else { alert("Import failed: " + await res.text()); }
    } catch (e) { alert("Error during import: " + e); }
    input.value = '';
}

async function addRSSFeed() {
    const url = prompt("Enter RSS Feed URL:"); if (!url) return;
    const fd = new FormData(); fd.append('url', url);
    await fetch('/api/v2/rss/add_feed', { method: 'POST', body: fd }); refreshRSSData();
}

async function removeRSSFeed(url) {
    if (confirm("Remove this feed?")) { const fd = new FormData(); fd.append('url', url); await fetch('/api/v2/rss/remove_feed', { method: 'POST', body: fd }); refreshRSSData(); }
}

async function addRSSRule() {
    const pattern = prompt("Enter Regex Pattern:"); if (!pattern) return;
    const type = confirm("Accept? (Cancel for Reject)") ? "accept" : "reject";
    const fd = new FormData(); fd.append('pattern', pattern); fd.append('type', type);
    await fetch('/api/v2/rss/set_rule', { method: 'POST', body: fd }); refreshRSSData();
}

async function removeRSSRule(index) {
    const fd = new FormData(); fd.append('index', index); await fetch('/api/v2/rss/remove_rule', { method: 'POST', body: fd }); refreshRSSData();
}

function showActionsMenu(e) {
    if (selectedHashes.size === 0) {
        alert("Please select at least one torrent first.");
        return;
    }
    
    const btn = document.getElementById('torrentActionsBtn');
    const rect = btn.getBoundingClientRect();
    
    // Simulate a contextmenu event at the button's position
    const menu = els.contextMenu();
    menu.style.display = 'block';
    
    // Position menu above the button
    const mHeight = menu.offsetHeight || 350;
    menu.style.left = rect.left + 'px';
    menu.style.top = (rect.top - mHeight - 10) + 'px';
    
    // Focus first item
    setTimeout(() => {
        const first = menu.querySelector('.dropdown-item');
        if (first) first.focus();
    }, 50);
}

function toggleSelectAllBtn() {
    const isAllSelected = visibleTorrents.length > 0 && visibleTorrents.every(t => selectedHashes.has(t.hash));
    if (isAllSelected) {
        selectedHashes.clear();
    } else {
        visibleTorrents.forEach(t => selectedHashes.add(t.hash));
    }
    updateSelectionVisuals();
    updateDetailsDebounced();
}

function hideContextMenu() { const menu = els.contextMenu(); if (menu) menu.style.display = 'none'; }

function handleMenuNavigation(e, menu) {
    const items = Array.from(menu.querySelectorAll('[role="menuitem"]:not([disabled])'));
    const currentIndex = items.indexOf(document.activeElement);
    if (e.key === 'ArrowDown') { e.preventDefault(); items[(currentIndex + 1) % items.length].focus(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); items[(currentIndex - 1 + items.length) % items.length].focus(); }
    else if (e.key === 'Escape') { hideContextMenu(); if (lastFocusedHash) focusRow(lastFocusedHash); }
}

setInterval(refreshData, 5000);

let torrentsMap = new Map();
let domRows = new Map(); 
let selectedHashes = new Set();
let currentFilter = 'All';
let currentProfileId = null;
let lastFocusedHash = null;
let lastUserActivity = 0;
let refreshIntervalId = null;

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
    selectAllCheck: () => document.getElementById('selectAllCheck'),
    aria: () => document.getElementById('aria-announcer'),
    stretcher: () => document.getElementById('tableStretcher'),
    sidebarNav: () => document.getElementById('sidebarNav'),
    actionsBtn: () => document.getElementById('torrentActionsBtn'),
    refreshRateInput: () => document.getElementById('webRefreshRate')
};

// Initialization
window.addEventListener('DOMContentLoaded', () => {
    const container = els.container();
    if (container) {
        container.addEventListener('scroll', () => {
            window.requestAnimationFrame(renderVirtualRows);
        });
    }

    // Initial fetch
    refreshData(true);
    startRefreshLoop();

    // Refresh rate listener
    const rr = els.refreshRateInput();
    if (rr) {
        rr.addEventListener('change', () => {
            startRefreshLoop();
        });
    }

    // Aggressive global context menu suppression for the torrent list area
    document.addEventListener('contextmenu', (e) => {
        const tableContainer = els.container();
        if (tableContainer && tableContainer.contains(e.target)) {
            e.preventDefault();
            e.stopPropagation();
            const row = e.target.closest('tr[data-hash]');
            showContextMenu(e, row);
            return false;
        }
    }, true);
 
    document.addEventListener('mousedown', (e) => {
        lastUserActivity = Date.now();
    });

    const selectAllCheck = els.selectAllCheck();
    if (selectAllCheck) {
        selectAllCheck.onchange = (e) => {
            if (e.target.checked) {
                visibleTorrents.forEach(t => selectedHashes.add(t.hash));
                announceToSR(`Selected all ${visibleTorrents.length} torrents`);
            } else {
                selectedHashes.clear();
                announceToSR("Selection cleared");
            }
            updateSelectionVisuals();
            updateDetailsDebounced();
        };
    }

    const actionsBtn = els.actionsBtn();
    if (actionsBtn) {
        actionsBtn.addEventListener('show.bs.dropdown', (e) => {
            if (selectedHashes.size === 0) {
                e.preventDefault();
                announceToSR("Please select at least one torrent first.", true);
            } else {
                lastUserActivity = Date.now();
                announceToSR("Menu opened", true);
            }
        });
        actionsBtn.addEventListener('hidden.bs.dropdown', () => {
            announceToSR("Menu closed");
            if (lastFocusedHash) {
                setTimeout(() => focusRow(lastFocusedHash, true), 10);
            }
        });
    }

    // Add Torrent Form Handler
    const addTorrentForm = document.getElementById('addTorrentForm');
    if (addTorrentForm) {
        addTorrentForm.onsubmit = async (e) => {
            e.preventDefault();
            const formData = new FormData();
            formData.append('urls', document.getElementById('torrentUrls').value);
            formData.append('savepath', document.getElementById('torrentSavePath').value);
            const files = document.getElementById('torrentFiles').files;
            for (let i = 0; i < files.length; i++) {
                formData.append('torrents', files[i]);
            }
            const res = await fetch('/api/v2/torrents/add', { method: 'POST', body: formData });
            if (res.ok) {
                const modal = bootstrap.Modal.getInstance(document.getElementById('addTorrentModal'));
                if (modal) modal.hide();
                e.target.reset();
                refreshData(true); 
            } else {
                alert("Failed to add torrent: " + await res.text());
            }
        };
    }

    document.addEventListener('click', (e) => {
        const link = e.target.closest('.sidebar-link');
        if (!link) return;
        e.preventDefault();
        activateSidebarLink(link, e);
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'ContextMenu' || (e.shiftKey && e.key === 'F10')) {  
            const activeRow = document.activeElement?.closest ? document.activeElement.closest('tr[data-hash]') : null;
            const targetRow = activeRow || (lastFocusedHash ? domRows.get(lastFocusedHash) : null);
            if (targetRow) {
                e.preventDefault();
                e.stopPropagation();
                showContextMenu(e, targetRow);
            }
            return false;
        }

        if (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'TEXTAREA') return;

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
            announceToSR(`All ${visibleTorrents.length} torrents selected`);
        }
    });
});

function startRefreshLoop() {
    if (refreshIntervalId) clearInterval(refreshIntervalId);
    let rate = 2000;
    const input = els.refreshRateInput();
    if (input && input.value) rate = parseInt(input.value);
    if (rate < 500) rate = 500;
    refreshIntervalId = setInterval(() => refreshData(), rate);
}

function handleSidebarNavigation(e) {
    const links = Array.from(document.querySelectorAll('.sidebar-link'));
    const currentIndex = links.indexOf(document.activeElement);
    let nextIndex = -1;

    if (e.key === 'ArrowDown') { e.preventDefault(); nextIndex = (currentIndex + 1) % links.length; }
    else if (e.key === 'ArrowUp') { e.preventDefault(); nextIndex = (currentIndex - 1 + links.length) % links.length; }
    else if (e.key === 'Home') { e.preventDefault(); nextIndex = 0; }
    else if (e.key === 'End') { e.preventDefault(); nextIndex = links.length - 1; }
    else if (e.key === 'Enter') { e.preventDefault(); activateSidebarLink(document.activeElement, e); }

    if (nextIndex !== -1) {
        links.forEach(l => l.tabIndex = -1);
        links[nextIndex].tabIndex = 0;
        links[nextIndex].focus();
    }
}

async function refreshData(force = false) {
    // If user is actively typing or interacting, skip background refresh unless forced
    if (!force && Date.now() - lastUserActivity < 1000) return;
    
    try {
        const isFirstLoad = torrentsMap.size === 0;
        // Get the full list from the client directly, info only provides MainFrame's filtered list
        const res = await fetch('/api/v2/torrents/all');
        if (res.status === 403) { window.location.href = '/login.html'; return; }
        const torrentsList = await res.json();
        
        // Also get stats from info
        const infoRes = await fetch('/api/v2/torrents/info');
        const infoData = await infoRes.json();
        
        syncTorrentsMap(Array.isArray(torrentsList) ? torrentsList : []);
        updateFilteredList();
        renderVirtualRows();
        updateSidebarStats(infoData.stats, infoData.trackers);
        
        const now = Date.now();
        if (now - lastProfileFetch > 30000) { fetchProfiles(); lastProfileFetch = now; }

        if (isFirstLoad && visibleTorrents.length > 0) {
            // Focus the first torrent on very first load
            setTimeout(() => focusRow(visibleTorrents[0].hash, true), 100);
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
    
    const table = els.table();
    if (table) table.setAttribute('aria-rowcount', visibleTorrents.length);
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

    tbody.style.transform = `translateY(${startIndex * ROW_HEIGHT}px)`;

    for (const [hash, tr] of domRows.entries()) {
        if (!visibleHashes.has(hash) && hash !== lastFocusedHash) {
            tr.remove(); domRows.delete(hash);
        }
    }
    visibleSubList.forEach((t, i) => {
        const absoluteIndex = startIndex + i;
        let tr = domRows.get(t.hash);
        if (!tr) { tr = createRowElement(t); domRows.set(t.hash, tr); }
        updateRowData(tr, t, absoluteIndex);
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
    
    tr.innerHTML = `
        <td role="gridcell"><input type="checkbox" class="row-check" tabindex="-1"></td>
        <td role="gridcell" class="col-name"></td>
        <td role="gridcell" class="col-size text-nowrap"></td>
        <td role="gridcell" class="col-status text-nowrap"></td>
        <td role="gridcell"><div class="progress" aria-hidden="true"><div class="progress-bar"></div></div></td>
        <td role="gridcell" class="col-speed text-nowrap"></td>
    `;
    
    const check = tr.querySelector('.row-check');
    check.onclick = (e) => { e.stopPropagation(); toggleSelection(t.hash); };

    tr.onclick = (e) => { 
        if (e.ctrlKey || e.metaKey) toggleSelection(t.hash); 
        else selectByHash(t.hash); 
    };
    tr.addEventListener('focus', () => { lastFocusedHash = t.hash; });
    return tr;
}

function updateRowData(tr, t, absIndex) {
    const progress = t.size > 0 ? (t.done / t.size * 100).toFixed(1) : 0;
    const isSelected = selectedHashes.has(t.hash);
    const statusText = t.state === 1 ? (progress >= 100 ? 'Seeding' : 'Downloading') : 'Paused';
    const speedText = `DL: ${fmtSize(t.down_rate)}/s`;
    
    tr.setAttribute('aria-rowindex', absIndex + 1);
    tr.setAttribute('aria-selected', isSelected);
    
    const check = tr.querySelector('.row-check');
    check.checked = isSelected;
    check.setAttribute('aria-label', `Select ${t.name}`);
    
    const nameCell = tr.querySelector('.col-name');
    if (nameCell.textContent !== t.name) { nameCell.textContent = t.name; nameCell.title = t.name; }
    
    const sizeCell = tr.querySelector('.col-size');
    const sz = fmtSize(t.size);
    if (sizeCell.textContent !== sz) sizeCell.textContent = sz;
    
    const statusCell = tr.querySelector('.col-status');
    if (statusCell.textContent !== statusText) statusCell.textContent = statusText;
    
    const bar = tr.querySelector('.progress-bar');
    bar.style.width = progress + '%';
    bar.textContent = progress + '%';
    
    const speedCell = tr.querySelector('.col-speed');
    if (speedCell.textContent !== speedText) speedCell.textContent = speedText;

    tr.classList.toggle('selected', isSelected);
}

function navigateToIndex(index) {
    if (index < 0 || index >= visibleTorrents.length) return;
    const t = visibleTorrents[index];
    selectedHashes.clear();
    selectedHashes.add(t.hash);
    lastFocusedHash = t.hash;
    scrollToRow(t.hash, index);
    renderVirtualRows();
    focusRow(t.hash);
    updateDetailsDebounced();
}

function selectByHash(hash) {
    selectedHashes.clear();
    selectedHashes.add(hash);
    lastFocusedHash = hash;
    updateSelectionVisuals();
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
    if (row) {
        document.querySelectorAll('#torrentTableBody tr').forEach(tr => tr.tabIndex = -1);
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
        tr.setAttribute('aria-selected', isSelected);
        tr.classList.toggle('selected', isSelected);
        const check = tr.querySelector('.row-check');
        if (check) check.checked = isSelected;
    });
    const allSelected = visibleTorrents.length > 0 && visibleTorrents.every(t => selectedHashes.has(t.hash));
    const selectAllCheck = els.selectAllCheck();
    if (selectAllCheck) { 
        selectAllCheck.checked = allSelected; 
        selectAllCheck.indeterminate = !allSelected && selectedHashes.size > 0; 
    }
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
    links.forEach(l => l.classList.toggle('active', l.dataset.filter === f));
    updateFilteredList();
    const container = els.container();
    if (container) container.scrollTop = 0;
    renderVirtualRows();
    if (visibleTorrents.length > 0) focusRow(visibleTorrents[0].hash, true);
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
    if (res.ok) { selectedHashes.clear(); lastFocusedHash = null; lastUserActivity = 0; refreshData(true); }
}

function updateDetailsDebounced() { if (detailsTimeout) clearTimeout(detailsTimeout); detailsTimeout = setTimeout(updateDetails, 200); }

async function updateDetails() {
    const detailPane = document.getElementById('details-general');
    if (selectedHashes.size === 0) { detailPane.innerHTML = '<p>Select a torrent.</p>'; return; }
    if (selectedHashes.size > 1) { detailPane.innerHTML = `<p>${selectedHashes.size} torrents selected.</p>`; return; }
    const hash = Array.from(selectedHashes)[0];
    const t = torrentsMap.get(hash);
    if (!t) return;
    detailPane.innerHTML = `<h3 class="fs-5">${t.name}</h3><p>Size: ${fmtSize(t.size)}<br>Hash: ${t.hash}<br>Path: ${t.save_path || 'N/A'}</p>`;
}

async function doAction(action, deleteFiles = false) {
    if (selectedHashes.size === 0) return;
    const formData = new FormData();
    formData.append('hashes', Array.from(selectedHashes).join('|'));
    if (deleteFiles) formData.append('deleteFiles', 'true');
    const res = await fetch(`/api/v2/torrents/${action}`, { method: 'POST', body: formData });
    if (res.ok) { 
        hideContextMenu(); 
        setTimeout(() => refreshData(true), 100); 
    }
}

function fmtSize(bytes) {
    if (!bytes || bytes === 0) return "0 B";
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return parseFloat((bytes / Math.pow(1024, i)).toFixed(2)) + ' ' + units[i];
}

async function logout() { await fetch('/api/v2/auth/logout', { method: 'POST' }); window.location.href = '/login.html'; }

function announceToSR(m, assertive = false) {
    const a = els.aria();
    if (a) {
        a.setAttribute('aria-live', assertive ? 'assertive' : 'polite');
        a.textContent = '';
        setTimeout(() => { a.textContent = m; }, 50);
    }
}

function applyTheme(theme) {
    if (theme === 'dark') { document.body.classList.add('dark-mode'); localStorage.setItem('web-theme', 'dark'); } 
    else { document.body.classList.remove('dark-mode'); localStorage.setItem('web-theme', 'light'); }
}

function showContextMenu(e, anchorRow = null) {
    const row = anchorRow || (e?.target && e.target.closest ? e.target.closest('tr[data-hash]') : null);
    if (row && row.dataset && row.dataset.hash && !selectedHashes.has(row.dataset.hash)) {
        selectByHash(row.dataset.hash);
    }

    const btn = els.actionsBtn();
    if (btn) {
        btn.focus();
        const dd = bootstrap.Dropdown.getOrCreateInstance(btn);
        dd.show();
    }
}

function hideContextMenu() { 
    const btn = els.actionsBtn();
    if (btn) {
        const dd = bootstrap.Dropdown.getInstance(btn);
        if (dd) dd.hide();
    }
}

function toggleSelectAllBtn() {
    const isAllSelected = visibleTorrents.length > 0 && visibleTorrents.every(t => selectedHashes.has(t.hash));
    if (isAllSelected) {
        selectedHashes.clear();
        announceToSR("Selection cleared");
    } else {
        visibleTorrents.forEach(t => selectedHashes.add(t.hash));
        announceToSR(`Selected all ${visibleTorrents.length} torrents`);
    }
    updateSelectionVisuals();
    updateDetailsDebounced();
}

function copyToClipboard(type) {
    if (selectedHashes.size === 0) return;
    let text = "";
    if (type === 'hash') {
        text = Array.from(selectedHashes).join('\n');
    } else {
        text = Array.from(selectedHashes).map(h => `magnet:?xt=urn:btih:${h}`).join('\n');
    }
    navigator.clipboard.writeText(text).then(() => {
        announceToSR("Copied to clipboard");
    });
    hideContextMenu();
}

setInterval(() => refreshData(), 5000);
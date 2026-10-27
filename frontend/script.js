/* ============================================================
   FraudGuard — script.js
   ============================================================ */

let currentType = 'sms';
let currentView = 'analyzer';
let currentFilter = 'all';
let currentPage = 1;
const PAGE_SIZE = 20;

// ---------- Boot ----------
document.addEventListener('DOMContentLoaded', () => {
    checkApiHealth();
    refreshHistoryBadge();
});

async function checkApiHealth() {
    const el = document.getElementById('api-status');
    try {
        const res = await fetch('/health');
        el.textContent = res.ok ? 'API Online' : 'API Error';
    } catch {
        el.textContent = 'API Offline';
    }
}

// ---------- View switching ----------
function switchView(view) {
    currentView = view;
    document.querySelectorAll('.nav-item').forEach(i =>
        i.classList.toggle('active', i.dataset.view === view));
    document.getElementById('view-analyzer').classList.toggle('hidden', view !== 'analyzer');
    document.getElementById('view-history').classList.toggle('hidden', view !== 'history');
    if (view === 'history') {
        currentPage = 1;
        loadHistory();
    }
}

// ---------- Type toggle ----------
function setType(type) {
    currentType = type;
    document.querySelectorAll('.type-btn').forEach(b =>
        b.classList.toggle('active', b.dataset.type === type));
    document.getElementById('input-text').placeholder =
        type === 'sms' ? 'Paste your SMS message...' : 'Paste the email body...';
}

// ---------- Input helpers ----------
function updateCharCount() {
    document.getElementById('char-count').textContent =
        document.getElementById('input-text').value.length;
}

function handleKeydown(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        analyze();
    }
}

// ---------- Analyze ----------
async function analyze() {
    const text = document.getElementById('input-text').value.trim();
    if (!text) { alert('Please enter a message'); return; }

    const btn = document.getElementById('analyze-btn');
    const loading = document.getElementById('loading');
    const result = document.getElementById('result');

    btn.disabled = true;
    result.classList.add('hidden');
    loading.classList.remove('hidden');

    try {
        const res = await fetch('/predict', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text,
                message_type: currentType,
                source: 'manual'
            })
        });
        if (!res.ok) throw new Error('Prediction failed (' + res.status + ')');
        const data = await res.json();
        renderResult(data, text);
        refreshHistoryBadge();
    } catch (err) {
        alert('Error: ' + err.message);
    } finally {
        btn.disabled = false;
        loading.classList.add('hidden');
    }
}

// ---------- Render result ----------
function renderResult(data, originalText) {
    const result = document.getElementById('result');
    const isFraud = ['spam', 'phishing'].includes(data.label);
    result.className = 'result-card ' + (isFraud ? 'fraud' : 'safe');

    const verdictLabel = document.getElementById('verdict-label');
    verdictLabel.textContent = (isFraud ? '⚠️ ' : '✅ ') + data.label.toUpperCase();
    verdictLabel.className = 'verdict-label ' + (isFraud ? 'fraud' : 'safe');

    document.getElementById('verdict-sub').textContent = isFraud
        ? 'Strong fraud signals detected.'
        : 'No significant fraud patterns detected.';

    const pct = Math.round(data.confidence * 100);
    const gauge = document.getElementById('gauge-fill');
    gauge.classList.toggle('safe', !isFraud);
    gauge.style.strokeDashoffset = '126';
    requestAnimationFrame(() => {
        gauge.style.strokeDashoffset = String(126 * (1 - data.confidence));
    });

    animateNumber(document.getElementById('confidence-num'), pct);
    renderHighlighted(originalText, data.explanation);
    renderChips(data.explanation);

    result.classList.remove('hidden');
    result.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function animateNumber(el, target) {
    const t0 = performance.now();
    function tick(now) {
        const p = Math.min((now - t0) / 800, 1);
        el.textContent = Math.round(target * (1 - Math.pow(1 - p, 3)));
        if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
}

function renderHighlighted(text, explanation) {
    const weights = {};
    (explanation || []).forEach(i => {
        weights[i.token.toLowerCase()] = i.weight;
    });

    const el = document.getElementById('highlighted-text');
    el.innerHTML = text.split(/(\s+)/).map(part => {
        if (/^\s+$/.test(part) || part === '') return part;
        const clean = part.toLowerCase().replace(/[^a-z]/g, '');
        const match = Object.keys(weights).find(k => clean.includes(k) && k.length > 2);
        if (!match) return escapeHtml(part);
        const cls = weights[match] > 0 ? 'highlight-positive' : 'highlight-negative';
        return `<span class="${cls}">${escapeHtml(part)}</span>`;
    }).join('');
}

function renderChips(explanation) {
    const el = document.getElementById('token-chips');
    if (!explanation || explanation.length === 0) {
        el.innerHTML = '<span style="color:var(--text-faint)">No dominant terms.</span>';
        return;
    }
    el.innerHTML = explanation.map(i => {
        const cls = i.weight > 0 ? 'pos' : 'neg';
        const sign = i.weight > 0 ? '+' : '';
        return `<span class="chip ${cls}">${escapeHtml(i.token)} <span class="chip-weight">${sign}${i.weight}</span></span>`;
    }).join('');
}

function escapeHtml(s) {
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

/* ============================================================
   HISTORY — list view
   ============================================================ */

async function refreshHistoryBadge() {
    try {
        const res = await fetch('/history?page=1&page_size=1');
        const data = await res.json();
        const count = data.stats.total;
        const badge = document.getElementById('history-count');
        badge.textContent = count;
        badge.classList.toggle('hidden', count === 0);
    } catch {
        /* badge is optional */
    }
}

async function loadHistory() {
    try {
        const res = await fetch(
            `/history?page=${currentPage}&page_size=${PAGE_SIZE}&filter=${currentFilter}`
        );
        if (!res.ok) throw new Error('Failed to load history');
        const data = await res.json();
        renderHistory(data);
    } catch (err) {
        console.error(err);
    }
}

function renderHistory(data) {
    const tbody = document.getElementById('history-tbody');
    const table = document.getElementById('history-table');
    const empty = document.getElementById('history-empty');

    document.getElementById('stat-total').textContent = data.stats.total;
    document.getElementById('stat-fraud').textContent = data.stats.fraud;
    document.getElementById('stat-rate').textContent = data.stats.rate + '%';
    document.getElementById('stat-last').textContent = data.stats.last_created
        ? formatRelativeTime(new Date(data.stats.last_created))
        : '—';

    if (data.items.length === 0) {
        table.classList.add('hidden');
        empty.classList.remove('hidden');
        return;
    }
    empty.classList.add('hidden');
    table.classList.remove('hidden');

    tbody.innerHTML = data.items.map(item => {
        const isFraud = ['spam', 'phishing'].includes(item.label);
        const conf = Math.round(item.confidence * 100);

        // Top 3 fraud-pushing tokens for fraud, top 3 safety-pushing for safe
        const signals = (item.explanation || [])
            .filter(t => isFraud ? t.weight > 0 : t.weight < 0)
            .slice(0, 3);

        const signalChips = signals.length > 0
            ? signals.map(t => {
                const cls = t.weight > 0 ? 'signal-fraud' : 'signal-safe';
                const sign = t.weight > 0 ? '+' : '';
                return `<span class="signal-chip ${cls}">${escapeHtml(t.token)} <span class="signal-weight">${sign}${t.weight.toFixed(2)}</span></span>`;
            }).join('')
            : '<span class="signal-empty">—</span>';

        const typeLabel = item.message_type === 'sms' ? '📱 SMS' : '📧 Email';
        const sourceTag = item.source === 'gmail' ? ' · Gmail' : '';

        // Show subject when available (Gmail), otherwise message preview
        const preview = item.subject
            ? item.subject
            : item.original_text;

        return `
            <tr onclick='openDetail(${item.id})'>
                <td><span class="type-pill">${typeLabel}${sourceTag}</span></td>
                <td><div class="msg-cell">${escapeHtml(preview)}</div></td>
                <td><span class="verdict-pill ${isFraud ? 'fraud' : 'safe'}">${item.label}</span></td>
                <td>
                    <div class="conf-bar">
                        <span>${conf}%</span>
                        <div class="conf-fill"><div class="conf-fill-inner" style="width:${conf}%"></div></div>
                    </div>
                </td>
                <td><div class="signal-list">${signalChips}</div></td>
                <td class="time-cell">${formatRelativeTime(new Date(item.created_at))}</td>
                <td><button class="delete-btn" onclick='event.stopPropagation(); deleteEntry(${item.id})'>🗑</button></td>
            </tr>
        `;
    }).join('');
}

function setFilter(filter) {
    currentFilter = filter;
    currentPage = 1;
    document.querySelectorAll('.filter-tab').forEach(t =>
        t.classList.toggle('active', t.dataset.filter === filter));
    loadHistory();
}

async function deleteEntry(id) {
    if (!confirm('Delete this analysis?')) return;
    try {
        const res = await fetch(`/history/${id}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Delete failed');
        await loadHistory();
        await refreshHistoryBadge();
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

async function clearHistory() {
    if (!confirm('Clear ALL history? This cannot be undone.')) return;
    try {
        const res = await fetch('/history', { method: 'DELETE' });
        if (!res.ok) throw new Error('Clear failed');
        await loadHistory();
        await refreshHistoryBadge();
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

function exportHistory() {
    window.location.href = '/history/export';
}

/* ============================================================
   DETAIL MODAL — full reasoning
   ============================================================ */

async function openDetail(id) {
    try {
        const res = await fetch(`/history/${id}`);
        if (!res.ok) throw new Error('Record not found');
        const detail = await res.json();

        const isFraud = ['spam', 'phishing'].includes(detail.label);

        // Rank all terms by absolute weight
        const sorted = [...(detail.explanation || [])].sort(
            (a, b) => Math.abs(b.weight) - Math.abs(a.weight)
        );
        const maxW = sorted.length > 0
            ? Math.max(...sorted.map(t => Math.abs(t.weight)))
            : 1;

        const termsHtml = sorted.length > 0
            ? sorted.map(t => {
                const pct = Math.round((Math.abs(t.weight) / maxW) * 100);
                const cls = t.weight > 0 ? 'fraud' : 'safe';
                const sign = t.weight > 0 ? '+' : '';
                return `
                    <div class="detail-term-row">
                        <div class="detail-term-name">${escapeHtml(t.token)}</div>
                        <div class="detail-term-bar-wrap">
                            <div class="detail-term-bar ${cls}" style="width:${pct}%"></div>
                        </div>
                        <div class="detail-term-weight ${cls}">${sign}${t.weight.toFixed(3)}</div>
                    </div>
                `;
            }).join('')
            : '<div class="signal-empty">No influencing terms recorded.</div>';

        const highlightedMessage = highlightFullText(
            detail.original_text,
            detail.explanation
        );

        document.getElementById('modal-title').textContent = isFraud
            ? `⚠️ Why this is ${detail.label.toUpperCase()}`
            : `✅ Why this is ${detail.label.toUpperCase()}`;

        document.getElementById('modal-body').innerHTML = `
            ${detail.subject ? `
                <div class="modal-section">
                    <div class="modal-section-label">Subject</div>
                    <div class="modal-subject">${escapeHtml(detail.subject)}</div>
                </div>` : ''}

            ${detail.sender ? `
                <div class="modal-section">
                    <div class="modal-section-label">From</div>
                    <div class="modal-subject">${escapeHtml(detail.sender)}</div>
                </div>` : ''}

            <div class="modal-section">
                <div class="modal-section-label">
                    Original Message
                    <span class="label-hint">(red = pushed toward fraud, green = pushed toward safe)</span>
                </div>
                <div class="modal-message">${highlightedMessage}</div>
            </div>

            <div class="modal-section">
                <div class="modal-section-label">Confidence Breakdown</div>
                <div class="modal-meta">
                    <div class="meta-item">
                        <div class="meta-label">Verdict</div>
                        <div class="meta-value">
                            <span class="verdict-pill ${isFraud ? 'fraud' : 'safe'}">${detail.label}</span>
                        </div>
                    </div>
                    <div class="meta-item">
                        <div class="meta-label">Confidence</div>
                        <div class="meta-value">${Math.round(detail.confidence * 100)}%</div>
                    </div>
                    <div class="meta-item">
                        <div class="meta-label">Type</div>
                        <div class="meta-value">${detail.message_type === 'sms' ? '📱 SMS' : '📧 Email'}${detail.source === 'gmail' ? ' · Gmail' : ''}</div>
                    </div>
                    <div class="meta-item">
                        <div class="meta-label">Analyzed</div>
                        <div class="meta-value">${new Date(detail.created_at).toLocaleString()}</div>
                    </div>
                </div>
            </div>

            <div class="modal-section">
                <div class="modal-section-label">
                    Influencing Terms (ranked)
                    <span class="label-hint">length = magnitude of influence</span>
                </div>
                <div class="detail-terms">
                    ${termsHtml}
                </div>
            </div>
        `;

        document.getElementById('modal').classList.remove('hidden');
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

function highlightFullText(text, explanation) {
    if (!text) return '';
    const weights = {};
    (explanation || []).forEach(i => {
        weights[i.token.toLowerCase()] = i.weight;
    });

    return text.split(/(\s+)/).map(part => {
        if (/^\s+$/.test(part) || part === '') return part;
        const clean = part.toLowerCase().replace(/[^a-z]/g, '');
        const match = Object.keys(weights).find(k => clean.includes(k) && k.length > 2);
        if (!match) return escapeHtml(part);
        const cls = weights[match] > 0 ? 'highlight-positive' : 'highlight-negative';
        return `<span class="${cls}">${escapeHtml(part)}</span>`;
    }).join('');
}

function closeModal(event) {
    if (event && event.target !== event.currentTarget) return;
    document.getElementById('modal').classList.add('hidden');
}

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        document.getElementById('modal').classList.add('hidden');
    }
});

/* ============================================================
   HELPERS
   ============================================================ */

function formatRelativeTime(date) {
    const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
    if (seconds < 60) return 'Just now';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return minutes + 'm ago';
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return hours + 'h ago';
    const days = Math.floor(hours / 24);
    if (days < 7) return days + 'd ago';
    return date.toLocaleDateString();
}

function showModelInfo() {
    document.getElementById('modal-title').textContent = 'Model Information';
    document.getElementById('modal-body').innerHTML = `
        <div class="modal-section">
            <div class="modal-section-label">SMS Model</div>
            <div class="modal-message">
                <strong>Algorithm:</strong> Naive Bayes<br>
                <strong>Features:</strong> TF-IDF (3,000 features, 1–2 grams)<br>
                <strong>Accuracy:</strong> 97%<br>
                <strong>Spam F1:</strong> 0.87
            </div>
        </div>
        <div class="modal-section">
            <div class="modal-section-label">Email Model</div>
            <div class="modal-message">
                <strong>Algorithm:</strong> Logistic Regression (balanced)<br>
                <strong>Features:</strong> TF-IDF (5,000 features, 1–2 grams)<br>
                <strong>Accuracy:</strong> 98%<br>
                <strong>Phishing F1:</strong> 0.98
            </div>
        </div>
        <div class="modal-section">
            <div class="modal-section-label">Explainability</div>
            <div class="modal-message">
                <strong>Library:</strong> LIME (Local Interpretable Model-agnostic Explanations)<br>
                Shows the top contributing tokens for each prediction with signed weights.
            </div>
        </div>
        <div class="modal-section">
            <div class="modal-section-label">Storage</div>
            <div class="modal-message">
                <strong>Database:</strong> SQLite (data/fraud_history.db)<br>
                Every analysis is persisted with full metadata and LIME explanations.
            </div>
        </div>
    `;
    document.getElementById('modal').classList.remove('hidden');
}
// ── Stock Screener App JS ──
var STRATEGIES = JSON.parse(document.getElementById('strat-data').textContent);
var FIRST_STRAT = document.getElementById('strat-data').dataset.first;
var MODE = document.getElementById('strat-data').dataset.mode;

// ── Restore saved results from sessionStorage (after returning from detail page) ──
(function() {
    var saved = sessionStorage.getItem('stock_results');
    if (saved) {
        try {
            var data = JSON.parse(saved);
            if (data.mode === MODE && data.html) {
                var container = document.getElementById(MODE === 'screener' ? 'results' : 'mf-results');
                if (container) {
                    container.innerHTML = data.html;
                    bindResultClicks(container);
                }
            }
        } catch(e) {}
    }
})();

function saveResults(html) {
    try {
        sessionStorage.setItem('stock_results', JSON.stringify({mode: MODE, html: html}));
    } catch(e) {}
}

function bindResultClicks(container) {
    container.querySelectorAll('tbody tr').forEach(function(tr) {
        tr.style.cursor = 'pointer';
        tr.addEventListener('click', function() {
            var cells = this.querySelectorAll('td');
            if (cells.length >= 2) {
                openDetail(cells[0].textContent.trim(), cells[1].textContent.trim());
            }
        });
    });
}

// ── Screener Mode ──
if (MODE === 'screener') {
    document.getElementById('strategy').addEventListener('change', function(e) {
        showParams(e.target.value);
    });
    showParams(FIRST_STRAT);

    document.querySelectorAll('.param-item input[type=range]').forEach(function(sl) {
        sl.addEventListener('input', function() {
            var d = document.getElementById('param-val-' + sl.id.replace('param-', ''));
            if (d) d.textContent = sl.value;
        });
    });
}

function showParams(key) {
    document.querySelectorAll('.strategy-params').forEach(function(el) { el.style.display = 'none'; });
    var el = document.getElementById('strat-' + key);
    if (el) el.style.display = 'flex';
}

// ── Polling helper ──
async function pollTask(taskId, containerId, showFn, btn) {
    var maxRetries = 120; // ~4 mins
    var count = 0;
    while (count < maxRetries) {
        try {
            var resp = await fetch('/api/task/' + taskId);
            var data = await resp.json();
            if (data.status === 'done') {
                showFn(data);
                btn.disabled = false; btn.textContent = '开始筛选';
                return;
            }
            if (data.status === 'error') {
                document.getElementById(containerId).innerHTML = '<div class="error-msg">筛选失败<br><small>' + data.error + '</small></div>';
                btn.disabled = false; btn.textContent = '开始筛选';
                return;
            }
        } catch(e) {}
        await new Promise(function(r) { setTimeout(r, 2000); });
        count++;
    }
    document.getElementById(containerId).innerHTML = '<div class="error-msg">任务超时，请重试</div>';
    btn.disabled = false; btn.textContent = '开始筛选';
}

// ── Screening ──
async function doSearch() {
    var btn = document.querySelector('.btn-primary');
    var strategy = document.getElementById('strategy').value;
    var topn = parseInt(document.getElementById('topn').value) || 50;
    var params = {};
    var info = STRATEGIES[strategy];
    if (info && info.params) {
        Object.keys(info.params).forEach(function(k) {
            var el = document.getElementById('param-' + k);
            if (el) params[k] = parseFloat(el.value);
        });
    }
    btn.disabled = true; btn.textContent = '已提交...';
    document.getElementById('results').innerHTML = '<div class="card"><div class="loading-overlay"><div class="spinner"></div>正在扫描市场（约需30-60秒），请稍候...</div></div>';
    try {
        var body = JSON.stringify({strategy: strategy, params: params, top_n: topn, exclude_st: true});
        var resp = await fetch('/api/screen/technical', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: body});
        if (!resp.ok) { var txt = await resp.text(); throw new Error(txt); }
        var task = await resp.json();
        pollTask(task.task_id, 'results', showResults, btn);
    } catch(e) {
        document.getElementById('results').innerHTML = '<div class="error-msg">提交失败<br><small>' + e.message + '</small></div>';
        btn.disabled = false; btn.textContent = '开始筛选';
    }
}

function showResults(data) {
    var container = document.getElementById('results');
    if (!data.results || data.results.length === 0) {
        container.innerHTML = '<div class="card"><div class="empty-msg">没有找到符合条件的股票<br><small>试试调整参数或换个策略</small></div></div>';
        return;
    }
    var h = '<div class="card"><div class="stats-bar"><span>扫描 <strong>' + data.total_scanned + '</strong> 支</span><span>匹配 <strong>' + data.total_matched + '</strong> 支</span><span>耗时 <strong>' + (data.elapsed_ms / 1000).toFixed(1) + 's</strong></span></div>';
    h += '<div class="table-wrapper"><table class="result-table" id="result-table"><thead><tr><th>代码</th><th>名称</th><th>最新价</th><th>涨跌幅</th><th>评分</th><th>信号</th></tr></thead><tbody></tbody></table></div></div>';
    container.innerHTML = h;
    var tbody = document.getElementById('result-table').querySelector('tbody');
    data.results.forEach(function(r) {
        var tr = document.createElement('tr');
        tr.style.cursor = 'pointer';
        tr.addEventListener('click', function() { openDetail(r.code, r.name, MODE); });
        var chg = r.change_pct != null ? (r.change_pct >= 0 ? '+' : '') + r.change_pct.toFixed(2) + '%' : '-';
        var chgCls = r.change_pct != null ? (r.change_pct >= 0 ? 'price-up' : 'price-down') : '';
        var badge = r.signal_strength === 'strong' ? '<span class="badge badge-strong">强烈推荐</span>' : r.signal_strength === 'moderate' ? '<span class="badge badge-moderate">可以考虑</span>' : '<span class="badge badge-weak">信号较弱</span>';
        var scoreHtml = '<div class="score-cell"><div class="score-bar" style="width:' + Math.max(6, r.score * 0.48) + 'px"></div><span class="score-num">' + r.score.toFixed(0) + '</span></div>';
        tr.innerHTML = '<td>' + r.code + '</td><td>' + r.name + '</td><td>' + (r.price != null ? r.price.toFixed(2) : '-') + '</td><td class="' + chgCls + '">' + chg + '</td><td>' + scoreHtml + '</td><td>' + badge + '</td>';
        tbody.appendChild(tr);
    });
    saveResults(container.innerHTML);
}

// ── Multifactor Mode ──
if (MODE === 'multifactor') {
    var mfSliders = ['wm', 'wv', 'ww', 'wr'];
    function updateMfSum() {
        var sum = 0;
        mfSliders.forEach(function(k) { sum += parseFloat(document.getElementById('mf-' + k).value); });
        document.getElementById('mf-sum').textContent = '权重合计: ' + (sum * 100).toFixed(0) + '%';
        document.getElementById('mf-sum').style.color = Math.abs(sum - 1) > 0.08 ? '#e03a3a' : '#6b7280';
        mfSliders.forEach(function(k) { document.getElementById('mf-val-' + k).textContent = (parseFloat(document.getElementById('mf-' + k).value) * 100).toFixed(0) + '%'; });
    }
    mfSliders.forEach(function(k) { document.getElementById('mf-' + k).addEventListener('input', updateMfSum); });
}

async function doMFSearch() {
    var btn = document.querySelector('.btn-primary');
    var body = {top_n: parseInt(document.getElementById('mf-topn').value), exclude_st: true};
    body.weight_momentum = parseFloat(document.getElementById('mf-wm').value);
    body.weight_volatility = parseFloat(document.getElementById('mf-wv').value);
    body.weight_volume = parseFloat(document.getElementById('mf-ww').value);
    body.weight_reversion = parseFloat(document.getElementById('mf-wr').value);
    btn.disabled = true; btn.textContent = '已提交...';
    document.getElementById('mf-results').innerHTML = '<div class="card"><div class="loading-overlay"><div class="spinner"></div>正在多因子评分（约需20-40秒），请稍候...</div></div>';
    try {
        var resp = await fetch('/api/screen/multifactor', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
        if (!resp.ok) throw new Error(await resp.text());
        var task = await resp.json();
        pollTask(task.task_id, 'mf-results', showMFResults, btn);
    } catch(e) {
        document.getElementById('mf-results').innerHTML = '<div class="error-msg">提交失败: ' + e.message + '</div>';
        btn.disabled = false; btn.textContent = '开始筛选';
    }
}

function showMFResults(data) {
    var container = document.getElementById('mf-results');
    if (!data.results || data.results.length === 0) {
        container.innerHTML = '<div class="card"><div class="empty-msg">没有符合条件的股票</div></div>';
        return;
    }
    var h = '<div class="card"><div class="stats-bar"><span>扫描 <strong>' + data.total_scanned + '</strong> 支</span><span>耗时 <strong>' + (data.elapsed_ms / 1000).toFixed(1) + 's</strong></span></div><div class="table-wrapper"><table class="result-table" id="mf-table"><thead><tr><th>代码</th><th>名称</th><th>最新价</th><th>涨跌幅</th><th>综合评分</th><th>推荐</th></tr></thead><tbody></tbody></table></div></div>';
    container.innerHTML = h;
    var tbody = document.getElementById('mf-table').querySelector('tbody');
    data.results.forEach(function(r) {
        var tr = document.createElement('tr');
        tr.style.cursor = 'pointer';
        tr.addEventListener('click', function() { openDetail(r.code, r.name, MODE); });
        var chg = r.change_pct != null ? (r.change_pct >= 0 ? '+' : '') + r.change_pct.toFixed(2) + '%' : '-';
        var chgCls = r.change_pct != null ? (r.change_pct >= 0 ? 'price-up' : 'price-down') : '';
        var badge = r.signal_strength === 'strong' ? '<span class="badge badge-strong">强烈推荐</span>' : r.signal_strength === 'moderate' ? '<span class="badge badge-moderate">可以考虑</span>' : '<span class="badge badge-weak">信号较弱</span>';
        var scoreHtml = '<div class="score-cell"><div class="score-bar" style="width:' + Math.max(6, r.score * 0.48) + 'px"></div><span class="score-num">' + r.score.toFixed(0) + '</span></div>';
        tr.innerHTML = '<td>' + r.code + '</td><td>' + r.name + '</td><td>' + (r.price != null ? r.price.toFixed(2) : '-') + '</td><td class="' + chgCls + '">' + chg + '</td><td>' + scoreHtml + '</td><td>' + badge + '</td>';
        tbody.appendChild(tr);
    });
    saveResults(container.innerHTML);
}

// ── Modal Detail ──
async function openDetail(code, name, source) {
    source = source || MODE || 'screener';
    var modal = document.getElementById('detail-modal');
    var body = document.getElementById('modal-body');
    if (!modal || !body) return;
    modal.style.display = 'flex';
    body.innerHTML = '<div class="loading-overlay"><div class="spinner"></div>加载 ' + code + ' ' + name + '...</div>';
    try {
        var resp = await fetch('/api/stocks/' + code + '/indicators');
        if (!resp.ok) throw new Error(await resp.text());
        var d = await resp.json();
        var detailUrl = '/detail/' + code + '?from=' + source;
        var h = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px"><div><span style="font-size:1.2rem;font-weight:700">' + name + '</span><span style="color:#6b7280;margin-left:8px;font-size:0.85rem">' + code + '</span></div><a href="' + detailUrl + '" class="btn btn-primary" style="text-decoration:none">查看K线图</a></div>';
        h += '<div class="indicator-grid">';
        h += indCard('RSI(6)', d.rsi, function(v) { return v != null ? v.toFixed(1) : '-'; });
        h += indCard('MA5', d.ma5, function(v) { return v != null ? Number(v).toFixed(2) : '-'; });
        h += indCard('MA20', d.ma20, function(v) { return v != null ? Number(v).toFixed(2) : '-'; });
        h += indCard('MA60', d.ma60, function(v) { return v != null ? Number(v).toFixed(2) : '-'; });
        h += indCard('偏离MA20', d.deviation_ma20, function(v) { return v != null ? (v >= 0 ? '+' : '') + (v * 100).toFixed(2) + '%' : '-'; }, 0);
        h += indCard('量比', d.volume_ratio, function(v) { return v != null ? Number(v).toFixed(2) : '-'; });
        h += indCard('5日涨跌', d.change_5d, function(v) { return v != null ? (v >= 0 ? '+' : '') + (v * 100).toFixed(2) + '%' : '-'; });
        h += indCard('20日涨跌', d.change_20d, function(v) { return v != null ? (v >= 0 ? '+' : '') + (v * 100).toFixed(2) + '%' : '-'; });
        h += indCard('年化波动', d.volatility_20d, function(v) { return v != null ? (v * 100).toFixed(2) + '%' : '-'; });
        h += '</div>';
        body.innerHTML = h;
    } catch(e) {
        body.innerHTML = '<div class="error-msg">加载失败: ' + e.message + '</div>';
    }
}

function indCard(label, value, fmt, threshold) {
    var dv = value != null ? fmt(value) : '-';
    var cc = (threshold != null && value != null) ? (value >= threshold ? 'price-up' : 'price-down') : '';
    return '<div class="indicator-card"><div class="ind-label">' + label + '</div><div class="ind-value ' + cc + '">' + dv + '</div></div>';
}

function closeDetail() {
    var modal = document.getElementById('detail-modal');
    if (modal) modal.style.display = 'none';
}

document.addEventListener('keydown', function(e) { if (e.key === 'Escape') closeDetail(); });

const { apiGet, apiPost, AppState, formatPrice, formatPct, formatNum, pctClass, badgeHtml, scoreBarHtml } = window;

export async function render(container) {
    if (!AppState.strategies || Object.keys(AppState.strategies).length === 0) {
        try {
            AppState.strategies = await apiGet('/strategies');
        } catch (e) {
            container.innerHTML = `<div class="error-msg">加载策略失败: ${e.message}</div>`;
            return;
        }
    }

    const strategies = AppState.strategies;
    const strategyKeys = Object.keys(strategies);
    const currentStrategy = document.getElementById('tech-strategy')?.value || strategyKeys[0];

    container.innerHTML = `
        <div class="card">
            <div class="filters">
                <div class="filter-group">
                    <label>策略</label>
                    <select id="tech-strategy">
                        ${strategyKeys.map(k =>
                            `<option value="${k}">${strategies[k].label}</option>`
                        ).join('')}
                    </select>
                </div>
                <div id="tech-params"></div>
                <div class="filter-group">
                    <label>返回数量</label>
                    <select id="tech-topn">
                        <option value="20">20</option>
                        <option value="50" selected>50</option>
                        <option value="100">100</option>
                    </select>
                </div>
                <div class="filter-group">
                    <label>&nbsp;</label>
                    <button class="btn btn-primary" id="tech-run">开始筛选</button>
                </div>
            </div>
        </div>
        <div id="tech-results"></div>
    `;

    renderParams(strategies, currentStrategy);
    document.getElementById('tech-strategy').addEventListener('change', (e) => {
        renderParams(strategies, e.target.value);
    });
    document.getElementById('tech-run').addEventListener('click', runScreening);
}

function renderParams(strategies, key) {
    const params = strategies[key].params;
    const container = document.getElementById('tech-params');
    if (!params || Object.keys(params).length === 0) {
        container.innerHTML = '';
        return;
    }
    container.innerHTML = Object.entries(params).map(([k, v]) => {
        let min, max, step;
        if (k === 'ma_period') { min = 5; max = 60; step = 1; }
        else if (k === 'band') { min = 0.01; max = 0.10; step = 0.005; }
        else if (k === 'period') { min = 4; max = 14; step = 1; }
        else if (k === 'vol_ma') { min = 10; max = 60; step = 1; }
        else if (k === 'price_lb') { min = 3; max = 20; step = 1; }
        else if (k === 'lookback') { min = 2; max = 20; step = 1; }
        else { min = 1; max = 100; step = 1; }
        return `
            <div class="filter-group">
                <label>${k}</label>
                <div class="param-slider">
                    <input type="range" id="param-${k}" min="${min}" max="${max}" step="${step}" value="${v}">
                    <span class="param-value" id="param-val-${k}">${v}</span>
                </div>
            </div>`;
    }).join('');
    Object.entries(params).forEach(([k]) => {
        const slider = document.getElementById('param-' + k);
        const display = document.getElementById('param-val-' + k);
        if (slider && display) {
            slider.addEventListener('input', () => { display.textContent = slider.value; });
        }
    });
}

async function runScreening() {
    const btn = document.getElementById('tech-run');
    const resultsDiv = document.getElementById('tech-results');
    const strategy = document.getElementById('tech-strategy').value;
    const topN = parseInt(document.getElementById('tech-topn').value);
    const strategyInfo = AppState.strategies[strategy];

    const params = {};
    if (strategyInfo.params) {
        Object.keys(strategyInfo.params).forEach(k => {
            const el = document.getElementById('param-' + k);
            if (el) params[k] = parseFloat(el.value);
        });
    }

    btn.disabled = true;
    btn.textContent = '筛选中...';
    resultsDiv.innerHTML = '<div class="loading-overlay"><div class="spinner"></div>正在扫描全市场股票，请稍候...</div>';

    try {
        const data = await apiPost('/screen/technical', {
            strategy, params, top_n: topN, exclude_st: true, min_market_cap: 0,
        });
        AppState.technicalResults = data.results;
        renderResults(resultsDiv, data);
    } catch (e) {
        resultsDiv.innerHTML = `<div class="error-msg">筛选失败: ${e.message}</div>`;
    } finally {
        btn.disabled = false;
        btn.textContent = '开始筛选';
    }
}

function renderResults(container, data) {
    if (!data.results || data.results.length === 0) {
        container.innerHTML = '<div class="empty-msg">没有找到符合条件的股票</div>';
        return;
    }

    // Store results for sorting
    container._results = data.results;
    container._sortKey = 'score';
    container._sortDir = -1;

    const headers = [
        { key: 'code', label: '代码' },
        { key: 'name', label: '名称' },
        { key: 'price', label: '最新价', fmt: formatPrice },
        { key: 'change_pct', label: '涨跌幅', fmt: formatPct, cls: pctClass },
        { key: 'score', label: '得分' },
        { key: 'indicator_value', label: '指标值' },
        { key: 'pe', label: 'PE', fmt: formatNum },
        { key: 'pb', label: 'PB', fmt: formatNum },
        { key: 'signal_strength', label: '信号' },
    ];

    function buildTable(results) {
        return `
        <div class="card">
            <div class="stats-bar">
                <span>扫描 <strong>${data.total_scanned}</strong> 支</span>
                <span>匹配 <strong>${data.total_matched}</strong> 支</span>
                <span>耗时 <strong>${(data.elapsed_ms / 1000).toFixed(1)}s</strong></span>
            </div>
            <div style="overflow-x:auto;">
            <table class="result-table">
                <thead>
                    <tr>
                        ${headers.map(h => {
                            const arrow = container._sortKey === h.key ? (container._sortDir > 0 ? ' ▲' : ' ▼') : '';
                            return `<th data-sort="${h.key}">${h.label}${arrow}</th>`;
                        }).join('')}
                    </tr>
                </thead>
                <tbody>
                    ${results.map((r, i) => `
                        <tr data-code="${r.code}">
                            ${headers.map(h => {
                                let val = r[h.key];
                                if (h.key === 'score') val = scoreBarHtml(val);
                                else if (h.key === 'signal_strength') val = badgeHtml(val);
                                else if (h.fmt) val = h.fmt(val);
                                if (val == null) val = '-';
                                const cls = h.cls ? h.cls(r[h.key]) : '';
                                const label = h.label;
                                return `<td class="${cls}" data-label="${label}">${val}</td>`;
                            }).join('')}
                        </tr>`).join('')}
                </tbody>
            </table>
            </div>
        </div>`;
    }

    container.innerHTML = buildTable(container._results);

    // Click row -> detail
    container.querySelectorAll('tbody tr').forEach(tr => {
        tr.addEventListener('click', () => {
            const code = tr.dataset.code;
            if (code) location.hash = 'detail/' + code;
        });
    });

    // Click header -> sort
    container.querySelectorAll('th[data-sort]').forEach(th => {
        th.addEventListener('click', () => {
            const key = th.dataset.sort;
            if (container._sortKey === key) {
                container._sortDir *= -1;
            } else {
                container._sortKey = key;
                container._sortDir = key === 'score' ? -1 : 1;
            }
            const sorted = [...container._results].sort((a, b) => {
                const va = a[key] ?? 0, vb = b[key] ?? 0;
                if (typeof va === 'string') return container._sortDir * va.localeCompare(vb);
                return container._sortDir * (va - vb);
            });
            container.innerHTML = buildTable(sorted);
            // Re-bind events
            container.querySelectorAll('tbody tr').forEach(tr => {
                tr.addEventListener('click', () => {
                    const code = tr.dataset.code;
                    if (code) location.hash = 'detail/' + code;
                });
            });
            container.querySelectorAll('th[data-sort]').forEach(h => {
                h.addEventListener('click', () => th.click());
            });
        });
    });
}

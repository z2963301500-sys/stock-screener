const { apiGet, apiPost, AppState, formatPrice, formatPct, formatNum, pctClass, badgeHtml, scoreBarHtml } = window;

export async function render(container) {
    const defaultWeights = { weight_momentum: 0.30, weight_volatility: 0.25, weight_volume: 0.25, weight_reversion: 0.20 };

    container.innerHTML = `
        <div class="card">
            <div class="weight-grid">
                ${[
                    { key: 'weight_momentum', label: '20日动量（高分高）' },
                    { key: 'weight_volatility', label: '低波动（低分高）' },
                    { key: 'weight_volume', label: '量能活跃（高分高）' },
                    { key: 'weight_reversion', label: '均值回归（高分高）' },
                ].map(({ key, label }) => `
                    <div class="weight-item">
                        <div class="weight-header">
                            <label>${label}</label>
                            <span class="param-value" id="mf-val-${key}">${defaultWeights[key].toFixed(2)}</span>
                        </div>
                        <input type="range" id="mf-${key}" min="0" max="1" step="0.05" value="${defaultWeights[key]}">
                    </div>
                `).join('')}
            </div>
            <div style="margin-top: 16px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">
                <div class="filter-group">
                    <label>返回数量</label>
                    <select id="mf-topn">
                        <option value="20">20</option>
                        <option value="50" selected>50</option>
                        <option value="100">100</option>
                    </select>
                </div>
                <div class="filter-group">
                    <label>&nbsp;</label>
                    <button class="btn btn-primary" id="mf-run">开始筛选</button>
                </div>
                <span style="font-size:0.75rem;color:var(--text-secondary)" id="mf-sum-hint">权重总和: 1.00</span>
            </div>
        </div>
        <div id="mf-results"></div>
    `;

    // Weight sliders
    const weightKeys = Object.keys(defaultWeights);
    weightKeys.forEach(k => {
        const slider = document.getElementById('mf-' + k);
        const display = document.getElementById('mf-val-' + k);
        slider.addEventListener('input', () => {
            display.textContent = parseFloat(slider.value).toFixed(2);
            updateWeightSum();
        });
    });

    document.getElementById('mf-run').addEventListener('click', runMultifactor);
}

function updateWeightSum() {
    const keys = ['weight_momentum', 'weight_volatility', 'weight_volume', 'weight_reversion'];
    let sum = 0;
    keys.forEach(k => {
        const el = document.getElementById('mf-' + k);
        if (el) sum += parseFloat(el.value);
    });
    const hint = document.getElementById('mf-sum-hint');
    hint.textContent = '权重总和: ' + sum.toFixed(2);
    hint.style.color = Math.abs(sum - 1.0) > 0.05 ? 'var(--up)' : 'var(--text-secondary)';
}

async function runMultifactor() {
    const btn = document.getElementById('mf-run');
    const resultsDiv = document.getElementById('mf-results');
    const keys = ['weight_momentum', 'weight_volatility', 'weight_volume', 'weight_reversion'];

    const body = { top_n: parseInt(document.getElementById('mf-topn').value), exclude_st: true };
    keys.forEach(k => { body[k] = parseFloat(document.getElementById('mf-' + k).value); });

    btn.disabled = true;
    btn.textContent = '筛选中...';
    resultsDiv.innerHTML = '<div class="loading-overlay"><div class="spinner"></div>正在计算多因子得分...</div>';

    try {
        const data = await apiPost('/screen/multifactor', body);
        AppState.multifactorResults = data.results;
        renderMFResults(resultsDiv, data);
    } catch (e) {
        resultsDiv.innerHTML = `<div class="error-msg">筛选失败: ${e.message}</div>`;
    } finally {
        btn.disabled = false;
        btn.textContent = '开始筛选';
    }
}

function renderMFResults(container, data) {
    if (!data.results || data.results.length === 0) {
        container.innerHTML = '<div class="empty-msg">没有找到符合条件的股票</div>';
        return;
    }

    container._results = data.results;
    container._sortKey = 'score';
    container._sortDir = -1;

    const headers = [
        { key: 'code', label: '代码' },
        { key: 'name', label: '名称' },
        { key: 'price', label: '最新价', fmt: formatPrice },
        { key: 'change_pct', label: '涨跌幅', fmt: formatPct, cls: pctClass },
        { key: 'score', label: '综合得分' },
        { key: 'pe', label: 'PE', fmt: formatNum },
        { key: 'pb', label: 'PB', fmt: formatNum },
        { key: 'signal_strength', label: '评级' },
    ];

    function buildTable(results) {
        return `
        <div class="card">
            <div class="stats-bar">
                <span>扫描 <strong>${data.total_scanned}</strong> 支</span>
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
                                return `<td class="${cls}" data-label="${h.label}">${val}</td>`;
                            }).join('')}
                        </tr>`).join('')}
                </tbody>
            </table>
            </div>
        </div>`;
    }

    container.innerHTML = buildTable(container._results);

    container.querySelectorAll('tbody tr').forEach(tr => {
        tr.addEventListener('click', () => {
            const code = tr.dataset.code;
            if (code) location.hash = 'detail/' + code;
        });
    });

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
            container.querySelectorAll('tbody tr').forEach(tr => {
                tr.addEventListener('click', () => {
                    const code = tr.dataset.code;
                    if (code) location.hash = 'detail/' + code;
                });
            });
        });
    });
}

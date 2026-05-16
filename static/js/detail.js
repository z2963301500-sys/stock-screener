const { apiGet, AppState, formatPrice, formatPct } = window;

export async function render(container, code) {
    container.innerHTML = `
        <div class="card">
            <div class="loading-overlay"><div class="spinner"></div>加载 ${code} 数据中...</div>
        </div>
    `;

    try {
        const [history, indicators] = await Promise.all([
            apiGet(`/stocks/${code}/history?days=120`),
            apiGet(`/stocks/${code}/indicators`),
        ]);

        AppState.currentStock = { code, history, indicators };
        renderDetail(container, history, indicators);
    } catch (e) {
        container.innerHTML = `
            <div class="error-msg">
                加载失败: ${e.message}
                <br><a href="#screener" style="color:var(--primary)">返回筛选</a>
            </div>`;
    }
}

function renderDetail(container, history, indicators) {
    const lastPrice = history.candles[history.candles.length - 1]?.close ?? 0;
    const prevPrice = history.candles[history.candles.length - 2]?.close ?? lastPrice;
    const change = lastPrice - prevPrice;
    const changePct = prevPrice ? (change / prevPrice * 100) : 0;

    container.innerHTML = `
        <div class="detail-header">
            <a class="back-link" onclick="history.back()">← 返回</a>
            <span class="stock-name">${history.name}</span>
            <span class="stock-code">${history.code}</span>
            <span style="font-size:1.15rem;font-weight:700" class="${change >= 0 ? 'price-up' : 'price-down'}">
                ${formatPrice(lastPrice)}
            </span>
            <span class="${change >= 0 ? 'price-up' : 'price-down'}" style="font-size:0.9rem">
                ${change >= 0 ? '+' : ''}${change.toFixed(2)} (${changePct >= 0 ? '+' : ''}${changePct.toFixed(2)}%)
            </span>
        </div>

        <div class="card">
            <div class="chart-container" id="main-chart"></div>
            <div class="chart-sub" id="volume-chart"></div>
            <div class="chart-sub" id="rsi-chart"></div>
        </div>

        <div class="card">
            <div class="indicator-grid">
                ${buildIndicatorCard('RSI (6)', indicators.rsi, val => val != null ? val.toFixed(1) : '-')}
                ${buildIndicatorCard('MA5', indicators.ma5, formatPrice)}
                ${buildIndicatorCard('MA20', indicators.ma20, formatPrice)}
                ${buildIndicatorCard('MA60', indicators.ma60, formatPrice)}
                ${buildIndicatorCard('MA20偏离', indicators.deviation_ma20, formatPct, 0)}
                ${buildIndicatorCard('量比', indicators.volume_ratio, formatNum)}
                ${buildIndicatorCard('5日涨幅', indicators.change_5d, formatPct)}
                ${buildIndicatorCard('20日涨幅', indicators.change_20d, formatPct)}
                ${buildIndicatorCard('20日波动率', indicators.volatility_20d, formatPct)}
            </div>
        </div>
    `;

    // Render charts asynchronously (library loads on demand)
    requestAnimationFrame(async () => {
        const mainEl = document.getElementById('main-chart');
        const volEl = document.getElementById('volume-chart');
        const rsiEl = document.getElementById('rsi-chart');

        try {
            const chartsModule = await import('./charts.js');
            const available = await chartsModule.chartsAvailable();

            if (available) {
                if (mainEl) await chartsModule.createStockChart(mainEl, history.candles, indicators);
                if (volEl) await chartsModule.createVolumeChart(volEl, history.candles);
                if (rsiEl) await chartsModule.createRSIChart(rsiEl, history.candles, 6);
            } else {
                if (mainEl) mainEl.innerHTML = '<div class="empty-msg">K线图加载失败（CDN 不可用）<br><small>请检查网络连接</small></div>';
                if (volEl) volEl.style.display = 'none';
                if (rsiEl) rsiEl.style.display = 'none';
            }
        } catch (e) {
            console.warn('Chart render error:', e);
            if (mainEl) mainEl.innerHTML = '<div class="empty-msg">K线图加载失败</div>';
        }
    });
}

function buildIndicatorCard(label, value, fmt, threshold) {
    const displayVal = value != null ? fmt(value) : '-';
    let colorClass = '';
    if (threshold != null && value != null) {
        colorClass = value >= threshold ? 'price-up' : 'price-down';
    }
    return `
        <div class="indicator-card">
            <div class="ind-label">${label}</div>
            <div class="ind-value ${colorClass}">${displayVal}</div>
        </div>
    `;
}

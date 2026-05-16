let _LC = null;
let _loadPromise = null;

async function loadLC() {
    if (_LC) return _LC;
    if (_loadPromise) return _loadPromise;
    _loadPromise = (async () => {
        try {
            // Try multiple CDN sources in case one is blocked
            const urls = [
                'https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js',
                'https://cdn.jsdelivr.net/npm/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js',
            ];
            for (const url of urls) {
                try {
                    await loadScript(url);
                    if (typeof LightweightCharts !== 'undefined') {
                        _LC = LightweightCharts;
                        return _LC;
                    }
                } catch (e) {
                    continue;
                }
            }
            throw new Error('Charts library not available');
        } catch (e) {
            console.warn('Failed to load charts:', e);
            return null;
        }
    })();
    return _loadPromise;
}

function loadScript(url) {
    return new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = url;
        script.onload = resolve;
        script.onerror = () => reject(new Error(`Failed to load ${url}`));
        script.timeout = 15000;
        document.head.appendChild(script);
        setTimeout(() => reject(new Error(`Timeout: ${url}`)), 15000);
    });
}

export async function chartsAvailable() {
    const lc = await loadLC();
    return lc !== null;
}

export async function createStockChart(container, candles, indicators) {
    const LC = await loadLC();
    if (!LC) return null;

    const chart = LC.createChart(container, {
        layout: { background: { color: '#ffffff' }, textColor: '#333' },
        grid: { vertLines: { color: '#f0f0f0' }, horzLines: { color: '#f0f0f0' } },
        crosshair: { mode: 1 },
        timeScale: { timeVisible: true, borderColor: '#dfe6e9' },
        rightPriceScale: { borderColor: '#dfe6e9' },
    });

    const candleSeries = chart.addCandlestickSeries({
        upColor: '#e03a3a', downColor: '#1aad19',
        borderUpColor: '#e03a3a', borderDownColor: '#1aad19',
        wickUpColor: '#e03a3a', wickDownColor: '#1aad19',
    });

    candleSeries.setData(candles.map(c => ({
        time: c.date, open: c.open, high: c.high, low: c.low, close: c.close,
    })));

    const maColors = { ma5: '#ff9800', ma20: '#e040fb', ma60: '#00bcd4' };
    Object.entries(maColors).forEach(([key, color]) => {
        if (indicators[key] != null) {
            const maData = calcMA(candles, parseInt(key.replace('ma', '')));
            if (maData.length > 0) {
                const maSeries = chart.addLineSeries({ color, lineWidth: 1, priceLineVisible: false });
                maSeries.setData(maData);
            }
        }
    });

    return chart;
}

function calcMA(candles, period) {
    const result = [];
    for (let i = period - 1; i < candles.length; i++) {
        let sum = 0;
        for (let j = i - period + 1; j <= i; j++) sum += candles[j].close;
        result.push({ time: candles[i].date, value: sum / period });
    }
    return result;
}

export async function createVolumeChart(container, candles) {
    const LC = await loadLC();
    if (!LC) return null;

    const chart = LC.createChart(container, {
        layout: { background: { color: '#ffffff' }, textColor: '#333' },
        grid: { vertLines: { color: '#f0f0f0' }, horzLines: { color: '#f0f0f0' } },
        crosshair: { mode: 0 },
        timeScale: { timeVisible: false },
        rightPriceScale: { borderColor: '#dfe6e9' },
    });

    const volumeSeries = chart.addHistogramSeries({
        color: '#26a69a', priceFormat: { type: 'volume' }, priceScaleId: '',
    });

    volumeSeries.setData(candles.map(c => ({
        time: c.date, value: c.volume,
        color: c.close >= c.open ? 'rgba(224,58,58,0.5)' : 'rgba(26,173,25,0.5)',
    })));

    return chart;
}

export async function createRSIChart(container, candles, period = 6) {
    const LC = await loadLC();
    if (!LC) return null;

    const chart = LC.createChart(container, {
        layout: { background: { color: '#ffffff' }, textColor: '#333' },
        grid: { vertLines: { color: '#f0f0f0' }, horzLines: { color: '#f0f0f0' } },
        crosshair: { mode: 0 },
        timeScale: { timeVisible: false },
        rightPriceScale: { borderColor: '#dfe6e9' },
    });

    const rsiData = calcRSI(candles, period);
    const rsiSeries = chart.addLineSeries({ color: '#7b1fa2', lineWidth: 1.5 });
    rsiSeries.setData(rsiData);

    [30, 70].forEach(level => {
        const ls = chart.addLineSeries({
            color: level === 30 ? '#1aad19' : '#e03a3a',
            lineWidth: 1, lineStyle: 2, priceLineVisible: false,
        });
        ls.setData([
            { time: candles[0].date, value: level },
            { time: candles[candles.length - 1].date, value: level },
        ]);
    });

    return chart;
}

function calcRSI(candles, period) {
    if (candles.length < period + 1) return [];
    const result = [];
    let gains = 0, losses = 0;
    for (let i = 1; i <= period; i++) {
        const diff = candles[i].close - candles[i - 1].close;
        if (diff > 0) gains += diff; else losses -= diff;
    }
    let avgGain = gains / period, avgLoss = losses / period;
    for (let i = period; i < candles.length; i++) {
        const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
        result.push({ time: candles[i].date, value: 100 - (100 / (1 + rs)) });
        const diff = candles[i].close - candles[i - 1].close;
        avgGain = (avgGain * (period - 1) + (diff > 0 ? diff : 0)) / period;
        avgLoss = (avgLoss * (period - 1) + (diff < 0 ? -diff : 0)) / period;
    }
    return result;
}

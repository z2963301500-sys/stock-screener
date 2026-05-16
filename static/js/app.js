const API_BASE = '/api';

const AppState = {
    technicalResults: [],
    multifactorResults: [],
    strategies: {},
    loading: false,
};

// Attach to window so dynamically-imported page modules can access them
window.API_BASE = API_BASE;
window.AppState = AppState;

window.apiGet = async function(path) {
    const res = await fetch(API_BASE + path);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
};

window.apiPost = async function(path, body) {
    const res = await fetch(API_BASE + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
};

window.formatPrice = function(v) {
    if (v == null) return '-';
    return Number(v).toFixed(2);
};

window.formatPct = function(v) {
    if (v == null) return '-';
    return (Number(v) > 0 ? '+' : '') + Number(v).toFixed(2) + '%';
};

window.formatNum = function(v) {
    if (v == null) return '-';
    const n = Number(v);
    if (n >= 1e12) return (n / 1e12).toFixed(2) + '万亿';
    if (n >= 1e8) return (n / 1e8).toFixed(2) + '亿';
    if (n >= 1e4) return (n / 1e4).toFixed(2) + '万';
    return n.toFixed(0);
};

window.pctClass = function(v) {
    if (v == null) return '';
    return Number(v) >= 0 ? 'price-up' : 'price-down';
};

window.badgeHtml = function(strength) {
    const map = { strong: '强烈', moderate: '中等', weak: '弱' };
    return `<span class="badge badge-${strength}">${map[strength] || strength}</span>`;
};

window.scoreBarHtml = function(score) {
    const w = Math.max(10, Math.min(100, score));
    return `<span class="score-bar" style="width:${w}px"></span>${Number(score).toFixed(0)}`;
};

function showError(content, msg) {
    content.innerHTML = `<div class="error-msg">${msg}<br><small><a href="#screener">点此重试</a></small></div>`;
}

async function loadPage(content, moduleName, renderArgs) {
    try {
        const m = await import(moduleName);
        await m.render(...renderArgs);
    } catch (e) {
        console.error('Page load error:', moduleName, e);
        showError(content, `页面加载失败: ${e.message || '未知错误'}`);
    }
}

function handleRoute() {
    const hash = location.hash.slice(1) || 'screener';
    const content = document.getElementById('app-content');
    const navLinks = document.querySelectorAll('.nav-link');

    navLinks.forEach(a => {
        a.classList.toggle('active', a.getAttribute('href') === '#' + hash.split('/')[0]);
    });

    // Show brief loading while switching
    content.innerHTML = '<div style="text-align:center;padding:40px"><div class="spinner"></div></div>';

    if (hash === 'screener') {
        loadPage(content, './screener.js', [content]);
    } else if (hash === 'multifactor') {
        loadPage(content, './multifactor.js', [content]);
    } else if (hash.startsWith('detail/')) {
        const code = hash.split('/')[1];
        loadPage(content, './detail.js', [content, code]);
    } else if (hash === 'about') {
        content.innerHTML = `
        <div class="card about-page">
            <h2>关于选股小程序</h2>
            <p>一款基于技术指标和多因子模型的 A 股智能选股工具。</p>
            <p><strong>功能：</strong></p>
            <ul>
                <li>6 种技术指标策略筛选（MA偏离、RSI超卖、放量突破、动量、超跌反弹、跳空回补）</li>
                <li>多因子综合评分（动量、波动率、量能、均值回归）</li>
                <li>个股 K 线图与详细技术指标</li>
            </ul>
            <p><strong>数据来源：</strong>akshare（新浪/腾讯）</p>
            <p><strong>免责声明：</strong>本工具仅供学习研究，不构成任何投资建议。股市有风险，投资需谨慎。</p>
        </div>`;
    }
}

window.addEventListener('hashchange', handleRoute);
window.addEventListener('DOMContentLoaded', handleRoute);
if (document.readyState !== 'loading') handleRoute();

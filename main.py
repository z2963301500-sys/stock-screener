import json
import pandas as pd
import numpy as np
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

from models import TechnicalScreeningRequest, MultifactorScreeningRequest, ScreeningResponse, StockSpotPage, StockSpotItem
from data import data_manager
from screener import screen_technical, screen_multifactor, _safe_float, create_task, get_task, run_technical_task, run_multifactor_task
from strategies import STRATEGIES, calc_rsi_score, calc_ma_deviation, calc_momentum_score, calc_volume_breakout


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(title="选股小程序", version="1.0.0", lifespan=lifespan)
_running_tasks = {}

H = '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>选股小程序</title><link rel="stylesheet" href="/static/style.css"></head><body>'
F = '</main><footer class="app-footer">数据来源 akshare · 仅供参考，不构成投资建议</footer></body></html>'

def nav(s=False, m=False, a=False):
    return '<header class="app-header"><h1 class="app-title">选股小程序</h1><nav class="app-nav">' + \
        f'<a href="/" class="nav-link{" active" if s else ""}">技术筛选</a>' + \
        f'<a href="/multifactor" class="nav-link{" active" if m else ""}">多因子评分</a>' + \
        f'<a href="/about" class="nav-link{" active" if a else ""}">关于</a>' + \
        '</nav></header><main id="app-content">'

label_map = {'ma_period': '均线周期', 'band': '偏离阈值', 'period': '计算周期', 'vol_ma': '均量周期', 'price_lb': '突破周期', 'lookback': '回溯天数'}
param_config = {'ma_period': (5, 60, 1), 'band': (0.01, 0.10, 0.005), 'period': (4, 14, 1), 'vol_ma': (10, 60, 1), 'price_lb': (3, 20, 1), 'lookback': (2, 20, 1)}

def build_strat_data():
    return json.dumps({k: {'label': v['label'], 'params': v['params']} for k, v in STRATEGIES.items()})

def build_params_html():
    parts = []
    for key, info in STRATEGIES.items():
        sliders = ''
        for pk, pv in info['params'].items():
            label = label_map.get(pk, pk)
            pmin, pmax, pstep = param_config.get(pk, (1, 100, 1))
            sliders += f'<div class="param-item"><label>{label}</label><div class="param-row"><input type="range" id="param-{pk}" min="{pmin}" max="{pmax}" step="{pstep}" value="{pv}"><span class="param-val" id="param-val-{pk}">{pv}</span></div></div>'
        parts.append(f'<div class="strategy-params" id="strat-{key}" style="display:none">{sliders}</div>')
    return ''.join(parts)

def build_strat_options():
    return ''.join(f'<option value="{k}">{v["label"]}</option>' for k, v in STRATEGIES.items())


@app.get("/", response_class=HTMLResponse)
async def page_screener():
    html = H + nav(s=True) + '''
<div class="card">
<div class="section-title">筛选条件</div>
<div class="filter-row">
<div class="filter-group"><label>选股策略</label><select id="strategy">''' + build_strat_options() + '''</select></div>
<div class="filter-group"><label>返回数量</label><select id="topn"><option value="20">前 20 名</option><option value="50" selected>前 50 名</option><option value="100">前 100 名</option></select></div>
<div class="filter-group"><label>&nbsp;</label><button class="btn btn-primary" onclick="doSearch()">开始筛选</button></div>
</div>
<div id="params-area" class="params-area">''' + build_params_html() + '''</div>
</div>
<div id="results"></div>
<div id="detail-modal" class="modal-overlay" style="display:none" onclick="if(event.target===this)closeDetail()">
<div class="modal-content card" id="modal-body"><div class="loading-overlay"><div class="spinner"></div>加载中...</div></div>
</div>
<script id="strat-data" type="application/json" data-first="''' + list(STRATEGIES.keys())[0] + '''" data-mode="screener">''' + build_strat_data() + '''</script>
<script src="/static/app.js?v=2"></script>
''' + F
    return HTMLResponse(content=html, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})


@app.get("/multifactor", response_class=HTMLResponse)
async def page_multifactor():
    html = H + nav(m=True) + '''
<div class="card">
<div class="section-title">因子权重配置</div>
<div class="weight-grid">
<div class="weight-item"><div class="weight-header"><label>动量趋势<small style="color:#6b7280;font-weight:400;margin-left:4px">涨幅越大得分越高</small></label><span class="weight-val" id="mf-val-wm">30%</span></div><input type="range" id="mf-wm" min="0" max="1" step="0.05" value="0.30"></div>
<div class="weight-item"><div class="weight-header"><label>低波动性<small style="color:#6b7280;font-weight:400;margin-left:4px">波动越小得分越高</small></label><span class="weight-val" id="mf-val-wv">25%</span></div><input type="range" id="mf-wv" min="0" max="1" step="0.05" value="0.25"></div>
<div class="weight-item"><div class="weight-header"><label>量能活跃<small style="color:#6b7280;font-weight:400;margin-left:4px">成交越活跃得分越高</small></label><span class="weight-val" id="mf-val-ww">25%</span></div><input type="range" id="mf-ww" min="0" max="1" step="0.05" value="0.25"></div>
<div class="weight-item"><div class="weight-header"><label>均值回归<small style="color:#6b7280;font-weight:400;margin-left:4px">越接近均线得分越高</small></label><span class="weight-val" id="mf-val-wr">20%</span></div><input type="range" id="mf-wr" min="0" max="1" step="0.05" value="0.20"></div>
</div>
<div style="margin-top:20px;display:flex;gap:12px;align-items:center;flex-wrap:wrap">
<div class="filter-group"><label>返回数量</label><select id="mf-topn"><option value="20">前 20 名</option><option value="50" selected>前 50 名</option><option value="100">前 100 名</option></select></div>
<div class="filter-group"><label>&nbsp;</label><button class="btn btn-primary" onclick="doMFSearch()">开始筛选</button></div>
<span style="font-size:0.8rem;color:#6b7280" id="mf-sum">权重合计: 100%</span>
</div></div>
<div id="mf-results"></div>
<div id="detail-modal" class="modal-overlay" style="display:none" onclick="if(event.target===this)closeDetail()">
<div class="modal-content card" id="modal-body"><div class="loading-overlay"><div class="spinner"></div>加载中...</div></div>
</div>
<script id="strat-data" type="application/json" data-first="" data-mode="multifactor">{}</script>
<script src="/static/app.js?v=2"></script>
''' + F
    return HTMLResponse(content=html, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})


@app.get("/detail/{code}", response_class=HTMLResponse)
async def page_detail(code: str, frm: str = Query("", alias="from")):
    back_url = '/multifactor' if frm == 'multifactor' else '/'
    try:
        df = await data_manager.get_history_detail(code, days=120)
        spot_df = await data_manager.get_spot_all()
        name_row = spot_df[spot_df['code'] == code]
        name = str(name_row.iloc[0]['name']) if len(name_row) > 0 else code

        candles = []
        for _, row in df.iterrows():
            candles.append({'date': row['date'].strftime('%Y-%m-%d'), 'open': _safe_float(row['open']), 'high': _safe_float(row['high']), 'low': _safe_float(row['low']), 'close': _safe_float(row['close']), 'volume': int(row['volume']) if pd.notna(row.get('volume')) else 0})

        rsi_r = calc_rsi_score(df, period=6)
        ma_r = calc_ma_deviation(df, ma_period=20)
        mom_r = calc_momentum_score(df, lookback=5)
        vol_r = calc_volume_breakout(df)
        rets = df['close'].pct_change().dropna().tail(20)
        vol_20d = float(rets.std() * np.sqrt(252)) if len(rets) > 0 else None
        ma5 = float(df['close'].rolling(5).mean().iloc[-1]) if len(df) >= 5 else None
        ma20 = float(df['close'].rolling(20).mean().iloc[-1]) if len(df) >= 20 else None
        ma60 = float(df['close'].rolling(60).mean().iloc[-1]) if len(df) >= 60 else None
        change_20d = float(df['close'].iloc[-1] / df['close'].iloc[-21] - 1) if len(df) >= 21 else None

        ind = {'rsi': round(rsi_r.get('rsi'), 1) if rsi_r.get('rsi') else None, 'ma5': round(ma5, 2) if ma5 else None, 'ma20': round(ma20, 2) if ma20 else None, 'ma60': round(ma60, 2) if ma60 else None, 'deviation_ma20': round(ma_r.get('deviation'), 4) if ma_r.get('deviation') else None, 'volume_ratio': round(vol_r.get('volume_ratio'), 2) if vol_r.get('volume_ratio') else None, 'change_5d': round(mom_r.get('return_n'), 4) if mom_r.get('return_n') is not None else None, 'change_20d': round(change_20d, 4) if change_20d is not None else None, 'volatility_20d': round(vol_20d, 4) if vol_20d else None}

        last = candles[-1]['close'] if candles else 0
        prev = candles[-2]['close'] if len(candles) >= 2 else last
        chg = last - prev
        chg_pct = (chg / prev * 100) if prev else 0
        pc = 'price-up' if chg_pct >= 0 else 'price-down'

        html = H + nav() + '''
<div class="detail-header"><a class="back-link" href="__BACK__">← 返回列表</a><span class="stock-name">__NAME__</span><span class="stock-code">__CODE__</span><span class="stock-price __PC__">¥__PRICE__</span><span class="stock-change __PC__">__CHANGE__</span></div>
''' .replace('__BACK__', back_url).replace('__NAME__', name).replace('__CODE__', code).replace('__PC__', pc).replace('__PRICE__', f'{last:.2f}').replace('__CHANGE__', f'{chg:+.2f} ({chg_pct:+.2f}%)') + '''
<div class="card"><div class="chart-container" id="main-chart"></div><div class="chart-sub" id="volume-chart"></div><div class="chart-sub" id="rsi-chart"></div></div>
<div class="card"><div class="section-title">技术指标</div><div class="indicator-grid" id="ind-grid"></div></div>
<script>
var CANDLES = __CANDLES__;
var INDICATORS = __INDICATORS__;
(function() {
    var cards = [["RSI(6)",INDICATORS.rsi,function(v){return v!=null?v.toFixed(1):"-";}],["MA5",INDICATORS.ma5,function(v){return v!=null?Number(v).toFixed(2):"-";}],["MA20",INDICATORS.ma20,function(v){return v!=null?Number(v).toFixed(2):"-";}],["MA60",INDICATORS.ma60,function(v){return v!=null?Number(v).toFixed(2):"-";}],["偏离MA20",INDICATORS.deviation_ma20,function(v){return v!=null?(v>=0?"+":"")+(v*100).toFixed(2)+"%":"-";},0],["量比",INDICATORS.volume_ratio,function(v){return v!=null?Number(v).toFixed(2):"-";}],["5日涨跌",INDICATORS.change_5d,function(v){return v!=null?(v>=0?"+":"")+(v*100).toFixed(2)+"%":"-";}],["20日涨跌",INDICATORS.change_20d,function(v){return v!=null?(v>=0?"+":"")+(v*100).toFixed(2)+"%":"-";}],["年化波动率",INDICATORS.volatility_20d,function(v){return v!=null?(v*100).toFixed(2)+"%":"-";}]];
    var h="";
    cards.forEach(function(c){var val=c[1],fmt=c[2],thr=c[3];var dv=val!=null?fmt(val):"-";var cc=(thr!=null&&val!=null)?(val>=thr?"price-up":"price-down"):"";h+='<div class="indicator-card"><div class="ind-label">'+c[0]+'</div><div class="ind-value '+cc+'">'+dv+'</div></div>';});
    document.getElementById("ind-grid").innerHTML=h;
})();
(function(){
    var CDNS=["https://cdn.jsdelivr.net/npm/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js","https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"];
    function ld(u){return new Promise(function(rs,rj){var s=document.createElement("script");s.src=u;s.onload=rs;s.onerror=rj;document.head.appendChild(s);setTimeout(function(){rj(new Error("timeout"));},10000);});}
    async function init(){
        var LC=null;for(var i=0;i<CDNS.length;i++){try{await ld(CDNS[i]);if(typeof LightweightCharts!=="undefined"){LC=LightweightCharts;break;}}catch(e){}}
        if(!LC){document.getElementById("main-chart").innerHTML='<div class="empty-msg">图表加载失败</div>';return;}
        var ch=LC.createChart(document.getElementById("main-chart"),{layout:{background:{color:"#fff"},textColor:"#333"},grid:{vertLines:{color:"#f0f0f0"},horzLines:{color:"#f0f0f0"}},crosshair:{mode:1},timeScale:{timeVisible:true,borderColor:"#e5e7eb"},rightPriceScale:{borderColor:"#e5e7eb"}});
        var cs=ch.addCandlestickSeries({upColor:"#e03a3a",downColor:"#1aad19",borderUpColor:"#e03a3a",borderDownColor:"#1aad19",wickUpColor:"#e03a3a",wickDownColor:"#1aad19"});
        cs.setData(CANDLES.map(function(c){return{time:c.date,open:c.open,high:c.high,low:c.low,close:c.close};}));
        var mc={ma5:"#f59e0b",ma20:"#8b5cf6",ma60:"#06b6d4"};
        Object.keys(mc).forEach(function(k){if(INDICATORS[k]!=null){var p=parseInt(k.replace("ma",""));var d=[];for(var i=p-1;i<CANDLES.length;i++){var s=0;for(var j=i-p+1;j<=i;j++)s+=CANDLES[j].close;d.push({time:CANDLES[i].date,value:s/p});}if(d.length>0){var ls=ch.addLineSeries({color:mc[k],lineWidth:1.5,priceLineVisible:false});ls.setData(d);}}});
        var vc=LC.createChart(document.getElementById("volume-chart"),{layout:{background:{color:"#fff"},textColor:"#333"},grid:{vertLines:{color:"#f0f0f0"},horzLines:{color:"#f0f0f0"}},crosshair:{mode:0},timeScale:{timeVisible:false},rightPriceScale:{borderColor:"#e5e7eb"}});
        var vs=vc.addHistogramSeries({color:"#26a69a",priceFormat:{type:"volume"},priceScaleId:""});
        vs.setData(CANDLES.map(function(c){return{time:c.date,value:c.volume,color:c.close>=c.open?"rgba(224,58,58,0.4)":"rgba(26,173,25,0.4)"};}));
        var rc=LC.createChart(document.getElementById("rsi-chart"),{layout:{background:{color:"#fff"},textColor:"#333"},grid:{vertLines:{color:"#f0f0f0"},horzLines:{color:"#f0f0f0"}},crosshair:{mode:0},timeScale:{timeVisible:false},rightPriceScale:{borderColor:"#e5e7eb"}});
        var rd=[];var g=0,l=0,p=6;for(var i=1;i<=p;i++){var d=CANDLES[i].close-CANDLES[i-1].close;if(d>0)g+=d;else l-=d;}var ag=g/p,al=l/p;
        for(var i=p;i<CANDLES.length;i++){var rs=al===0?100:ag/al;rd.push({time:CANDLES[i].date,value:100-(100/(1+rs))});var d=CANDLES[i].close-CANDLES[i-1].close;ag=(ag*(p-1)+(d>0?d:0))/p;al=(al*(p-1)+(d<0?-d:0))/p;}
        var rls=rc.addLineSeries({color:"#7c3aed",lineWidth:1.5});rls.setData(rd);
        [30,70].forEach(function(lv){var lb=rc.addLineSeries({color:lv===30?"#16a34a":"#dc2626",lineWidth:1,lineStyle:2,priceLineVisible:false});lb.setData([{time:CANDLES[0].date,value:lv},{time:CANDLES[CANDLES.length-1].date,value:lv}]);});
    }init();
})();
</script>''' .replace('__CANDLES__', json.dumps(candles)).replace('__INDICATORS__', json.dumps(ind)) + F
        return HTMLResponse(content=html, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})
    except Exception as e:
        html = H + nav() + f'<div class="error-msg">加载失败: {e}</div>' + F
        return HTMLResponse(content=html, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})


@app.get("/about", response_class=HTMLResponse)
async def page_about():
    html = H + nav(a=True) + '''<div class="card about-card"><h2>关于选股小程序</h2><p>基于技术指标和多因子模型的 A 股智能选股工具。</p><p style="margin-top:10px"><strong>核心功能</strong></p><ul><li>技术筛选 — 6 种短线策略</li><li>多因子评分 — 四维综合排名</li><li>个股详情 — K 线图表与指标</li></ul><div class="disclaimer">免责声明：本工具仅供学习研究，不构成投资建议。股市有风险，投资需谨慎。</div></div>''' + F
    return HTMLResponse(content=html, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})


@app.get("/test", response_class=HTMLResponse)
async def page_test():
    return HTMLResponse(content='''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Test</title></head><body><h1>JS测试</h1><button onclick="document.getElementById('r').textContent='OK '+new Date().toLocaleTimeString()">点我</button><div id="r">等待...</div><script>document.getElementById('r').textContent='JS OK '+new Date().toLocaleTimeString();</script></body></html>''')


@app.post("/api/screen/technical")
async def api_screen_technical(req: TechnicalScreeningRequest):
    task_id = create_task()
    # Store reference to prevent GC
    task_ref = asyncio.ensure_future(run_technical_task(task_id, req.strategy, req.params, req.top_n, req.exclude_st, req.min_market_cap))
    _running_tasks[task_id] = task_ref
    return {"task_id": task_id, "status": "running"}


@app.post("/api/screen/multifactor")
async def api_screen_multifactor(req: MultifactorScreeningRequest):
    task_id = create_task()
    weights = {'weight_momentum': req.weight_momentum, 'weight_volatility': req.weight_volatility, 'weight_volume': req.weight_volume, 'weight_reversion': req.weight_reversion}
    task_ref = asyncio.ensure_future(run_multifactor_task(task_id, weights, req.top_n, req.exclude_st))
    _running_tasks[task_id] = task_ref
    return {"task_id": task_id, "status": "running"}


@app.get("/api/task/{task_id}")
async def api_task(task_id: str):
    task = get_task(task_id)
    if task['status'] == 'done':
        return task['result'] | {'status': 'done'}
    return task


@app.get("/api/stocks/{code}/indicators")
async def api_indicators(code: str):
    try:
        df = await data_manager.get_history_detail(code, days=120)
        rsi_r = calc_rsi_score(df, period=6); ma_r = calc_ma_deviation(df, ma_period=20)
        mom_r = calc_momentum_score(df, lookback=5); vol_r = calc_volume_breakout(df)
        rets = df['close'].pct_change().dropna().tail(20)
        vol_20d = float(rets.std() * np.sqrt(252)) if len(rets) > 0 else None
        ma5 = float(df['close'].rolling(5).mean().iloc[-1]) if len(df) >= 5 else None
        ma20 = float(df['close'].rolling(20).mean().iloc[-1]) if len(df) >= 20 else None
        ma60 = float(df['close'].rolling(60).mean().iloc[-1]) if len(df) >= 60 else None
        change_20d = float(df['close'].iloc[-1] / df['close'].iloc[-21] - 1) if len(df) >= 21 else None
        return {'code': code, 'rsi': round(rsi_r.get('rsi'), 1) if rsi_r.get('rsi') else None, 'ma5': round(ma5, 2) if ma5 else None, 'ma20': round(ma20, 2) if ma20 else None, 'ma60': round(ma60, 2) if ma60 else None, 'deviation_ma20': round(ma_r.get('deviation'), 4) if ma_r.get('deviation') else None, 'volume_ratio': round(vol_r.get('volume_ratio'), 2) if vol_r.get('volume_ratio') else None, 'change_5d': round(mom_r.get('return_n'), 4) if mom_r.get('return_n') is not None else None, 'change_20d': round(change_20d, 4) if change_20d is not None else None, 'volatility_20d': round(vol_20d, 4) if vol_20d else None}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/stocks/spot", response_model=StockSpotPage)
async def get_stocks_spot(page: int = Query(1, ge=1), page_size: int = Query(50, ge=10, le=200), keyword: str = Query("")):
    df = await data_manager.get_spot_all()
    if keyword: df = df[df['name'].str.contains(keyword, na=False) | df['code'].str.contains(keyword, na=False)]
    total = len(df)
    page_df = df.iloc[(page-1)*page_size : page*page_size]
    stocks = [StockSpotItem(code=str(r['code']), name=str(r['name']), price=_safe_float(r['price']), change_pct=_safe_float(r.get('change_pct'))) for _, r in page_df.iterrows()]
    return StockSpotPage(total=total, page=page, page_size=page_size, stocks=stocks)


app.mount("/static", StaticFiles(directory="static"), name="static")

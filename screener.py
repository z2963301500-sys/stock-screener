import asyncio
import time
import uuid
import threading
import pandas as pd
import numpy as np
from data import data_manager
from strategies import STRATEGIES
from factors import compute_multifactor_scores

MAX_CONCURRENT_HISTORY = 8
STRATEGY_FUNCS = {name: info['func'] for name, info in STRATEGIES.items()}

# In-memory task store
_tasks = {}

def create_task():
    task_id = uuid.uuid4().hex[:12]
    _tasks[task_id] = {'status': 'running', 'result': None, 'error': None}
    return task_id

def get_task(task_id):
    return _tasks.get(task_id, {'status': 'not_found'})


async def screen_technical(strategy: str, params: dict, top_n: int = 50,
                           exclude_st: bool = True, min_market_cap: float = 0) -> dict:
    t0 = time.time()
    spot_df = await data_manager.get_spot_all()
    total = len(spot_df)
    if exclude_st:
        spot_df = spot_df[~spot_df['name'].str.contains(r'^\*?ST', na=False)]
    if 'amount' in spot_df.columns:
        spot_df = spot_df[spot_df['amount'].notna() & (spot_df['amount'] > 1e6)]
        spot_df = spot_df.sort_values('amount', ascending=False)

    candidates = spot_df.head(40)
    codes = candidates['code'].tolist()
    strategy_func = STRATEGY_FUNCS[strategy]
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_HISTORY)

    async def score_one(idx: int, code: str) -> dict | None:
        async with semaphore:
            try:
                hist = await data_manager.get_history(code, days=30)
                result = strategy_func(hist, **params)
                row = candidates.iloc[idx]
                indicator_keys = [k for k in result if k != 'score']
                indicator_val = result.get(indicator_keys[0]) if indicator_keys else None
                return {'code': code, 'name': str(row['name']), 'price': _safe_float(row['price']),
                        'score': float(result['score']), 'indicator_value': indicator_val,
                        'pe': None, 'pb': None, 'change_pct': _safe_float(row.get('change_pct')),
                        'signal_strength': _strength_label(result['score'])}
            except Exception:
                return None

    tasks = [score_one(i, code) for i, code in enumerate(codes)]
    raw_results = await asyncio.gather(*tasks)
    results = [r for r in raw_results if r is not None and r['score'] > 0]
    results.sort(key=lambda x: x['score'], reverse=True)
    elapsed = (time.time() - t0) * 1000
    return {'results': results[:top_n], 'total_scanned': total,
            'total_matched': len(results), 'elapsed_ms': elapsed}


async def screen_multifactor(spot_df: pd.DataFrame, weights: dict,
                              top_n: int = 50, exclude_st: bool = True) -> dict:
    t0 = time.time()
    total = len(spot_df)
    df = spot_df.copy()
    if exclude_st:
        df = df[~df['name'].str.contains(r'^\*?ST', na=False)]
    if 'amount' in df.columns:
        df = df[df['amount'].notna() & (df['amount'] > 1e6)]
        df = df.sort_values('amount', ascending=False)

    candidates = df.head(30)
    codes = candidates['code'].tolist()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_HISTORY)
    histories = {}

    async def fetch_one(code: str):
        async with semaphore:
            try:
                hist = await data_manager.get_history(code, days=20)
                return code, hist
            except Exception:
                return code, None

    raw = await asyncio.gather(*[fetch_one(code) for code in codes])
    for code, hist in raw:
        histories[code] = hist

    candidates = compute_multifactor_scores(candidates, histories, weights)
    candidates = candidates.sort_values('factor_score', ascending=False)
    top = candidates.head(top_n)

    results = []
    for _, row in top.iterrows():
        results.append({'code': str(row['code']), 'name': str(row['name']),
                        'price': _safe_float(row['price']), 'score': round(float(row['factor_score']), 1),
                        'indicator_value': round(float(row['factor_score']), 1),
                        'pe': None, 'pb': None, 'change_pct': _safe_float(row.get('change_pct')),
                        'signal_strength': _strength_label(row['factor_score'])})
    elapsed = (time.time() - t0) * 1000
    return {'results': results, 'total_scanned': total,
            'total_matched': len(results), 'elapsed_ms': elapsed}


async def run_technical_task(task_id: str, strategy: str, params: dict,
                              top_n: int, exclude_st: bool, min_market_cap: float):
    try:
        result = await screen_technical(strategy, params, top_n, exclude_st, min_market_cap)
        _tasks[task_id] = {'status': 'done', 'result': result}
    except Exception as e:
        _tasks[task_id] = {'status': 'error', 'error': str(e)}


async def run_multifactor_task(task_id: str, weights: dict, top_n: int, exclude_st: bool):
    try:
        spot_df = await data_manager.get_spot_all()
        result = await screen_multifactor(spot_df, weights, top_n, exclude_st)
        _tasks[task_id] = {'status': 'done', 'result': result}
    except Exception as e:
        import traceback
        msg = str(e)[:300]
        tb = traceback.format_exc()
        # Check which step failed
        if 'decode' in msg.lower() or '<' in msg:
            msg = '数据接口返回异常（可能地域限制），请稍后重试'
        _tasks[task_id] = {'status': 'error', 'error': msg} if 'stock_zh' not in tb else {'status': 'error', 'error': '行情数据拉取失败，请重试'}


def _strength_label(score: float) -> str:
    if score >= 70: return 'strong'
    elif score >= 40: return 'moderate'
    return 'weak'


def _safe_float(val) -> float | None:
    if val is None: return None
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f): return None
        return round(f, 4)
    except (ValueError, TypeError):
        return None

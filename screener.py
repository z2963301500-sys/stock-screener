import asyncio
import time
import pandas as pd
import numpy as np
from data import data_manager
from strategies import STRATEGIES
from factors import compute_multifactor_scores

MAX_CONCURRENT_HISTORY = 15

STRATEGY_FUNCS = {name: info['func'] for name, info in STRATEGIES.items()}


async def screen_technical(strategy: str, params: dict, top_n: int = 50,
                           exclude_st: bool = True, min_market_cap: float = 0) -> dict:
    t0 = time.time()

    spot_df = await data_manager.get_spot_all()
    total = len(spot_df)

    if exclude_st:
        spot_df = spot_df[~spot_df['name'].str.contains(r'^\*?ST', na=False)]

    # Filter by minimum amount (liquidity)
    if 'amount' in spot_df.columns:
        spot_df = spot_df[spot_df['amount'].notna() & (spot_df['amount'] > 1e6)]
    elif 'turnover' in spot_df.columns:
        spot_df = spot_df[spot_df['turnover'].notna() & (spot_df['turnover'] > 1e6)]

    # Sort by approximate market activity and take top candidates
    if 'amount' in spot_df.columns:
        spot_df = spot_df.sort_values('amount', ascending=False)

    candidates = spot_df.head(200)
    codes = candidates['code'].tolist()

    strategy_func = STRATEGY_FUNCS[strategy]
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_HISTORY)

    async def score_one(idx: int, code: str) -> dict | None:
        async with semaphore:
            try:
                hist = await data_manager.get_history(code, days=60)
                result = strategy_func(hist, **params)
                row = candidates.iloc[idx]
                indicator_keys = [k for k in result if k != 'score']
                indicator_val = result.get(indicator_keys[0]) if indicator_keys else None

                return {
                    'code': code,
                    'name': str(row['name']),
                    'price': _safe_float(row['price']),
                    'score': float(result['score']),
                    'indicator_value': indicator_val,
                    'pe': None,
                    'pb': None,
                    'change_pct': _safe_float(row.get('change_pct')),
                    'signal_strength': _strength_label(result['score']),
                }
            except Exception:
                return None

    tasks = [score_one(i, code) for i, code in enumerate(codes)]
    raw_results = await asyncio.gather(*tasks)

    results = [r for r in raw_results if r is not None and r['score'] > 0]
    results.sort(key=lambda x: x['score'], reverse=True)

    elapsed = (time.time() - t0) * 1000

    return {
        'results': results[:top_n],
        'total_scanned': total,
        'total_matched': len(results),
        'elapsed_ms': elapsed,
    }


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

    candidates = df.head(150)
    codes = candidates['code'].tolist()

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_HISTORY)
    histories = {}

    async def fetch_one(code: str):
        async with semaphore:
            try:
                hist = await data_manager.get_history(code, days=30)
                return code, hist
            except Exception:
                return code, None

    tasks = [fetch_one(code) for code in codes]
    raw = await asyncio.gather(*tasks)
    for code, hist in raw:
        histories[code] = hist

    # Compute multi-factor scores
    candidates_with_scores = compute_multifactor_scores(candidates, histories, weights)
    candidates_with_scores = candidates_with_scores.sort_values('factor_score', ascending=False)
    top = candidates_with_scores.head(top_n)

    results = []
    for _, row in top.iterrows():
        results.append({
            'code': str(row['code']),
            'name': str(row['name']),
            'price': _safe_float(row['price']),
            'score': round(float(row['factor_score']), 1),
            'indicator_value': round(float(row['factor_score']), 1),
            'pe': None,
            'pb': None,
            'change_pct': _safe_float(row.get('change_pct')),
            'signal_strength': _strength_label(row['factor_score']),
        })

    elapsed = (time.time() - t0) * 1000

    return {
        'results': results,
        'total_scanned': total,
        'total_matched': len(results),
        'elapsed_ms': elapsed,
    }


def _strength_label(score: float) -> str:
    if score >= 70:
        return 'strong'
    elif score >= 40:
        return 'moderate'
    return 'weak'


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f):
            return None
        return round(f, 4)
    except (ValueError, TypeError):
        return None

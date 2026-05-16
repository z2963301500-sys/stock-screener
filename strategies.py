import pandas as pd
import numpy as np


def calc_ma_deviation(df: pd.DataFrame, ma_period: int = 20, band: float = 0.02) -> dict:
    if len(df) < ma_period + 1:
        return {'score': 0, 'ma': None, 'deviation': None}

    ma = df['close'].rolling(ma_period).mean().iloc[-1]
    price = df['close'].iloc[-1]
    if pd.isna(ma) or ma == 0:
        return {'score': 0, 'ma': None, 'deviation': None}
    deviation = price / ma - 1

    if deviation >= 0:
        score = 0
    else:
        score = min(100, abs(deviation) / (2 * band) * 100)

    return {'score': round(score, 1), 'ma': round(float(ma), 2), 'deviation': round(deviation, 4)}


def calc_rsi_score(df: pd.DataFrame, period: int = 6) -> dict:
    if len(df) < period + 1:
        return {'score': 0, 'rsi': None}

    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(period).mean().iloc[-1]
    avg_loss = loss.rolling(period).mean().iloc[-1]

    if pd.isna(avg_gain) or pd.isna(avg_loss):
        return {'score': 0, 'rsi': None}
    if avg_loss == 0:
        rsi = 100
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

    if rsi >= 50:
        score = 0
    else:
        score = min(100, (50 - rsi) / 40 * 100)

    return {'score': round(score, 1), 'rsi': round(rsi, 1)}


def calc_volume_breakout(df: pd.DataFrame, vol_ma: int = 20, price_lb: int = 5) -> dict:
    min_len = max(vol_ma, price_lb) + 1
    if len(df) < min_len:
        return {'score': 0, 'volume_ratio': None, 'price_position': None}

    vol_mean = df['volume'].rolling(vol_ma).mean().iloc[-1]
    vol_latest = df['volume'].iloc[-1]
    if pd.isna(vol_mean) or vol_mean == 0:
        return {'score': 0, 'volume_ratio': None, 'price_position': None}
    vol_ratio = vol_latest / vol_mean

    high_n = df['high'].rolling(price_lb).max().iloc[-2]
    price = df['close'].iloc[-1]
    price_ratio = price / high_n if high_n > 0 else 0

    vol_score = min(50, max(0, (vol_ratio - 0.8) / 2.2 * 50))
    price_score = 50 if price >= high_n * 0.995 else max(0, (price_ratio - 0.9) / 0.095 * 50)

    return {
        'score': round(vol_score + price_score, 1),
        'volume_ratio': round(float(vol_ratio), 2),
        'price_position': round(float(price_ratio), 4),
    }


def calc_momentum_score(df: pd.DataFrame, lookback: int = 5) -> dict:
    if len(df) < lookback + 20:
        return {'score': 0, 'return_n': None, 'percentile': None}

    ret_n = df['close'].iloc[-1] / df['close'].iloc[-(lookback + 1)] - 1

    rolling_rets = df['close'].pct_change(lookback).dropna()
    if len(rolling_rets) < 10:
        return {'score': 0, 'return_n': round(ret_n, 4), 'percentile': None}

    percentile = (rolling_rets < ret_n).sum() / len(rolling_rets)

    if ret_n <= 0:
        score = 0
    else:
        score = min(100, percentile * 100)

    return {
        'score': round(score, 1),
        'return_n': round(ret_n, 4),
        'percentile': round(percentile, 4),
    }


def calc_reversal_score(df: pd.DataFrame, lookback: int = 3) -> dict:
    if len(df) < lookback + 1:
        return {'score': 0, 'return_n': None}

    ret_n = df['close'].iloc[-1] / df['close'].iloc[-(lookback + 1)] - 1

    if ret_n >= 0:
        score = 0
    else:
        score = min(100, abs(ret_n) / 0.06 * 100)

    return {'score': round(score, 1), 'return_n': round(ret_n, 4)}


def calc_gap_fade_score(df: pd.DataFrame) -> dict:
    if len(df) < 3:
        return {'score': 0, 'prev_ret': None, 'gap': None}

    prev_ret = df['close'].iloc[-2] / df['close'].iloc[-3] - 1
    today_open = df['open'].iloc[-1]
    prev_close = df['close'].iloc[-2]
    gap = today_open / prev_close - 1 if prev_close > 0 else 0

    if prev_ret >= -0.01 or gap >= -0.005:
        score = 0
    else:
        drop_score = min(50, abs(prev_ret) / 0.04 * 50)
        gap_score = min(50, abs(gap) / 0.02 * 50)
        score = drop_score + gap_score

    return {
        'score': round(score, 1),
        'prev_ret': round(prev_ret, 4),
        'gap': round(gap, 4),
    }


STRATEGIES = {
    'ma_band': {'func': calc_ma_deviation, 'label': 'MA均线偏离', 'params': {'ma_period': 20, 'band': 0.02}},
    'rsi_extreme': {'func': calc_rsi_score, 'label': 'RSI超卖', 'params': {'period': 6}},
    'volume_breakout': {'func': calc_volume_breakout, 'label': '放量突破', 'params': {'vol_ma': 20, 'price_lb': 5}},
    'momentum': {'func': calc_momentum_score, 'label': '动量强度', 'params': {'lookback': 5}},
    'reversal': {'func': calc_reversal_score, 'label': '超跌反弹', 'params': {'lookback': 3}},
    'gap_fade': {'func': calc_gap_fade_score, 'label': '跳空回补', 'params': {}},
}

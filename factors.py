import pandas as pd
import numpy as np


def compute_multifactor_scores(spot_df: pd.DataFrame, histories: dict[str, pd.DataFrame],
                                weights: dict) -> pd.DataFrame:
    """
    Compute composite technical multi-factor scores.
    Factors: momentum (20d), volatility, volume activity, mean-reversion distance.
    """
    df = spot_df.copy()
    scores = pd.DataFrame(index=df.index)

    momentum_vals = {}
    volatility_vals = {}
    volume_vals = {}
    reversion_vals = {}

    for code, hist in histories.items():
        if hist is None or len(hist) < 20:
            momentum_vals[code] = np.nan
            volatility_vals[code] = np.nan
            volume_vals[code] = np.nan
            reversion_vals[code] = np.nan
            continue

        closes = hist['close']
        volumes = hist['volume']

        # Momentum: 20-day return
        mom = closes.iloc[-1] / closes.iloc[-20] - 1 if len(closes) >= 20 else np.nan
        momentum_vals[code] = mom

        # Volatility: 20-day annualized (lower is better)
        rets = closes.pct_change().dropna().tail(20)
        vol = rets.std() * np.sqrt(252) if len(rets) > 0 else np.nan
        volatility_vals[code] = vol

        # Volume activity: latest volume / 20-day average volume
        vol_avg = volumes.tail(20).mean()
        latest_vol = volumes.iloc[-1]
        vol_ratio = latest_vol / vol_avg if vol_avg > 0 else 1.0
        volume_vals[code] = vol_ratio

        # Mean-reversion: distance from 20-day MA
        ma20 = closes.rolling(20).mean().iloc[-1]
        price = closes.iloc[-1]
        deviation = (price / ma20 - 1) if ma20 > 0 else 0
        reversion_vals[code] = -abs(deviation)  # closer to MA = better

    df['momentum_val'] = df['code'].map(momentum_vals)
    df['volatility_val'] = df['code'].map(volatility_vals)
    df['volume_val'] = df['code'].map(volume_vals)
    df['reversion_val'] = df['code'].map(reversion_vals)

    # Momentum score: higher momentum = higher score
    mom_clean = df['momentum_val'].replace([np.inf, -np.inf], np.nan)
    if mom_clean.notna().sum() > 0:
        scores['momentum_score'] = 100 * mom_clean.rank(pct=True)
    else:
        scores['momentum_score'] = 50

    # Volatility score: lower vol = higher score
    vol_clean = df['volatility_val'].replace([np.inf, -np.inf], np.nan)
    if vol_clean.notna().sum() > 0:
        scores['volatility_score'] = 100 * (1 - vol_clean.rank(pct=True))
    else:
        scores['volatility_score'] = 50

    # Volume score: higher volume ratio = higher score
    vol_act = df['volume_val'].replace([np.inf, -np.inf], np.nan)
    if vol_act.notna().sum() > 0:
        scores['volume_score'] = 100 * vol_act.rank(pct=True)
    else:
        scores['volume_score'] = 50

    # Reversion score: closer to MA = higher score
    rev_clean = df['reversion_val'].replace([np.inf, -np.inf], np.nan)
    if rev_clean.notna().sum() > 0:
        scores['reversion_score'] = 100 * rev_clean.rank(pct=True)
    else:
        scores['reversion_score'] = 50

    scores = scores.fillna(50)

    df['factor_score'] = (
        weights.get('weight_momentum', 0.30) * scores['momentum_score'] +
        weights.get('weight_volatility', 0.25) * scores['volatility_score'] +
        weights.get('weight_volume', 0.25) * scores['volume_score'] +
        weights.get('weight_reversion', 0.20) * scores['reversion_score']
    )

    return df

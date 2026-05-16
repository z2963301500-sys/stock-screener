import asyncio
import time
import pandas as pd
import numpy as np
import akshare as ak


class DataManager:
    def __init__(self):
        self._spot_cache: pd.DataFrame | None = None
        self._spot_cache_time: float = 0
        self._spot_ttl: float = 300
        self._history_cache: dict[str, tuple[float, pd.DataFrame]] = {}
        self._history_ttl: float = 600

    async def get_spot_all(self, force_refresh: bool = False) -> pd.DataFrame:
        if not force_refresh and (time.time() - self._spot_cache_time) < self._spot_ttl:
            if self._spot_cache is not None:
                return self._spot_cache.copy()

        df = await asyncio.to_thread(ak.stock_zh_a_spot)
        df = self._normalize_spot_columns(df)
        df['price'] = pd.to_numeric(df['price'], errors='coerce')
        df = df[df['price'] > 0]
        df = df[df['name'].notna()]

        self._spot_cache = df
        self._spot_cache_time = time.time()
        return df.copy()

    async def get_history(self, code: str, days: int = 60) -> pd.DataFrame:
        """Fast history for screening - uses Tencent source (no py_mini_racer)."""
        cache_key = f"tx:{code}:{days}"
        if cache_key in self._history_cache:
            ts, df = self._history_cache[cache_key]
            if time.time() - ts < self._history_ttl:
                return df.copy()

        symbol = self._to_sina_symbol(code)
        end_date = pd.Timestamp.now().strftime('%Y-%m-%d')
        start_date = (pd.Timestamp.now() - pd.Timedelta(days=days * 2)).strftime('%Y-%m-%d')

        df = await asyncio.to_thread(
            ak.stock_zh_a_hist_tx,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )
        df = self._normalize_tx_columns(df)
        df = df.sort_values('date').tail(days)

        self._history_cache[cache_key] = (time.time(), df)
        return df.copy()

    async def get_history_detail(self, code: str, days: int = 120) -> pd.DataFrame:
        """Full history for detail page - uses Sina source (has volume)."""
        cache_key = f"sina:{code}:{days}"
        if cache_key in self._history_cache:
            ts, df = self._history_cache[cache_key]
            if time.time() - ts < self._history_ttl:
                return df.copy()

        symbol = self._to_sina_symbol(code)
        end_date = pd.Timestamp.now().strftime('%Y%m%d')
        start_date = (pd.Timestamp.now() - pd.Timedelta(days=days * 2)).strftime('%Y%m%d')

        df = await asyncio.to_thread(
            ak.stock_zh_a_daily,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            adjust='qfq'
        )
        df = self._normalize_sina_hist_columns(df)
        df = df.sort_values('date').tail(days)

        self._history_cache[cache_key] = (time.time(), df)
        return df.copy()

    def _to_sina_symbol(self, code: str) -> str:
        clean = code.replace('sz', '').replace('sh', '').replace('bj', '')
        if clean.startswith(('00', '30')):
            return f"sz{clean}"
        elif clean.startswith('6'):
            return f"sh{clean}"
        elif clean.startswith(('8', '4', '9')):
            return f"bj{clean}"
        return f"sz{clean}"

    def _normalize_spot_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        col_order = ['code', 'name', 'price', 'change_amount', 'change_pct',
                     'open', 'prev_close', 'high', 'low',
                     'bid', 'ask', 'volume', 'amount', 'timestamp']
        if len(df.columns) == len(col_order):
            df.columns = col_order
        else:
            known = {0: 'code', 1: 'name', 2: 'price', 4: 'change_pct',
                     5: 'open', 11: 'volume', 12: 'amount'}
            df.columns = [known.get(i, f'col_{i}') for i in range(len(df.columns))]
        if 'code' in df.columns:
            df['code'] = df['code'].astype(str).str.replace('sz', '').str.replace('sh', '').str.replace('bj', '')
        return df

    def _normalize_tx_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        # Tencent returns: date, open, close, high, low, amount
        # Derive volume from amount/close (approximate)
        if 'close' in df.columns and 'amount' in df.columns:
            df['volume'] = np.where(
                df['close'] > 0,
                (df['amount'] * 100 / df['close']).astype(int),
                0
            )
        return df

    def _normalize_sina_hist_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        col_map = {
            'date': 'date', 'open': 'open', 'high': 'high',
            'low': 'low', 'close': 'close', 'volume': 'volume',
            'amount': 'amount',
        }
        existing = {k: v for k, v in col_map.items() if k in df.columns}
        df = df[list(existing.keys())].rename(columns=existing)
        df['date'] = pd.to_datetime(df['date'])
        return df


data_manager = DataManager()

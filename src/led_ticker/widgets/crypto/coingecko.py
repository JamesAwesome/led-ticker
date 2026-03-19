"""CoinGecko price monitor widget."""

import asyncio
import logging

import attrs

from led_ticker.widget import run_monitor_loop
from led_ticker.widgets import register
from led_ticker.widgets.crypto.coinbase import _draw_price_ticker

COINGECKO_API = "https://api.coingecko.com/api/v3"
COINGECKO_COIN_LIST = f"{COINGECKO_API}/coins/list"
COINGECKO_PRICE_API = f"{COINGECKO_API}/simple/price"


@register("coingecko")
@attrs.define
class CoinGeckoPriceMonitor:
    """Crypto price monitor using the CoinGecko API."""

    symbol: str
    symbol_id: str
    currency: str
    session: object
    center: bool = True
    padding: int = 6
    price_data: dict = attrs.field(init=False, factory=dict)

    @classmethod
    async def start(cls, symbol, symbol_id, currency, session, update_interval=300):
        widget = cls(
            symbol=symbol, symbol_id=symbol_id,
            currency=currency, session=session,
        )
        await widget.update()
        asyncio.create_task(run_monitor_loop(widget, update_interval))
        return widget

    async def update(self):
        logging.info("Updating monitor for %s via CoinGecko", self.symbol)
        params = {
            "ids": [self.symbol_id],
            "vs_currencies": self.currency,
            "include_24hr_change": "true",
        }
        async with self.session.get(COINGECKO_PRICE_API, params=params) as response:
            price_data = await response.json()
            cur = self.currency.lower()
            cur_change = f"{cur}_24h_change"

            for coin_id, data in price_data.items():
                try:
                    price = f"{data[cur]:,.4f}"
                    change_24h = f"{data[cur_change]:.2f}%"
                except (KeyError, TypeError):
                    logging.warning(
                        "API data not complete for %s: %s", coin_id, data
                    )
                    continue

                self.price_data = {"price": price, "change_24h": change_24h}

    def draw(self, canvas, cursor_pos=0, **kwargs):
        return _draw_price_ticker(
            canvas, self.symbol,
            self.price_data["price"],
            self.price_data["change_24h"],
            cursor_pos=cursor_pos, center=self.center,
            padding=self.padding, end_padding=self.padding,
        )


async def _get_coingecko_coin_list(session):
    logging.info("Fetching CoinGecko coin list...")
    headers = {"Accept": "application/json"}
    async with session.get(COINGECKO_COIN_LIST, headers=headers) as response:
        return await response.json()


def _find_coingecko_symbol_id(coin_list, symbol):
    for coin_meta in coin_list:
        if symbol.lower() == coin_meta["symbol"].lower():
            return coin_meta["id"]


async def start_coingecko_monitors(symbols, currency, session, **kwargs):
    coin_list = await _get_coingecko_coin_list(session)
    symbol_map = {}
    for symbol in symbols:
        symbol_id = _find_coingecko_symbol_id(coin_list, symbol)
        symbol_map[symbol] = symbol_id

    return [
        await CoinGeckoPriceMonitor.start(
            symbol, symbol_id, currency, session, **kwargs
        )
        for symbol, symbol_id in symbol_map.items()
    ]

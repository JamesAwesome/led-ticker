import json
import logging
import os
import requests
import sys
from datetime import date
from datetime import timedelta


# Set up the logger
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


API_CLASS_MAP = {'coinmarketcap': 'CoinMarketCap', 'coingecko': 'CoinGecko', 'coinbase': 'CoinBase'}


def get_api_cls(api_name):
    """

    Args:
        api_name (str): The name of the API to use.
    """
    if api_name not in API_CLASS_MAP:
        raise RuntimeError(f'"{api_name}" api is not implemented.')
    return getattr(sys.modules[__name__], API_CLASS_MAP[api_name])


class PriceAPI:
    """The base class for Price API"""

    def __init__(self, symbols, currency='usd'):
        self._symbols = symbols
        self.currency = currency
        self.validate_currency(currency)

    def get_symbols(self):
        """Get a list of symbols needed"""
        return [s.split(':')[0] for s in self._symbols.split(',')]

    def get_name_for_symbol(self, symbol):
        """Return the name for the symbol, if specified"""
        for sym in self._symbols.split(','):
            sym_split = sym.split(':')
            if symbol == sym_split[0]:
                return sym_split[1] if len(sym_split) == 2 else None
        return None

    def fetch_price_data(self):
        """Fetch new price data from the API.

        Returns:
            A list of dicts that represent price data for a single asset. For example:

            [{'symbol': .., 'price': .., 'change_24h': ..}]
        """
        raise NotImplementedError

    @property
    def supported_currencies(self):
        raise NotImplementedError

    def validate_currency(self, currency):
        supported = self.supported_currencies
        if currency not in self.supported_currencies:
            raise ValueError(
                f"CURRENCY={currency} is not supported. Options are: {self.supported_currencies}."
            )


class CoinBase(PriceAPI):
    API = 'https://api.coinbase.com'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @property
    def supported_currencies(self):
        return ['usd', 'eur', 'btc']

    def fetch_today_price(self, symbol):
        response = requests.get(
            f'{self.API}/v2/prices/{symbol}-{self.currency.upper()}/spot'
        )

        todays_price = float(response.json().get('data', {}).get('amount'))

        logger.info(f'Todays price for {symbol} is {todays_price}')
        return todays_price

    def fetch_price_data(self):
        """Fetch new price data from the CoinMarketCap API"""
        logger.info('`fetch_price_data` called.')

        response = requests.get(
            f'{self.API}/v2/exchange-rates',
            params={'currency': self.currency},
        )
        price_data = []
        items = []

        try:
            for symbol in self.get_symbols():
                price = self.fetch_today_price(symbol.upper())
                items.append((symbol, price))

        except json.JSONDecodeError:
            logger.error(f'JSON decode error: {response.text}')
            return

        for symbol, price in items:
            try:
                yesterdays_price = self.fetch_yesterdays_price(symbol)
                percent_change_24h = ((price - yesterdays_price) / yesterdays_price) * 100
                change_24h = f'{percent_change_24h:.2f}%'
            except KeyError:
                # TODO: Add error logging
                continue

            item_data = dict(symbol=symbol, price=f'{price:.4f}', change_24h=str(change_24h))
            logger.info(json.dumps(item_data, indent=4))

            price_data.append(item_data)

        return price_data

    def fetch_yesterdays_price(self, symbol):
        # Yesterday date
        yesterday = date.today() - timedelta(days = 1)

        response = requests.get(
            f'{self.API}/v2/prices/{symbol}-{self.currency.upper()}/spot',
            params={'date': yesterday}
        )

        yesterdays_price = float(response.json().get('data', {}).get('amount'))

        logger.info(f'Yesterdays price for {symbol} is {yesterdays_price}')
        return yesterdays_price


class CoinMarketCap(PriceAPI):
    SANDBOX_API = 'https://sandbox-api.coinmarketcap.com'
    PRODUCTION_API = 'https://pro-api.coinmarketcap.com'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Confirm an API key is present
        try:
            self.api_key = os.environ['CMC_API_KEY']
        except KeyError:
            raise RuntimeError('CMC_API_KEY environment variable must be set.')

        self.env = (
            self.SANDBOX_API
            if os.environ.get('SANDBOX', '') == 'true'
            else self.PRODUCTION_API
        )

    @property
    def supported_currencies(self):
        return ["usd"]

    def fetch_price_data(self):
        """Fetch new price data from the CoinMarketCap API"""
        logger.info('`fetch_price_data` called.')

        response = requests.get(
            '{0}/v1/cryptocurrency/quotes/latest'.format(self.api),
            params={'symbol': self.get_symbols()},
            headers={'X-CMC_PRO_API_KEY': self.api_key},
        )
        price_data = []

        try:
            items = response.json().get('data', {}).items()
        except json.JSONDecodeError:
            logger.error(f'JSON decode error: {response.text}')
            return

        for symbol, data in items:
            try:
                price = f"${data['quote']['USD']['price']:,.2f}"
                change_24h = f"{data['quote']['USD']['percent_change_24h']:.1f}%"
            except KeyError:
                # TODO: Add error logging
                continue

            item_data = dict(symbol=symbol, price=price, change_24h=change_24h)
            logger.info(json.dumps(item_data, indent=4))

            price_data.append(item_data)

        return price_data


class CoinGecko(PriceAPI):
    API = 'https://api.coingecko.com/api/v3'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Fetch the coin list and cache data for our symbols
        response = requests.get(f'{self.API}/coins/list')

        # The CoinGecko API uses ids to fetch price data
        symbol_map = {}

        # Symbols is the list of symbols we want to fetch data for
        symbols = self.get_symbols()

        for coin in response.json():
            symbol = coin['symbol']
            # If we specified a name for our symbol, check for it
            name = self.get_name_for_symbol(symbol)
            if name is not None and name != coin['id']:
                continue
            if symbol in symbols:
                symbol_map[coin['id']] = symbol

        self.symbol_map = symbol_map

    @property
    def supported_currencies(self):
        return ["usd", "eur"]

    def fetch_price_data(self):
        """Fetch new price data from the CoinGecko API"""
        logger.info('`fetch_price_data` called.')
        logger.info(f'Fetching data for {self.symbol_map}.')

        # Make the API request
        response = requests.get(
            f'{self.API}/simple/price',
            params={
                'ids': ','.join(list(self.symbol_map.keys())),
                'vs_currencies': self.currency,
                'include_24hr_change': 'true',
            },
        )
        price_data = []

        logger.info(response.json())

        cur = self.currency
        cur_change = f"{cur}_24h_change"
        cur_symbol = "€" if cur == "eur" else "$"

        for coin_id, data in response.json().items():
            try:
                price = f"{cur_symbol}{data[cur]:,.4f}"
                change_24h = f"{data[cur_change]:.1f}%"
            except (KeyError, TypeError):
                logging.warn(f'api data not complete for {0}: {1}', coin_id, data)
                continue

            price_data.append(
                dict(
                    symbol=self.symbol_map[coin_id], price=price, change_24h=change_24h
                )
            )

        return price_data

#!/usr/bin/env python

from distutils.core import setup

setup(
    name='AsyncTicker',
    version='1.0',
    description='Asyncio Cryptocurrency Ticker',
    author='James Awesome',
    author_email='james@morelli.nyc',
    packages=[
        'async_ticker',
        'async_ticker.fonts'
    ],
    package_data={
        'async_ticker.fonts': ['async_ticker/fonts/*.bdf']
    },
    include_package_data=True,
    package_dir={
        '': 'src/'
    },
    install_requires=[
        'Pillow',
        'asyncio',
        'aiohttp',
        'attrs',
        'feedparser',
    ],
    scripts=[
        'scripts/crypto-ticker.py'
    ]
)

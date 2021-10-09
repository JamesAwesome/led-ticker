#!/usr/bin/env python

from distutils.core import setup

setup(
    name='AsyncTicker',
    version='1.0',
    description='Asyncio Cryptocurrency Ticker',
    author='James Awesome',
    author_email='james@morelli.nyc',
    packages=[
        'async_ticker'
    ],
    package_dir={
        '': 'src/'
    },
    requires=[
        'Pillow',
        'asyncio',
        'aiohttp',
        'attrs',
        'feedparser',
    ],
)

import os
import sys

sys.path.append(os.path.abspath(os.path.join(__file__, '..', '..')))

import asyncio
import pytest

import async_ticker


@pytest.mark.asyncio
async def test__enque_ticker_objects():
    test_queue = asyncio.Queue()
    test_iter = iter(range(0, 5))

    asyncio.create_task(
        async_ticker._enque_ticker_objects(test_iter, test_queue)
    )

    # Consume the same amount of items from the queue
    while not test_queue.empty():
        item = await test_queue.get()
        assert item

    # Ensure the queue is now empty
    assert test_queue.empty()

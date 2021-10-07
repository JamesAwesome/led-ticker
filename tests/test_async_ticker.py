import os
import sys

sys.path.append(os.path.abspath(os.path.join(__file__, '..', '..')))

import asyncio
import pytest

import async_ticker


@pytest.mark.asyncio
async def test__enque_ticker_objects():
    test_queue = asyncio.Queue()
    test_items = list(range(0, 5))
    test_iter = iter(test_items)

    # Create a task to enqueue items onto our queue
    asyncio.create_task(
        async_ticker._enque_ticker_objects(test_iter, test_queue)
    )

    # Make a list to store our results
    res_items = []

    # Leave some time to make sure the next object is on the queue
    res_items.append(await test_queue.get())

    # Get items until the queue is empty
    while not test_queue.empty():
        res_item = await test_queue.get()
        res_items.append(res_item)

        # Leave time for the next object to make it onto the queue
        await asyncio.sleep(0.05)

    assert res_items == test_items

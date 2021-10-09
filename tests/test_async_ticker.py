import os
import sys

import asyncio
import itertools
import pytest


from async_ticker import async_ticker


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

    # Block until we get the first item
    res_items.append(await test_queue.get())

    # Get items until the queue is empty
    while not test_queue.empty():
        res_item = await test_queue.get()
        res_items.append(res_item)

        # Leave time for the next object to make it onto the queue
        await asyncio.sleep(0.05)

    assert res_items == test_items


@pytest.mark.asyncio
async def test__build_ticker_iter():
    test_items = list(range(0, 5))
    test_title = 'test title'

    # Test with loop count 1
    test_iter = async_ticker._build_ticker_iter(test_items, loop_count=1)
    result_items = list(test_iter)

    assert result_items == test_items

    # Test with loop count 2
    test_iter = async_ticker._build_ticker_iter(test_items, loop_count=2)
    result_items = list(test_iter)

    assert result_items == (test_items * 2)

    # Test with loop count 1 & title
    test_iter = async_ticker._build_ticker_iter(test_items, title=test_title, loop_count=1)
    result_items = list(test_iter)

    assert result_items == [test_title] + test_items

    # Test with loop count 2 & title
    test_iter = async_ticker._build_ticker_iter(test_items, title=test_title, loop_count=2)
    result_items = list(test_iter)

    assert result_items == [test_title] + (test_items * 2)

    # Test with loop count 0 taking 5, then 10 -- items should repeat
    test_iter = async_ticker._build_ticker_iter(test_items, loop_count=0)
    result_items = list(itertools.islice(test_iter, len(test_items)))

    assert result_items == test_items

    result_items = list(itertools.islice(test_iter, (len(test_items) * 2)))

    assert result_items == (test_items * 2)

    # Test with loop count 0 taking 5, then 10 with title -- items should repeat
    # however, the title should not
    test_iter = async_ticker._build_ticker_iter(test_items, title=test_title, loop_count=0)

    # take one extra for the title
    result_items = list(itertools.islice(test_iter, (len(test_items) + 1)))

    assert result_items == [test_title] + test_items

    test_iter = async_ticker._build_ticker_iter(test_items, title=test_title, loop_count=0)

    # take one extra for the title
    result_items = list(itertools.islice(test_iter, (len(test_items) * 2) + 1))

    assert result_items == [test_title] + (test_items * 2)

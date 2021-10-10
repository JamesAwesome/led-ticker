#!/usr/bin/env python3

import mock
import pytest


@pytest.fixture
def mock_canvas():
    mock_canvas = mock.Mock()
    mock_canvas.width = 160
    return mock_canvas

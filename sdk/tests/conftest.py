import pytest


@pytest.fixture
def tapiod_base_url():
    return "http://localhost:4001"


@pytest.fixture
def tapiod_api_key():
    return "test-key"

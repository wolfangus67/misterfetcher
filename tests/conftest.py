"""
Pytest configuration and shared fixtures for streams-prefetcher tests.
"""
import pytest
import sys
import os
import tempfile
import shutil
import time
from pathlib import Path

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


# ============================================================================
# Pytest Configuration
# ============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "serial: mark test to run serially (not in parallel with other tests)"
    )
    config.addinivalue_line(
        "markers", "job_test: mark test that starts/manages jobs (requires serialization)"
    )


# ============================================================================
# Job Management Fixtures
# ============================================================================

@pytest.fixture(scope="function")
def ensure_job_idle():
    """
    Ensure no job is running before and after the test.
    Use this for tests that need to start jobs.
    """
    try:
        import requests
        BASE_URL = f"http://{os.getenv('STREAMS_PREFETCHER_HOST', 'localhost:5000')}"

        # Cancel any running job before test
        try:
            response = requests.get(f'{BASE_URL}/api/job/status', timeout=5)
            if response.status_code == 200:
                status = response.json()['status']['status']
                if status in ['running', 'pausing', 'paused', 'resuming']:
                    requests.post(f'{BASE_URL}/api/job/cancel', timeout=5)
                    # Wait for cancellation to complete (up to 10 seconds)
                    for _ in range(20):
                        time.sleep(0.5)
                        response = requests.get(f'{BASE_URL}/api/job/status', timeout=5)
                        current_status = response.json()['status']['status']
                        if current_status in ['idle', 'cancelled', 'completed', 'failed']:
                            break
                    # Add extra delay to ensure job thread is fully terminated
                    # Long-running job tests need substantial cleanup time
                    time.sleep(10)
        except requests.exceptions.ConnectionError:
            pass  # Container not running, skip cleanup

        yield

        # Cancel any running job after test
        try:
            response = requests.get(f'{BASE_URL}/api/job/status', timeout=5)
            if response.status_code == 200:
                status = response.json()['status']['status']
                if status in ['running', 'pausing', 'paused', 'resuming']:
                    requests.post(f'{BASE_URL}/api/job/cancel', timeout=5)
                    # Wait for cancellation
                    for _ in range(20):
                        time.sleep(0.5)
                        response = requests.get(f'{BASE_URL}/api/job/status', timeout=5)
                        current_status = response.json()['status']['status']
                        if current_status in ['idle', 'cancelled', 'completed', 'failed']:
                            break
                    # Add extra delay to ensure job thread is fully terminated
                    # Long-running job tests need substantial cleanup time
                    time.sleep(10)
        except requests.exceptions.ConnectionError:
            pass
    except ImportError:
        # requests not installed in this environment
        yield


# ============================================================================
# Data Fixtures
# ============================================================================

@pytest.fixture
def temp_data_dir():
    """Create a temporary data directory for testing."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)

@pytest.fixture
def sample_movie_item():
    """Sample movie catalog item for testing."""
    return {
        'id': 'tt1234567',
        'type': 'movie',
        'title': 'Test Movie',
        'year': 2023,
        'poster': 'https://example.com/poster.jpg'
    }

@pytest.fixture
def sample_series_item():
    """Sample series catalog item for testing."""
    return {
        'id': 'tt7654321',
        'type': 'series',
        'title': 'Test Series',
        'year': 2023,
        'poster': 'https://example.com/poster.jpg'
    }

@pytest.fixture
def sample_episode_item():
    """Sample episode data for testing."""
    return {
        'id': 'tt7654321:1:1',
        'title': 'Episode 1',
        'season': 1,
        'episode': 1,
        'released': '2023-01-01'
    }

@pytest.fixture
def sample_addon_config():
    """Sample addon configuration for testing."""
    return [
        {
            'url': 'http://test-addon.com/stremio/v1',
            'type': 'both',
            'name': 'Test Addon'
        }
    ]

@pytest.fixture
def sample_catalog():
    """Sample catalog for testing."""
    return {
        'id': 'test-catalog',
        'type': 'movie',
        'name': 'Test Catalog',
        'extra': [
            {'name': 'search'},
            {'name': 'skip', 'isRequired': False}
        ]
    }

@pytest.fixture
def mock_manifest():
    """Sample addon manifest for testing."""
    return {
        'name': 'Test Addon',
        'id': 'test.addon',
        'version': '1.0.0',
        'description': 'Test addon for unit tests',
        'catalogs': [
            {
                'id': 'test-movies',
                'type': 'movie',
                'name': 'Test Movies'
            },
            {
                'id': 'test-series',
                'type': 'series',
                'name': 'Test Series'
            }
        ],
        'resources': ['catalog', 'stream'],
        'types': ['movie', 'series'],
        'idPrefixes': ['tt']
    }
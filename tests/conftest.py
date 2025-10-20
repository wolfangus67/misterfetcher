"""
Pytest configuration and shared fixtures for streams-prefetcher tests.
"""
import pytest
import sys
import os
import tempfile
import shutil
from pathlib import Path

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

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
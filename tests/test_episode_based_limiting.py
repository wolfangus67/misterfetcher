"""
Integration tests for episode-based limiting feature.
Tests the complete workflow of episode limits, series counters, and cache ID formats.
"""
import pytest
import requests
import time
import json
import os


# Get base URL from environment variable (defaults to localhost:5000 for host testing)
# Set STREAMS_PREFETCHER_HOST=streams-prefetcher:5000 when running in Docker
BASE_URL = f"http://{os.getenv('STREAMS_PREFETCHER_HOST', 'localhost:5000')}"


@pytest.mark.serial
class TestEpisodeBasedLimiting:
    """Test episode-based limiting functionality."""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self, ensure_job_idle):
        """Setup and teardown for each test."""
        try:
            # Backup original config
            response = requests.get(f'{BASE_URL}/api/config', timeout=5)
            self.original_config = response.json()['config']
            yield
            # Restore original config
            requests.post(f'{BASE_URL}/api/config', json=self.original_config, timeout=5)
        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - integration test skipped")

    def test_episodes_global_limit_enforcement(self):
        """Test that episodes global limit is enforced correctly."""
        try:
            # Configure test with low episode limit
            test_config = self.original_config.copy()
            test_config['episodes_global_limit'] = 10
            test_config['movies_global_limit'] = 5
            test_config['episodes_per_catalog'] = 50
            test_config['delay'] = 0  # Fast testing

            # Save config
            response = requests.post(f'{BASE_URL}/api/config', json=test_config, timeout=5)
            assert response.status_code == 200

            # Start job
            response = requests.post(f'{BASE_URL}/api/job/run', timeout=5)
            assert response.status_code == 200

            # Wait for completion (max 3 minutes)
            for _ in range(180):
                time.sleep(1)
                response = requests.get(f'{BASE_URL}/api/job/status', timeout=5)
                status = response.json()['status']

                if status['status'] in ['completed', 'failed', 'cancelled']:
                    break

            # Verify episode limit was respected
            final_response = requests.get(f'{BASE_URL}/api/job/status', timeout=5)
            final_status = final_response.json()['status']

            if 'summary' in final_status:
                stats = final_status['summary'].get('statistics', {})
                episodes_prefetched = stats.get('episodes_prefetched', 0)

                # Episodes should not exceed the global limit
                assert episodes_prefetched <= 10, f"Episodes ({episodes_prefetched}) exceeded global limit (10)"

        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - integration test skipped")

    def test_episodes_per_catalog_limit(self):
        """Test that episodes per catalog limit is enforced."""
        try:
            # Configure with per-catalog limit
            test_config = self.original_config.copy()
            test_config['episodes_global_limit'] = -1  # Unlimited global
            test_config['episodes_per_catalog'] = 5  # Limit per catalog
            test_config['delay'] = 0

            response = requests.post(f'{BASE_URL}/api/config', json=test_config, timeout=5)
            assert response.status_code == 200

            # Start job
            response = requests.post(f'{BASE_URL}/api/job/run', timeout=5)
            assert response.status_code == 200

            # Wait for completion
            for _ in range(180):
                time.sleep(1)
                response = requests.get(f'{BASE_URL}/api/job/status', timeout=5)
                status = response.json()['status']

                if status['status'] in ['completed', 'failed', 'cancelled']:
                    break

            # Check that series catalogs respected the per-catalog limit
            final_response = requests.get(f'{BASE_URL}/api/job/status', timeout=5)
            final_status = final_response.json()['status']

            if 'summary' in final_status:
                catalogs = final_status['summary'].get('processed_catalogs', [])

                for catalog in catalogs:
                    if catalog['type'] == 'series':
                        # Each series catalog should have ≤ 5 episodes prefetched
                        success_count = catalog['success_count']
                        assert success_count <= 5, f"Series catalog '{catalog['name']}' prefetched {success_count} (limit: 5)"

        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - integration test skipped")

    def test_series_supplementary_counter(self):
        """Test that series counter increments as supplementary stat."""
        try:
            test_config = self.original_config.copy()
            test_config['episodes_global_limit'] = 20
            test_config['delay'] = 0

            response = requests.post(f'{BASE_URL}/api/config', json=test_config, timeout=5)
            assert response.status_code == 200

            response = requests.post(f'{BASE_URL}/api/job/run', timeout=5)
            assert response.status_code == 200

            # Wait for completion
            for _ in range(180):
                time.sleep(1)
                response = requests.get(f'{BASE_URL}/api/job/status', timeout=5)
                status = response.json()['status']

                if status['status'] in ['completed', 'failed', 'cancelled']:
                    break

            # Verify series counter
            final_response = requests.get(f'{BASE_URL}/api/job/status', timeout=5)
            final_status = final_response.json()['status']

            if 'summary' in final_status:
                stats = final_status['summary'].get('statistics', {})
                series_prefetched = stats.get('series_prefetched', 0)
                episodes_prefetched = stats.get('episodes_prefetched', 0)

                # If episodes were prefetched, series counter should be >= 1
                if episodes_prefetched > 0:
                    assert series_prefetched >= 1, "Series counter should increment when episodes are prefetched"

                # Series count should be less than or equal to episodes (can't have more series than episodes)
                assert series_prefetched <= episodes_prefetched, "Series count cannot exceed episode count"

        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - integration test skipped")

    def test_episode_cache_id_format(self):
        """Test that episode cache IDs use correct format: series_id:season:episode."""
        try:
            # This test verifies the cache ID format by checking the database
            # We can't directly access the database in integration tests,
            # but we can verify the format through the progress tracking

            test_config = self.original_config.copy()
            test_config['episodes_global_limit'] = 5
            test_config['delay'] = 0

            response = requests.post(f'{BASE_URL}/api/config', json=test_config, timeout=5)
            assert response.status_code == 200

            response = requests.post(f'{BASE_URL}/api/job/run', timeout=5)
            assert response.status_code == 200

            # Monitor progress and check current_imdb_id format
            episode_ids_seen = []

            for _ in range(60):
                time.sleep(1)
                response = requests.get(f'{BASE_URL}/api/job/status', timeout=5)
                status = response.json()['status']

                if status['status'] == 'running':
                    progress = status.get('progress', {})
                    current_id = progress.get('current_imdb_id', '')
                    current_type = progress.get('current_item_type', '')

                    # If processing an episode, check ID format
                    if current_type == 'episode' and current_id and current_id not in episode_ids_seen:
                        episode_ids_seen.append(current_id)

                        # Episode IDs should have format: tt1234567:1:1
                        parts = current_id.split(':')
                        assert len(parts) == 3, f"Episode ID '{current_id}' should have 3 parts (series:season:episode)"
                        assert parts[0].startswith('tt'), f"Series ID should start with 'tt', got: {parts[0]}"
                        assert parts[1].isdigit(), f"Season should be numeric, got: {parts[1]}"
                        assert parts[2].isdigit(), f"Episode should be numeric, got: {parts[2]}"

                elif status['status'] in ['completed', 'failed', 'cancelled']:
                    break

            # We should have seen at least one episode ID
            assert len(episode_ids_seen) > 0, "Should have processed at least one episode"

        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - integration test skipped")

    def test_progress_stats_structure(self):
        """Test that progress stats include all episode-related fields."""
        try:
            response = requests.post(f'{BASE_URL}/api/job/run', timeout=5)
            assert response.status_code == 200

            time.sleep(2)  # Let job start

            response = requests.get(f'{BASE_URL}/api/job/status', timeout=5)
            status = response.json()['status']

            # Cancel job if running
            if status['status'] == 'running':
                progress = status.get('progress', {})

                # Verify all required fields exist
                required_fields = [
                    'movies_prefetched',
                    'episodes_prefetched',
                    'series_prefetched',
                    'movies_limit',
                    'episodes_limit'
                ]

                for field in required_fields:
                    assert field in progress, f"Progress should include '{field}' field"

                # Verify data types
                assert isinstance(progress['movies_prefetched'], int)
                assert isinstance(progress['episodes_prefetched'], int)
                assert isinstance(progress['series_prefetched'], int)
                assert isinstance(progress['movies_limit'], int)
                assert isinstance(progress['episodes_limit'], int)

                # Cancel the job
                requests.post(f'{BASE_URL}/api/job/cancel', timeout=5)

        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - integration test skipped")

    def test_config_migration_from_old_keys(self):
        """Test that old series-based config keys are migrated correctly."""
        try:
            # Create config with old keys
            old_config = {
                'addon_urls': self.original_config.get('addon_urls', []),
                'series_global_limit': 15,  # Old key
                'series_per_catalog': 10,  # Old key
                'items_per_mixed_catalog': 5,  # Old key
                'movies_global_limit': 20,
                'movies_per_catalog': 10,
                'delay': 0,
                'network_request_timeout': 30,
                'proxy': '',
                'randomize_catalog_processing': False,
                'randomize_item_prefetching': False,
                'cache_validity': 1209600,
                'max_execution_time': 14400,
                'enable_logging': True,
                'catalog_selection': {},
                'saved_catalogs': [],
                'schedule': {'enabled': False, 'schedules': []},
                'cache_uncached_streams': {
                    'enabled': False,
                    'cached_stream_regex': '⚡',
                    'skip_streams_regex': '🎯',
                    'max_successful_cache_requests_per_item': 1,
                    'max_cache_request_attempts_per_item': 3,
                    'max_cache_requests_global': 50,
                    'cached_streams_count_threshold': 0
                },
                'max_movie_items_per_catalog_fetch': 100,
                'max_series_items_per_catalog_fetch': 50,
                'max_mixed_items_per_catalog_fetch': 50
            }

            # Save config with old keys
            response = requests.post(f'{BASE_URL}/api/config', json=old_config, timeout=5)
            assert response.status_code == 200

            # Retrieve config and verify migration
            response = requests.get(f'{BASE_URL}/api/config', timeout=5)
            loaded_config = response.json()['config']

            # New keys should exist with migrated values
            assert 'episodes_global_limit' in loaded_config
            assert 'episodes_per_catalog' in loaded_config
            assert 'episodes_per_mixed_catalog' in loaded_config

            # Values should be migrated (1:1 ratio)
            assert loaded_config['episodes_global_limit'] == 15
            assert loaded_config['episodes_per_catalog'] == 10
            assert loaded_config['episodes_per_mixed_catalog'] == 5

        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - integration test skipped")


@pytest.mark.serial
class TestMultipleCatalogTypes:
    """Test behavior with multiple catalog types."""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self, ensure_job_idle):
        """Setup and teardown for each test."""
        try:
            response = requests.get(f'{BASE_URL}/api/config', timeout=5)
            self.original_config = response.json()['config']
            yield
            requests.post(f'{BASE_URL}/api/config', json=self.original_config, timeout=5)
        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - integration test skipped")

    def test_mixed_catalog_episode_counting(self):
        """Test that mixed catalogs count items correctly."""
        try:
            test_config = self.original_config.copy()
            test_config['episodes_per_mixed_catalog'] = 3  # Small limit for testing
            test_config['delay'] = 0

            response = requests.post(f'{BASE_URL}/api/config', json=test_config, timeout=5)
            assert response.status_code == 200

            response = requests.post(f'{BASE_URL}/api/job/run', timeout=5)
            assert response.status_code == 200

            # Wait for completion
            for _ in range(180):
                time.sleep(1)
                response = requests.get(f'{BASE_URL}/api/job/status', timeout=5)
                status = response.json()['status']

                if status['status'] in ['completed', 'failed', 'cancelled']:
                    break

            # Verify mixed catalog limits
            final_response = requests.get(f'{BASE_URL}/api/job/status', timeout=5)
            final_status = final_response.json()['status']

            if 'summary' in final_status:
                catalogs = final_status['summary'].get('processed_catalogs', [])

                for catalog in catalogs:
                    if catalog['type'] == 'mixed':
                        # Mixed catalogs should respect episodes_per_mixed_catalog limit
                        # (movies + episodes as individual items)
                        success_count = catalog['success_count']
                        assert success_count <= 3, f"Mixed catalog '{catalog['name']}' prefetched {success_count} items (limit: 3)"

        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - integration test skipped")

    def test_unlimited_limits(self):
        """Test that -1 (unlimited) limits work correctly."""
        try:
            test_config = self.original_config.copy()
            test_config['movies_global_limit'] = -1
            test_config['episodes_global_limit'] = -1
            test_config['movies_per_catalog'] = -1
            test_config['episodes_per_catalog'] = -1
            test_config['delay'] = 0

            response = requests.post(f'{BASE_URL}/api/config', json=test_config, timeout=5)
            assert response.status_code == 200

            # Verify config was saved with -1 values
            response = requests.get(f'{BASE_URL}/api/config', timeout=5)
            loaded_config = response.json()['config']

            assert loaded_config['movies_global_limit'] == -1
            assert loaded_config['episodes_global_limit'] == -1
            assert loaded_config['movies_per_catalog'] == -1
            assert loaded_config['episodes_per_catalog'] == -1

        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - integration test skipped")

"""
Test all API endpoints functionality.
Tests based on the manual API tests we performed.
"""
import pytest
import requests
import json
import time
import os
from unittest.mock import Mock, patch, MagicMock


# Get base URL from environment variable (defaults to localhost:5000 for host testing)
# Set STREAMS_PREFETCHER_HOST=streams-prefetcher:5000 when running in Docker
BASE_URL = f"http://{os.getenv('STREAMS_PREFETCHER_HOST', 'localhost:5000')}"


class TestHealthEndpoint:
    """Test /api/health endpoint."""

    def test_health_check_success(self):
        """Test successful health check."""
        try:
            response = requests.get(f'{BASE_URL}/api/health', timeout=5)
            assert response.status_code == 200

            data = response.json()
            assert 'success' in data
            assert data['success'] is True
            assert 'status' in data
            assert data['status'] == 'healthy'
            assert 'timestamp' in data
        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - test skipped")

    def test_health_check_response_format(self):
        """Test health check response format."""
        try:
            response = requests.get(f'{BASE_URL}/api/health', timeout=5)
            assert response.status_code == 200

            data = response.json()
            required_fields = ['success', 'status', 'timestamp']
            for field in required_fields:
                assert field in data, f"Missing field: {field}"

            # Check timestamp format
            timestamp = data['timestamp']
            assert 'T' in timestamp  # ISO format
        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - test skipped")


class TestConfigEndpoints:
    """Test /api/config endpoints."""

    def test_get_config_success(self):
        """Test successful config retrieval."""
        try:
            response = requests.get(f'{BASE_URL}/api/config', timeout=5)
            assert response.status_code == 200

            data = response.json()
            assert 'success' in data
            assert data['success'] is True
            assert 'config' in data

            config = data['config']
            required_fields = [
                'addon_urls',
                'movies_global_limit',
                'series_global_limit',
                'movies_per_catalog',
                'series_per_catalog',
                'delay',
                'saved_catalogs'
            ]

            for field in required_fields:
                assert field in config, f"Missing config field: {field}"
        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - test skipped")

    def test_post_config_validation(self):
        """Test config validation on POST."""
        try:
            # Get valid config first
            response = requests.get(f'{BASE_URL}/api/config', timeout=5)
            valid_config = response.json()['config']

            # Test with missing required fields
            incomplete_config = {
                'addon_urls': []  # Missing many required fields
            }

            response = requests.post(f'{BASE_URL}/api/config', json=incomplete_config, timeout=5)
            assert response.status_code == 400

            error_data = response.json()
            assert 'error' in error_data
            assert 'validation failed' in error_data['error'].lower()

            # Test with complete valid config
            response = requests.post(f'{BASE_URL}/api/config', json=valid_config, timeout=5)
            assert response.status_code == 200

            success_data = response.json()
            assert 'success' in success_data
            assert success_data['success'] is True
        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - test skipped")

    def test_post_config_addon_validation(self):
        """Test addon URL validation in config."""
        try:
            # Test with invalid addon configuration
            invalid_config = {
                'addon_urls': [
                    {'url': '', 'type': 'both'},  # Empty URL
                    {'url': 'not-a-url', 'type': 'invalid'},  # Invalid URL and type
                ],
                'movies_global_limit': 100,
                'series_global_limit': 10,
                'movies_per_catalog': 50,
                'series_per_catalog': 3,
                'items_per_mixed_catalog': 20,
                'delay': 2,
                'network_request_timeout': 30,
                'proxy': '',
                'randomize_catalog_processing': False,
                'randomize_item_prefetching': False,
                'cache_validity': 604800,
                'max_execution_time': 5400,
                'enable_logging': False,
                'saved_catalogs': []
            }

            response = requests.post(f'{BASE_URL}/api/config', json=invalid_config, timeout=5)
            assert response.status_code == 400

            error_data = response.json()
            assert 'error' in error_data
        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - test skipped")


class TestJobEndpoints:
    """Test job management endpoints."""

    def test_get_job_status(self):
        """Test getting job status."""
        try:
            response = requests.get(f'{BASE_URL}/api/job/status', timeout=5)
            assert response.status_code == 200

            data = response.json()
            assert 'success' in data
            assert data['success'] is True
            assert 'status' in data

            status = data['status']
            required_fields = ['status']
            for field in required_fields:
                assert field in status

            # Status should be one of expected values
            expected_statuses = ['idle', 'running', 'completed', 'failed', 'cancelled', 'pausing', 'paused', 'resuming']
            assert status['status'] in expected_statuses
        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - test skipped")

    def test_post_job_run(self):
        """Test starting a job."""
        try:
            # Check initial status
            response = requests.get(f'{BASE_URL}/api/job/status', timeout=5)
            initial_status = response.json()['status']['status']

            # Only run if idle
            if initial_status == 'idle':
                response = requests.post(f'{BASE_URL}/api/job/run', timeout=5)
                assert response.status_code == 200

                data = response.json()
                assert 'success' in data
                assert data['success'] is True

                # Give it time to start
                time.sleep(2)

                # Check status changed
                response = requests.get(f'{BASE_URL}/api/job/status', timeout=5)
                new_status = response.json()['status']['status']
                assert new_status in ['running', 'completed', 'failed']

                # Cancel if still running
                if new_status == 'running':
                    requests.post(f'{BASE_URL}/api/job/cancel', timeout=5)
            else:
                pytest.skip(f"Job not idle (status: {initial_status}) - test skipped")
        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - test skipped")

    def test_post_job_cancel(self):
        """Test cancelling a job."""
        try:
            # Try to cancel (will succeed if job running, fail if idle)
            response = requests.post(f'{BASE_URL}/api/job/cancel', timeout=5)
            # Status code could be 200 (success) or 400 (no job running)
            assert response.status_code in [200, 400]

            if response.status_code == 200:
                data = response.json()
                assert 'success' in data
                assert data['success'] is True
        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - test skipped")

    def test_post_job_pause_resume(self):
        """Test pause/resume functionality."""
        try:
            # Check if job is running first
            response = requests.get(f'{BASE_URL}/api/job/status', timeout=5)
            status = response.json()['status']['status']

            if status == 'running':
                # Test pause
                response = requests.post(f'{BASE_URL}/api/job/pause', timeout=5)
                assert response.status_code == 200

                # Wait a moment
                time.sleep(1)

                # Test resume
                response = requests.post(f'{BASE_URL}/api/job/resume', timeout=5)
                assert response.status_code == 200
            else:
                pytest.skip(f"Job not running (status: {status}) - pause/resume test skipped")
        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - test skipped")


class TestCatalogEndpoints:
    """Test catalog-related endpoints."""

    @patch('requests.get')
    def test_load_catalogs_endpoint(self, mock_get, mock_manifest):
        """Test catalog loading functionality."""
        # This tests the internal load_catalogs function
        try:
            from web_app import load_catalogs
        except ModuleNotFoundError as e:
            if 'flask' in str(e).lower():
                pytest.skip("Flask not installed - skipping web_app test")
            raise

        # Mock successful manifest response
        mock_response = Mock()
        mock_response.json.return_value = mock_manifest
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # Test loading catalogs
        catalogs = load_catalogs()
        assert isinstance(catalogs, list)

        # Check catalog structure
        for catalog in catalogs:
            assert 'id' in catalog
            assert 'name' in catalog
            assert 'type' in catalog
            assert 'addon_name' in catalog
            assert 'addon_url' in catalog
            assert 'enabled' in catalog
            assert 'order' in catalog

            # Verify addon name is extracted (Addon object usage)
            assert catalog['addon_name'] == mock_manifest['name']

    def test_catalog_config_structure(self):
        """Test that catalog configuration has correct structure."""
        try:
            response = requests.get(f'{BASE_URL}/api/config', timeout=5)
            assert response.status_code == 200

            config = response.json()['config']
            saved_catalogs = config.get('saved_catalogs', [])

            # Check catalog structure
            for catalog in saved_catalogs:
                required_fields = ['id', 'name', 'type', 'addon_name', 'addon_url', 'enabled', 'order']
                for field in required_fields:
                    assert field in catalog, f"Missing catalog field: {field}"

                # Check type is valid
                assert catalog['type'] in ['movie', 'series', 'mixed']

                # Check addon_url is not empty
                assert catalog['addon_url'] and len(catalog['addon_url']) > 0

                # Check enabled is boolean
                assert isinstance(catalog['enabled'], bool)

                # Check order is integer
                assert isinstance(catalog['order'], int)
        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - test skipped")


class TestEventsEndpoint:
    """Test Server-Sent Events endpoint."""

    def test_events_endpoint_accessible(self):
        """Test that events endpoint accepts connections."""
        try:
            # SSE endpoint should always accept connections
            response = requests.get(f'{BASE_URL}/api/events', timeout=1, stream=True)
            assert response.status_code == 200

            # Check content type
            content_type = response.headers.get('content-type', '')
            assert 'text/event-stream' in content_type

            # Don't wait for data - just test connectivity
        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - test skipped")
        except requests.exceptions.ReadTimeout:
            # Timeout is expected for SSE
            pass

    def test_events_endpoint_format(self):
        """Test SSE event format."""
        try:
            response = requests.get(f'{BASE_URL}/api/events', timeout=2, stream=True)
            assert response.status_code == 200

            # Try to read first few lines
            lines = []
            try:
                for i, line in enumerate(response.iter_lines(decode_unicode=True)):
                    if i >= 3:  # Only read first 3 lines
                        break
                    lines.append(line)
            except (requests.exceptions.ReadTimeout, StopIteration):
                pass  # Expected for SSE

            # Check format if we got any data
            for line in lines:
                if line:
                    # SSE lines should start with "data:", "event:", "id:", or "retry:"
                    assert any(line.startswith(prefix) for prefix in ['data:', 'event:', 'id:', 'retry:'])
        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - test skipped")
        except requests.exceptions.ReadTimeout:
            # Timeout is expected
            pass


class TestErrorHandling:
    """Test API error handling."""

    def test_invalid_endpoint(self):
        """Test handling of invalid endpoints."""
        try:
            response = requests.get(f'{BASE_URL}/api/invalid_endpoint', timeout=5)
            assert response.status_code == 404

            error_data = response.json()
            assert 'error' in error_data
            assert 'success' in error_data
            assert error_data['success'] is False
        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - test skipped")

    def test_invalid_method(self):
        """Test handling of invalid HTTP methods."""
        try:
            # Try POST on GET endpoint
            response = requests.post(f'{BASE_URL}/api/health', timeout=5)
            assert response.status_code == 405  # Method Not Allowed
        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - test skipped")

    def test_malformed_json(self):
        """Test handling of malformed JSON in POST requests."""
        try:
            # Send invalid JSON
            response = requests.post(
                f'{BASE_URL}/api/config',
                data='not valid json',
                headers={'Content-Type': 'application/json'},
                timeout=5
            )
            assert response.status_code == 400
        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - test skipped")

    def test_missing_content_type(self):
        """Test handling of requests without proper content type."""
        try:
            # Send JSON without content-type header
            response = requests.post(
                f'{BASE_URL}/api/config',
                json={'delay': 5},
                headers={},
                timeout=5
            )
            # Should still work (Flask handles this)
            assert response.status_code in [200, 400]
        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - test skipped")


class TestAPIResponseFormats:
    """Test that API responses follow consistent format."""

    def test_success_response_format(self):
        """Test success response format."""
        try:
            # Test GET endpoint
            response = requests.get(f'{BASE_URL}/api/health', timeout=5)
            assert response.status_code == 200

            data = response.json()
            assert 'success' in data
            assert isinstance(data['success'], bool)
            assert data['success'] is True
        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - test skipped")

    def test_error_response_format(self):
        """Test error response format."""
        try:
            # Test invalid endpoint for error response
            response = requests.get(f'{BASE_URL}/api/invalid', timeout=5)
            assert response.status_code == 404

            data = response.json()
            assert 'success' in data
            assert isinstance(data['success'], bool)
            assert data['success'] is False
            assert 'error' in data
            assert isinstance(data['error'], str)
            assert len(data['error']) > 0
        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - test skipped")

    def test_cors_headers(self):
        """Test that CORS headers are present."""
        try:
            response = requests.options(f'{BASE_URL}/api/health', timeout=5)
            # Should have CORS headers
            cors_headers = [
                'Access-Control-Allow-Origin',
                'Access-Control-Allow-Methods',
                'Access-Control-Allow-Headers'
            ]

            for header in cors_headers:
                assert header in response.headers
        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - test skipped")
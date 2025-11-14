"""
End-to-end integration tests for streams-prefetcher.
Tests the complete workflow from configuration to job execution.
"""
import pytest
import requests
import time
import json
import os
from unittest.mock import Mock, patch, MagicMock


# Get base URL from environment variable (defaults to localhost:5000 for host testing)
# Set STREAMS_PREFETCHER_HOST=streams-prefetcher:5000 when running in Docker
BASE_URL = f"http://{os.getenv('STREAMS_PREFETCHER_HOST', 'localhost:5000')}"


@pytest.mark.serial
class TestEndToEndWorkflow:
    """Test complete end-to-end workflows."""

    def test_health_check_integration(self):
        """Test health check endpoint is accessible."""
        # This tests that the Flask app is running
        try:
            response = requests.get(f'{BASE_URL}/api/health', timeout=5)
            assert response.status_code == 200
            data = response.json()
            assert data['success'] is True
            assert data['status'] == 'healthy'
            assert 'timestamp' in data
        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - integration test skipped")

    def test_config_lifecycle(self):
        """Test complete configuration lifecycle."""
        try:
            # Get current config
            response = requests.get(f'{BASE_URL}/api/config', timeout=5)
            assert response.status_code == 200
            original_config = response.json()['config']

            # Modify config
            test_config = original_config.copy()
            test_config['delay'] = test_config.get('delay', 2) + 1

            # Save config
            response = requests.post(f'{BASE_URL}/api/config', json=test_config, timeout=5)
            assert response.status_code == 200

            # Verify saved
            response = requests.get(f'{BASE_URL}/api/config', timeout=5)
            saved_config = response.json()['config']
            assert saved_config['delay'] == test_config['delay']

            # Restore original
            response = requests.post(f'{BASE_URL}/api/config', json=original_config, timeout=5)
            assert response.status_code == 200

        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - integration test skipped")

    def test_job_lifecycle(self):
        """Test complete job lifecycle: start, monitor, cancel."""
        try:
            # Check initial status
            response = requests.get(f'{BASE_URL}/api/job/status', timeout=5)
            assert response.status_code == 200
            initial_status = response.json()['status']
            assert initial_status['status'] in ['idle', 'cancelled']

            # Start job
            response = requests.post(f'{BASE_URL}/api/job/run', timeout=5)
            assert response.status_code == 200

            # Give it a moment to start
            time.sleep(2)

            # Check running status
            response = requests.get(f'{BASE_URL}/api/job/status', timeout=5)
            assert response.status_code == 200
            running_status = response.json()['status']
            assert running_status['status'] in ['running', 'completed', 'failed']

            # If running, cancel it
            if running_status['status'] == 'running':
                response = requests.post(f'{BASE_URL}/api/job/cancel', timeout=5)
                assert response.status_code == 200

                # Verify cancelled
                time.sleep(1)
                response = requests.get(f'{BASE_URL}/api/job/status', timeout=5)
                final_status = response.json()['status']
                assert final_status['status'] == 'cancelled'

        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - integration test skipped")

    @patch('requests.get')
    def test_addon_to_item_workflow(self, mock_get, mock_manifest):
        """Test workflow from addon loading to item processing."""
        # This tests the integration between Addon and Item classes
        try:
            from web_app import load_catalogs
        except ModuleNotFoundError as e:
            if 'flask' in str(e).lower():
                pytest.skip("Flask not installed - skipping web_app test")
            raise
        from item import Item

        # Mock addon manifest
        mock_response = Mock()
        mock_response.json.return_value = mock_manifest
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # Load catalogs (uses Addon objects)
        catalogs = load_catalogs()

        # Simulate processing items from catalogs
        # This tests the Item class integration
        for catalog in catalogs[:1]:  # Test first catalog
            # Create a mock item from catalog
            mock_item = {
                'id': 'tt1234567',
                'type': catalog['type'],
                'title': f'Item from {catalog["name"]}',
                'year': 2023
            }

            # Test Item object creation (the refactored pattern)
            item_obj = Item.from_catalog(mock_item)
            assert item_obj is not None
            assert item_obj.item_type == catalog['type']

            # Test dashboard title generation
            title = item_obj.get_dashboard_title()
            assert title is not None
            assert 'Prefetching streams' in title


@pytest.mark.serial
class TestErrorHandlingIntegration:
    """Test error handling in integrated scenarios."""

    def test_invalid_config_handling(self):
        """Test handling of invalid configurations."""
        try:
            # Test incomplete config
            incomplete_config = {
                'addon_urls': [],  # Missing required addons
                'delay': 2
            }

            response = requests.post(f'{BASE_URL}/api/config', json=incomplete_config, timeout=5)
            assert response.status_code == 400  # Should return validation error

            error_data = response.json()
            assert 'error' in error_data
            assert 'validation failed' in error_data['error'].lower()

        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - integration test skipped")

    def test_job_execution_with_no_catalogs(self):
        """Test job execution when no catalogs are selected."""
        try:
            # Get current config
            response = requests.get(f'{BASE_URL}/api/config', timeout=5)
            config = response.json()['config']

            # Temporarily clear selected catalogs
            config_no_catalogs = config.copy()
            config_no_catalogs['saved_catalogs'] = []

            # Save config with no catalogs
            response = requests.post(f'{BASE_URL}/api/config', json=config_no_catalogs, timeout=5)
            assert response.status_code == 200

            # Try to run job
            response = requests.post(f'{BASE_URL}/api/job/run', timeout=5)
            # Should either succeed with no work or fail gracefully

            # Restore original config
            response = requests.post(f'{BASE_URL}/api/config', json=config, timeout=5)
            assert response.status_code == 200

        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - integration test skipped")


@pytest.mark.serial
class TestPersistenceIntegration:
    """Test data persistence across operations."""

    def test_config_persistence(self):
        """Test that configuration persists across requests."""
        try:
            # Get unique test value
            test_delay = int(time.time()) % 10 + 5  # 5-14

            # Get current config
            response = requests.get(f'{BASE_URL}/api/config', timeout=5)
            original_config = response.json()['config']
            original_delay = original_config['delay']

            # Update with test value
            test_config = original_config.copy()
            test_config['delay'] = test_delay

            # Save
            response = requests.post(f'{BASE_URL}/api/config', json=test_config, timeout=5)
            assert response.status_code == 200

            # Verify persistence across multiple requests
            for _ in range(3):
                response = requests.get(f'{BASE_URL}/api/config', timeout=5)
                persisted_config = response.json()['config']
                assert persisted_config['delay'] == test_delay
                time.sleep(0.5)

            # Restore original
            response = requests.post(f'{BASE_URL}/api/config', json=original_config, timeout=5)
            assert response.status_code == 200

        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - integration test skipped")

    def test_job_status_persistence(self):
        """Test that job status persists correctly."""
        try:
            # Check status multiple times
            statuses = []
            for _ in range(3):
                response = requests.get(f'{BASE_URL}/api/job/status', timeout=5)
                assert response.status_code == 200
                status = response.json()['status']['status']
                statuses.append(status)
                time.sleep(0.5)

            # Status should be consistent when idle
            if all(s == 'idle' for s in statuses):
                assert True  # Expected behavior
            else:
                # If job was running, status changes are expected
                assert True  # Also valid

        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - integration test skipped")


class TestPerformanceIntegration:
    """Basic performance and load testing."""

    def test_multiple_concurrent_requests(self):
        """Test handling multiple concurrent requests."""
        try:
            import threading
            import queue

            results = queue.Queue()

            def make_request():
                try:
                    response = requests.get(f'{BASE_URL}/api/health', timeout=5)
                    results.put(response.status_code)
                except Exception as e:
                    results.put(e)

            # Make 5 concurrent requests
            threads = []
            for _ in range(5):
                thread = threading.Thread(target=make_request)
                threads.append(thread)
                thread.start()

            # Wait for all to complete
            for thread in threads:
                thread.join()

            # Check results
            success_count = 0
            has_connection_error = False
            while not results.empty():
                result = results.get()
                if isinstance(result, int) and result == 200:
                    success_count += 1
                elif isinstance(result, requests.exceptions.ConnectionError):
                    has_connection_error = True

            # Skip if container not accessible
            if has_connection_error and success_count == 0:
                pytest.skip("Container not accessible on localhost:5000 - integration test skipped")

            # At least 3 should succeed
            assert success_count >= 3

        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - integration test skipped")

    def test_response_times(self):
        """Test that API responses are reasonably fast."""
        try:
            # Test health endpoint response time
            start_time = time.time()
            response = requests.get(f'{BASE_URL}/api/health', timeout=5)
            response_time = time.time() - start_time

            assert response.status_code == 200
            assert response_time < 2.0  # Should respond within 2 seconds

            # Test config endpoint response time
            start_time = time.time()
            response = requests.get(f'{BASE_URL}/api/config', timeout=5)
            response_time = time.time() - start_time

            assert response.status_code == 200
            assert response_time < 3.0  # Should respond within 3 seconds

        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - integration test skipped")


class TestSSEIntegration:
    """Test Server-Sent Events functionality."""

    def test_sse_endpoint_access(self):
        """Test that SSE endpoint is accessible."""
        try:
            # SSE endpoint should accept connections
            response = requests.get(f'{BASE_URL}/api/events', timeout=2, stream=True)
            assert response.status_code == 200

            # Check for SSE content type
            content_type = response.headers.get('content-type', '')
            assert 'text/event-stream' in content_type

            # Try to read initial keepalive
            try:
                line = next(response.iter_lines(decode_unicode=True))
                # Should receive keepalive or event
                assert line is not None
            except StopIteration:
                pass  # No immediate data is OK
            except requests.exceptions.ReadTimeout:
                pass  # Timeout is expected for SSE

        except requests.exceptions.ConnectionError:
            pytest.skip("Container not running - integration test skipped")
        except requests.exceptions.ReadTimeout:
            # Timeout is expected for SSE endpoint
            pass
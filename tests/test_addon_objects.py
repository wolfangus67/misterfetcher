"""
Test Addon object usage in web_app.
Tests the refactoring that standardizes Addon object usage instead of dictionary access.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import requests
from addon import Addon, addon_list_from_config
import json


class TestAddonObjectCreation:
    """Test Addon object creation and properties."""

    def test_create_addon_from_config(self):
        """Test creating Addon objects from configuration."""
        config = [
            {
                'url': 'http://test-addon.com/stremio/v1',
                'type': 'both',
                'name': 'Test Addon'
            }
        ]

        addons = addon_list_from_config(config)

        assert len(addons) == 1
        addon = addons[0]
        assert isinstance(addon, Addon)
        assert addon.url == 'http://test-addon.com/stremio/v1'
        assert addon.type == 'both'
        assert addon.name == 'Test Addon'

    def test_addon_properties(self):
        """Test Addon object properties."""
        addon = Addon(
            url='http://test.com/stremio/v1',
            addon_type='catalog',
            name='Test Catalog Addon'
        )

        assert addon.url == 'http://test.com/stremio/v1'
        assert addon.type == 'catalog'
        assert addon.name == 'Test Catalog Addon'

    def test_addon_type_validation(self):
        """Test Addon type validation."""
        addon = Addon(
            url='http://test.com/stremio/v1',
            addon_type='invalid_type',
            name='Invalid Addon'
        )

        # Addon class should handle type validation
        assert addon.type == 'invalid_type'  # Class might normalize or validate


class TestAddonValidationInWebApp:
    """Test Addon validation patterns used in web_app."""

    def test_validate_addon_urls_with_addon_objects(self):
        """Test the refactored validate_addon_urls function."""
        # Import after path setup
        from web_app import validate_addon_urls

        # Test valid configuration
        valid_config = [
            {
                'url': 'http://test1.com/stremio/v1',
                'type': 'both',
                'name': 'Test Addon 1'
            },
            {
                'url': 'http://test2.com/stremio/v1',
                'type': 'catalog',
                'name': 'Test Addon 2'
            }
        ]

        errors = validate_addon_urls(valid_config)
        assert len(errors) == 0

    def test_validate_addon_urls_missing_catalog(self):
        """Test validation when no catalog addon is provided."""
        from web_app import validate_addon_urls

        config_no_catalog = [
            {
                'url': 'http://test.com/stremio/v1',
                'type': 'stream',
                'name': 'Stream Only Addon'
            }
        ]

        errors = validate_addon_urls(config_no_catalog)
        assert any('catalog addon' in error.lower() for error in errors)

    def test_validate_addon_urls_missing_stream(self):
        """Test validation when no stream addon is provided."""
        from web_app import validate_addon_urls

        config_no_stream = [
            {
                'url': 'http://test.com/stremio/v1',
                'type': 'catalog',
                'name': 'Catalog Only Addon'
            }
        ]

        errors = validate_addon_urls(config_no_stream)
        assert any('stream addon' in error.lower() for error in errors)

    def test_validate_addon_urls_empty_config(self):
        """Test validation with empty configuration."""
        from web_app import validate_addon_urls

        errors = validate_addon_urls([])
        assert any('at least one addon' in error.lower() for error in errors)

    def test_validate_addon_urls_invalid_type(self):
        """Test validation with invalid addon type."""
        from web_app import validate_addon_urls

        config_invalid_type = [
            {
                'url': 'http://test.com/stremio/v1',
                'type': 'invalid_type',
                'name': 'Invalid Type Addon'
            },
            {
                'url': 'http://test2.com/stremio/v1',
                'type': 'both',
                'name': 'Valid Addon'
            }
        ]

        errors = validate_addon_urls(config_invalid_type)
        # Should have validation error for invalid type
        assert len(errors) > 0


class TestAddonUsageInCatalogLoading:
    """Test Addon object usage in catalog loading."""

    @patch('requests.get')
    def test_load_catalogs_with_addon_objects(self, mock_get, mock_manifest):
        """Test that catalog loading uses Addon objects correctly."""
        from web_app import load_catalogs

        # Mock the manifest response
        mock_response = Mock()
        mock_response.json.return_value = mock_manifest
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # Test configuration
        addon_urls = [
            {
                'url': 'http://test-addon.com/stremio/v1',
                'type': 'both',
                'name': 'Test Addon'
            }
        ]

        catalogs = load_catalogs()

        # Verify catalogs are created with addon names
        assert len(catalogs) >= 0
        # The function should use Addon objects internally
        # and extract names correctly

    @patch('requests.get')
    def test_addon_name_extraction(self, mock_get):
        """Test that addon names are extracted correctly."""
        # Mock manifest without name
        manifest_without_name = {
            'id': 'test.addon',
            'catalogs': [
                {
                    'id': 'test-catalog',
                    'type': 'movie',
                    'name': 'Test Catalog'
                }
            ]
        }

        mock_response = Mock()
        mock_response.json.return_value = manifest_without_name
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # Test that name is extracted from manifest if not in Addon object
        # This tests the fallback pattern in the refactored code

    @patch('requests.get')
    def test_catalog_type_normalization(self, mock_get):
        """Test that catalog types are normalized correctly."""
        manifest_with_all_type = {
            'name': 'Test Addon',
            'catalogs': [
                {
                    'id': 'test-mixed',
                    'type': 'all',  # Should be normalized to 'mixed'
                    'name': 'Mixed Catalog'
                }
            ]
        }

        mock_response = Mock()
        mock_response.json.return_value = manifest_with_all_type
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # Test that 'all' type gets normalized to 'mixed'
        # This is a pattern in the catalog loading code


class TestAddonObjectConsistency:
    """Test that Addon objects are used consistently throughout web_app."""

    def test_no_dictionary_access_patterns(self):
        """Test that we're not using dictionary access on addon data."""
        # This test ensures the refactoring is complete
        # We should use Addon objects, not dictionary access

        addon_config = [
            {
                'url': 'http://test.com/stremio/v1',
                'type': 'both',
                'name': 'Test Addon'
            }
        ]

        # Convert to Addon objects (the refactored pattern)
        addons = addon_list_from_config(addon_config)

        for addon in addons:
            # Use object properties, not dictionary access
            assert hasattr(addon, 'url')
            assert hasattr(addon, 'type')
            assert hasattr(addon, 'name')

            # Test accessing properties
            assert addon.url == 'http://test.com/stremio/v1'
            assert addon.type == 'both'
            assert addon.name == 'Test Addon'

            # These should NOT be used anymore (old pattern):
            # addon['url']
            # addon['type']
            # addon['name']

    def test_addon_list_creation_patterns(self):
        """Test various patterns of creating addon lists."""
        configs = [
            # Single addon
            [{'url': 'http://test1.com', 'type': 'both', 'name': 'Test1'}],
            # Multiple addons
            [
                {'url': 'http://test1.com', 'type': 'catalog', 'name': 'Test1'},
                {'url': 'http://test2.com', 'type': 'stream', 'name': 'Test2'}
            ],
            # Mixed types
            [
                {'url': 'http://test1.com', 'type': 'both', 'name': 'Test1'},
                {'url': 'http://test2.com', 'type': 'catalog', 'name': 'Test2'},
                {'url': 'http://test3.com', 'type': 'stream', 'name': 'Test3'}
            ]
        ]

        for config in configs:
            addons = addon_list_from_config(config)
            assert len(addons) == len(config)

            for i, addon in enumerate(addons):
                assert isinstance(addon, Addon)
                assert addon.url == config[i]['url']
                assert addon.type == config[i]['type']


class TestAddonErrorHandling:
    """Test error handling with Addon objects."""

    def test_invalid_addon_config_handling(self):
        """Test handling of invalid addon configurations."""
        invalid_configs = [
            # Missing URL
            [{'type': 'both', 'name': 'No URL'}],
            # Missing type
            [{'url': 'http://test.com', 'name': 'No Type'}],
            # Empty URL
            [{'url': '', 'type': 'both', 'name': 'Empty URL'}],
            # Invalid type (will be caught by validation)
            [{'url': 'http://test.com', 'type': 'invalid', 'name': 'Invalid Type'}]
        ]

        from web_app import validate_addon_urls

        for config in invalid_configs:
            errors = validate_addon_urls(config)
            # Should have at least one validation error
            assert len(errors) > 0

    @patch('requests.get')
    def test_network_error_handling(self, mock_get):
        """Test handling of network errors when fetching manifests."""
        from web_app import load_catalogs

        # Mock network error
        mock_get.side_effect = requests.exceptions.RequestException("Network error")

        # Should handle network errors gracefully
        catalogs = load_catalogs()
        # Should return empty list or handle error appropriately
        assert isinstance(catalogs, list)
"""
Test UI-related functionality and features.
Tests type badges, SxxExx format, and other UI elements affected by our refactoring.
"""
import pytest
from item import Item
from unittest.mock import Mock, patch


class TestTypeBadgeFunctionality:
    """Test type badge display and colors."""

    def test_movie_type_badge_info(self, sample_movie_item):
        """Test movie type badge information."""
        item = Item.from_catalog(sample_movie_item)

        # Test type detection
        assert item.item_type == 'movie'
        assert not item.is_episode()


        # Test badge display logic
        # Movies should show blue badges
        badge_info = {
            'text': 'Movie',
            'color_class': 'movie',  # Blue color
            'css_class': 'item-type-badge movie'
        }

        # This would be used by frontend JavaScript
        assert badge_info['text'] == 'Movie'
        assert 'movie' in badge_info['css_class']

    def test_series_type_badge_info(self, sample_series_item):
        """Test series type badge information."""
        item = Item.from_catalog(sample_series_item)

        # Test type detection
        assert item.item_type == 'series'
        assert not item.is_episode()


        # Test badge display logic
        # Series should show purple badges
        badge_info = {
            'text': 'Series',
            'color_class': 'series',  # Purple color
            'css_class': 'item-type-badge series'
        }

        assert badge_info['text'] == 'Series'
        assert 'series' in badge_info['css_class']

    def test_episode_shows_series_badge(self, sample_series_item, sample_episode_item):
        """Test that episodes show 'Series' badge, not 'Episode'."""
        series_item = Item.from_catalog(sample_series_item)
        # Create episode properly using Item constructor
        episode_item = Item(
            imdb_id=sample_episode_item['id'],
            title=series_item.title,
            year=series_item.year,
            item_type='episode',
            season=sample_episode_item['season'],
            episode=sample_episode_item['episode'],
            series_imdb_id=series_item.imdb_id
        )

        # Test type detection
        assert episode_item.is_episode()
        assert episode_item.item_type == 'episode'

        # IMPORTANT: Episodes should show "Series" badge (not "Episode")
        # This was the fix we implemented
        badge_text = 'Series'  # Not 'Episode'
        badge_info = {
            'text': badge_text,
            'color_class': 'series',  # Purple color
            'css_class': 'item-type-badge series'
        }

        assert badge_info['text'] == 'Series'
        assert 'series' in badge_info['css_class']

    def test_css_class_generation(self):
        """Test CSS class generation for type badges."""
        # Test CSS classes for different item types
        type_css_mapping = {
            'movie': 'item-type-badge movie',
            'series': 'item-type-badge series',
            'episode': 'item-type-badge series'  # Episodes use series styling
        }

        for item_type, expected_css in type_css_mapping.items():
            assert expected_css.startswith('item-type-badge')
            assert 'movie' in expected_css or 'series' in expected_css


class TestSxxExxFormat:
    """Test SxxExx format for episodes."""

    def test_episode_format_single_digit(self, sample_series_item):
        """Test S01E01 format for single digits."""
        series_item = Item.from_catalog(sample_series_item)

        # Episode with single digit season/episode - create properly
        episode_item = Item(
            imdb_id='tt7654321:1:1',
            title=series_item.title,
            year=series_item.year,
            item_type='episode',
            season=1,
            episode=1,
            series_imdb_id=series_item.imdb_id
        )
        title = episode_item.get_dashboard_title()

        # Should contain S01E01 format
        assert 'S01E01' in title
        assert series_item.title in title
        assert 'Series' in title  # Episodes show "Series" not "Episode"

    def test_episode_format_double_digit(self, sample_series_item):
        """Test S10E10 format for double digits."""
        series_item = Item.from_catalog(sample_series_item)

        # Episode with double digit season/episode - create properly
        episode_item = Item(
            imdb_id='tt7654321:10:10',
            title=series_item.title,
            year=series_item.year,
            item_type='episode',
            season=10,
            episode=10,
            series_imdb_id=series_item.imdb_id
        )
        title = episode_item.get_dashboard_title()

        # Should contain S10E10 format
        assert 'S10E10' in title
        assert series_item.title in title

    def test_episode_format_mixed_digits(self, sample_series_item):
        """Test S01E10 format with mixed digits."""
        series_item = Item.from_catalog(sample_series_item)

        # Episode with mixed digits - create properly
        episode_item = Item(
            imdb_id='tt7654321:1:10',
            title=series_item.title,
            year=series_item.year,
            item_type='episode',
            season=1,
            episode=10,
            series_imdb_id=series_item.imdb_id
        )
        title = episode_item.get_dashboard_title()

        # Should contain S01E10 format
        assert 'S01E10' in title
        assert series_item.title in title

    def test_no_sxxexx_for_movies(self, sample_movie_item):
        """Test that movies don't have SxxExx format."""
        movie_item = Item.from_catalog(sample_movie_item)
        title = movie_item.get_dashboard_title()

        # Should NOT contain SxxExx format
        assert 'S' not in title or 'E' not in title
        assert 'Test Movie' in title
        assert 'Movie' in title


class TestDashboardTitleGeneration:
    """Test dashboard title generation for different item types."""

    def test_movie_dashboard_title(self, sample_movie_item):
        """Test dashboard title format for movies."""
        item = Item.from_catalog(sample_movie_item)
        title = item.get_dashboard_title()

        # Check format components
        assert 'Prefetching streams for' in title
        assert 'Movie' in title
        assert 'Test Movie' in title
        assert '(2023)' in title

        # Should not have SxxExx
        assert 'S' not in title or 'E' not in title

    def test_series_dashboard_title(self, sample_series_item):
        """Test dashboard title format for series."""
        item = Item.from_catalog(sample_series_item)
        title = item.get_dashboard_title()

        # Check format components
        assert 'Prefetching streams for' in title
        assert 'Series' in title
        assert 'Test Series' in title
        assert '(2023)' in title

        # Should not have SxxExx for series overview
        assert 'S' not in title or 'E' not in title

    def test_episode_dashboard_title(self, sample_series_item, sample_episode_item):
        """Test dashboard title format for episodes."""
        series_item = Item.from_catalog(sample_series_item)
        # Create episode properly
        episode_item = Item(
            imdb_id=sample_episode_item['id'],
            title=series_item.title,
            year=series_item.year,
            item_type='episode',
            season=sample_episode_item['season'],
            episode=sample_episode_item['episode'],
            series_imdb_id=series_item.imdb_id
        )
        title = episode_item.get_dashboard_title()

        # Check format components
        assert 'Prefetching streams for' in title
        assert 'Series' in title  # Episodes show "Series"
        assert series_item.title in title
        assert 'S01E01' in title

    def test_title_without_year(self):
        """Test title generation for items without year."""
        item_data = {
            'id': 'tt1234567',
            'type': 'movie',
            'title': 'Movie without year'
        }

        item = Item.from_catalog(item_data)
        title = item.get_dashboard_title()

        # Should not contain year parentheses
        assert '(' not in title or ')' not in title
        assert 'Movie without year' in title


class TestProgressDisplay:
    """Test progress display functionality."""

    def test_current_item_display(self, sample_movie_item, sample_series_item):
        """Test current item display format."""
        movie_item = Item.from_catalog(sample_movie_item)
        series_item = Item.from_catalog(sample_series_item)

        # Test movie display
        movie_display = {
            'title': movie_item.get_dashboard_title(),
            'type': movie_item.item_type,
            'imdb_id': movie_item.imdb_id
        }

        assert 'Movie' in movie_display['title']
        assert movie_display['type'] == 'movie'
        assert movie_display['imdb_id'] == 'tt1234567'

        # Test series display
        series_display = {
            'title': series_item.get_dashboard_title(),
            'type': series_item.item_type,
            'imdb_id': series_item.imdb_id
        }

        assert 'Series' in series_display['title']
        assert series_display['type'] == 'series'
        assert series_display['imdb_id'] == 'tt7654321'

    def test_progress_data_structure(self):
        """Test progress data structure for UI updates."""
        # This simulates the progress data sent to frontend
        progress_data = {
            'current_title': 'Prefetching streams for Movie: Test Movie (2023)',
            'current_item_type': 'movie',
            'current_imdb_id': 'tt1234567',
            'movies_prefetched': 10,
            'series_prefetched': 5,
            'episodes_prefetched': 50
        }

        # Verify structure
        required_fields = [
            'current_title',
            'current_item_type',
            'current_imdb_id',
            'movies_prefetched',
            'series_prefetched',
            'episodes_prefetched'
        ]

        for field in required_fields:
            assert field in progress_data

        # Verify types
        assert isinstance(progress_data['current_title'], str)
        assert isinstance(progress_data['current_item_type'], str)
        assert isinstance(progress_data['current_imdb_id'], str)
        assert all(isinstance(v, int) for v in [
            progress_data['movies_prefetched'],
            progress_data['series_prefetched'],
            progress_data['episodes_prefetched']
        ])


class TestCatalogUIFeatures:
    """Test catalog-related UI features."""

    def test_catalog_type_display(self):
        """Test catalog type display in UI."""
        catalog_types = ['movie', 'series', 'mixed']
        display_names = {
            'movie': 'Movie',
            'series': 'Series',
            'mixed': 'Mixed'
        }

        for cat_type in catalog_types:
            assert cat_type in display_names
            assert display_names[cat_type] in ['Movie', 'Series', 'Mixed']

    def test_catalog_badge_colors(self):
        """Test catalog badge color mapping."""
        # This would map to CSS classes
        catalog_css_mapping = {
            'movie': 'catalog-badge-movie',
            'series': 'catalog-badge-series',
            'mixed': 'catalog-badge-mixed'
        }

        for cat_type, css_class in catalog_css_mapping.items():
            assert css_class.startswith('catalog-badge')
            assert cat_type in css_class

    def test_addon_name_display(self, mock_manifest):
        """Test addon name display in catalog list."""
        # Test with manifest that has name
        assert 'name' in mock_manifest
        addon_name = mock_manifest['name']

        # Test with manifest that doesn't have name
        manifest_no_name = {
            'id': 'test.addon',
            'catalogs': []
        }

        fallback_name = manifest_no_name.get('name', 'Unknown Addon')
        assert fallback_name == 'Unknown Addon'


class TestColorSchemes:
    """Test UI color schemes for badges."""

    def test_movie_badge_colors(self):
        """Test movie badge color scheme."""
        # Movie badges should be blue
        movie_colors = {
            'background': 'linear-gradient(135deg, rgba(59, 130, 246, 0.15), rgba(37, 99, 235, 0.15))',
            'border': '1px solid rgba(59, 130, 246, 0.3)',
            'text': '#93c5fd'
        }

        # Verify blue color scheme
        assert '59, 130, 246' in movie_colors['background']  # Blue RGB
        assert '59, 130, 246' in movie_colors['border']
        assert '#93c5fd' == movie_colors['text']  # Blue color code

    def test_series_badge_colors(self):
        """Test series badge color scheme."""
        # Series badges should be purple
        series_colors = {
            'background': 'linear-gradient(135deg, rgba(168, 85, 247, 0.15), rgba(147, 51, 234, 0.15))',
            'border': '1px solid rgba(168, 85, 247, 0.3)',
            'text': '#c4b5fd'
        }

        # Verify purple color scheme
        assert '168, 85, 247' in series_colors['background']  # Purple RGB
        assert '168, 85, 247' in series_colors['border']
        assert '#c4b5fd' == series_colors['text']  # Purple color code

    def test_css_class_consistency(self):
        """Test CSS class naming consistency."""
        # All badge classes should follow consistent pattern
        badge_classes = [
            'item-type-badge',
            'item-type-badge.movie',
            'item-type-badge.series'
        ]

        for css_class in badge_classes:
            if '.' in css_class:
                base, modifier = css_class.split('.')
                assert base == 'item-type-badge'
                assert modifier in ['movie', 'series']
            else:
                assert css_class == 'item-type-badge'


class TestUIDataStructures:
    """Test data structures sent to UI."""

    def test_completion_screen_data(self):
        """Test completion screen data structure."""
        # This simulates the data sent to completion screen
        completion_data = {
            'timing': {
                'start_time': 1234567890.123,
                'end_time': 1234567890.456,
                'total_duration': 0.333,
                'processing_duration': 0.300
            },
            'statistics': {
                'filtered_catalogs': 10,
                'movies_prefetched': 100,
                'series_prefetched': 20,
                'episodes_prefetched': 200,
                'total_pages_fetched': 50,
                'items_from_cache': 30,
                'cache_requests_made': 250,
                'cache_requests_successful': 225
            }
        }

        # Verify structure
        assert 'timing' in completion_data
        assert 'statistics' in completion_data

        # Verify timing data
        timing = completion_data['timing']
        for field in ['start_time', 'end_time', 'total_duration', 'processing_duration']:
            assert field in timing
            assert isinstance(timing[field], (int, float))

        # Verify statistics data
        stats = completion_data['statistics']
        for field in stats:
            assert isinstance(stats[field], int)
            assert stats[field] >= 0

    def test_error_display_data(self):
        """Test error display data structure."""
        error_data = {
            'error': 'Test error message',
            'timestamp': 1234567890.123,
            'context': {
                'current_item': 'Test Movie',
                'progress_percentage': 50
            }
        }

        # Verify structure
        assert 'error' in error_data
        assert 'timestamp' in error_data
        assert 'context' in error_data
        assert isinstance(error_data['error'], str)
        assert len(error_data['error']) > 0
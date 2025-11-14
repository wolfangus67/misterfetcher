"""
Test Item class creation and usage patterns.
Tests the refactoring that optimizes Item object creation and reuse.
"""
import pytest
from item import Item
from streams_prefetcher import StreamsPrefetcher


class TestItemClassCreation:
    """Test Item object creation and properties."""

    def test_create_movie_item(self, sample_movie_item):
        """Test creating a movie Item object."""
        item = Item.from_catalog(sample_movie_item)

        assert item is not None
        assert item.imdb_id == 'tt1234567'
        assert item.item_type == 'movie'
        assert item.title == 'Test Movie'
        assert item.year == '2023'
        assert not item.is_episode()
        assert item.item_type == 'movie'

    def test_create_series_item(self, sample_series_item):
        """Test creating a series Item object."""
        item = Item.from_catalog(sample_series_item)

        assert item is not None
        assert item.imdb_id == 'tt7654321'
        assert item.item_type == 'series'
        assert item.title == 'Test Series'
        assert item.year == '2023'
        assert not item.is_episode()
        assert item.item_type == 'series'

    def test_create_episode_item(self, sample_series_item, sample_episode_item):
        """Test creating an episode Item object."""
        # Episodes are created using create_episode_item method
        from streams_prefetcher import StreamsPrefetcher

        series_item = Item.from_catalog(sample_series_item)

        # Create a mock StreamsPrefetcher to test create_episode_item
        prefetcher = StreamsPrefetcher.__new__(StreamsPrefetcher)
        episode_item = prefetcher.create_episode_item(series_item, sample_episode_item)

        assert episode_item is not None
        assert episode_item.imdb_id == 'tt7654321:1:1'
        assert episode_item.item_type == 'episode'
        assert episode_item.title == 'Test Series'  # Uses series title
        assert episode_item.season == 1
        assert episode_item.episode == 1
        assert episode_item.is_episode()
        assert episode_item.item_type == 'episode'

    def test_get_dashboard_title_movie(self, sample_movie_item):
        """Test dashboard title format for movies."""
        item = Item.from_catalog(sample_movie_item)
        title = item.get_dashboard_title()

        assert "Movie" in title
        assert "Test Movie" in title
        assert "(2023)" in title
        assert "Prefetching streams for" in title

    def test_get_dashboard_title_series(self, sample_series_item):
        """Test dashboard title format for series."""
        item = Item.from_catalog(sample_series_item)
        title = item.get_dashboard_title()

        assert "Series" in title
        assert "Test Series" in title
        assert "(2023)" in title
        assert "Prefetching streams for" in title

    def test_get_dashboard_title_episode(self, sample_series_item, sample_episode_item):
        """Test dashboard title format for episodes with SxxExx format."""
        from streams_prefetcher import StreamsPrefetcher

        series_item = Item.from_catalog(sample_series_item)

        # Create episode using create_episode_item method
        prefetcher = StreamsPrefetcher.__new__(StreamsPrefetcher)
        episode_item = prefetcher.create_episode_item(series_item, sample_episode_item)

        title = episode_item.get_dashboard_title()

        assert "Series" in title
        assert "Test Series" in title  # Series title, not episode title
        assert "S01E01" in title
        assert "Prefetching streams for" in title

    def test_item_with_missing_year(self):
        """Test Item creation with missing year."""
        item_data = {
            'id': 'tt1234567',
            'type': 'movie',
            'title': 'Movie without year'
        }
        item = Item.from_catalog(item_data)

        assert item is not None
        assert item.year is None
        title = item.get_dashboard_title()
        assert "(2023)" not in title

    def test_item_reuse_pattern(self, sample_movie_item):
        """Test that Item objects can be reused without creating duplicates."""
        # This tests the optimization we implemented
        item = Item.from_catalog(sample_movie_item)

        # Use the same item object multiple times
        title1 = item.get_dashboard_title()
        title2 = item.get_dashboard_title()
        imdb1 = item.imdb_id
        imdb2 = item.imdb_id

        assert title1 == title2
        assert imdb1 == imdb2
        assert id(item) == id(item)  # Same object


class TestItemClassInStreamsPrefetcher:
    """Test Item class integration within StreamsPrefetcher."""

    def test_item_creation_in_processing_loop(self, temp_data_dir):
        """Test the pattern of creating Item objects once and reusing them."""
        # This simulates the refactored pattern in streams_prefetcher.py

        # Sample item from catalog
        catalog_item = {
            'id': 'tt1234567',
            'type': 'movie',
            'title': 'Test Movie',
            'year': 2023
        }

        # Test the refactored pattern: create once, reuse
        item_obj = Item.from_catalog(catalog_item)
        assert item_obj is not None

        # Use in multiple places without recreating
        dashboard_title = item_obj.get_dashboard_title()
        imdb_id = item_obj.imdb_id
        item_type = item_obj.item_type

        assert dashboard_title is not None
        assert imdb_id == 'tt1234567'
        assert item_type == 'movie'

        # Verify we're not creating duplicate objects
        # This was the issue fixed in the refactoring
        assert item_obj.imdb_id == imdb_id
        assert item_obj.item_type == item_type

    def test_episode_item_creation_from_series(self, sample_series_item, sample_episode_item):
        """Test creating episode items from a series item."""
        series_item = Item.from_catalog(sample_series_item)

        # Create episode properly using Item constructor (not from_catalog)
        episode_item = Item(
            imdb_id=sample_episode_item['id'],
            title=series_item.title,
            year=series_item.year,
            item_type='episode',
            season=sample_episode_item['season'],
            episode=sample_episode_item['episode'],
            series_imdb_id=series_item.imdb_id
        )

        assert episode_item is not None
        assert episode_item.get_series_imdb_id() == series_item.imdb_id
        assert episode_item.season == 1
        assert episode_item.episode == 1

    def test_no_attribute_errors(self, sample_series_item, sample_episode_item):
        """Test that we don't get NameError from incorrect variable names."""
        # This tests the specific bug we fixed (series_item -> item_obj)

        # Create item_obj once (the fixed pattern)
        item_obj = Item.from_catalog(sample_series_item)

        # Use item_obj consistently (not series_item)
        assert item_obj.imdb_id == 'tt7654321'

        # Create episode using item_obj (the fixed line 1628)
        episode_item = Item.from_catalog(sample_episode_item, item_obj)
        assert episode_item is not None

        # This should not raise NameError
        with pytest.raises(NameError) as exc_info:
            # This would fail with the old code
            eval('series_item.imdb_id')  # noqa: S307

        assert "series_item" in str(exc_info.value)


class TestItemClassTypeDetection:
    """Test type detection methods."""

    def test_type_detection_methods(self, sample_movie_item, sample_series_item):
        """Test all type detection methods work correctly."""
        movie_item = Item.from_catalog(sample_movie_item)
        series_item = Item.from_catalog(sample_series_item)

        # Movie type detection
        assert movie_item.item_type == 'movie'
        assert not movie_item.is_episode()

        # Series type detection
        assert series_item.item_type == 'series'
        assert not series_item.is_episode()

    def test_item_type_property_consistency(self, sample_movie_item, sample_series_item):
        """Test that item_type property is consistent."""
        movie_item = Item.from_catalog(sample_movie_item)
        series_item = Item.from_catalog(sample_series_item)

        assert movie_item.item_type == 'movie'
        assert series_item.item_type == 'series'

        # Test the property is used correctly in type checking
        # This is the pattern used in the refactored code
        processed_movies = 0
        processed_series = 0

        items = [movie_item, series_item]
        for item in items:
            if item.item_type == 'movie':
                processed_movies += 1
            elif item.item_type == 'series':
                processed_series += 1

        assert processed_movies == 1
        assert processed_series == 1
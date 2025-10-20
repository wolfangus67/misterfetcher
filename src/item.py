"""
Item data class for representing movies, series, and episodes
"""

from typing import Optional, Dict, Any


class Item:
    """Data class representing a movie, series, or episode for prefetching"""

    def __init__(self, imdb_id: str, title: str, item_type: str, year: Optional[str] = None,
                 season: Optional[int] = None, episode: Optional[int] = None,
                 series_imdb_id: Optional[str] = None):
        self.imdb_id = imdb_id
        self.title = title
        self.year = year
        self.item_type = item_type  # 'movie', 'series', or 'episode'
        self.season = season  # for episodes
        self.episode = episode  # for episodes
        self.series_imdb_id = series_imdb_id  # for episodes (base series ID)

    def __repr__(self) -> str:
        return f"Item(id={self.imdb_id}, type={self.item_type}, title={self.title})"

    def get_logging_text(self) -> str:
        """Format this Item object for logging display"""
        if self.item_type == 'episode':
            # Only show year if it exists
            year_part = f" ({self.year})" if self.year else ""
            return f"{self.title}{year_part} S{self.season:02d}E{self.episode:02d} [{self.imdb_id}]"
        else:
            type_prefix = self.item_type.capitalize() if self.item_type else 'Item'
            # Only show year if it exists
            year_part = f" ({self.year})" if self.year else ""
            return f"{type_prefix}: {self.title}{year_part} [{self.imdb_id}]"

    def get_cache_title(self) -> str:
        """Get title in format for database storage: 'Title (Year)'"""
        return f"{self.title} ({self.year})" if self.year else self.title

    def get_dashboard_title(self) -> str:
        """Get title for dashboard progress display"""
        if self.is_episode():
            # Episodes: "Prefetching streams for Series: Series Title (Year) S01E01"
            year_part = f" ({self.year})" if self.year else ""
            episode_part = f" S{self.season:02d}E{self.episode:02d}"
            return f"Prefetching streams for Series: {self.title}{year_part}{episode_part}"
        else:
            # Movies/Series: "Prefetching streams for Movie/Series: Title (Year)"
            type_str = self.item_type.capitalize()
            year_part = f" ({self.year})" if self.year else ""
            return f"Prefetching streams for {type_str}: {self.title}{year_part}"

    def is_episode(self) -> bool:
        """Check if this Item is an episode"""
        return self.item_type == 'episode'

    def get_episode_info(self) -> str:
        """Get episode info in format SxxExx (only for episodes)"""
        if self.is_episode():
            return f"S{self.season:02d}E{self.episode:02d}"
        return ""

    def get_content_id(self) -> str:
        """Get the content ID for streaming requests"""
        # For episodes, use the composite ID format
        if self.is_episode():
            return f"{self.series_imdb_id}:{self.season}:{self.episode}"
        return self.imdb_id

    def get_series_imdb_id(self) -> str:
        """Get the base series IMDb ID (for episodes)"""
        if self.is_episode():
            return self.series_imdb_id or self.imdb_id
        return self.imdb_id

    def get_episode_id(self) -> str:
        """Get the full episode ID (for episodes)"""
        if self.is_episode():
            return self.imdb_id
        return ""

    @staticmethod
    def from_catalog(item: Dict[str, Any], item_type: str = None) -> Optional['Item']:
        """Create an Item object from catalog data"""
        # Extract IMDb ID
        imdb_id = None
        for key in ['imdb_id', 'id']:
            item_id = item.get(key)
            if item_id and isinstance(item_id, str) and item_id.startswith('tt'):
                imdb_id = item_id
                break

        if not imdb_id:
            return None

        # Extract title
        title = item.get('name', item.get('title', 'Unknown Title')).strip()

        # Extract year
        year = item.get('year')
        if not year:
            released = item.get('released')
            if released:
                try:
                    year = str(released)[:4] if len(str(released)) >= 4 else None
                except:
                    pass

        # Determine item type
        if not item_type:
            item_type = item.get('type', 'unknown')

        # Only convert to string if it's not already a string
        if year and not isinstance(year, str):
            year = str(year)

        return Item(
            imdb_id=imdb_id,
            title=title,
            item_type=item_type,
            year=year
        )
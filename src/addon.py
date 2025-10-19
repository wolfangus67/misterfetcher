"""
Addon data class for representing Stremio addons
"""

import json
import requests
from typing import Optional, Dict, Any, List
from urllib.parse import urljoin, quote


class Addon:
    """Data class representing a Stremio addon"""

    ADDON_TYPES = {
        'catalog': 'Provides catalog data',
        'stream': 'Provides stream data',
        'both': 'Provides both catalog and stream data'
    }

    def __init__(self, url: str, addon_type: str = 'both',
                 name: Optional[str] = None, logo: Optional[str] = None):
        """
        Initialize an Addon object

        Args:
            url: The base URL of the addon
            addon_type: Type of addon ('catalog', 'stream', or 'both')
            name: Display name of the addon
            logo: URL to addon's logo
        """
        self.url = url.rstrip('/')  # Clean URL by removing trailing slash
        self.type = addon_type.lower()
        self.name = name
        self.logo = logo

        # Validate the addon
        self._validate()

    def _validate(self) -> None:
        """Validate addon data"""
        if not self.url:
            raise ValueError("Addon URL is required")

        if not self.url.startswith(('http://', 'https://')):
            raise ValueError("Addon URL must start with http:// or https://")

        if self.type not in self.ADDON_TYPES:
            raise ValueError(f"Invalid addon type '{self.type}'. Must be one of: {list(self.ADDON_TYPES.keys())}")

    def get_display_name(self) -> str:
        """Get display name, falling back to URL if name not set"""
        return self.name or self.url

    def is_catalog_type(self) -> bool:
        """Check if addon provides catalogs"""
        return self.type in ['catalog', 'both']

    def is_stream_type(self) -> bool:
        """Check if addon provides streams"""
        return self.type in ['stream', 'both']

    def get_manifest_url(self) -> str:
        """Get the manifest URL for this addon"""
        return f"{self.url}/manifest.json"

    def get_catalog_url(self, catalog_id: str, catalog_type: str, skip: int = 0) -> str:
        """
        Get catalog URL for this addon

        Args:
            catalog_id: The catalog ID
            catalog_type: Type of catalog ('movie', 'series', or 'mixed')
            skip: Number of items to skip (for pagination)
        """
        encoded_catalog_id = quote(catalog_id, safe='')
        skip_param = f"skip={skip}" if skip > 0 else ""
        url = f"{self.url}/catalog/{catalog_type}/{encoded_catalog_id}.json"
        if skip_param:
            url += f"?{skip_param}"
        return url

    def get_stream_url(self, content_id: str, content_type: str) -> str:
        """
        Get stream URL for this addon

        Args:
            content_id: The content ID (IMDb ID or composite ID)
            content_type: Type of content ('movie' or 'series')
        """
        return f"{self.url}/stream/{content_type}/{content_id}.json"

    def to_dict(self) -> Dict[str, Any]:
        """Convert Addon to dictionary for JSON serialization"""
        return {
            'url': self.url,
            'type': self.type,
            'name': self.name,
            'logo': self.logo
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Addon':
        """Create Addon from dictionary"""
        if not isinstance(data, dict):
            raise ValueError("Addon data must be a dictionary")

        # Handle old format (url, type tuple)
        if isinstance(data, list) and len(data) == 2:
            return cls(url=data[0], addon_type=data[1])

        # Handle new format
        return cls(
            url=data.get('url', ''),
            addon_type=data.get('type', 'both'),
            name=data.get('name'),
            logo=data.get('logo')
        )

    @classmethod
    def from_url(cls, url: str, addon_type: str = 'both') -> 'Addon':
        """Create Addon from just URL and type"""
        return cls(url=url, addon_type=addon_type)

    def fetch_manifest(self, timeout: int = 10) -> Dict[str, Any]:
        """
        Fetch the addon manifest and return parsed JSON

        Args:
            timeout: Request timeout in seconds

        Returns:
            Parsed manifest JSON
        """
        try:
            response = requests.get(
                self.get_manifest_url(),
                timeout=timeout,
                headers={
                    'User-Agent': 'Streams Prefetcher/1.0',
                    'Accept': 'application/json'
                }
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to fetch manifest from {self.url}: {str(e)}")

    def update_metadata(self) -> None:
        """
        Fetch and update addon metadata (name and logo) from manifest
        """
        try:
            manifest = self.fetch_manifest()
            self.name = manifest.get('name', self.name or 'Unknown Addon')
            self.logo = manifest.get('logo', self.logo)
        except Exception as e:
            # Don't raise error, just log it (caller can handle)
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to update metadata for {self.url}: {str(e)}")

    def __repr__(self) -> str:
        return f"Addon(url='{self.url}', type='{self.type}', name='{self.name}')"

    def __str__(self) -> str:
        return self.get_display_name()

    def __eq__(self, other) -> bool:
        if not isinstance(other, Addon):
            return False
        return self.url == other.url and self.type == other.type

    def __hash__(self) -> int:
        return hash((self.url, self.type))


def addon_list_from_config(config_addons: List[Any]) -> List[Addon]:
    """
    Convert addon list from config to list of Addon objects

    Args:
        config_addons: List of addon data (can be dict or tuple)

    Returns:
        List of Addon objects
    """
    addons = []
    for item in config_addons:
        if isinstance(item, dict):
            # New format
            addons.append(Addon.from_dict(item))
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            # Old format (url, type) tuple
            addons.append(Addon.from_url(item[0], item[1]))
        else:
            raise ValueError(f"Invalid addon format: {item}")
    return addons


def addon_list_to_config(addons: List[Addon]) -> List[Dict[str, Any]]:
    """
    Convert list of Addon objects to config format

    Args:
        addons: List of Addon objects

    Returns:
        List of dictionaries for config storage
    """
    return [addon.to_dict() for addon in addons]
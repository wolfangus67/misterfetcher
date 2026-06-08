"""
Configuration Manager
Handles persistence of user configuration to disk
"""

import copy
import json
import os
import re
from typing import Dict, Any, List, Tuple
from pathlib import Path
from logger import get_logger
from addon import addon_list_from_config, addon_list_to_config

logger = get_logger('streams_prefetcher.config_manager')

class ConfigManager:
    """Manages configuration persistence"""

    DEFAULT_CONFIG = {
        'addon_urls': [],  # List of {'url': 'https://...', 'type': 'catalog'|'stream'|'both'}
        'movies_global_limit': -1,
        'episodes_global_limit': -1,
        'movies_per_catalog': 50,
        'episodes_per_catalog': 50,
        'episodes_per_mixed_catalog': 50,
        'delay': 2,  # In seconds
        'network_request_timeout': 30,  # In seconds
        'proxy': '',
        'randomize_catalog_processing': False,
        'randomize_item_prefetching': False,
        'cache_validity': 604800,  # 1 week in seconds
        'max_execution_time': 5400,  # 90 minutes in seconds
        'enable_logging': False,
        'catalog_selection': {},  # {catalog_id: {enabled: bool, order: int}}
        'schedule': {
            'enabled': True,
            'cron_expression': '0 2,5,8 * * *',  # Daily at 2 AM, 5 AM, 8 AM
            'timezone': 'UTC'
        },
        'cache_uncached_streams': {
            'enabled': False,
            'cached_stream_regex': '⚡',
            'skip_streams_regex': '',
            'max_successful_cache_requests_per_item': 1,
            'max_cache_request_attempts_per_item': 1,
            'max_cache_requests_global': 50,
            'cached_streams_count_threshold': 0
        },
        'max_movie_items_per_catalog_fetch': 50,
        'max_series_items_per_catalog_fetch': 50,
        'max_mixed_items_per_catalog_fetch': 50
    }

    def __init__(self, config_path: str = 'data/config/config.json', user_id: str = None):
        self.user_id = user_id
        if user_id:
            safe_user_id = self._sanitize_user_id(user_id)
            self.config_path = Path('data/users') / safe_user_id / 'config.json'
        else:
            self.config_path = Path(config_path)
        self.config = self.load()

    @staticmethod
    def _sanitize_user_id(user_id: str) -> str:
        safe = re.sub(r'[^a-z0-9._-]+', '_', str(user_id).strip().lower())
        return safe.strip('._-') or 'user'

    def load(self) -> Dict[str, Any]:
        """Load configuration from disk or return default"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    loaded_config = json.load(f)

                # Migrate old addon format to new format if needed
                loaded_config = self._migrate_config(loaded_config)

                # Merge with defaults to ensure all keys exist
                config = copy.deepcopy(self.DEFAULT_CONFIG)
                config.update(loaded_config)

                # Migrate series-based limits to episode-based limits
                config = self._migrate_series_to_episode_limits(config)

                return config
            else:
                return copy.deepcopy(self.DEFAULT_CONFIG)
        except Exception as e:
            print(f"Error loading config: {e}")
            return copy.deepcopy(self.DEFAULT_CONFIG)

    def _migrate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate configuration to new formats"""
        migrated = False

        # Migrate addon_urls from old tuple format to new dict format
        if 'addon_urls' in config:
            old_addon_urls = config['addon_urls']
            if old_addon_urls and isinstance(old_addon_urls, list):
                # Check if we have old format (list of tuples or dicts with just url/type)
                needs_migration = False
                for item in old_addon_urls:
                    if isinstance(item, (list, tuple)) and len(item) == 2:
                        needs_migration = True
                        break
                    elif isinstance(item, dict) and 'url' in item and 'type' in item and 'name' not in item:
                        needs_migration = True
                        break

                if needs_migration:
                    logger.info("[CONFIG MIGRATION] Migrating addon_urls to new format")
                    # Convert to new Addon object format
                    try:
                        addons = addon_list_from_config(old_addon_urls)
                        config['addon_urls'] = addon_list_to_config(addons)
                        migrated = True
                        logger.info(f"[CONFIG MIGRATION] Migrated {len(addons)} addons to new format")
                    except Exception as e:
                        logger.error(f"[CONFIG MIGRATION] Failed to migrate addons: {e}")

        # Migrate addon_name_cache into addon objects
        if 'addon_name_cache' in config and 'addon_urls' in config:
            addon_name_cache = config.get('addon_name_cache', {})
            if addon_name_cache:
                logger.info("[CONFIG MIGRATION] Migrating addon_name_cache to addon objects")
                for addon_data in config['addon_urls']:
                    addon_url = addon_data.get('url')
                    if addon_url and addon_url in addon_name_cache:
                        addon_data['name'] = addon_name_cache[addon_url]
                        migrated = True

                # Remove old addon_name_cache
                del config['addon_name_cache']
                logger.info("[CONFIG MIGRATION] Removed old addon_name_cache")

        # Migrate addon_logo_cache into addon objects
        if 'addon_logo_cache' in config and 'addon_urls' in config:
            addon_logo_cache = config.get('addon_logo_cache', {})
            if addon_logo_cache:
                logger.info("[CONFIG MIGRATION] Migrating addon_logo_cache to addon objects")
                for addon_data in config['addon_urls']:
                    addon_url = addon_data.get('url')
                    if addon_url and addon_url in addon_logo_cache:
                        addon_data['logo'] = addon_logo_cache[addon_url]
                        migrated = True

                # Remove old addon_logo_cache
                del config['addon_logo_cache']
                logger.info("[CONFIG MIGRATION] Removed old addon_logo_cache")

        if migrated:
            # Save the migrated config
            try:
                with open(self.config_path, 'w') as f:
                    json.dump(config, f, indent=2)
                logger.info("[CONFIG MIGRATION] Saved migrated configuration")
            except Exception as e:
                logger.error(f"[CONFIG MIGRATION] Failed to save migrated config: {e}")

        return config

    def _migrate_series_to_episode_limits(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate old series-based limits to episode-based limits.

        Conversion ratio: 1:1 (1 episode ≈ 1 movie in terms of prefetching streams)
        """
        migrated = False

        # Migrate series_global_limit → episodes_global_limit
        if 'series_global_limit' in config and 'episodes_global_limit' not in config:
            old_value = config['series_global_limit']
            config['episodes_global_limit'] = old_value  # 1:1 ratio
            del config['series_global_limit']
            migrated = True
            logger.info(f"[CONFIG MIGRATION] series_global_limit ({old_value}) → episodes_global_limit ({config['episodes_global_limit']})")

        # Migrate series_per_catalog → episodes_per_catalog
        if 'series_per_catalog' in config and 'episodes_per_catalog' not in config:
            old_value = config['series_per_catalog']
            config['episodes_per_catalog'] = old_value  # 1:1 ratio
            del config['series_per_catalog']
            migrated = True
            logger.info(f"[CONFIG MIGRATION] series_per_catalog ({old_value}) → episodes_per_catalog ({config['episodes_per_catalog']})")

        # Migrate items_per_mixed_catalog → episodes_per_mixed_catalog
        if 'items_per_mixed_catalog' in config and 'episodes_per_mixed_catalog' not in config:
            old_value = config['items_per_mixed_catalog']
            config['episodes_per_mixed_catalog'] = old_value  # Keep same value
            del config['items_per_mixed_catalog']
            migrated = True
            logger.info(f"[CONFIG MIGRATION] items_per_mixed_catalog ({old_value}) → episodes_per_mixed_catalog ({config['episodes_per_mixed_catalog']})")

        if migrated:
            logger.info("[CONFIG MIGRATION] Configuration migrated from series-based to episode-based limits")
            # Save migrated config
            try:
                with open(self.config_path, 'w') as f:
                    json.dump(config, f, indent=2)
                logger.info("[CONFIG MIGRATION] Saved migrated configuration")
            except Exception as e:
                logger.error(f"[CONFIG MIGRATION] Failed to save migrated config: {e}")

        return config

    def save(self, config: Dict[str, Any] = None) -> bool:
        """Save configuration to disk"""
        try:
            logger.info(f"[CONFIG SAVE] save() called, config_path={self.config_path}")

            # Ensure directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"[CONFIG SAVE] Config directory ensured: {self.config_path.parent}")

            # Use provided config or instance config
            config_to_save = config if config is not None else self.config
            logger.info(f"[CONFIG SAVE] Config keys to save: {list(config_to_save.keys())}")

            # Log saved_catalogs if present
            if 'saved_catalogs' in config_to_save:
                saved_cat_count = len(config_to_save['saved_catalogs'])
                logger.info(f"[CONFIG SAVE] saved_catalogs count: {saved_cat_count}")
                if saved_cat_count > 0:
                    enabled_count = len([c for c in config_to_save['saved_catalogs'] if c.get('enabled', False)])
                    logger.info(f"[CONFIG SAVE] Enabled catalogs in saved_catalogs: {enabled_count}")

            # Write to disk with pretty formatting
            logger.info(f"[CONFIG SAVE] Writing to {self.config_path}...")
            with open(self.config_path, 'w') as f:
                json.dump(config_to_save, f, indent=2)

            file_size = os.path.getsize(self.config_path)
            logger.info(f"[CONFIG SAVE] ✓ File written successfully, size: {file_size} bytes")

            # Update instance config
            if config is not None:
                self.config = config
                logger.info("[CONFIG SAVE] Instance config updated")

            return True
        except Exception as e:
            logger.error(f"[CONFIG SAVE] ✗ Error saving config: {e}", exc_info=True)
            print(f"Error saving config: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value"""
        return self.config.get(key, default)

    def set(self, key: str, value: Any) -> bool:
        """Set a configuration value and save"""
        logger.info(f"[CONFIG SET] set() called for key='{key}'")

        if key == 'saved_catalogs':
            count = len(value) if isinstance(value, list) else 0
            logger.info(f"[CONFIG SET] Setting saved_catalogs with {count} catalogs")

        self.config[key] = value
        logger.info(f"[CONFIG SET] Key '{key}' updated in memory, calling save()...")

        result = self.save()
        logger.info(f"[CONFIG SET] save() returned: {result}")

        return result

    def update(self, updates: Dict[str, Any]) -> bool:
        """Update multiple configuration values and save"""
        # Migrate old config keys before updating
        # This ensures backward compatibility when old keys are sent via API
        migrated_updates = self._migrate_series_to_episode_limits(updates.copy())
        self.config.update(migrated_updates)
        return self.save()

    def get_all(self) -> Dict[str, Any]:
        """Get all configuration"""
        return self.config.copy()

    def reset(self) -> bool:
        """Reset configuration to defaults"""
        self.config = copy.deepcopy(self.DEFAULT_CONFIG)
        return self.save()

    def get_addons(self) -> List:
        """Get addon URLs as Addon objects"""
        from addon import addon_list_from_config
        return addon_list_from_config(self.config.get('addon_urls', []))

    def set_addons(self, addons: List) -> bool:
        """Set addon URLs from list of Addon objects"""
        from addon import addon_list_to_config
        return self.set('addon_urls', addon_list_to_config(addons))

    def to_cli_args(self) -> List[str]:
        """Convert configuration to CLI arguments for streams_prefetcher.py"""
        args = []

        # Addon URLs (required)
        if self.config['addon_urls']:
            url_strings = [f"{item['type']}:{item['url']}" for item in self.config['addon_urls']]
            args.extend(['--addon-urls', ','.join(url_strings)])

        # Integer limits
        args.extend(['--movies-global-limit', str(self.config['movies_global_limit'])])
        args.extend(['--episodes-global-limit', str(self.config['episodes_global_limit'])])
        args.extend(['--movies-per-catalog', str(self.config['movies_per_catalog'])])
        args.extend(['--episodes-per-catalog', str(self.config['episodes_per_catalog'])])
        args.extend(['--episodes-per-mixed-catalog', str(self.config['episodes_per_mixed_catalog'])])
        args.extend(['--max-movie-items-per-catalog-fetch', str(self.config['max_movie_items_per_catalog_fetch'])])
        args.extend(['--max-series-items-per-catalog-fetch', str(self.config['max_series_items_per_catalog_fetch'])])
        args.extend(['--max-mixed-items-per-catalog-fetch', str(self.config['max_mixed_items_per_catalog_fetch'])])

        # Time-based parameters (convert seconds to string format)
        if self.config['delay'] > 0:
            args.extend(['--delay', f"{self.config['delay']}s"])

        args.extend(['--cache-validity', f"{self.config['cache_validity']}s"])
        args.extend(['--max-execution-time', f"{self.config['max_execution_time']}s"])

        # Proxy (optional)
        if self.config.get('proxy'):
            args.extend(['--proxy', self.config['proxy']])

        # Flags
        if self.config['randomize_catalog_processing']:
            args.append('--randomize-catalog-processing')

        if self.config['randomize_item_prefetching']:
            args.append('--randomize-item-prefetching')

        if self.config['enable_logging']:
            args.append('--enable-logging')

        return args

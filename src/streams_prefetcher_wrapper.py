"""
Streams Prefetcher Wrapper
Provides a programmatic interface to run streams_prefetcher.py with callbacks
"""

import sys
import io
from typing import Callable, Optional, Dict, Any, List, Tuple
from streams_prefetcher_filtered import FilteredStreamsPrefetcher
from config_manager import ConfigManager
from addon import addon_list_from_config, addon_list_to_config, Addon
from catalog_id_utils import get_addon_url_part, get_catalog_id_part, get_catalog_type_part
from logger import get_logger

# Initialize logger for this module
logger = get_logger('streams_prefetcher.wrapper')


class StreamsPrefetcherWrapper:
    """Wrapper for programmatic execution of StreamsPrefetcher"""

    def __init__(
        self,
        config_manager: ConfigManager,
        scheduler = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        output_callback: Optional[Callable[[str], None]] = None
    ):
        self.config_manager = config_manager
        self.scheduler = scheduler
        self.progress_callback = progress_callback
        self.output_callback = output_callback
        self.prefetcher = None

    def _parse_config_to_args(self) -> Dict[str, Any]:
        """Parse configuration into arguments for StreamsPrefetcher"""
        logger.info("🔧 [WRAPPER] Parsing configuration...")
        config = self.config_manager.get_all()
        logger.debug(f"📊 [WRAPPER] Config has {len(config)} keys")

        # Get saved catalogs (filtered by enabled state)
        saved_catalogs = config.get('saved_catalogs', [])
        logger.debug(f"📋 [WRAPPER] Found {len(saved_catalogs)} saved catalogs")
        enabled_catalogs = [cat for cat in saved_catalogs if cat.get('enabled', False)]
        logger.info(f"✅ [WRAPPER] {len(enabled_catalogs)} catalogs enabled")

        # Group enabled catalogs by addon URL
        addon_catalog_map = {}
        for cat in enabled_catalogs:
            addon_url = cat['addon_url']
            if addon_url not in addon_catalog_map:
                addon_catalog_map[addon_url] = []
            addon_catalog_map[addon_url].append(cat)
        logger.debug(f"🗺️ [WRAPPER] Catalogs mapped to {len(addon_catalog_map)} addon URLs")


        # Build catalog filter (tuples of addon_url, catalog_id and type to include)
        # This keeps selections scoped to the exact addon source.
        catalog_filter = []
        for cat in enabled_catalogs:
            # Extract catalog ID and type from the full ID (format: "addon_url|catalog_id|catalog_type")
            addon_url = get_addon_url_part(cat['id']) or cat.get('addon_url', '')
            catalog_id = get_catalog_id_part(cat['id'])
            catalog_type = get_catalog_type_part(cat['id'])
            logger.debug(f"   • Catalog: {cat.get('name', 'Unknown')} -> ID: {catalog_id}, Type: {catalog_type}")
            if addon_url and catalog_id and catalog_type:
                # Include addon URL so identical catalog IDs in different addons do not all match.
                catalog_filter.append((addon_url, catalog_id, catalog_type))
        logger.info(f"🔍 [WRAPPER] Built catalog filter with {len(catalog_filter)} entries")

        # Get cache_uncached_streams config
        cache_uncached_streams = config.get('cache_uncached_streams', {})
        logger.debug("💾 [WRAPPER] Cache uncached streams config parsed")

        # Convert addon URLs to Addon objects
        addons = []
        addon_urls = config.get('addon_urls', [])
        logger.debug(f"📡 [WRAPPER] Processing {len(addon_urls)} addon URLs")
        for item in addon_urls:
            # Include catalog addons that have enabled catalogs
            if item['type'] in ['catalog', 'both'] and item['url'] in addon_catalog_map:
                logger.debug(f"   • Adding {item['type']} addon: {item['url']}")
                try:
                    addon = Addon.from_dict(item)
                    addons.append(addon)
                    logger.debug(f"     ✅ Successfully created Addon object")
                except Exception as e:
                    logger.error(f"     ❌ Failed to create Addon object: {e}")
            # Always include stream-only addons regardless of catalog selection
            elif item['type'] == 'stream':
                logger.debug(f"   • Adding stream-only addon: {item['url']}")
                try:
                    addon = Addon.from_dict(item)
                    addons.append(addon)
                    logger.debug(f"     ✅ Successfully created stream Addon object")
                except Exception as e:
                    logger.error(f"     ❌ Failed to create stream Addon object: {e}")

        if not addons:
            logger.error("❌ [WRAPPER] No addons configured or no catalogs enabled")
            raise ValueError("No addons configured or no catalogs enabled")

        logger.info(f"✅ [WRAPPER] Successfully created {len(addons)} addon objects")

        args = {
            'addons': addons,
            'catalog_filter': catalog_filter if catalog_filter else None,
            'movies_global_limit': config.get('movies_global_limit', -1),
            'episodes_global_limit': config.get('episodes_global_limit', -1),
            'movies_per_catalog': config.get('movies_per_catalog', 50),
            'episodes_per_catalog': config.get('episodes_per_catalog', 50),
            'episodes_per_mixed_catalog': config.get('episodes_per_mixed_catalog', 20),
            'delay': config.get('delay', 0),
            'network_request_timeout': config.get('network_request_timeout', 30),
            'proxy_url': config.get('proxy', None) or None,
            'randomize_catalogs': config.get('randomize_catalog_processing', False),
            'randomize_items': config.get('randomize_item_prefetching', False),
            'cache_validity_seconds': config.get('cache_validity', 259200),
            'max_execution_time': config.get('max_execution_time', -1),
            'enable_logging': config.get('enable_logging', False),
            'cache_uncached_streams_enabled': cache_uncached_streams.get('enabled', False),
            'cached_stream_regex': cache_uncached_streams.get('cached_stream_regex', '⚡'),
            'skip_streams_regex': cache_uncached_streams.get('skip_streams_regex', ''),
            'max_successful_cache_requests_per_item': cache_uncached_streams.get('max_successful_cache_requests_per_item', 1),
            'max_cache_request_attempts_per_item': cache_uncached_streams.get('max_cache_request_attempts_per_item', 3),
            'max_cache_requests_global': cache_uncached_streams.get('max_cache_requests_global', 50),
            'cached_streams_count_threshold': cache_uncached_streams.get('cached_streams_count_threshold', 0),
            'max_movie_items_per_catalog_fetch': config.get('max_movie_items_per_catalog_fetch', -1),
            'max_series_items_per_catalog_fetch': config.get('max_series_items_per_catalog_fetch', -1),
            'max_mixed_items_per_catalog_fetch': config.get('max_mixed_items_per_catalog_fetch', -1)
        }

        logger.debug("🔧 [WRAPPER] Configuration parsing complete")
        return args

    def run(self) -> Dict[str, Any]:
        """Run the prefetcher and return results"""
        try:
            # Parse configuration
            logger.info("🚀 [WRAPPER] Starting prefetch job...")
            args = self._parse_config_to_args()
            logger.info(f"📊 [WRAPPER] Parsed {len(args.get('addons', []))} addons and {len(args.get('catalog_filter', []))} catalog filters")

            # Debug: log all args
            logger.debug("🔧 [WRAPPER] Configuration arguments:")
            for key, value in args.items():
                if key not in ['addons']:  # Don't log full addon objects
                    logger.debug(f"   • {key}: {value}")

            logger.debug(f"   • addons: {len(args.get('addons', []))} objects")

            # Create prefetcher instance with filtering support
            logger.info("🔧 [WRAPPER] Creating FilteredStreamsPrefetcher instance...")
            self.prefetcher = FilteredStreamsPrefetcher(scheduler=self.scheduler, **args)
            logger.info("✅ [WRAPPER] FilteredStreamsPrefetcher created successfully")

            # Optionally wrap progress tracker methods to provide callbacks
            if self.progress_callback:
                logger.debug("📊 [WRAPPER] Wrapping progress tracker callbacks...")
                self._wrap_progress_tracker()
                logger.debug("✅ [WRAPPER] Progress tracker wrapped")

            # Run the prefetcher
            logger.info("🚀 [WRAPPER] Starting prefetcher.process_all()...")
            results = self.prefetcher.process_all()
            logger.info("✅ [WRAPPER] prefetcher.process_all() completed")

            # Print summary
            logger.info("📋 [WRAPPER] Printing summary...")
            self.prefetcher.print_summary(interrupted=False)

            return {'success': True, 'results': results}

        except KeyboardInterrupt:
            logger.error("⚠️ [WRAPPER] Keyboard interrupt received")
            if self.output_callback:
                self.output_callback("\n\nScript interrupted by user. Cleaning up and generating summary...")

            results = None
            if self.prefetcher:
                logger.debug("🧹 [WRAPPER] Cleaning up dashboard...")
                self.prefetcher.progress_tracker.cleanup_dashboard()
                # Use centralized method to get finalized results with all statistics
                logger.debug("📊 [WRAPPER] Getting final results...")
                results = self.prefetcher.get_final_results(interrupted=True)
                logger.debug("📋 [WRAPPER] Printing interrupted summary...")
                self.prefetcher.print_summary(interrupted=True)

            return {'success': False, 'interrupted': True, 'results': results}

        except Exception as e:
            logger.error(f"❌ [WRAPPER] EXCEPTION: {type(e).__name__}: {e}", exc_info=True)
            if self.output_callback:
                self.output_callback(f"\n\nAn unexpected error occurred: {e}")

            results = None
            if self.prefetcher:
                logger.debug("🧹 [WRAPPER] Cleaning up dashboard after error...")
                self.prefetcher.progress_tracker.cleanup_dashboard()
                # Use centralized method to get finalized results with all statistics
                logger.debug("📊 [WRAPPER] Getting final results after error...")
                results = self.prefetcher.get_final_results(interrupted=True)

            return {'success': False, 'error': str(e), 'results': results}

        finally:
            if self.prefetcher and self.prefetcher.db_conn:
                logger.debug("🔐 [WRAPPER] Closing database connection...")
                self.prefetcher.db_conn.close()
                logger.debug("✅ [WRAPPER] Database connection closed")

    def _wrap_progress_tracker(self):
        """Wrap progress tracker methods to provide callbacks"""
        original_redraw = self.prefetcher.progress_tracker.redraw_dashboard

        def wrapped_redraw(**kwargs):
            # Call original method
            original_redraw(**kwargs)

            # Extract progress data and call callback
            if self.progress_callback:
                mode = kwargs.get('mode', 'idle')
                cached_count = kwargs.get('prefetched_cached_count', 0)

                # Build comprehensive progress data
                progress_data = {
                    'catalog_name': kwargs.get('catalog_name', ''),
                    'catalog_mode': kwargs.get('catalog_mode', ''),
                    'completed_catalogs': kwargs.get('completed_catalogs', 0),
                    'total_catalogs': kwargs.get('total_catalogs', 0),
                    'movies_prefetched': kwargs.get('prefetched_movies_count', 0),
                    'movies_limit': kwargs.get('movies_global_limit', -1),
                    'series_prefetched': self.prefetcher.series_count,
                    'episodes_prefetched': kwargs.get('prefetched_episodes_count', 0),
                    'episodes_limit': kwargs.get('episodes_global_limit', -1),
                    'cached_count': cached_count,
                    'catalog_movies_count': kwargs.get('catalog_movies_count', 0),
                    'catalog_episodes_count': kwargs.get('catalog_episodes_count', 0),
                    'mode': mode,
                    'current_title': kwargs.get('current_title', ''),
                    'current_imdb_id': kwargs.get('current_imdb_id', ''),
                    'current_item_type': kwargs.get('current_item_type', ''),
                    'current_catalog_items': kwargs.get('prefetched_in_this_catalog', 0),
                    'current_catalog_limit': kwargs.get('per_catalog_limit', -1),
                    'service_cache_requests_sent': self.prefetcher.cache_requests_sent_count,
                    'service_cache_requests_successful': self.prefetcher.cache_requests_successful_count,
                    'service_cache_requests_limit': self.prefetcher.max_cache_requests_global,
                }

                # Debug logging for cache requests
                if self.prefetcher.cache_requests_sent_count > 0:
                    logger.debug(f"📊 PROGRESS UPDATE: Cache requests - sent: {self.prefetcher.cache_requests_sent_count}, successful: {self.prefetcher.cache_requests_successful_count}")

                # Add page fetching information
                if mode == 'fetching':
                    progress_data['current_page'] = kwargs.get('fetched_items', 0)
                    progress_data['fetching_page'] = True
                elif mode == 'prefetching':
                    # Calculate items discovered from item_statuses or total_items
                    item_statuses = kwargs.get('item_statuses', [])
                    total_items = kwargs.get('total_items', len(item_statuses))
                    progress_data['items_on_current_page'] = total_items
                    progress_data['processed_items_on_page'] = len(item_statuses)
                    progress_data['fetching_page'] = False

                self.progress_callback(progress_data)

        # Replace the method
        self.prefetcher.progress_tracker.redraw_dashboard = wrapped_redraw

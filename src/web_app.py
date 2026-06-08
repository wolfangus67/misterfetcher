"""
Streams Prefetcher - Web Application
Flask backend providing REST API and SSE for real-time updates
"""

import os
import sys
import json
import time
import queue
from collections import defaultdict
import requests
from datetime import datetime
from typing import Dict, Any
from flask import Flask, jsonify, request, send_from_directory, Response, session, stream_with_context
from flask_cors import CORS
from croniter import croniter
import pytz

# Add src directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_manager import ConfigManager
from job_scheduler import JobScheduler, JobStatus
from logger import setup_logging, get_logger
from catalog_id_utils import create_catalog_id
from user_manager import UserManager

# Initialize logging
setup_logging()
logger = get_logger('streams_prefetcher.web_app')

app = Flask(__name__, static_folder='../web', static_url_path='')
app.secret_key = os.environ.get('STREAMS_PREFETCHER_SECRET_KEY', 'streams-prefetcher-dev-secret')
CORS(app, supports_credentials=True)

# Suppress Flask's default logging, use our logger instead
import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)

user_manager = UserManager()
config_manager_cache: Dict[str, ConfigManager] = {}
job_scheduler_cache: Dict[str, JobScheduler] = {}
event_queues_by_user = defaultdict(list)


def get_current_user():
    """Return current session user info."""
    user_id = session.get('user_id')
    username = session.get('username')
    if not user_id or not username:
        return None
    if not user_manager.get_user(username):
        session.clear()
        return None
    return {'user_id': user_id, 'username': username}


def require_auth():
    """Return session user or an auth error response."""
    user = get_current_user()
    if not user:
        return None, (jsonify({'success': False, 'error': 'Authentication required'}), 401)
    return user, None


def get_user_config_manager(user_id: str) -> ConfigManager:
    """Get per-user config manager."""
    if user_id not in config_manager_cache:
        config_manager_cache[user_id] = ConfigManager(user_id=user_id)
    return config_manager_cache[user_id]


def broadcast_event(user_id: str, event_type: str, data: Dict[str, Any]):
    """Broadcast event to SSE clients for one user."""
    dead_queues = []
    for q in event_queues_by_user.get(user_id, []):
        try:
            q.put({'event': event_type, 'data': data}, block=False)
        except queue.Full:
            dead_queues.append(q)

    for dead_q in dead_queues:
        if dead_q in event_queues_by_user.get(user_id, []):
            event_queues_by_user[user_id].remove(dead_q)


def get_user_job_scheduler(user_id: str) -> JobScheduler:
    """Get per-user scheduler."""
    if user_id not in job_scheduler_cache:
        user_config_manager = get_user_config_manager(user_id)
        scheduler = JobScheduler(user_config_manager)
        scheduler.register_callback(
            lambda event_type, data, uid=user_id: broadcast_event(uid, event_type, data)
        )
        job_scheduler_cache[user_id] = scheduler
    return job_scheduler_cache[user_id]


# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================

def validate_addon_urls(addon_urls, require_runnable=True):
    """Validate addon URLs list"""
    from addon import addon_list_from_config

    errors = []

    if not addon_urls or len(addon_urls) == 0:
        errors.append('At least one addon URL is required')
        return errors

    # Convert to Addon objects for proper validation
    try:
        addons = addon_list_from_config(addon_urls)
    except Exception as e:
        errors.append(f'Failed to parse addon configuration: {str(e)}')
        return errors

    if require_runnable:
        has_catalog = any(addon.type in ['catalog', 'both'] for addon in addons)
        if not has_catalog:
            errors.append('At least one catalog addon (type "catalog" or "both") is required')

        has_stream = any(addon.type in ['stream', 'both'] for addon in addons)
        if not has_stream:
            errors.append('At least one stream addon (type "stream" or "both") is required')

    # Validate each addon using Addon object properties
    for idx, addon in enumerate(addons):
        if not addon.url or not addon.url.strip():
            errors.append(f'Addon URL #{idx + 1} cannot be empty')

        # Validate addon type (already validated by Addon class but keeping for clarity)
        if addon.type not in ['catalog', 'stream', 'both']:
            errors.append(f'Invalid addon type for URL #{idx + 1}: {addon.type}')

    return errors

def validate_limits(config):
    """Validate limit configuration values"""
    errors = []

    limit_fields = [
        ('movies_global_limit', 'Movies Global Limit'),
        ('episodes_global_limit', 'Episodes Global Limit'),
        ('movies_per_catalog', 'Movies per Catalog'),
        ('episodes_per_catalog', 'Episodes per Catalog'),
        ('episodes_per_mixed_catalog', 'Episodes per Mixed Catalog')
    ]

    for field, name in limit_fields:
        value = config.get(field)
        if value is None:
            errors.append(f'{name} is required')
        elif not isinstance(value, int):
            errors.append(f'{name} must be an integer')
        elif value < -1:
            errors.append(f'{name} must be -1 or greater (got: {value})')

    return errors

def validate_time_fields(config):
    """Validate time-based configuration values"""
    errors = []

    # Delay must be >= 0
    delay = config.get('delay')
    if delay is None:
        errors.append('Delay is required')
    elif not isinstance(delay, (int, float)):
        errors.append('Delay must be a number')
    elif delay < 0:
        errors.append('Delay must be 0 or greater')

    # Cache validity must be non-negative or -1 for unlimited
    cache_validity = config.get('cache_validity')
    if cache_validity is None:
        errors.append('Cache validity is required')
    elif not isinstance(cache_validity, (int, float)):
        errors.append('Cache validity must be a number')
    elif cache_validity < -1:
        errors.append('Cache validity must be 0 or positive, or -1 for unlimited')

    # Max execution time must be positive or -1
    max_exec = config.get('max_execution_time')
    if max_exec is None:
        errors.append('Max execution time is required')
    elif not isinstance(max_exec, (int, float)):
        errors.append('Max execution time must be a number')
    elif max_exec < -1 or max_exec == 0:
        errors.append('Max execution time must be positive or -1 for unlimited')

    return errors

def validate_configuration(config, require_runnable=True):
    """Validate entire configuration"""
    all_errors = []

    addon_urls = config.get('addon_urls', [])
    all_errors.extend(validate_addon_urls(addon_urls, require_runnable=require_runnable))
    all_errors.extend(validate_limits(config))
    all_errors.extend(validate_time_fields(config))

    return all_errors


# ============================================================================
# STATIC FILES
# ============================================================================

@app.route('/')
def serve_index():
    """Serve the main HTML page"""
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/<path:path>')
def serve_static(path):
    """Serve static files"""
    return send_from_directory(app.static_folder, path)


# ============================================================================
# AUTH API
# ============================================================================

@app.route('/api/auth/me', methods=['GET'])
def auth_me():
    """Return the current authenticated user."""
    user = get_current_user()
    if not user:
        return jsonify({'success': True, 'authenticated': False, 'user': None})

    return jsonify({
        'success': True,
        'authenticated': True,
        'user': {
            'id': user['user_id'],
            'username': user['username']
        }
    })


@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    """Create a new user account."""
    try:
        data = request.get_json() or {}
        username = str(data.get('username', '')).strip()
        password = str(data.get('password', ''))
        user = user_manager.register_user(username, password)

        session.clear()
        session['user_id'] = user['user_id']
        session['username'] = user['username']

        get_user_config_manager(user['user_id'])

        return jsonify({
            'success': True,
            'user': {
                'id': user['user_id'],
                'username': user['username']
            }
        })
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Registration failed: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    """Authenticate an existing user."""
    try:
        data = request.get_json() or {}
        username = str(data.get('username', '')).strip()
        password = str(data.get('password', ''))
        user = user_manager.authenticate(username, password)

        if not user:
            return jsonify({'success': False, 'error': 'Invalid username or password'}), 401

        session.clear()
        session['user_id'] = user['user_id']
        session['username'] = user['username']

        get_user_config_manager(user['user_id'])

        return jsonify({
            'success': True,
            'user': {
                'id': user['user_id'],
                'username': user['username']
            }
        })
    except Exception as e:
        logger.error(f"Login failed: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    """Clear current session."""
    session.clear()
    return jsonify({'success': True})


# ============================================================================
# CONFIGURATION API
# ============================================================================

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration"""
    try:
        user, auth_error = require_auth()
        if auth_error:
            return auth_error

        config_manager = get_user_config_manager(user['user_id'])
        config = config_manager.get_all()
        return jsonify({'success': True, 'config': config})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config', methods=['POST'])
def update_config():
    """Update configuration"""
    try:
        user, auth_error = require_auth()
        if auth_error:
            return auth_error

        config_manager = get_user_config_manager(user['user_id'])
        job_scheduler = get_user_job_scheduler(user['user_id'])

        # Check if job is running
        if job_scheduler.job_status == JobStatus.RUNNING:
            return jsonify({
                'success': False,
                'error': 'Cannot modify configuration while job is running'
            }), 400

        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        # Migrate old config keys BEFORE validation
        data = config_manager._migrate_series_to_episode_limits(data)

        # Validate configuration
        validation_errors = validate_configuration(data, require_runnable=False)
        if validation_errors:
            return jsonify({
                'success': False,
                'error': 'Validation failed: ' + '; '.join(validation_errors)
            }), 400

        # Update configuration
        success = config_manager.update(data)

        if success:
            return jsonify({'success': True, 'config': config_manager.get_all()})
        else:
            return jsonify({'success': False, 'error': 'Failed to save configuration'}), 500

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config/reset', methods=['POST'])
def reset_config():
    """Reset configuration to defaults and clear all data except database"""
    try:
        user, auth_error = require_auth()
        if auth_error:
            return auth_error

        config_manager = get_user_config_manager(user['user_id'])
        job_scheduler = get_user_job_scheduler(user['user_id'])

        # Check if job is running
        if job_scheduler.job_status == JobStatus.RUNNING:
            return jsonify({
                'success': False,
                'error': 'Cannot reset configuration while job is running'
            }), 400

        # Reset configuration to defaults
        success = config_manager.reset()

        if not success:
            return jsonify({'success': False, 'error': 'Failed to reset configuration'}), 500

        # Clear addon name and logo cache
        config_manager.set('addon_name_cache', {})
        config_manager.set('addon_logo_cache', {})

        # Disable any active schedule
        job_scheduler.disable_schedule()

        logger.info("Configuration reset completed for current user")

        return jsonify({'success': True, 'config': config_manager.get_all()})

    except Exception as e:
        logger.error(f"Error during reset: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# CATALOG API
# ============================================================================

@app.route('/api/catalogs/load', methods=['POST'])
def load_catalogs():
    """Load catalogs from configured addon URLs"""
    try:
        user, auth_error = require_auth()
        if auth_error:
            return auth_error

        config_manager = get_user_config_manager(user['user_id'])
        addon_urls = config_manager.get('addon_urls', [])

        if not addon_urls:
            return jsonify({
                'success': False,
                'error': 'No addon URLs configured'
            }), 400

        catalogs = []
        errors = []

        # Convert to Addon objects for consistent usage
        from addon import addon_list_from_config
        addons = addon_list_from_config(addon_urls)

        for addon in addons:
            if addon.type in ['catalog', 'both']:
                try:
                    # Fetch manifest using Addon object URL
                    response = requests.get(
                        f"{addon.url}/manifest.json",
                        timeout=10,
                        headers={
                            'User-Agent': 'Streams Prefetcher/1.0',
                            'Accept': 'application/json'
                        }
                    )
                    response.raise_for_status()
                    manifest = response.json()

                    # Extract addon name using Addon object if available, otherwise from manifest
                    addon_name = addon.name if addon.name else manifest.get('name', 'Unknown Addon')

                    # Process catalogs
                    for catalog in manifest.get('catalogs', []):
                        # Skip search-only catalogs
                        extras = catalog.get('extra', [])
                        is_search_only = (
                            len(extras) == 1 and
                            extras[0].get('name') == 'search'
                        )
                        if is_search_only:
                            continue

                        # Skip unsupported types
                        cat_type = catalog.get('type', '').lower()
                        if cat_type in ['tv', 'channel']:
                            continue

                        # Rename 'all' to 'mixed'
                        if cat_type == 'all':
                            cat_type = 'mixed'

                        catalogs.append({
                            'id': create_catalog_id(addon.url, catalog.get('id', ''), cat_type),
                            'name': catalog.get('name', 'Unknown'),
                            'type': cat_type,
                            'addon_name': addon_name,
                            'addon_url': addon.url,
                            'extra': catalog.get('extra', []),
                            'pageSize': catalog.get('pageSize', 100),
                            'showInHome': catalog.get('showInHome', False),
                            'isSearch': catalog.get('isSearch', False),
                            'enabled': True,  # Default enabled
                            'order': len(catalogs)
                        })

                except Exception as e:
                    errors.append({
                        'url': addon.url,
                        'error': str(e)
                    })

        return jsonify({
            'success': True,
            'catalogs': catalogs,
            'errors': errors,
            'total_addons': len([addon for addon in addons if addon.type in ['catalog', 'both']]),
            'total_catalogs': len(catalogs)
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _get_current_catalog_ids_for_addons(addon_urls):
    """Fetch current catalog IDs from configured catalog addons."""
    current_ids = set()
    if not addon_urls:
        return current_ids

    from addon import addon_list_from_config
    addons = addon_list_from_config(addon_urls)

    for addon in addons:
        if addon.type not in ['catalog', 'both']:
            continue

        try:
            response = requests.get(
                f"{addon.url}/manifest.json",
                timeout=10,
                headers={
                    'User-Agent': 'Streams Prefetcher/1.0',
                    'Accept': 'application/json'
                }
            )
            response.raise_for_status()
            manifest = response.json()

            for catalog in manifest.get('catalogs', []):
                extras = catalog.get('extra', [])
                is_search_only = (
                    len(extras) == 1 and
                    extras[0].get('name') == 'search'
                )
                if is_search_only:
                    continue

                cat_type = catalog.get('type', '').lower()
                if cat_type in ['tv', 'channel']:
                    continue
                if cat_type == 'all':
                    cat_type = 'mixed'

                current_ids.add(create_catalog_id(addon.url, catalog.get('id', ''), cat_type))

        except Exception as e:
            logger.warning(f"Failed to refresh catalogs for pruning from {addon.url}: {e}")

    return current_ids


@app.route('/api/catalogs/selection', methods=['GET'])
def get_catalog_selection():
    """Get saved catalog selection"""
    try:
        user, auth_error = require_auth()
        if auth_error:
            return auth_error

        config_manager = get_user_config_manager(user['user_id'])
        saved_catalogs = config_manager.get('saved_catalogs', [])
        addon_urls = config_manager.get('addon_urls', [])
        current_catalog_ids = _get_current_catalog_ids_for_addons(addon_urls)

        if current_catalog_ids:
            pruned_catalogs = [cat for cat in saved_catalogs if cat.get('id') in current_catalog_ids]
            removed_count = len(saved_catalogs) - len(pruned_catalogs)
            if removed_count > 0:
                logger.info(f"Pruned {removed_count} stale saved catalogs that no longer exist in the addon manifests")
                config_manager.set('saved_catalogs', pruned_catalogs)
                saved_catalogs = pruned_catalogs

        return jsonify({'success': True, 'catalogs': saved_catalogs})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/catalogs/selection', methods=['POST'])
def save_catalog_selection():
    """Save catalog selection and order"""
    try:
        user, auth_error = require_auth()
        if auth_error:
            return auth_error

        config_manager = get_user_config_manager(user['user_id'])
        logger.info("[CATALOG SAVE] ========== SAVE REQUEST RECEIVED ==========")

        data = request.get_json()
        logger.info(f"[CATALOG SAVE] Request data keys: {list(data.keys()) if data else 'None'}")

        if not data or 'catalogs' not in data:
            logger.warning("[CATALOG SAVE] ✗ No catalog data provided in request")
            return jsonify({'success': False, 'error': 'No catalog data provided'}), 400

        catalogs = data['catalogs']
        logger.info(f"[CATALOG SAVE] Total catalogs received: {len(catalogs)}")
        logger.info(f"[CATALOG SAVE] Enabled catalogs: {len([c for c in catalogs if c.get('enabled', False)])}")
        logger.info(f"[CATALOG SAVE] Disabled catalogs: {len([c for c in catalogs if not c.get('enabled', False)])}")

        # Log first 3 catalogs for debugging
        for idx, cat in enumerate(catalogs[:3]):
            logger.info(f"[CATALOG SAVE] Catalog {idx + 1}: name='{cat.get('name', 'Unknown')}', enabled={cat.get('enabled', False)}, order={cat.get('order', -1)}")

        if len(catalogs) > 3:
            logger.info(f"[CATALOG SAVE] ... and {len(catalogs) - 3} more catalogs")

        # Save full catalog data (not just selection)
        logger.info("[CATALOG SAVE] Calling config_manager.set('saved_catalogs', ...)")
        success = config_manager.set('saved_catalogs', catalogs)
        logger.info(f"[CATALOG SAVE] config_manager.set returned: {success}")

        if success:
            # Verify the save by reading back
            saved_catalogs = config_manager.get('saved_catalogs', [])
            logger.info(f"[CATALOG SAVE] Verification read: {len(saved_catalogs)} catalogs found in config")
            logger.info("[CATALOG SAVE] ✓ Save successful!")
            return jsonify({'success': True})
        else:
            logger.error("[CATALOG SAVE] ✗ config_manager.set returned False")
            return jsonify({'success': False, 'error': 'Failed to save catalog selection'}), 500

    except Exception as e:
        logger.error(f"[CATALOG SAVE] ✗ Exception occurred: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/catalogs/reset', methods=['POST'])
def reset_catalog_selections():
    """Reset catalog selections and clear saved catalogs from config"""
    try:
        user, auth_error = require_auth()
        if auth_error:
            return auth_error

        config_manager = get_user_config_manager(user['user_id'])
        # Clear saved catalogs from config
        config_manager.set('saved_catalogs', [])

        logger.info("Catalog selections reset - cleared all saved catalogs")

        return jsonify({'success': True, 'message': 'Catalog selections reset successfully'})

    except Exception as e:
        logger.error(f"Error resetting catalog selections: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/addon/manifest', methods=['POST'])
def fetch_addon_manifest():
    """Fetch addon manifest and extract name"""
    try:
        user, auth_error = require_auth()
        if auth_error:
            return auth_error

        config_manager = get_user_config_manager(user['user_id'])
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({'success': False, 'error': 'No URL provided'}), 400

        addon_url = data['url'].split('#')[0].split('?')[0].rstrip('/')

        if addon_url.endswith('/manifest.json'):
            addon_url = addon_url[:-len('/manifest.json')]
        addon_url = addon_url.rstrip('/')

        try:
            # Fetch manifest
            response = requests.get(
                f"{addon_url}/manifest.json",
                timeout=10,
                headers={
                    'User-Agent': 'Streams Prefetcher/1.0',
                    'Accept': 'application/json'
                }
            )
            response.raise_for_status()
            manifest = response.json()

            addon_name = manifest.get('name', 'Unknown Addon')
            addon_logo = manifest.get('logo', '')

            # Cache the addon name and logo in config
            addon_name_cache = config_manager.get('addon_name_cache', {})
            addon_name_cache[addon_url] = addon_name
            config_manager.set('addon_name_cache', addon_name_cache)

            addon_logo_cache = config_manager.get('addon_logo_cache', {})
            addon_logo_cache[addon_url] = addon_logo
            config_manager.set('addon_logo_cache', addon_logo_cache)

            return jsonify({
                'success': True,
                'name': addon_name,
                'logo': addon_logo,
                'url': addon_url
            })

        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to fetch manifest from {addon_url}: {str(e)}")
            return jsonify({
                'success': False,
                'error': f'Failed to fetch manifest: {str(e)}'
            }), 400

    except Exception as e:
        logger.error(f"Error fetching addon manifest: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# TIMEZONE API
# ============================================================================

@app.route('/api/timezone', methods=['GET'])
def get_timezone():
    """Get server timezone from TZ environment variable"""
    try:
        # Get timezone from environment, default to UTC
        tz = os.environ.get('TZ', 'UTC')

        return jsonify({
            'success': True,
            'timezone': tz
        })

    except Exception as e:
        logger.error(f"Error getting timezone: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# SCHEDULE API
# ============================================================================

@app.route('/api/schedule', methods=['GET'])
def get_schedule():
    """Get schedule information"""
    try:
        user, auth_error = require_auth()
        if auth_error:
            return auth_error

        config_manager = get_user_config_manager(user['user_id'])
        schedule_config = config_manager.get('schedule', {})

        return jsonify({
            'success': True,
            'schedule': {
                'enabled': schedule_config.get('enabled', False),
                'schedules': schedule_config.get('schedules', [])
            }
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/schedule', methods=['POST'])
def update_schedule():
    """Update schedule configuration"""
    try:
        user, auth_error = require_auth()
        if auth_error:
            return auth_error

        job_scheduler = get_user_job_scheduler(user['user_id'])
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        enabled = data.get('enabled', False)
        schedules = data.get('schedules', [])
        timezone_str = data.get('timezone') or 'UTC'

        try:
            pytz.timezone(timezone_str)
        except Exception:
            return jsonify({
                'success': False,
                'error': f'Invalid timezone: {timezone_str}'
            }), 400

        # Validate schedules format
        if enabled and schedules:
            for idx, schedule in enumerate(schedules):
                if 'time' not in schedule:
                    return jsonify({
                        'success': False,
                        'error': f'Schedule #{idx + 1} missing time field'
                    }), 400

                if 'days' not in schedule or not isinstance(schedule['days'], list):
                    return jsonify({
                        'success': False,
                        'error': f'Schedule #{idx + 1} missing or invalid days field'
                    }), 400

                # Validate time format (HH:MM)
                time_str = schedule['time']
                try:
                    time_parts = time_str.split(':')
                    if len(time_parts) != 2:
                        raise ValueError()
                    hour = int(time_parts[0])
                    minute = int(time_parts[1])
                    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                        raise ValueError()
                except:
                    return jsonify({
                        'success': False,
                        'error': f'Schedule #{idx + 1} has invalid time format. Expected HH:MM'
                    }), 400

                # Validate days (0-6)
                for day in schedule['days']:
                    if not isinstance(day, int) or day < 0 or day > 6:
                        return jsonify({
                            'success': False,
                            'error': f'Schedule #{idx + 1} has invalid day value. Must be 0-6'
                        }), 400

        # Update schedule
        success = job_scheduler.update_schedules(enabled, schedules, timezone_str)

        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to update schedule'}), 500

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/schedule', methods=['DELETE'])
def disable_schedule():
    """Disable scheduled jobs"""
    try:
        user, auth_error = require_auth()
        if auth_error:
            return auth_error

        job_scheduler = get_user_job_scheduler(user['user_id'])
        job_scheduler.disable_schedule()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# JOB API
# ============================================================================

@app.route('/api/job/status', methods=['GET'])
def get_job_status():
    """Get current job status"""
    try:
        user, auth_error = require_auth()
        if auth_error:
            return auth_error

        job_scheduler = get_user_job_scheduler(user['user_id'])
        status = job_scheduler.get_status()
        return jsonify({'success': True, 'status': status})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/job/run', methods=['POST'])
def run_job():
    """Run a prefetch job manually"""
    try:
        user, auth_error = require_auth()
        if auth_error:
            return auth_error

        config_manager = get_user_config_manager(user['user_id'])
        job_scheduler = get_user_job_scheduler(user['user_id'])

        # Validate configuration before running
        config = config_manager.get_all()
        validation_errors = validate_configuration(config)
        if validation_errors:
            return jsonify({
                'success': False,
                'error': 'Configuration validation failed: ' + '; '.join(validation_errors)
            }), 400

        # Check if catalogs are available
        saved_catalogs = config_manager.get('saved_catalogs', [])
        if not saved_catalogs or len(saved_catalogs) == 0:
            return jsonify({
                'success': False,
                'error': 'No catalogs loaded. Please load catalogs first'
            }), 400

        # Check if at least one catalog is selected
        selected_catalogs = [cat for cat in saved_catalogs if cat.get('enabled', False)]
        if len(selected_catalogs) == 0:
            return jsonify({
                'success': False,
                'error': 'At least one catalog must be selected'
            }), 400

        success, message = job_scheduler.run_job(manual=True)

        if success:
            logger.info(f"Prefetch job started manually - {len(selected_catalogs)} catalogs selected")
            logger.debug(f"Selected catalogs: {[cat.get('name', 'Unknown') for cat in selected_catalogs]}")
            return jsonify({'success': True, 'message': message})
        else:
            logger.warning(f"Failed to start prefetch job: {message}")
            return jsonify({'success': False, 'error': message}), 400

    except Exception as e:
        logger.error(f"Error starting prefetch job: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/job/cancel', methods=['POST'])
def cancel_job():
    """Cancel running job"""
    try:
        user, auth_error = require_auth()
        if auth_error:
            return auth_error

        job_scheduler = get_user_job_scheduler(user['user_id'])
        success = job_scheduler.cancel_job()

        if success:
            return jsonify({'success': True, 'message': 'Job cancelled'})
        else:
            return jsonify({
                'success': False,
                'error': 'No running job to cancel'
            }), 400

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/job/pause', methods=['POST'])
def pause_job():
    """Pause running job"""
    try:
        user, auth_error = require_auth()
        if auth_error:
            return auth_error

        job_scheduler = get_user_job_scheduler(user['user_id'])
        success, message = job_scheduler.pause_job()

        if success:
            logger.info("Job paused via API")
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'success': False, 'error': message}), 400

    except Exception as e:
        logger.error(f"Error pausing job: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/job/resume', methods=['POST'])
def resume_job():
    """Resume paused job"""
    try:
        user, auth_error = require_auth()
        if auth_error:
            return auth_error

        job_scheduler = get_user_job_scheduler(user['user_id'])
        success, message = job_scheduler.resume_job()

        if success:
            logger.info("Job resumed via API")
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'success': False, 'error': message}), 400

    except Exception as e:
        logger.error(f"Error resuming job: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/job/reset', methods=['POST'])
def reset_job():
    """Reset job status from failed/completed/cancelled to idle"""
    try:
        user, auth_error = require_auth()
        if auth_error:
            return auth_error

        job_scheduler = get_user_job_scheduler(user['user_id'])
        success, message = job_scheduler.reset_job()

        if success:
            logger.info("Job status reset via API")
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'success': False, 'error': message}), 400

    except Exception as e:
        logger.error(f"Error resetting job: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/job/output', methods=['GET'])
def get_job_output():
    """Get job output (paginated)"""
    try:
        user, auth_error = require_auth()
        if auth_error:
            return auth_error

        job_scheduler = get_user_job_scheduler(user['user_id'])
        from_line = request.args.get('from_line', 0, type=int)
        output = job_scheduler.get_output(from_line)

        return jsonify({'success': True, 'output': output})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# SERVER-SENT EVENTS (SSE) FOR REAL-TIME UPDATES
# ============================================================================

@app.route('/api/events')
def stream_events():
    """Server-Sent Events endpoint for real-time updates"""
    user, auth_error = require_auth()
    if auth_error:
        return auth_error

    user_id = user['user_id']
    job_scheduler = get_user_job_scheduler(user_id)

    @stream_with_context
    def event_stream():
        # Create a queue for this client
        q = queue.Queue(maxsize=100)
        event_queues_by_user[user_id].append(q)
        logger.info(f"New SSE connection established for {user_id}. Active connections: {len(event_queues_by_user[user_id])}")

        try:
            # Send initial connection message
            yield f"data: {json.dumps({'event': 'connected', 'data': {}})}\n\n"

            # Send initial status
            status = job_scheduler.get_status()
            yield f"data: {json.dumps({'event': 'status', 'data': status})}\n\n"

            # Stream events
            while True:
                try:
                    event = q.get(timeout=10)  # 10 second timeout (reduced from 30s for faster cleanup)
                    yield f"data: {json.dumps(event)}\n\n"
                except queue.Empty:
                    # Send keepalive
                    yield f": keepalive\n\n"

        except GeneratorExit:
            # Client disconnected
            if q in event_queues_by_user[user_id]:
                event_queues_by_user[user_id].remove(q)
                logger.info(f"SSE connection closed for {user_id}. Active connections: {len(event_queues_by_user[user_id])}")

    return Response(event_stream(), mimetype='text/event-stream')


# ============================================================================
# LOG FILES API
# ============================================================================

@app.route('/api/logs', methods=['GET'])
def list_logs():
    """List all log files"""
    try:
        _, auth_error = require_auth()
        if auth_error:
            return auth_error

        logs_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'logs')

        if not os.path.exists(logs_dir):
            return jsonify({'success': True, 'logs': []})

        # Get all .txt files starting with streams_prefetcher_logs_
        log_files = []
        for filename in os.listdir(logs_dir):
            if filename.startswith('streams_prefetcher_logs_') and filename.endswith('.txt'):
                filepath = os.path.join(logs_dir, filename)
                stat = os.stat(filepath)
                log_files.append({
                    'filename': filename,
                    'size': stat.st_size,
                    'modified': stat.st_mtime
                })

        # Sort by modified time (most recent first)
        log_files.sort(key=lambda x: x['modified'], reverse=True)

        return jsonify({'success': True, 'logs': log_files})

    except Exception as e:
        logger.error(f"Error listing log files: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/logs/<filename>', methods=['GET'])
def get_log_content(filename):
    """Get content of a specific log file"""
    try:
        _, auth_error = require_auth()
        if auth_error:
            return auth_error

        # Security: only allow files starting with streams_prefetcher_logs_
        if not filename.startswith('streams_prefetcher_logs_') or not filename.endswith('.txt'):
            return jsonify({'success': False, 'error': 'Invalid filename'}), 400

        logs_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'logs')
        filepath = os.path.join(logs_dir, filename)

        if not os.path.exists(filepath):
            return jsonify({'success': False, 'error': 'File not found'}), 404

        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        return jsonify({'success': True, 'content': content})

    except Exception as e:
        logger.error(f"Error reading log file {filename}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/logs/<filename>', methods=['DELETE'])
def delete_log(filename):
    """Delete a specific log file"""
    try:
        _, auth_error = require_auth()
        if auth_error:
            return auth_error

        # Security: only allow files starting with streams_prefetcher_logs_
        if not filename.startswith('streams_prefetcher_logs_') or not filename.endswith('.txt'):
            return jsonify({'success': False, 'error': 'Invalid filename'}), 400

        logs_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'logs')
        filepath = os.path.join(logs_dir, filename)

        if not os.path.exists(filepath):
            return jsonify({'success': False, 'error': 'File not found'}), 404

        os.remove(filepath)
        logger.info(f"Deleted log file: {filename}")

        return jsonify({'success': True, 'message': f'Deleted {filename}'})

    except Exception as e:
        logger.error(f"Error deleting log file {filename}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/logs', methods=['DELETE'])
def delete_all_logs():
    """Delete all log files"""
    try:
        _, auth_error = require_auth()
        if auth_error:
            return auth_error

        logs_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'logs')

        if not os.path.exists(logs_dir):
            return jsonify({'success': True, 'deleted': 0})

        deleted_count = 0
        for filename in os.listdir(logs_dir):
            if filename.startswith('streams_prefetcher_logs_') and filename.endswith('.txt'):
                filepath = os.path.join(logs_dir, filename)
                os.remove(filepath)
                deleted_count += 1

        logger.info(f"Deleted {deleted_count} log files")

        return jsonify({'success': True, 'deleted': deleted_count})

    except Exception as e:
        logger.error(f"Error deleting all log files: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# UTILITY API
# ============================================================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'success': True,
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors"""
    # For API routes, return JSON
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'error': 'Endpoint not found'}), 404

    # For other routes, serve index.html (SPA fallback)
    return send_from_directory(app.static_folder, 'index.html')


@app.errorhandler(500)
def internal_error(e):
    """Handle 500 errors"""
    return jsonify({'success': False, 'error': 'Internal server error'}), 500


# ============================================================================
# APPLICATION STARTUP
# ============================================================================

if __name__ == '__main__':
    # Ensure data directories exist
    os.makedirs('data/config', exist_ok=True)
    os.makedirs('data/db', exist_ok=True)
    os.makedirs('data/logs', exist_ok=True)
    os.makedirs('data/users', exist_ok=True)

    # Run the application
    port = int(os.environ.get('PORT', 5000))
    logger.info("=" * 60)
    logger.info("STREAMS PREFETCHER - WEB APPLICATION STARTING")
    logger.info("=" * 60)
    logger.info(f"Server port: {port}")
    logger.info(f"Log level: {os.getenv('LOG_LEVEL', 'INFO')}")
    logger.info(f"Data directory: {os.path.abspath('data')}")
    logger.info("Web interface will be available at configured hostname")
    logger.info("=" * 60)

    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)

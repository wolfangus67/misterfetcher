"""
User Manager
Handles account registration and password verification.
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, Optional

from werkzeug.security import generate_password_hash, check_password_hash


class UserManager:
    """Manage user accounts stored on disk."""

    def __init__(self, users_path: str = 'data/users/users.json'):
        self.users_path = Path(users_path)

    def _ensure_parent(self):
        self.users_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_users(self) -> Dict[str, Any]:
        if not self.users_path.exists():
            return {'users': {}}

        with open(self.users_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if 'users' not in data or not isinstance(data['users'], dict):
            data = {'users': {}}

        return data

    def _save_users(self, data: Dict[str, Any]):
        self._ensure_parent()
        with open(self.users_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

    def normalize_username(self, username: str) -> str:
        return username.strip().lower()

    def make_user_id(self, username: str) -> str:
        normalized = self.normalize_username(username)
        safe = re.sub(r'[^a-z0-9._-]+', '_', normalized).strip('._-')
        return safe or 'user'

    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        normalized = self.normalize_username(username)
        users = self._load_users()['users']
        return users.get(normalized)

    def register_user(self, username: str, password: str) -> Dict[str, Any]:
        normalized = self.normalize_username(username)
        if not normalized:
            raise ValueError('Username is required')
        if len(password or '') < 6:
            raise ValueError('Password must be at least 6 characters long')

        data = self._load_users()
        users = data['users']
        if normalized in users:
            raise ValueError('User already exists')

        users[normalized] = {
            'username': normalized,
            'user_id': self.make_user_id(normalized),
            'password_hash': generate_password_hash(password)
        }
        self._save_users(data)
        return users[normalized]

    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        user = self.get_user(username)
        if not user:
            return None

        if not check_password_hash(user['password_hash'], password):
            return None

        return user

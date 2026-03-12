\
import json
import os
from pathlib import Path
from typing import Dict, List

from .security import hash_password, verify_password


class UserDB:
    def __init__(self, users_file: Path):
        self.users_file = users_file
        self.users_file.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> Dict[str, Dict[str, str]]:
        if not self.users_file.exists():
            return {"users": {}}
        data = json.loads(self.users_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Invalid users data")
        users = data.setdefault("users", {})
        if not isinstance(users, dict):
            raise ValueError("Invalid users payload")
        return data

    def save(self, data: Dict[str, Dict[str, str]]) -> None:
        self.users_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.chmod(self.users_file, 0o600)

    def add_user(self, username: str, password: str) -> None:
        data = self.load()
        data["users"][username] = hash_password(password)
        self.save(data)

    def remove_user(self, username: str) -> None:
        data = self.load()
        if username not in data["users"]:
            raise KeyError(f"user not found: {username}")
        del data["users"][username]
        self.save(data)

    def change_password(self, username: str, password: str) -> None:
        data = self.load()
        if username not in data["users"]:
            raise KeyError(f"user not found: {username}")
        data["users"][username] = hash_password(password)
        self.save(data)

    def list_users(self) -> List[str]:
        return sorted(self.load()["users"].keys())

    def verify(self, username: str, password: str) -> bool:
        record = self.load()["users"].get(username)
        return bool(record) and verify_password(record, password)

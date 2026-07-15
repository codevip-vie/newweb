from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any


@dataclass
class StorageAccount:
    index: int
    service_account: str | None
    oauth_client_id: str | None
    oauth_client_secret: str | None
    oauth_refresh_token: str | None
    oauth_token_file: str | None
    oauth_token_uri: str
    system_folder_id: str | None
    posters_folder_id: str | None
    videos_folder_id: str | None


class StorageManager:
    def __init__(self, accounts: list[dict[str, Any]] | None = None) -> None:
        self._lock = threading.Lock()
        self._index = 0
        self._accounts: list[StorageAccount] = []
        if accounts is not None:
            self.initialize(accounts)

    def initialize(self, accounts: list[dict[str, Any]]) -> None:
        with self._lock:
            self._accounts = [StorageAccount(**account) for account in accounts]
            self._index = 0

    def _has_auth(self, account: StorageAccount) -> bool:
        return bool(
            account.service_account
            or (
                account.oauth_client_id
                and account.oauth_client_secret
                and (account.oauth_refresh_token or account.oauth_token_file)
            )
        )

    def _is_upload_account_configured(self, account: StorageAccount) -> bool:
        return self._has_auth(account) and bool(account.posters_folder_id and account.videos_folder_id)

    def _is_backup_account_configured(self, account: StorageAccount) -> bool:
        return self._has_auth(account) and bool(account.system_folder_id)

    def next_account(self) -> StorageAccount:
        with self._lock:
            if not self._accounts:
                raise ValueError("No storage accounts have been configured.")

            for _ in range(len(self._accounts)):
                account = self._accounts[self._index]
                self._index = (self._index + 1) % len(self._accounts)
                if self._is_upload_account_configured(account):
                    return account

            raise ValueError("No configured Google Drive storage accounts are available.")

    def get_account(self, index: int) -> StorageAccount:
        if not self._accounts:
            raise ValueError("No storage accounts have been configured.")
        if 0 <= index < len(self._accounts):
            return self._accounts[index]
        return self._accounts[0]


storage_manager = StorageManager()

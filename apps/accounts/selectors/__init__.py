"""
Selectors package for accounts app.
"""

from apps.accounts.selectors.auth import (
    get_account_by_identifier,
    get_active_account_by_identifier,
)

__all__ = [
    "get_account_by_identifier",
    "get_active_account_by_identifier",
]

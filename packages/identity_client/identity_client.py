"""
Lightweight package copy of the integratie identity_client for reuse or packaging.
This file mirrors `integratie/identity_client.py` and is intended for packaging only.
"""
from integratie.identity_client import (
    create_user,
    lookup_by_email,
    lookup_by_uuid,
    IdentityError,
    IdentityUnavailableError,
    IdentityEmailAlreadyExists,
)

__all__ = [
    "create_user",
    "lookup_by_email",
    "lookup_by_uuid",
    "IdentityError",
    "IdentityUnavailableError",
    "IdentityEmailAlreadyExists",
]

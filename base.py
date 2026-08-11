"""
Abstract storage backend interface.

Every backend (Discord, S3, local disk, ...) implements this same
contract so the pipeline never needs to know which one it's talking to.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class StoredRef:
    """
    Opaque reference a backend needs to fetch a chunk back later.
    For Discord this is (channel_id/webhook info, message_id).
    For S3 this would just be a key. Stored as JSON in the manifest DB.
    """
    backend: str
    data: dict


class StorageBackend(ABC):
    @abstractmethod
    def put(self, chunk_id: str, data: bytes) -> StoredRef:
        """Upload raw bytes, return a reference to retrieve them later."""
        ...

    @abstractmethod
    def get(self, ref: StoredRef) -> bytes:
        """Fetch raw bytes given a previously returned reference."""
        ...

    @abstractmethod
    def delete(self, ref: StoredRef) -> None:
        """Delete the stored object."""
        ...

    @abstractmethod
    def exists(self, ref: StoredRef) -> bool:
        """Check whether the object is still retrievable."""
        ...
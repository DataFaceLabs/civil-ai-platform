from functools import lru_cache

from civilai_platform.settings import get_settings
from civilai_platform.store.base import PlatformStore
from civilai_platform.store.dynamodb import DynamoDBStore
from civilai_platform.store.file import FileStore
from civilai_platform.store.memory import MemoryStore


@lru_cache
def get_store() -> PlatformStore:
    settings = get_settings()
    if settings.store_backend == "dynamodb":
        return DynamoDBStore()
    if settings.store_backend == "file":
        return FileStore(settings.file_store_path)
    return MemoryStore()

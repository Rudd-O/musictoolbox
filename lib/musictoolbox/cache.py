import collections
import fcntl
import io
import logging
import collections.abc
import os
import pickle
import typing
import xdg.BaseDirectory


_LOGGER = logging.getLogger(__name__)


class OnDiskCacheable(typing.Protocol):
    """
    The protocol for on-disk cacheable objects.

    Objects implementing this protocol must be pickleable.
    """

    def is_dirty(self) -> bool:
        """
        Is the cache dirty?

        Implementors must keep track of such state and return accordingly.
        """
        pass

    def mark_clean(self) -> None:
        """
        Mark the cache clean.

        Implementors must keep track of such state.
        """
        pass


C = typing.TypeVar("C")


class FileMetadataCache(OnDiskCacheable, typing.Generic[C]):
    def __init__(self, cache_item_factory: collections.abc.Callable[[str], C]) -> None:
        """
        Initializes a cache.

        The cache_item_factory takes a path (in string form) and must return a cache
        item, or None if the factory cannot produce an item.

        Cache keys are absolute paths internally.  This is an implementation detail,
        and it is subject to change in the future.  For convenience, the cache store
        is exposed as self._store, but your code will break if you use this directly,
        so limit yourself to the methods exposed by this class.
        """
        self.__factory = cache_item_factory
        self._store: dict[str, tuple[float, C]] = {}
        self.__dirty = False

    def update_metadata_for(self, allfiles: list[str]) -> None:
        """
        Instruct the cache to update itself for the passed files.

        is_dirty() will return True after this, if any of the files passed
        had its corresponding cache entry updated.
        """
        dirty = False
        for ff in allfiles:
            ff = os.path.abspath(ff)
            try:
                modtime = os.stat(ff).st_mtime
            except Exception as exc:
                _LOGGER.error("Error examining %s: %s", ff, exc)
                continue
            if ff in self._store and self._store[ff][0] >= modtime:
                if _LOGGER.level <= logging.DEBUG:
                    _LOGGER.debug("No need to update cache for file %s", ff)
                continue
            if _LOGGER.level <= logging.DEBUG:
                _LOGGER.debug("Updated cache for file %s at mod time %s", ff, modtime)
            metadata = self.__factory(ff)
            self._store[ff] = (modtime, metadata)
            dirty = True
        self.__dirty = dirty

    def __getitem__(self, key: str) -> C:
        key = os.path.abspath(key)
        return self._store[key][1]

    def has_key(self, key: str) -> bool:
        """Returns whether the cache contains an entry for the key."""
        key = os.path.abspath(key)
        return key in self._store

    def get(self, key: str) -> C | None:
        """Return a cache entry."""
        key = os.path.abspath(key)
        m = self._store.get(key)
        if m is None:
            return None
        return m[1]

    def mark_clean(self) -> None:
        """Mark the cache as clean again."""
        self.__dirty = False

    def is_dirty(self) -> bool:
        """Return whether the cache is dirty."""
        return self.__dirty


D = typing.TypeVar("D", bound="OnDiskCacheable")


class OnDiskMetadataCache(typing.Generic[D]):
    """
    Cache utility with locking.

    The object manufactured by the cache_factory is returned when called
    as a context manager, but only after the cache file has safely locked
    on disk.

    The the cache is pickled to the file, and the file is unlocked and
    closed, when the scope of the context manager ends.

    Failing to lead the cache is never an error (it defaults to the
    empty cache object created by the factory), but failing to save the
    cache will raise the appropriate exception.
    """

    def __init__(
        self,
        cache_name: str,
        cache_version: int,
        cache_factory: collections.abc.Callable[[], D],
    ):
        """
        Context manager that initializes an on-disk cache.

        Caches are loaded from $XDG_DATA_DIR/.cache/musictoolbox and named
        as files therein..

        The cache_factory will be called to produce an empty cache in case
        the cache cannot be loaded from disk.
        """
        self.__cache_version = cache_version
        self.__cache_factory = cache_factory
        self.__f: io.BufferedRandom | None = None
        self.__metadata: D = None  # type: ignore
        p = xdg.BaseDirectory.save_cache_path("musictoolbox")
        self.__path = os.path.join(p, cache_name.replace(os.path.sep, "_"))

    def __enter__(self) -> D:
        f: io.BufferedRandom

        metadata = self.__cache_factory()
        fsize = 0
        try:
            if _LOGGER.level <= logging.DEBUG:
                _LOGGER.debug("Loading cache from %s", self.__path)
            f = open(self.__path, "a+b")
            fcntl.flock(f, fcntl.LOCK_EX)
            fsize = os.stat(self.__path).st_size
            f.seek(0, 0)
        except Exception as exc:
            if not isinstance(exc, FileNotFoundError):
                _LOGGER.error("Error opening cache from %s: %s", self.__path, exc)

        if f and fsize:
            try:
                version, loaded_metadata = typing.cast(tuple[int, D], pickle.load(f))
                if version == self.__cache_version:
                    metadata = loaded_metadata
                else:
                    _LOGGER.debug(
                        "Expected cache version was %s, loaded cache version was %s,"
                        " ignoring cache",
                        self.__cache_version,
                        version,
                    )
            except Exception as exc:
                _LOGGER.error("Error opening cache from %s: %s", self.__path, exc)

        self.__f = f
        self.__metadata = metadata
        return metadata

    def __exit__(self, *unused_args: typing.Any, **unused_kw: typing.Any) -> None:
        if self.__f and self.__metadata.is_dirty():
            try:
                self.__metadata.mark_clean()
                if _LOGGER.level <= logging.DEBUG:
                    _LOGGER.debug("Saving cache to %s", self.__path)
                self.__f.seek(0, 0)
                self.__f.truncate()
                pickle.dump((self.__cache_version, self.__metadata), self.__f)
                self.__f.flush()
            finally:
                self.__f.close()

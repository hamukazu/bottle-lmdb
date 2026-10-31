import inspect
import typing
import lmdb


class LMDBPlugin:
    name = "lmdb"
    api = 2

    def __init__(self, db_path: str, **kwargs) -> None:
        """Initialize the plugin.

        Args:
            db_path: Path to the LMDB database directory.
            **kwargs: Extra options forwarded to ``lmdb.Environment``.
                The ``keyword`` option sets the route keyword argument
                name used to inject the environment (default: ``"db"``).
        """
        self._db_path = db_path
        self._kwargs = kwargs.copy()
        self._env: None | lmdb.Environment = None
        if "keyword" in kwargs:
            keyword = self._kwargs["keyword"]
            del self._kwargs["keyword"]
        else:
            keyword = "db"
        self._keyword: str = keyword

    @property
    def env(self) -> lmdb.Environment:
        """Return the LMDB environment, opening it lazily on first access.

        Returns:
            lmdb.Environment: The environment for ``db_path``.
        """
        # When a work process access this first time db is initialized
        if self._env is None:
            self._env = lmdb.Environment(self._db_path, **self._kwargs)
        return self._env

    def apply(self, callback: typing.Callable, route) -> typing.Callable:
        """Wrap a route callback to inject the LMDB environment.

        Args:
            callback: The original route callback.
            route: The Bottle route object (unused).

        Returns:
            A wrapper that passes the environment to the callback
            via the configured keyword argument.
        """
        keyword = route.config.get("lmdb.keyword", self._keyword)
        
        try:
            args = inspect.signature(route.callback).parameters
        except (TypeError, ValueError):
            return callback
        if keyword not in args:
            return callback

        def wrapper(*a, **ka):
            ka[keyword] = self.env
            return callback(*a, **ka)

        return wrapper

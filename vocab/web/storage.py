"""Reuse database operations in a single transaction for browser mutations."""
from contextlib import contextmanager
from threading import local

from vocab.db import Database


class _Connection:
    def __init__(self, connection):
        self.connection = connection

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def commit(self):
        # The outer transaction owns the commit.
        pass


class WebDatabase(Database):
    def __init__(self, path):
        self._local = local()
        super().__init__(path)

    @contextmanager
    def get_connection(self):
        connection = getattr(self._local, "connection", None)
        if connection is not None:
            yield _Connection(connection)
        else:
            with super().get_connection() as connection:
                yield connection

    @contextmanager
    def transaction(self):
        with super().get_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._local.connection = connection
            try:
                yield
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            finally:
                self._local.connection = None

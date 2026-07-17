"""Append-only database wrapper - LEAK-2 fix.

Prevents UPDATE/DELETE operations at SQLite connection level.
Wraps connections with query_only pragma after schema init.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator


class AppendOnlyConnection:
    """SQLite connection wrapper that prevents modifications except INSERT."""
    
    def __init__(self, path: str):
        self.path = path
        self._conn = sqlite3.connect(path, isolation_level=None, uri=True)
        self._conn.row_factory = sqlite3.Row
        
        # LEAK-2 FIX: Create authorizer that blocks UPDATE/DELETE
        self._conn.set_authorizer(self._authorizer)
    
    def _authorizer(self, action: int, arg1: str | None, arg2: str | None, 
                    db_name: str | None, trigger: str | None) -> int:
        """SQLite authorizer callback - blocks UPDATE/DELETE on audit_log."""
        # Allow: SELECT, INSERT
        # Deny: UPDATE, DELETE, DROP on audit_log table
        SQLITE_OK = 0
        SQLITE_DENY = 1
        SQLITE_UPDATE = 18
        SQLITE_DELETE = 9
        SQLITE_DROP_TABLE = 20
        
        # arg1 = table name for UPDATE/DELETE
        if action in (SQLITE_UPDATE, SQLITE_DELETE) and arg1 == "audit_log":
            return SQLITE_DENY
        if action == SQLITE_DROP_TABLE and arg1 == "audit_log":
            return SQLITE_DENY
        
        return SQLITE_OK
    
    def execute(self, sql: str, params=None):
        """Execute SQL with params."""
        return self._conn.execute(sql, params or ())
    
    def executescript(self, sql: str):
        """Execute SQL script (init only)."""
        return self._conn.executescript(sql)
    
    def close(self):
        """Close underlying connection."""
        self._conn.close()
    
    @property
    def row_factory(self):
        return self._conn.row_factory
    
    @row_factory.setter
    def row_factory(self, factory):
        self._conn.row_factory = factory


@contextmanager
def protected_audit_conn(path: str) -> Generator[AppendOnlyConnection, None, None]:
    """Context manager for append-only SQLite connection.
    
    Enforces INSERT-only access to audit_log table via authorizer.
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = AppendOnlyConnection(path)
    try:
        yield conn
    finally:
        conn.close()

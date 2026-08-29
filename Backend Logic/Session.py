"""
Session.py  (v2 — thread-safe)
==============================
Problem with v1:
    _user was a class-level dict. In any multi-threaded environment (a web
    server, a concurrent CLI, tests running in parallel) every thread shared
    the same _user. User A's login would be visible from User B's thread.

Fix:
    threading.local() creates a per-thread namespace. Each OS thread that
    calls Session.login() gets its own isolated _user dict that is invisible
    to every other thread.

For a single-process CLI this makes no practical difference, but it means
the same Session class can be dropped into a FastAPI/Django application
later without modification.
"""

import threading


class Session:
    _local = threading.local()   # one namespace per OS thread

    # ── Auth ──────────────────────────────────────────────────────────────

    @classmethod
    def login(cls, user_id: int, username: str, role: str, full_name: str):
        cls._local.user = {
            "user_id":   user_id,
            "username":  username,
            "role":      role,
            "full_name": full_name,
        }

    @classmethod
    def logout(cls):
        cls._local.user = None

    # ── Accessors ─────────────────────────────────────────────────────────

    @classmethod
    def current(cls) -> dict | None:
        return getattr(cls._local, "user", None)

    @classmethod
    def user_id(cls) -> int | None:
        u = cls.current()
        return u["user_id"] if u else None

    @classmethod
    def username(cls) -> str | None:
        u = cls.current()
        return u["username"] if u else None

    @classmethod
    def role(cls) -> str | None:
        u = cls.current()
        return u["role"] if u else None

    # ── Guards ────────────────────────────────────────────────────────────

    @classmethod
    def require(cls) -> dict:
        """Return current user or raise PermissionError."""
        u = cls.current()
        if not u:
            raise PermissionError("No active session — please log in first.")
        return u

    @classmethod
    def require_role(cls, *allowed: str) -> dict:
        """Return current user only if their role is in allowed."""
        u = cls.require()
        if u["role"] not in allowed:
            raise PermissionError(
                f"Access denied. Your role '{u['role']}' cannot perform this "
                f"action. Required: {list(allowed)}"
            )
        return u
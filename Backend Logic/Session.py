"""
Session.py
==========
Lightweight in-process session manager.

Holds the currently authenticated user for the lifetime of the process.
Every write operation in every module calls Session.require() or
Session.require_role() so that:
  - Unauthenticated actions are blocked.
  - The acting user_id is captured for audit logs and created_by fields.

Usage:
    from Session import Session

    Session.login(user_id=1, username='admin', role='admin', full_name='Ali Hassan')
    user = Session.require()          # raises PermissionError if not logged in
    uid  = Session.user_id()          # returns int or None
    Session.require_role('admin', 'manager')   # role guard
    Session.logout()
"""


class Session:
    _user: dict | None = None

    # ── Auth ──────────────────────────────────────────────────────────────

    @classmethod
    def login(cls, user_id: int, username: str, role: str, full_name: str):
        cls._user = {
            "user_id":   user_id,
            "username":  username,
            "role":      role,
            "full_name": full_name,
        }

    @classmethod
    def logout(cls):
        cls._user = None

    # ── Accessors ─────────────────────────────────────────────────────────

    @classmethod
    def current(cls) -> dict | None:
        return cls._user

    @classmethod
    def user_id(cls) -> int | None:
        return cls._user["user_id"] if cls._user else None

    @classmethod
    def username(cls) -> str | None:
        return cls._user["username"] if cls._user else None

    # ── Guards (raise PermissionError on failure) ─────────────────────────

    @classmethod
    def require(cls) -> dict:
        """Return current user or raise PermissionError."""
        if not cls._user:
            raise PermissionError("No active session — please log in first.")
        return cls._user

    @classmethod
    def require_role(cls, *allowed: str) -> dict:
        """Return current user only if their role is in allowed, else raise."""
        user = cls.require()
        if user["role"] not in allowed:
            raise PermissionError(
                f"Access denied. Your role '{user['role']}' cannot perform this action. "
                f"Required: {list(allowed)}"
            )
        return user

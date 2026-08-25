"""
edit_history.py

Simple in-memory, session-scoped undo/redo. Rather than trying to
reverse individual low-level PDF operations (which is error-prone),
this keeps a stack of whole-document byte snapshots taken right
before each edit. This is easy to reason about and correct, at the
cost of some memory - acceptable for a personal, local tool editing
one document at a time.

No database, no disk persistence: everything lives in the process
memory and disappears when the app is closed, as required.
"""
from __future__ import annotations

MAX_HISTORY = 50


class EditHistory:
    def __init__(self, initial_bytes: bytes):
        self.current: bytes = initial_bytes
        self._undo_stack: list[bytes] = []
        self._redo_stack: list[bytes] = []

    def push_and_commit(self, new_bytes: bytes) -> None:
        """Record the state before an edit, then commit the new state."""
        self._undo_stack.append(self.current)
        if len(self._undo_stack) > MAX_HISTORY:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self.current = new_bytes

    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    def undo(self) -> bytes:
        if not self.can_undo():
            return self.current
        self._redo_stack.append(self.current)
        self.current = self._undo_stack.pop()
        return self.current

    def redo(self) -> bytes:
        if not self.can_redo():
            return self.current
        self._undo_stack.append(self.current)
        self.current = self._redo_stack.pop()
        return self.current

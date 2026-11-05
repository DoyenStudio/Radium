# coding=utf-8
"""Synchronous, explicit transactions. No engine imports or persistence on abort."""
from collections import OrderedDict, deque
from threading import current_thread
import math
from .values import integer_types, string_types


def immutable_state(value):
    if isinstance(value, tuple):
        for part in value:
            immutable_state(part)
    elif value is not None and not isinstance(value, integer_types + string_types + (float, bool)):
        raise TypeError("Cell state must contain only immutable scalars and tuples")
    elif isinstance(value, float) and math.isnan(value):
        raise ValueError("Cell state must not contain NaN")
    return value


class TransactionError(RuntimeError):
    pass


class TransactionManager(object):
    def __init__(self, report=None):
        self.current = None
        self.epoch = 0
        self.thread = current_thread().ident
        self.report = report or self._report
        self.dirty = OrderedDict()
        self.notifications = deque()
        self.dispatching = False
        self.persisting = False
        self.applying = False

    @staticmethod
    def _report(message):
        print("[radium] " + message)

    def assert_thread(self):
        if current_thread().ident != self.thread:
            raise TransactionError("radium is server-thread only")

    def assert_idle(self):
        self.assert_thread()
        if self.persisting:
            raise TransactionError("Persistence callbacks must not mutate resources")
        if self.current is not None:
            raise TransactionError("Use explicit handlers inside an open transaction")

    def open(self, parent=None):
        self.assert_thread()
        if self.persisting or self.applying:
            raise TransactionError("Storage callbacks must not open transactions")
        if self.current is not parent:
            raise TransactionError("Pass the current transaction as parent")
        return Transaction(self, parent)

    def tick(self):
        self.assert_thread()
        self.epoch += 1
        # A transaction must not survive a server tick, even if never committed.
        if self.current is not None:
            self.report("Aborting a transaction that crossed a tick")
            while self.current is not None:
                self.current.abort()
        self.flush()

    def flush(self):
        self.assert_idle()
        self.persisting = True
        try:
            for key, callback in list(self.dirty.items()):
                try:
                    callback()
                except Exception as exc:
                    self.report("Persistence remains dirty: %s" % exc)
                else:
                    self.dirty.pop(key, None)
        finally:
            self.persisting = False
        if self.dispatching:
            return
        self.dispatching = True
        try:
            while self.notifications:
                callback, args = self.notifications.popleft()
                try:
                    callback(*args)
                except Exception as exc:
                    # State is already committed. Never replay the transfer.
                    self.report("Post-commit notification failed: %s" % exc)
        finally:
            self.dispatching = False


class Cell(object):
    """Immutable scalar/tuple state; apply must only update memory, without events."""
    def __init__(self, manager, state, read=None, apply=None, persist=None,
                 changed=None, owner=None, valid=None):
        for callback in (read, apply, persist, changed, valid):
            if callback is not None and not callable(callback):
                raise TypeError("Cell callbacks must be callable")
        if (read is None) != (apply is None):
            raise ValueError("External cells require both read and apply")
        self.manager = manager
        self.state = immutable_state(state)
        self.read = read
        self.apply = apply
        self.persist = persist
        self.changed = changed
        self.owner = self if owner is None else owner
        hash(self.owner)
        self.valid = valid or (lambda: True)
        self.version = 0

    def get(self):
        self.manager.assert_thread()
        return self.state if self.read is None else immutable_state(self.read())

    def _apply(self, state):
        if self.apply is not None:
            self.apply(state)
        else:
            self.state = state

    def set(self, state):
        """Legacy immediate write: persist, but do not synthesize business events."""
        self.manager.assert_idle()
        immutable_state(state)
        if not self.valid():
            raise TransactionError("Storage is no longer available")
        if state == self.get():
            return
        self._apply(state)
        self.version += 1
        if self.persist is not None:
            self.manager.dirty[self.owner] = self.persist
            self.manager.flush()


class Transaction(object):
    def __init__(self, manager, parent):
        self.manager = manager
        self.parent = parent
        self.epoch = manager.epoch
        self.entries = OrderedDict()
        self.guards = []
        self.effects = OrderedDict()
        self.closed = False
        manager.current = self

    def __enter__(self):
        self.check()
        return self

    def __exit__(self, exc_type, exc, traceback):
        if not self.closed:
            self.abort()
        return False

    def check(self):
        self.manager.assert_thread()
        if self.closed or self.manager.current is not self:
            raise TransactionError("Transaction is closed or not current")
        if self.epoch != self.manager.epoch:
            raise TransactionError("Transaction crossed a tick")

    def read(self, cell):
        self.check()
        if cell.manager is not self.manager:
            raise TransactionError("Storage belongs to a different manager")
        if cell not in self.entries:
            ancestor = self.parent
            entry = None
            while ancestor is not None:
                if cell in ancestor.entries:
                    entry = ancestor.entries[cell]
                    break
                ancestor = ancestor.parent
            if entry is None:
                state = cell.get()
                self.entries[cell] = [cell.version, state, state]
            else:
                self.entries[cell] = [entry[0], entry[1], entry[2]]
        return self.entries[cell][2]

    def write(self, cell, state):
        immutable_state(state)
        self.read(cell)
        self.entries[cell][2] = state

    def guard(self, predicate):
        self.check()
        if not predicate():
            raise TransactionError("Resource endpoint is no longer available")
        self.guards.append(predicate)

    def record(self, key, callback, amount):
        self.check()
        if callback is None or amount == 0:
            return
        previous = self.effects.get(key)
        self.effects[key] = (callback, amount + (previous[1] if previous else 0))

    def abort(self):
        self.manager.assert_thread()
        if self.manager.current is not self:
            raise TransactionError("Close child transactions first")
        self.closed = True
        self.manager.current = self.parent

    def commit(self):
        self.check()
        if not all(guard() for guard in self.guards):
            raise TransactionError("Resource endpoint changed before commit")
        if self.parent is not None:
            for cell, entry in self.entries.items():
                self.parent.entries[cell] = entry
            self.parent.guards.extend(self.guards)
            for key, (callback, amount) in self.effects.items():
                previous = self.parent.effects.get(key)
                self.parent.effects[key] = (
                    callback, amount + (previous[1] if previous else 0))
            self.abort()
            return
        for cell, (version, original, final) in self.entries.items():
            if not cell.valid() or cell.version != version or cell.get() != original:
                raise TransactionError("Resource storage changed before commit")
        changed = [(c, e[1], e[2]) for c, e in self.entries.items() if e[1] != e[2]]
        applied = []
        self.manager.applying = True
        try:
            for cell, original, final in changed:
                applied.append((cell, original))
                cell._apply(final)
        except Exception:
            for cell, original in reversed(applied):
                cell._apply(original)
            raise
        finally:
            self.manager.applying = False
        groups = OrderedDict()
        for cell, original, final in changed:
            cell.version += 1
            if cell.persist is not None:
                self.manager.dirty[cell.owner] = cell.persist
            if cell.changed is not None:
                if cell.owner not in groups:
                    groups[cell.owner] = (cell.changed, [])
                groups[cell.owner][1].append((cell, original, final))
        self.abort()
        for callback, changes in groups.values():
            self.manager.notifications.append((callback, (changes,)))
        for callback, amount in self.effects.values():
            self.manager.notifications.append((callback, (amount,)))
        self.manager.flush()

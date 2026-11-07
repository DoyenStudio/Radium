# coding=utf-8
from ..core.transaction import Cell, TransactionError
from .backend import UnsupportedContainer


class NativeOwner(object):
    """One compensated participant per physical inventory, shared by every face."""
    def __init__(self, manager, backend, size):
        self.manager, self.backend = manager, backend
        self.alive = True
        self.memory = {}
        self.cells = {}
        for slot in range(size):
            initial = (None, 0)
            self.memory[slot] = initial
            self.cells[slot] = Cell(manager, initial,
                read=lambda s=slot: self.backend.read_slot(s),
                apply=lambda state, s=slot: self.memory.__setitem__(s, state),
                owner=self, valid=self.valid, participant=self)
        self.slot_for_cell = dict((cell, slot) for slot, cell in self.cells.items())

    def valid(self):
        if not self.alive or self.manager.is_quarantined(participant=self):
            return False
        try:
            self.backend.check()
        except UnsupportedContainer:
            return False
        return True

    def prepare(self, changes):
        if not self.valid():
            raise TransactionError("Native container was invalidated")
        before = self.backend.capture()
        final = list(before["slots"])
        touched = []
        for cell, original, state in changes:
            slot = self.slot_for_cell[cell]
            if before["slots"][slot] != original:
                raise TransactionError("Native inventory changed before commit")
            final[slot] = state
            touched.append(slot)
        return {"before": before, "final": tuple(final), "touched": tuple(sorted(touched)),
                "attempted": False, "observed": before}

    def write(self, token):
        self.backend.write_slots(token["before"], token["final"], token["touched"], token)

    def restore(self, token):
        self.backend.restore(token)

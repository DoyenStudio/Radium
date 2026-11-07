# coding=utf-8
"""Optional item/fluid host example; never loaded automatically by radium."""
import mod.server.extraServerApi as serverApi


def get_transfer_api():
    api = serverApi.GetComponent(serverApi.GetLevelId(), "radium", "transfer")
    if api is None or api.API_VERSION[0] != 1 or api.API_VERSION < (1, 2, 0):
        return None
    return api


class ExampleItemMachine(object):
    """The host owns its loaded pool, stack-limit lookup and BlockEntityData."""
    def __init__(self, api, bdata, stack_limit):
        self.api = api
        self.bdata = bdata
        self.alive = True
        self.needs_client_sync = False
        saved = bdata["example:resources"] or {}
        # stack_limit(resource) comes from the host's verified item catalog;
        # tools, pearls and ordinary items need their actual individual limits.
        self.items = api.create_item_storage(
            {0: 64, 4: 64}, stack_limit, saved=saved.get("items"),
            persist=self.save, changed=self.resources_changed, owner=self,
            valid=self.is_alive)
        self.fluid = api.create_fluid_storage(
            {0: 4000}, saved=saved.get("fluid"),
            persist=self.save, changed=self.resources_changed, owner=self)
        self.fluid.valid = self.is_alive
        for cell in self.fluid.cells.values():
            cell.valid = self.is_alive
        self.item_input = api.item_view(self.items, (0,), output_slots=())
        self.item_output = api.item_view(self.items, (4,), input_slots=())
        self.fluid_input = api.fluid_view(self.fluid, output_slots=())

    def is_alive(self):
        return self.alive

    def save(self):
        self.bdata["example:resources"] = {
            "items": self.api.save_item(self.items),
            "fluid": self.api.save_fluid(self.fluid),
        }

    def resources_changed(self, changes):
        self.needs_client_sync = True

    def try_process(self, ingredient, product):
        # Identities are immutable resources; counts belong to each operation.
        # No persistent writes or UI notifications occur until all steps succeed.
        with self.api.open_transaction() as tx:
            if self.items.extract(ingredient, 1, tx, slot=0) != 1:
                return False
            if self.fluid.extract("minecraft:water", 250, tx) != 250:
                return False
            if self.items.insert(product, 2, tx, slot=4) != 2:
                return False
            tx.commit()
        return True

    def close(self):
        self.api.flush()
        if self in self.api.manager.dirty:
            # Keep this owner alive for persistence retries before retiring it.
            raise RuntimeError("Item machine still has unsaved resources")
        self.alive = False
        self.api.invalidate()


def register_machine_providers(api, loaded_machines):
    def item_provider(dimension, pos, face):
        machine = loaded_machines.get((dimension, pos))
        if machine is None or not machine.alive:
            return None
        if face == 0:
            return machine.item_input
        if face == 1:
            return machine.item_output
        return None

    def fluid_provider(dimension, pos, face):
        machine = loaded_machines.get((dimension, pos))
        if machine is None or not machine.alive:
            return None
        return machine.fluid_input if face == 2 else None

    api.register_provider(api.ITEM, "example:item_machine", item_provider)
    api.register_provider(api.FLUID, "example:item_machine", fluid_provider)
    return item_provider, fluid_provider


def push_items_up(api, dimension, source_pos, resource, budget):
    x, y, z = source_pos
    source = api.query(api.ITEM, dimension, source_pos, face=1)
    target = api.query(api.ITEM, dimension, (x, y + 1, z), face=0)
    if source is None or target is None:
        return 0
    try:
        with api.open_transaction() as tx:
            moved = api.move_item(source, target, resource, budget, tx)
            tx.commit()
            return moved
    except api.TransactionError:
        # The host retries a fresh query on its next scheduled transport round.
        return 0

# coding=utf-8
"""Copy into the consuming addon's own script package. Never auto-loaded by radium."""
import mod.server.extraServerApi as serverApi


def get_transfer_api():
    # Call after all addon scripts have initialized, or lazily on the first use.
    api = serverApi.GetComponent(serverApi.GetLevelId(), "radium", "transfer")
    if api is None or api.API_VERSION[0] != 1:
        return None
    return api


class ExampleMachine(object):
    """No SkyBlueTech base class. Host supplies its existing BlockEntityData object."""
    def __init__(self, api, bdata):
        self.api = api
        self.bdata = bdata
        self.alive = True
        saved = bdata["example:resources"] or {}
        self.energy = api.create_energy_storage(
            100000, saved=saved.get("energy"),
            persist=self.save, changed=self.resources_changed, owner=self)
        self.fluid = api.create_fluid_storage(
            {0: 4000, 3: 4000}, saved=saved.get("fluid"),
            persist=self.save, changed=self.resources_changed, owner=self)
        self.energy.valid = self.is_alive
        self.fluid.valid = self.is_alive
        for cell in self.energy.cells:
            cell.valid = self.is_alive
        for cell in self.fluid.cells.values():
            cell.valid = self.is_alive
        self.energy_input = api.energy_view(self.energy, can_extract=False)
        self.energy_output = api.energy_view(self.energy, can_insert=False)
        self.fluid_input = api.fluid_view(self.fluid, (0,), output_slots=())
        self.fluid_output = api.fluid_view(self.fluid, (3,), input_slots=())
        self.needs_client_sync = False

    def is_alive(self):
        return self.alive

    def save(self):
        # Detached, string-keyed native dicts; one assignment for both resources.
        self.bdata["example:resources"] = {
            "energy": self.api.save_energy(self.energy),
            "fluid": self.api.save_fluid(self.fluid),
        }

    def resources_changed(self, changes):
        # Called once after every participating cell contains its final value.
        # Host's normal tick can coalesce UI/network packets using this flag.
        self.needs_client_sync = True

    def try_process(self):
        # Example recipe: 100 FE + 250 mB water -> 250 mB product.
        with self.api.open_transaction() as tx:
            if self.energy.extract(100, tx) != 100:
                return False
            if self.fluid.extract("minecraft:water", 250, tx, slot=0) != 250:
                return False
            if self.fluid.insert("example:product", 250, tx, slot=3) != 250:
                return False
            tx.commit()
        return True

    def close(self):
        self.api.flush()
        self.alive = False
        self.api.invalidate()


def register_machine_providers(api, loaded_machines):
    """Register once. Host updates the pool on its verified load/unload lifecycle."""
    def energy_provider(dimension, pos, face):
        machine = loaded_machines.get((dimension, pos))
        if machine is None or not machine.alive:
            return None
        if face is None:
            return machine.energy
        if face == 0:
            return machine.energy_input
        if face == 1:
            return machine.energy_output
        return None

    def fluid_provider(dimension, pos, face):
        machine = loaded_machines.get((dimension, pos))
        if machine is None or not machine.alive:
            return None
        if face is None:
            return machine.fluid
        if face == 2:
            return machine.fluid_input
        if face == 3:
            return machine.fluid_output
        return None

    api.register_provider(api.ENERGY, "example:machine", energy_provider)
    api.register_provider(api.FLUID, "example:machine", fluid_provider)
    return energy_provider, fluid_provider


def transfer_pair(api, dimension, source_pos, target_pos):
    # Caller owns adjacency/topology and converts direction to the target's face.
    source = api.query(api.ENERGY, dimension, source_pos, face=1)
    target = api.query(api.ENERGY, dimension, target_pos, face=0)
    if source is None or target is None:
        return 0
    try:
        with api.open_transaction() as tx:
            moved = api.move_energy(source, target, 200, tx)
            tx.commit()
            return moved
    except api.TransactionError:
        # A controller/port changed; query fresh endpoints on the next scheduling pass.
        return 0

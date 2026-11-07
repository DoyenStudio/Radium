# coding=utf-8
"""Fake-engine native integration tests; execute only in the game's interpreter."""
from copy import deepcopy
import traceback
from ..core.service import TransferService
from ..core.transaction import TransactionError, RecoveryError
from ..core.item_resource import item_resource
from ..vanilla.registry import VanillaRegistry
from ..vanilla.backend import UnsupportedContainer
from ..vanilla import item_codec


def atom(kind, value):
    return {"__type__": kind, "__value__": value}


def expect(error, callback):
    try:
        callback()
    except error as exc:
        return exc
    raise AssertionError("Expected %r" % (error,))


class FakeWorld(object):
    """Physical half inventories, with independently addressable slot/API faults."""
    def __init__(self):
        self.blocks, self.entities, self.states = {}, {}, {}
        self.sizes, self.pairs = {}, {}
        self.unloaded = set()
        self.item_reads, self.slot_writes, self.nbt_writes, self.state_writes = [], [], [], []
        self.slot_modes, self.nbt_modes, self.state_modes = [], [], []
        self.raw_extras = {}
        self.block_states = {"minecraft:stone": {}, "minecraft:dirt": {},
                             "minecraft:iron_ore": {}}

    def CreateBlockInfo(self, level_id):
        return self

    CreateItem = CreateBlockInfo
    CreateBlockState = CreateBlockInfo
    CreateChunkSource = CreateBlockInfo

    def add(self, name, pos=(0, 4, 0), size=27, dimension=0):
        key = (dimension, pos)
        self.blocks[key] = {"name": name, "aux": 0}
        self.entities[key] = {"id": atom(8, "Chest"), "Items": []}
        self.sizes[key] = size
        return pos

    def add_cauldron(self, level=0, liquid="water", pos=(0, 4, 0)):
        self.add("minecraft:cauldron", pos, 1)
        self.entities[(0, pos)] = {"id": atom(8, "Cauldron"), "Items": [],
                                  "PotionId": atom(2, -1), "PotionType": atom(2, -1)}
        self.states[(0, pos)] = {"fill_level": level, "cauldron_liquid": liquid,
                                "unrelated_state": 5}
        return pos

    def pair(self, first, second, dimension=0):
        self.pairs[(dimension, first)] = second
        self.pairs[(dimension, second)] = first

    def unpair(self, first, second, dimension=0):
        self.pairs.pop((dimension, first), None)
        self.pairs.pop((dimension, second), None)

    def seed(self, pos, slot, resource, count, dimension=0):
        key = (dimension, pos)
        entries = [entry for entry in self.entities[key].get("Items", [])
                   if entry["Slot"]["__value__"] != slot]
        if count:
            entry = item_codec.encode_entry(resource, count, slot,
                                            basic_info=self.GetItemBasicInfo)
            self._materialize_palette(entry)
            entries.append(entry)
        self.entities[key]["Items"] = sorted(entries, key=lambda entry: entry["Slot"]["__value__"])

    def CheckChunkState(self, dimension, pos):
        key = (dimension, pos)
        return key in self.blocks and key not in self.unloaded

    def GetBlockNew(self, pos, dimension):
        return deepcopy(self.blocks.get((dimension, pos)))

    def GetChestPairedPosition(self, pos, dimension):
        return self.pairs.get((dimension, pos))

    def GetContainerSize(self, pos, dimension):
        key = (dimension, pos)
        other = self.pairs.get(key)
        return self.sizes.get(key, -1) + (self.sizes[(dimension, other)] if other else 0)

    def GetBlockEntityData(self, dimension, pos):
        return deepcopy(self.entities.get((dimension, pos)))

    def SetBlockEntityData(self, dimension, pos, data):
        self.nbt_writes.append((dimension, pos, deepcopy(data)))
        mode = self.nbt_modes.pop(0) if self.nbt_modes else "ok"
        if mode == "false_before":
            return False
        self.entities[(dimension, pos)] = deepcopy(data)
        for entry in self.entities[(dimension, pos)].get("Items", []):
            self._materialize_palette(entry)
        return mode != "false_after"

    def _materialize_palette(self, entry):
        name = entry["Name"]["__value__"]
        if name in self.block_states and "Block" not in entry:
            entry["Block"] = {"name": atom(8, name), "val": deepcopy(entry["Damage"]),
                              "version": atom(3, 18168865), "states": {}}

    def _physical(self, pos, slot, dimension):
        other = self.pairs.get((dimension, pos))
        if other is None:
            return pos, slot
        first, second = sorted((pos, other))
        return (first, slot) if slot < 27 else (second, slot - 27)

    def GetContainerItem(self, pos, slot, dimension, get_user_data=False):
        self.item_reads.append((pos, slot, dimension, get_user_data))
        physical, local = self._physical(pos, slot, dimension)
        for entry in self.entities[(dimension, physical)].get("Items", []):
            if entry["Slot"]["__value__"] == local:
                resource, count, ignored = item_codec.decode_entry(entry, self.GetItemBasicInfo)
                result = item_codec.api_stack(resource, count)
                result.update(deepcopy(self.raw_extras))
                return result
        return None

    def SpawnItemToContainer(self, stack, slot, pos, dimension):
        self.slot_writes.append((deepcopy(stack), slot, pos, dimension))
        mode = self.slot_modes.pop(0) if self.slot_modes else "ok"
        if mode == "false_before":
            return False
        if mode == "nochange":
            return True
        resource, count = item_codec.decode_stack(stack, self.GetItemBasicInfo)
        if mode == "corrupt":
            resource, count = item_resource("minecraft:dirt"), 13
        physical, local = self._physical(pos, slot, dimension)
        self.seed(physical, local, resource, count, dimension)
        return mode != "false_after"

    def GetItemBasicInfo(self, name, aux=0):
        result = {"maxStackSize": 1 if name == "minecraft:diamond_sword" else 64,
                  "maxDurability": 1561 if name == "minecraft:diamond_sword" else 0,
                  "fuelDuration": 80.0 if name == "minecraft:coal" else 0.0}
        if name in self.block_states:
            result.update({"itemType": "block", "_radium_block_states":
                           deepcopy(self.block_states[name])})
        return result

    def GetBlockStatesFromAuxValue(self, name, aux):
        return deepcopy(self.block_states.get(name))

    def GetBlockStates(self, pos, dimension):
        return deepcopy(self.states.get((dimension, pos)))

    def SetBlockStates(self, pos, states, dimension):
        self.state_writes.append((pos, deepcopy(states), dimension))
        mode = self.state_modes.pop(0) if self.state_modes else "ok"
        if mode == "false_before":
            return False
        self.states[(dimension, pos)] = deepcopy(states)
        return mode != "false_after"


def setup(world):
    reports = []
    service = TransferService(world.CheckChunkState,
        lambda dimension, pos: world.blocks.get((dimension, pos), {}).get("name"),
        report=reports.append)
    registry = VanillaRegistry(service, world, "fake-level")
    return service, registry, reports


def test_ordinary_faces_share_all_cells_and_stage_without_native_writes():
    for name, size in (("chest", 27), ("trapped_chest", 27), ("barrel", 27),
                       ("hopper", 5), ("dropper", 9), ("dispenser", 9)):
        world = FakeWorld()
        pos = world.add("minecraft:" + name, size=size)
        api, registry, reports = setup(world)
        ports = [api.query(api.ITEM, 0, pos, face) for face in range(6)]
        assert all(port.get_slots() == tuple(range(size)) for port in ports)
        assert all(port.get_storage_ids() == ports[0].get_storage_ids() for port in ports)
        assert all(port.handler.owner is ports[0].handler.owner for port in ports)
        with api.open_transaction() as tx:
            assert ports[0].insert("minecraft:stone", 5, tx, size - 1) == 5
            assert ports[1].get_amount(size - 1, tx) == 5
            assert not world.slot_writes and not world.nbt_writes
        assert ports[1].get_amount(size - 1) == 0
        with api.open_transaction() as tx:
            assert ports[2].insert("minecraft:stone", 5, tx, size - 1) == 5
            tx.commit()
        assert ports[5].get_amount(size - 1) == 5
        assert len(world.slot_writes) == 1 and not world.nbt_writes
        assert all(call[3] is True for call in world.item_reads)


def test_double_chest_both_aliases_use_one_anchor_and_all_fifty_four_slots():
    world = FakeWorld()
    left = world.add("minecraft:chest", (0, 4, 0))
    right = world.add("minecraft:chest", (1, 4, 0))
    world.pair(left, right)
    world.seed(left, 0, "minecraft:stone", 3)
    world.seed(right, 26, "minecraft:dirt", 7)
    api, registry, reports = setup(world)
    right_port = api.query(api.ITEM, 0, right, 3)
    left_port = api.query(api.ITEM, 0, left, 5)
    assert right_port.handler.owner is left_port.handler.owner
    assert right_port.get_slots() == tuple(range(54))
    assert right_port.get_amount(0) == 3 and left_port.get_amount(53) == 7
    with api.open_transaction() as tx:
        assert right_port.insert("minecraft:dirt", 2, tx, 53) == 2
        assert left_port.get_amount(53, tx) == 9
        tx.commit()
    assert all(call[0] == left for call in world.item_reads)
    assert all(call[2] == left for call in world.slot_writes)
    assert world.entities[(0, right)]["Items"][0]["Count"] == atom(1, 9)


def test_chest_pair_changes_require_new_owners_and_do_not_revive_old_handles():
    world = FakeWorld()
    left = world.add("minecraft:chest", (0, 4, 0))
    right = world.add("minecraft:chest", (1, 4, 0))
    api, registry, reports = setup(world)
    single = api.query(api.ITEM, 0, left, 1)
    world.pair(left, right)
    double = api.query(api.ITEM, 0, right, 1)
    assert double.get_slots() == tuple(range(54))
    expect(TransactionError, lambda: single.get_amount(0))
    world.unpair(left, right)
    renewed = api.query(api.ITEM, 0, left, 1)
    assert renewed.get_slots() == tuple(range(27))
    assert renewed.handler.owner is not single.handler.owner
    expect(TransactionError, lambda: single.get_amount(0))
    expect(TransactionError, lambda: double.get_amount(0))


def test_same_family_identity_change_can_be_queried_again():
    world = FakeWorld()
    pos = world.add("minecraft:chest")
    api, registry, reports = setup(world)
    old = api.query(api.ITEM, 0, pos, 2)
    world.blocks[(0, pos)]["aux"] = 3
    renewed = api.query(api.ITEM, 0, pos, 2)
    assert renewed is not None and renewed.handler.owner is not old.handler.owner
    expect(TransactionError, lambda: old.get_amount(0))
    assert renewed.get_amount(0) == 0


def test_false_native_slot_write_after_mutation_restores_both_native_and_memory():
    world = FakeWorld()
    pos = world.add("minecraft:barrel")
    world.seed(pos, 0, "minecraft:stone", 6)
    before = deepcopy(world.entities)
    api, registry, reports = setup(world)
    port = api.query(api.ITEM, 0, pos, 0)
    world.slot_modes = ["false_after"]
    with api.open_transaction() as tx:
        assert port.extract("minecraft:stone", 2, tx, 0) == 2
        error = expect(TransactionError, tx.commit)
    assert not isinstance(error, RecoveryError)
    assert world.entities == before and port.get_amount(0) == 6
    assert port.handler.owner.memory[0] == (item_resource("minecraft:stone"), 6)
    assert not world.nbt_writes and not api.manager.faults
    api.flush()
    assert len(world.slot_writes) == 2  # Write and immediate restore; no deferred retry.


def test_readback_nochange_on_second_slot_restores_first_successful_slot():
    world = FakeWorld()
    pos = world.add("minecraft:chest")
    world.seed(pos, 0, "minecraft:stone", 6)
    before = deepcopy(world.entities)
    api, registry, reports = setup(world)
    port = api.query(api.ITEM, 0, pos, 1)
    world.slot_modes = ["ok", "nochange"]
    with api.open_transaction() as tx:
        assert port.extract("minecraft:stone", 2, tx, 0) == 2
        assert port.insert("minecraft:dirt", 3, tx, 1) == 3
        error = expect(TransactionError, tx.commit)
    assert not isinstance(error, RecoveryError)
    assert world.entities == before and not api.manager.faults
    assert len(world.slot_writes) == 3 and not world.nbt_writes


def test_double_chest_rollback_uses_only_anchor_slot_api_for_both_halves():
    for name in ("minecraft:chest", "minecraft:copper_chest"):
        world = FakeWorld()
        left = world.add(name, (0, 4, 0))
        right = world.add(name, (1, 4, 0))
        world.pair(left, right)
        world.seed(left, 0, "minecraft:stone", 6)
        world.seed(right, 26, "minecraft:dirt", 8)
        before = deepcopy(world.entities)
        api, registry, reports = setup(world)
        port = api.query(api.ITEM, 0, right, 1)
        world.slot_modes = ["ok", "false_after", "ok", "ok"]
        with api.open_transaction() as tx:
            assert port.extract("minecraft:stone", 2, tx, 0) == 2
            assert port.extract("minecraft:dirt", 3, tx, 53) == 3
            error = expect(TransactionError, tx.commit)
        assert not isinstance(error, RecoveryError)
        assert world.entities == before and not api.manager.faults
        assert [call[1] for call in world.slot_writes] == [0, 53, 53, 0]
        assert all(call[2] == left for call in world.slot_writes)
        assert not world.nbt_writes


def test_double_chest_failed_slot_compensation_quarantines_without_nbt_fallback():
    world = FakeWorld()
    left = world.add("minecraft:copper_chest", (0, 4, 0))
    right = world.add("minecraft:copper_chest", (1, 4, 0))
    world.pair(left, right)
    world.seed(left, 0, "minecraft:stone", 6)
    world.seed(right, 26, "minecraft:dirt", 8)
    api, registry, reports = setup(world)
    port = api.query(api.ITEM, 0, right, 1)
    world.slot_modes = ["ok", "false_after", "false_before"]
    with api.open_transaction() as tx:
        port.extract("minecraft:stone", 2, tx, 0)
        port.extract("minecraft:dirt", 3, tx, 53)
        expect(RecoveryError, tx.commit)
    assert not world.nbt_writes and len(world.slot_writes) == 3
    assert api.manager.faults
    for pos in (left, right):
        expect(RecoveryError, lambda p=pos: api.query(api.ITEM, 0, p, 1))
    api.flush()
    assert len(world.slot_writes) == 3 and not world.nbt_writes


def test_api_compensation_requires_exact_item_nbt_not_only_matching_counts():
    world = FakeWorld()
    pos = world.add("minecraft:barrel")
    world.seed(pos, 0, "minecraft:stone", 6)
    world.entities[(0, pos)]["Items"][0]["WasPickedUp"] = atom(1, 1)
    api, registry, reports = setup(world)
    port = api.query(api.ITEM, 0, pos, 1)
    world.slot_modes = ["false_after", "ok"]
    with api.open_transaction() as tx:
        port.extract("minecraft:stone", 2, tx, 0)
        expect(RecoveryError, tx.commit)
    # The native slot API restored the count but regenerated its flag. This is
    # deliberately quarantined rather than reported as a successful rollback.
    assert world.entities[(0, pos)]["Items"][0]["Count"] == atom(1, 6)
    assert world.entities[(0, pos)]["Items"][0]["WasPickedUp"] == atom(1, 0)
    assert api.manager.faults and len(world.slot_writes) == 2 and not world.nbt_writes


def test_unexpected_third_state_is_quarantined_without_blind_restore_or_requery():
    world = FakeWorld()
    pos = world.add("minecraft:chest")
    world.seed(pos, 0, "minecraft:stone", 6)
    api, registry, reports = setup(world)
    port = api.query(api.ITEM, 0, pos, 1)
    world.slot_modes = ["corrupt"]
    with api.open_transaction() as tx:
        port.extract("minecraft:stone", 1, tx, 0)
        expect(RecoveryError, tx.commit)
    assert api.manager.faults and not world.nbt_writes
    expect(RecoveryError, lambda: api.query(api.ITEM, 0, pos, 2))
    registry.invalidate()
    expect(RecoveryError, lambda: api.query(api.ITEM, 0, pos, 2))


def test_native_change_before_commit_is_detected_without_setter_calls():
    world = FakeWorld()
    pos = world.add("minecraft:barrel")
    world.seed(pos, 0, "minecraft:stone", 6)
    api, registry, reports = setup(world)
    port = api.query(api.ITEM, 0, pos, 1)
    with api.open_transaction() as tx:
        port.extract("minecraft:stone", 1, tx, 0)
        world.seed(pos, 0, "minecraft:stone", 3)
        expect(TransactionError, tx.commit)
    assert port.get_amount(0) == 3 and not world.slot_writes and not world.nbt_writes


def test_cauldron_owner_quantizes_abort_and_commit_without_replacing_nbt():
    world = FakeWorld()
    pos = world.add_cauldron(0)
    original_nbt = deepcopy(world.entities[(0, pos)])
    api, registry, reports = setup(world)
    top = api.query(api.FLUID, 0, pos, 1)
    side = api.query(api.FLUID, 0, pos, 3)
    assert top.get_storage_ids() == side.get_storage_ids()
    with api.open_transaction() as tx:
        assert top.insert("minecraft:water", 200.0, tx) == 167.0
        assert side.get_amount(0, tx) == 167.0
        assert not world.state_writes
    assert top.get_amount(0) == 0.0
    with api.open_transaction() as tx:
        assert top.insert("minecraft:water", 200.0, tx) == 167.0
        tx.commit()
    assert side.get_amount(0) == 167.0
    assert world.entities[(0, pos)] == original_nbt
    assert world.states[(0, pos)]["unrelated_state"] == 5
    with api.open_transaction() as tx:
        assert side.extract("minecraft:water", 100.0, tx) == 0.0
        tx.commit()
    assert len(world.state_writes) == 1


def test_cauldron_failed_state_write_restores_the_exact_previous_state():
    world = FakeWorld()
    pos = world.add_cauldron(6)
    before = deepcopy(world.states)
    api, registry, reports = setup(world)
    port = api.query(api.FLUID, 0, pos, 0)
    world.state_modes = ["false_after"]
    with api.open_transaction() as tx:
        assert port.extract("minecraft:water", 500.0, tx) == 500.0
        error = expect(TransactionError, tx.commit)
    assert not isinstance(error, RecoveryError)
    assert world.states == before and port.get_amount(0) == 1000.0
    assert len(world.state_writes) == 2 and not world.nbt_writes


def test_unopened_loot_is_unavailable_without_reading_or_writing_inventory():
    world = FakeWorld()
    pos = world.add("minecraft:chest")
    world.entities[(0, pos)]["LootTable"] = atom(8, "loot_tables/chests/test.json")
    api, registry, reports = setup(world)
    assert api.query(api.ITEM, 0, pos, 1) is None
    assert api.query(api.ITEM, 0, pos, 2) is None
    assert len(reports) == 1 and not world.item_reads
    assert not world.slot_writes and not world.nbt_writes


def test_unknown_item_metadata_rejects_reads_and_staging_without_writes():
    world = FakeWorld()
    pos = world.add("minecraft:barrel")
    world.seed(pos, 0, "minecraft:stone", 3)
    api, registry, reports = setup(world)
    port = api.query(api.ITEM, 0, pos, 1)
    world.raw_extras = {"newUnknownData": "cannot drop"}
    expect(TransactionError, lambda: port.get_resource(0))
    world.raw_extras = {}
    resource = item_resource("minecraft:dirt", 0, {"unknown": "data"})
    with api.open_transaction() as tx:
        expect(ValueError, lambda: port.insert(resource, 1, tx, 1))
    assert not world.slot_writes and not world.nbt_writes


def test_furnace_nbt_write_preserves_progress_and_unmodified_item_entry_bytes():
    world = FakeWorld()
    pos = world.add("minecraft:furnace", size=3)
    world.seed(pos, 0, "minecraft:iron_ore", 5)
    world.seed(pos, 1, "minecraft:coal", 9)
    world.seed(pos, 2, "minecraft:iron_ingot", 4)
    data = world.entities[(0, pos)]
    data.update({"BurnTime": atom(2, 120), "CookTime": atom(2, 65),
                 "BurnDuration": atom(2, 1600), "StoredXPInt": atom(3, 7),
                 "CustomName": atom(8, "kept furnace")})
    data["Items"][1]["WasPickedUp"] = atom(1, 1)
    untouched = deepcopy(data["Items"][:2])
    other_fields = dict((key, deepcopy(val)) for key, val in data.items() if key != "Items")
    api, registry, reports = setup(world)
    bottom = api.query(api.ITEM, 0, pos, 0)
    with api.open_transaction() as tx:
        assert bottom.extract("minecraft:iron_ingot", 2, tx, 2) == 2
        assert not world.nbt_writes
        tx.commit()
    saved = world.entities[(0, pos)]
    assert dict((key, val) for key, val in saved.items() if key != "Items") == other_fields
    assert saved["Items"][:2] == untouched and bottom.get_amount(2) == 2
    assert len(world.nbt_writes) == 1 and not world.slot_writes


def test_native_palette_materialization_does_not_change_bare_block_identity():
    world = FakeWorld()
    pos = world.add("minecraft:furnace", size=3)
    api, registry, reports = setup(world)
    top = api.query(api.ITEM, 0, pos, 1)
    with api.open_transaction() as tx:
        assert top.insert("minecraft:stone", 3, tx, 0) == 3
        tx.commit()
    assert top.get_resource(0) == item_resource("minecraft:stone")
    assert top.get_amount(0) == 3 and not api.manager.faults
    assert world.entities[(0, pos)]["Items"][0]["Block"]["name"] == atom(8, "minecraft:stone")


def test_nbt_duplicate_slots_and_unloaded_half_do_not_return_empty_inventory():
    world = FakeWorld()
    pos = world.add("minecraft:furnace", size=3)
    world.seed(pos, 0, "minecraft:iron_ore", 1)
    api, registry, reports = setup(world)
    port = api.query(api.ITEM, 0, pos, 1)
    world.entities[(0, pos)]["Items"] *= 2
    expect(UnsupportedContainer, lambda: port.get_amount(0))
    assert api.query(api.ITEM, 0, pos, 1) is None
    world = FakeWorld()
    left = world.add("minecraft:chest", (0, 4, 0))
    right = world.add("minecraft:chest", (1, 4, 0))
    world.pair(left, right)
    api, registry, reports = setup(world)
    port = api.query(api.ITEM, 0, left, 1)
    world.unloaded.add((0, right))
    expect(TransactionError, lambda: port.get_amount(0))
    assert not world.slot_writes and not world.nbt_writes


def test_api_inventory_rejects_duplicate_and_out_of_range_physical_slots():
    for name, size in (("minecraft:barrel", 27), ("minecraft:hopper", 5),
                        ("minecraft:dispenser", 9)):
        for duplicate in (True, False):
            world = FakeWorld()
            pos = world.add(name, size=size)
            world.seed(pos, 0, "minecraft:stone", 3)
            entry = deepcopy(world.entities[(0, pos)]["Items"][0])
            entry["Slot"] = atom(1, 0 if duplicate else size)
            world.entities[(0, pos)]["Items"].append(entry)
            before = deepcopy(world.entities)
            api, registry, reports = setup(world)
            assert api.query(api.ITEM, 0, pos, 1) is None
            assert world.entities == before and not world.item_reads
            assert not world.slot_writes and not world.nbt_writes


def test_paired_inventory_validates_each_half_and_rechecks_before_commit():
    world = FakeWorld()
    left = world.add("minecraft:chest", (0, 4, 0))
    right = world.add("minecraft:chest", (1, 4, 0))
    world.pair(left, right)
    world.seed(right, 0, "minecraft:stone", 3)
    api, registry, reports = setup(world)
    port = api.query(api.ITEM, 0, left, 1)
    assert port.get_amount(27) == 3
    # Physical index 27 is invalid even though the paired API has 54 slots.
    world.entities[(0, right)]["Items"][0]["Slot"] = atom(1, 27)
    assert api.query(api.ITEM, 0, left, 1) is None
    assert api.query(api.ITEM, 0, right, 1) is None
    before = deepcopy(world.entities)
    with api.open_transaction() as tx:
        assert port.insert("minecraft:dirt", 1, tx, 0) == 1
        expect(TransactionError, tx.commit)
    assert world.entities == before and not world.slot_writes and not world.nbt_writes


def test_native_stacking_normalizes_defaults_before_matching_full_inventory():
    world = FakeWorld()
    pos = world.add("minecraft:barrel")
    world.seed(pos, 0, "minecraft:stone", 60)
    for slot in range(1, 27):
        world.seed(pos, slot, "minecraft:dirt", 64)
    api, registry, reports = setup(world)
    port = api.query(api.ITEM, 0, pos, 1)
    view = api.item_view(api.item_view(port))
    incoming = api.item_resource_from_stack({
        "newItemName": "minecraft:stone", "newAuxValue": 0, "count": 4,
        "durability": 0, "enchantData": [], "modEnchantData": [],
        "userData": {}, "itemId": 1})
    assert incoming != port.get_resource(0)
    assert view.normalize_resource(incoming) == item_resource("minecraft:stone")
    with api.open_transaction() as tx:
        assert api.insert_item_stacking(view, incoming, 4, tx) == 4
        assert not world.slot_writes and not world.nbt_writes
        tx.commit()
    assert port.get_amount(0) == 64
    assert all(port.get_amount(slot) == 64 for slot in range(1, 27))
    assert len(world.slot_writes) == 1 and world.slot_writes[0][1] == 0


def test_stacking_normalization_fallback_preserves_third_party_metadata():
    api = TransferService(lambda d, p: True, lambda d, p: "example:inventory",
                          report=lambda message: None)
    store = api.create_item_storage({0: 64, 1: 64}, 64)
    original = item_resource("minecraft:stone", 0, {"pluginMarker": "keep"})
    plain = item_resource("minecraft:stone")
    with api.open_transaction() as tx:
        assert store.insert(original, 10, tx, 0) == 10
        assert store.insert(plain, 50, tx, 1) == 50
        tx.commit()
    api.register_provider(api.ITEM, "example:inventory", lambda d, p, f: store)
    proxy = api.query(api.ITEM, 0, (0, 0, 0), 1)
    view = api.item_view(api.item_view(proxy))
    assert view.normalize_resource(original) == original
    with api.open_transaction() as tx:
        assert api.insert_item_stacking(view, original, 5, tx) == 5
        tx.commit()
    assert store.get_resource(0) == original and store.get_amount(0) == 15
    assert store.get_resource(1) == plain and store.get_amount(1) == 50


def run():
    cases = sorted((name, value) for name, value in globals().items()
                   if name.startswith("test_") and callable(value))
    passed, failed = [], {}
    for name, case in cases:
        try:
            case()
            passed.append(name)
        except Exception:
            failed[name] = traceback.format_exc()
    return {"passed": passed, "failed": failed, "total": len(cases), "ok": not failed}

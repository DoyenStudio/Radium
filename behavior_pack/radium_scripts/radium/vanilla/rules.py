# coding=utf-8
"""Bedrock container rules. No engine calls or writes during permission checks.

Native slot IDs: ModAPI/接口/方块/容器.md and BrewingStandSlotType.
Brewing reagents: bundled GameAssets/behavior_packs/vanilla/recipes/brew_*.json.
GetItemBasicInfo documents fuelDuration=0 for vanilla block fuels, requiring
the explicit vanilla block table below. Unknown mod blocks are not guessed.
"""
import math
from ..core.item_resource import get_item_id, get_item_aux
from ..core.values import integer_types


def _ids(names):
    return frozenset("minecraft:" + name for name in names)


_COLORS = ("white", "orange", "magenta", "light_blue", "yellow", "lime",
           "pink", "gray", "light_gray", "cyan", "purple", "blue", "brown",
           "green", "red", "black")
_COPPER = ("copper_chest", "exposed_copper_chest", "weathered_copper_chest",
           "oxidized_copper_chest")
CHESTS = _ids(("chest", "trapped_chest") + _COPPER +
              tuple("waxed_" + name for name in _COPPER))
SHULKERS = _ids(("shulker_box", "undyed_shulker_box") +
                tuple(color + "_shulker_box" for color in _COLORS))
FURNACES = _ids(("furnace", "lit_furnace", "smoker", "lit_smoker",
                "blast_furnace", "lit_blast_furnace"))
CAULDRONS = _ids(("cauldron", "lava_cauldron"))
ITEM_BLOCKS = CHESTS | SHULKERS | FURNACES | _ids(
    ("barrel", "hopper", "dispenser", "dropper", "brewing_stand"))

_PROFILES = dict((name, ("chest", 27)) for name in CHESTS)
_PROFILES.update((name, ("shulker", 27)) for name in SHULKERS)
_PROFILES.update((name, ("furnace", 3)) for name in FURNACES)
_PROFILES.update({"minecraft:barrel": ("barrel", 27),
                  "minecraft:hopper": ("hopper", 5),
                  "minecraft:dispenser": ("dispenser", 9),
                  "minecraft:dropper": ("dropper", 9),
                  "minecraft:brewing_stand": ("brewing", 5)})
_SIZES = dict(_PROFILES.values())

BREWING_INGREDIENTS = _ids((
    "nether_wart", "redstone", "glowstone_dust", "gunpowder", "dragon_breath",
    "blaze_powder", "breeze_rod", "fermented_spider_eye", "ghast_tear",
    "golden_carrot", "magma_cream", "phantom_membrane", "pufferfish",
    "rabbit_foot", "slime", "speckled_melon", "spider_eye", "stone", "sugar",
    "turtle_helmet", "web"))
_BOTTLES = _ids(("potion", "splash_potion", "lingering_potion", "glass_bottle"))

# These are finite vanilla families, not suffix-based rules for arbitrary items.
_TREES = ("oak", "spruce", "birch", "jungle", "acacia", "dark_oak",
          "mangrove", "cherry", "pale_oak")
_WOOD_FORMS = ("planks", "stairs", "slab", "double_slab", "fence", "fence_gate",
               "door", "trapdoor", "button", "pressure_plate", "sign", "wall_sign",
               "standing_sign", "hanging_sign", "wall_hanging_sign", "shelf")
_WOOD_BLOCKS = tuple(tree + "_" + form for tree in _TREES + ("bamboo",)
                     for form in _WOOD_FORMS)
_LOG_BLOCKS = tuple(prefix + tree + "_" + form for tree in _TREES
                    for prefix in ("", "stripped_") for form in ("log", "wood"))
_SAPLINGS = tuple(tree + "_sapling" for tree in _TREES if tree != "mangrove")
FUEL_BLOCKS = _ids(_WOOD_BLOCKS + _LOG_BLOCKS + _SAPLINGS + (
    "coal_block", "dried_kelp_block", "bamboo", "bamboo_block", "stripped_bamboo_block",
    "bamboo_mosaic", "bamboo_mosaic_stairs", "bamboo_mosaic_slab", "scaffolding",
    "chest", "trapped_chest", "barrel", "crafting_table", "cartography_table",
    "fletching_table", "smithing_table", "loom", "bookshelf", "chiseled_bookshelf",
    "lectern", "composter", "jukebox", "noteblock", "note_block", "ladder",
    "daylight_detector", "daylight_detector_inverted", "beehive", "bee_nest",
    "azalea", "flowering_azalea", "mangrove_roots", "mangrove_propagule", "deadbush",
    "wooden_door", "trapdoor", "fence_gate", "wooden_button", "wooden_pressure_plate",
    "standing_sign", "wall_sign", "sign")) | _ids(tuple(
        color + "_" + form for color in _COLORS for form in ("wool", "carpet")))

# Legacy aux encodings must not broaden to Nether wood or invalid wood species.
_WOOD_AUX = frozenset(tuple(range(6)) + tuple(range(8, 14)))
_LEGACY_FUELS = {
    "minecraft:log": frozenset(range(16)),
    "minecraft:log2": frozenset((0, 1, 4, 5, 8, 9, 12, 13)),
    "minecraft:wood": _WOOD_AUX,
    "minecraft:planks": frozenset(range(6)),
    "minecraft:wooden_slab": _WOOD_AUX,
    "minecraft:double_wooden_slab": _WOOD_AUX,
    "minecraft:fence": frozenset(range(6)),
    "minecraft:sapling": _WOOD_AUX,
    "minecraft:wool": frozenset(range(16)),
    "minecraft:carpet": frozenset(range(16)),
    "minecraft:banner": frozenset(range(16)),
    "minecraft:standing_banner": frozenset(range(16)),
    "minecraft:wall_banner": frozenset(range(16)),
}


def profile(name):
    return _PROFILES.get(name)


def ports(kind, face):
    """Input and output slots for the target's absolute face (0 bottom, 1 top)."""
    if kind not in _SIZES:
        raise ValueError("Unknown vanilla container kind")
    if face is not None and (isinstance(face, bool) or
                             not isinstance(face, integer_types) or face not in range(6)):
        raise ValueError("Face must be 0..5 or None")
    if kind == "furnace":
        if face is None:
            return (0, 1), (2, 1)
        if face == 1:
            return (0,), ()
        if face == 0:
            return (), (2, 1)
        return (1,), ()
    if kind == "brewing":
        if face is None:
            return (0, 1, 2, 3, 4), (1, 2, 3)
        if face == 1:
            return (0,), ()
        if face == 0:
            return (), (1, 2, 3)
        return (1, 2, 3, 4), ()
    slots = tuple(range(_SIZES[kind]))
    return slots, slots


def _slot(kind, slot):
    # Chest rules cover both shapes; the live handler enforces 27 versus 54.
    return (not isinstance(slot, bool) and isinstance(slot, integer_types)
            and kind in _SIZES and 0 <= slot < (54 if kind == "chest" else _SIZES[kind]))


def _empty_bucket(resource):
    return get_item_id(resource) == "minecraft:bucket" and get_item_aux(resource) == 0


def _is_fuel(resource, basic_info):
    duration = (basic_info.get("fuelDuration", 0) if isinstance(basic_info, dict)
                else getattr(basic_info, "fuelDuration", 0))
    if (not isinstance(duration, bool) and isinstance(duration, integer_types + (float,))
            and duration > 0 and not math.isinf(duration)):
        return True
    item_id = get_item_id(resource)
    if item_id in FUEL_BLOCKS:
        return True
    return get_item_aux(resource) in _LEGACY_FUELS.get(item_id, ())


def accepts(kind, slot, resource, basic_info=None):
    if resource is None or not _slot(kind, slot):
        return False
    item_id = get_item_id(resource)
    if kind == "shulker":
        return item_id not in SHULKERS
    if kind == "furnace":
        # Target NetEase hopper probes reject empty buckets on the fuel input.
        return slot == 0 or (slot == 1 and _is_fuel(resource, basic_info))
    if kind == "brewing":
        if slot == 0:
            return item_id in BREWING_INGREDIENTS
        if slot == 4:
            return item_id == "minecraft:blaze_powder"
        return item_id in _BOTTLES
    return True


def allows_extract(kind, slot, resource):
    if resource is None or not _slot(kind, slot):
        return False
    if kind == "furnace":
        return slot == 2 or (slot == 1 and _empty_bucket(resource))
    if kind == "brewing":
        # The target game's bottom hopper does not extract reagent-slot bottles.
        return slot in (1, 2, 3)
    return True

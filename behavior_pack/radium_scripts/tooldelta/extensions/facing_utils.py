# coding=utf-8


class FacingStrEnum:
    DOWN = "down"
    UP = "up"
    NORTH = "north"
    SOUTH = "south"
    WEST = "west"
    EAST = "east"


class RelativeFacingStrEnum:
    FRONT = "front"
    LEFT = "left"
    TOP = "top"
    RIGHT = "right"
    DOWN = "down"
    BACK = "back"


_HORIZONTAL_FACINGS = (
    FacingStrEnum.NORTH,
    FacingStrEnum.EAST,
    FacingStrEnum.SOUTH,
    FacingStrEnum.WEST,
)
_RELATIVE_HORIZONTAL_FACINGS = (
    RelativeFacingStrEnum.FRONT,
    RelativeFacingStrEnum.LEFT,
    RelativeFacingStrEnum.BACK,
    RelativeFacingStrEnum.RIGHT,
)


def get_relative_facing(cardinal_direction, facing):
    # type: (str, str) -> str
    # 将 FacingStrEnum 的值转换为 RelativeFacingStrEnum 的值。

    # cardinal_direction 是方块正面朝向，仅接受 north/east/south/west。
    # 左右以面对方块正面的视角为准，与 FrontFacingRes 一致：
    # 正面朝 north 时，east 为 left，west 为 right。up 对应 top。
    # 无效参数抛出 ValueError。
    front_index = _HORIZONTAL_FACINGS.index(cardinal_direction)
    if facing == FacingStrEnum.UP:
        return RelativeFacingStrEnum.TOP
    if facing == FacingStrEnum.DOWN:
        return RelativeFacingStrEnum.DOWN
    facing_index = _HORIZONTAL_FACINGS.index(facing)
    return _RELATIVE_HORIZONTAL_FACINGS[(facing_index - front_index) % 4]


def get_absolute_facing(cardinal_direction, relative_facing):
    # type: (str, str) -> str
    # 将 RelativeFacingStrEnum 的值转换为 FacingStrEnum 的值。

    # 与 get_relative_facing 互为逆转换，使用相同的正面和左右约定。
    # top 对应 up，down 对应 down；无效参数抛出 ValueError。
    front_index = _HORIZONTAL_FACINGS.index(cardinal_direction)
    if relative_facing == RelativeFacingStrEnum.TOP:
        return FacingStrEnum.UP
    if relative_facing == RelativeFacingStrEnum.DOWN:
        return FacingStrEnum.DOWN
    relative_index = _RELATIVE_HORIZONTAL_FACINGS.index(relative_facing)
    return _HORIZONTAL_FACINGS[(front_index + relative_index) % 4]


_RELATIVE_FACINGS = _RELATIVE_HORIZONTAL_FACINGS + (
    RelativeFacingStrEnum.TOP,
    RelativeFacingStrEnum.DOWN,
)
# 每行依次对应 front、left、back、right、top、down。
# 从正面朝北、顶部朝上的姿态上下翻转，不额外绕正面旋转。
_VERTICAL_ABSOLUTE_FACINGS = {
    FacingStrEnum.UP: (
        FacingStrEnum.UP,
        FacingStrEnum.EAST,
        FacingStrEnum.DOWN,
        FacingStrEnum.WEST,
        FacingStrEnum.SOUTH,
        FacingStrEnum.NORTH,
    ),
    FacingStrEnum.DOWN: (
        FacingStrEnum.DOWN,
        FacingStrEnum.EAST,
        FacingStrEnum.UP,
        FacingStrEnum.WEST,
        FacingStrEnum.NORTH,
        FacingStrEnum.SOUTH,
    ),
}


def get_relative_facing_by_facing_direction(facing_direction, facing):
    # type: (str, str) -> str
    """根据六面向 facing_direction，将绝对朝向转换为相对朝向。

    两个参数均接受 FacingStrEnum 的六个字符串值。
    水平方向与 get_relative_facing 一致。正面朝 up 时，top 朝 south；
    正面朝 down 时，top 朝 north；两者的 left 均朝 east。
    facing_direction 本身不包含绕正面的旋转信息，此处固定使用上述约定。
    无效方向字符串抛出 ValueError。
    """
    if facing_direction in _HORIZONTAL_FACINGS:
        return get_relative_facing(facing_direction, facing)
    absolute_facings = _VERTICAL_ABSOLUTE_FACINGS.get(facing_direction)
    if absolute_facings is None:
        raise ValueError("Invalid facing_direction: %r" % (facing_direction,))
    return _RELATIVE_FACINGS[absolute_facings.index(facing)]


def get_absolute_facing_by_facing_direction(facing_direction, relative_facing):
    # type: (str, str) -> str
    """根据六面向 facing_direction，将相对朝向转换为绝对朝向。

    facing_direction 接受 FacingStrEnum 的六个字符串值，relative_facing
    接受 RelativeFacingStrEnum 的值。与 get_relative_facing_by_facing_direction
    互为逆转换，使用相同的上下翻转约定。无效方向字符串抛出 ValueError。
    """
    if facing_direction in _HORIZONTAL_FACINGS:
        return get_absolute_facing(facing_direction, relative_facing)
    absolute_facings = _VERTICAL_ABSOLUTE_FACINGS.get(facing_direction)
    if absolute_facings is None:
        raise ValueError("Invalid facing_direction: %r" % (facing_direction,))
    return absolute_facings[_RELATIVE_FACINGS.index(relative_facing)]

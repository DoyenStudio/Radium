# radium 1.1.0 第三方模组接口文档

适用于网易我的世界服务端 Python 2.7.13。管道、电缆等运输模组通过 `query` 查找端口，通过 `move_*` 或 `distribute_*` 搬运资源。机器模组通过 `register_provider` 告诉其他模组，哪个方块的哪一面能存取 RF 或流体。一个模组可以同时承担两种角色。

## 快速接入

### 在使用方获取组件

```python
import mod.server.extraServerApi as serverApi

def get_transfer_api():
    api = serverApi.GetComponent(serverApi.GetLevelId(), "radium", "transfer")
    if api is None or api.API_VERSION[0] != 1:
        return None
    return api
```

将这段代码放在使用方的服务端脚本中。用到传输功能时再获取组件；返回 `None` 时跳过联动，保留模组自身的运行流程，下次使用时可再次获取。使用方无需导入 radium 脚本、创建组件或在 manifest 中声明强制依赖。

### 运输模组：从下方机器向上方机器输送 RF

```python
def push_up(dimension, source_pos):
    api = get_transfer_api()
    if api is None:
        return 0
    x, y, z = source_pos
    try:
        source = api.query(api.ENERGY, dimension, source_pos, face=1)
        target = api.query(api.ENERGY, dimension, (x, y + 1, z), face=0)
        if source is None or target is None:
            return 0
        with api.open_transaction() as tx:
            moved = api.move_energy(source, target, 200, tx)
            tx.commit()
        return moved
    except api.TransactionError:
        # 端口可能已卸载或重绑，交给宿主下一轮重新查询。
        return 0
```

由运输模组在自己的调度中调用 `push_up`。两个面编号分别相对于各自被查询的方块。若上方机器只能接收 60 RF，提交后源端只扣 60 RF，函数返回 60。搬运流体时，两端都查 `api.FLUID`，然后调用例如 `api.move_fluid(source, target, "minecraft:water", 250, tx)`，返回量以 mB 计。

### 机器模组：向其他模组开放电池端口

```python
def register_battery(api, loaded_batteries):
    def provider(dimension, pos, face):
        battery = loaded_batteries.get((dimension, pos))
        if battery is None:
            return None
        if face == 0:
            return battery.input_port
        if face == 1:
            return battery.output_port
        return None

    api.register_provider(api.ENERGY, "example:battery", provider)
    return provider
```

1. 在取得兼容组件后，为自己的实际方块 ID 注册一次 provider，并保存返回的回调引用。`loaded_batteries` 是宿主管理的已加载机器字典，键为 `(维度整数, (x, y, z))`。
2. 在机器加载时创建或恢复它的 `battery.energy`。用 `api.energy_view(battery.energy, can_extract=False)` 创建 `input_port`，用 `api.energy_view(battery.energy, can_insert=False)` 创建 `output_port`，再将机器加入字典。上下两面共享这份储量。
3. 单台机器卸载时，从字典移除该实例并调用 `api.invalidate()`，让已有查询结果失效。同类其他机器继续使用已注册的 provider。停用整类方块的联动时，用保存的回调调用 `api.unregister_provider(api.ENERGY, "example:battery", provider)`。

带存档的机器可参考[完整宿主示例](../examples/third_party_machine.py)，其中包含服务发现、稀疏流体槽、RF 与流体的原子配方、存档回调和卸载处理。

## 服务发现与生命周期

通过 `serverApi.GetComponent(levelId, "radium", "transfer")` 获取服务端组件。使用方检查 `None` 与 `API_VERSION[0]`，不导入库的脚本包。所有调用必须在该组件所属的服务端线程执行。

组件属性：`API_VERSION=(1,1,0)`、`ENERGY="radium:energy"`、`FLUID="radium:fluid"`、`TransactionError`。使用新流体身份接口前检查 `API_VERSION >= (1, 1, 0)`。

服务的每个模拟 tick 只执行两项维护：中止跨 tick 未关闭的事务，重试脏持久化回调。没有自动资源调度。退出世界时执行最后一次维护并清理 provider 引用。

## 存储和端点

| 方法 | 返回 / 用途 |
| --- | --- |
| `create_energy_storage(capacity, amount=0, saved=None, persist=None, changed=None, owner=None)` | 单 Cell RF 存储；saved 非 None 时从快照恢复 |
| `create_fluid_storage(capacities, saved=None, persist=None, changed=None, owner=None)` | capacities 为非空的整数槽位 → 容量字典；初始为空 |
| `create_cell(state, read=None, apply=None, persist=None, changed=None, owner=None, valid=None)` | 为现有缓存创建事务 Cell；state 只能是不可变标量或元组 |
| `create_energy_handler(cells, capacity, can_insert=True, can_extract=True, max_insert=None, max_extract=None, valid=None, on_insert=None, on_extract=None, owner=None)` | `cells` 是同一组件下非空、无重复的 RF Cell 序列，每个 Cell 保存整数储量；`capacity(cell)` 返回该 Cell 的容量 |
| `create_fluid_handler(cells, capacity, input_slots=None, output_slots=None, accepts=None, valid=None)` | `cells` 将非负整数槽位映射到同一组件下各自独立的 Cell，每个 Cell 保存 `(resource, amount)`；`capacity(slot)` 返回槽容量 |
| `combine_energy(handlers, valid=None)` | 按给定顺序调用多个能源端点 |
| `create_voiding_energy(on_insert=None, valid=None)` | 接受任意有限非负 RF；无储量、无提取；提交后统计 |
| `energy_view(handler, can_insert=True, can_extract=True, valid=None, max_insert=None, max_extract=None)` | 委托原端点，附加方向和每次调用限额 |
| `fluid_view(handler, slots=None, input_slots=None, output_slots=None, valid=None, accepts=None)` | 委托原端点，附加可见槽位、方向和资源过滤 |
| `fluid_resource(fluid_id, properties=None)` | 创建不可变流体身份；无属性时仍返回字符串 |
| `get_fluid_id(resource)` / `get_fluid_properties(resource)` | 取得基础 ID / 脱离身份对象的属性副本 |

视图可包装原始存储、query 保护代理、组合能源 handler、其他视图和遵守公开协议的自定义端点。它们调用原端点的存取方法，不重新构造存储算法，因此保留虚空接收、自定义存取规则、失效检查与提交后回调。多层视图只能收紧权限；外层声明输入槽也不能使内层已禁用的输入恢复。能源限额随原端点更新，附加限额不会放宽原端点限制。

能源视图的方向参数可为布尔值或无参函数，限额可为非负整数、无参函数或 None。方向、限额字段的替换和函数返回值在提交时重验。流体视图的 `accepts(slot, resource)` 是额外过滤，提交时重验。视图的 `valid()` 只提供额外生命周期限制。

未限制流体槽位且未增加插入资源过滤时，无槽位调用原样委托，保留端点的批量调度规则。显式限制槽位或添加资源过滤时，按视图顺序调用原端点的单槽方法；每次调用仍受原端点约束。只支持整体处理的自定义端点必须拒绝不支持的单槽操作。

RF handler 方法：`get_amount(tx=None)`、`get_capacity()`、`insert(amount, tx)`、`extract(amount, tx)`。数量必须是非负整数，允许值为整数的有限 float 作为兼容输入；拒绝 bool、小数、负数、NaN 与无穷。运行时可使用 Python long，但不得直接持久化。

RF handler 选项：`can_insert/can_extract` 为布尔值或无参函数，`max_insert/max_extract` 为非负整数、无参函数或 None，`valid()` 检查生命周期，`on_insert(actual)/on_extract(actual)` 在最终提交后调用。限额是**每次 handler 调用的限额**，不是每 tick 或每事务的全局预算。方向、容量及限额在提交时重验。

流体端点的方法如下。读取储量或流体身份时，显式传入当前 `tx` 可看到本层暂存的修改，省略时读取已提交状态。RF 的 `get_amount` 也遵循这个规则。

| 方法 | 返回值及用法 |
| --- | --- |
| `get_slots()` | 可见槽位序号；遍历返回的序号即可处理稀疏槽位 |
| `get_resource(slot, tx=None)` | 该槽的完整流体身份，空槽返回 `None` |
| `get_amount(slot, tx=None)` | 该槽的储量（mB），空槽返回 `0.0` |
| `get_capacity(slot, fluid_id=None)` | 该槽总容量（mB）；传入身份时，输入规则拒绝该身份则返回 `0.0` |
| `is_valid(slot, fluid_id)` | 输入方向及过滤规则是否允许该身份；实际能装多少还取决于槽内流体和剩余容量 |
| `insert(fluid_id, amount, tx, slot=None)` | 本次实际接收的 mB 数；指定槽位时只尝试该槽 |
| `extract(fluid_id, amount, tx, slot=None)` | 本次实际提取的 mB 数；指定槽位时只尝试该槽 |

流体 handler 选项：`input_slots/output_slots` 为无重复的已有槽位，None 表示全部，空元组表示禁用该方向；`accepts(slot, resource)` 是入槽过滤函数；`valid()` 检查生命周期。参数名为 `fluid_id` 的流体方法均接受字符串 ID 或 `fluid_resource` 返回的身份。数量为非负有限浮点 mB，空槽为 `(None, 0.0)`，不混液。槽位序号可以不连续。跨槽按配置顺序操作。

只有容量明确为 `float("inf")` 的槽位是创造模式无限源：首次正量插入配置完整流体身份，随后拒绝插入，提取不减少储量。这是显式的非守恒设施。

有限槽仍使用双精度浮点 mB，不强制量化为整数。库检查实际储量变化能否精确表示，并只报告该实际数量；舍入时可少接收，无法表示正变化时返回 0。例如 `2**54 mB` 的有限罐无法提取 `1 mB`，不会向目标凭空提供该数量。跨槽、跨目标累加无法精确表示时跳过相应操作；最终源端提取量与接收总量必须严格相等，否则抛 TransactionError 并放弃该次转移子事务。普通调用方仍须使用返回值决定是否满足配方。

## 流体身份与属性

```python
coolant = api.fluid_resource("example:coolant", {
    "grade": 2,
    "components": {"example:additive": 0.125},
})
view = api.fluid_view(tank, accepts=lambda slot, resource:
                      api.get_fluid_id(resource) == "example:coolant")
with api.open_transaction() as tx:
    received = view.insert(coolant, 250, tx)
    tx.commit()
```

身份由基础 `namespace:name` 和完整属性组成；属性键顺序不影响相等与哈希。同 ID 不同属性不能混合或相互提取；字符串只匹配无属性流体。需要按基础类型过滤时调用 `get_fluid_id`，需要精确匹配时比较完整身份。

属性根节点必须为 dict，支持嵌套 dict/list、字符串、整数（含运行时 long）、有限 float、bool 和 None。键必须为字符串，unicode 规范化为 UTF-8 str。整数、浮点数与布尔值保留类型区别。创建身份时深度冻结，`.properties` / `get_fluid_properties` 返回深拷贝；调用方修改输入属性或返回副本不会改变已有身份。身份本身是可哈希的不可变元组对象，可安全放入 Cell。无需导入库中的类。

## 自定义端点公开协议

端点必须提供属于当前组件的 `manager`、稳定的 `storage_ids` 身份集合，以及上述能源或流体公开方法；包装器不要求暴露 `cells`、容量回调或内部方向字段。每个真实存储必须使用同一身份标记，不能为别名重新生成标记。所有存取必须遵守传入的事务，支持放弃与嵌套模拟，生命周期和业务限制必须由端点自行 guard；不能在模拟中调用旧的立即写入接口或发送通知。

流体端点可额外实现 `get_storage_ids(slots=None)`，返回所选槽位对应的稳定身份集合。内置存储、查询代理和流体视图支持该方法，因此同罐分槽视图仍能互转。未实现时，任何子视图保守保留原端点整个 `storage_ids` 集合；这种端点的同源分槽互转会被消重跳过，避免错误推断独立性。

## 事务

`open_transaction(parent=None)` 立即创建并成为当前事务。使用 with 块，必须显式 `commit()`。有当前事务时必须显式传入该事务作为 parent，禁止隐式加入。子事务提交不修改真实存储；子事务放弃保留父层状态；父层放弃也丢弃所有已合并子层。

```python
with api.open_transaction() as root:
    with api.open_transaction(root) as attempt:
        if api.move_energy(source, target, 100, attempt) == 100:
            attempt.commit()
    # 这里还可操作流体；最后一起提交。
    root.commit()
```

`tx.read(cell)` 读取本层暂存值；`tx.write(cell, immutable_value)` 暂存修改；`tx.guard(predicate)` 立即及提交时核验端点；`tx.abort()` 关闭本层。同一 Cell 的外部缓存、版本或有效性在根提交前发生变化会抛出 TransactionError。事务不得跨 tick、线程或服务实例。

`cell.set(value)` 是适配旧调用的立即写入口，仅在无事务时可用，触发持久化但不合成业务通知。不要在事务内调用旧 AddPower/AddFluid 等直接修改方法，也不要直接写 cells/state。

### 提交顺序

1. 校验全部 guard、Cell 版本、外部原值与生命周期。
2. 将所有修改应用到内存；apply 失败时恢复已应用的原值。
3. 按 owner 合并脏持久化，关闭事务。
4. 执行 persist，再执行合并后的 changed 与统计回调。

回调约定：

- `read()` 返回不可变快照；`apply(value)` **仅更新内存**，必须支持恢复原值，不执行 NBT/事件/网络发送，也不得开启事务。这两个参数必须成对提供。
- `persist()` 写当前最终快照，只做持久化；不得修改资源或开启事务。失败时抛异常（原生接口返回 False 时由适配方转为异常），库记录日志并留待下个 tick 重试。
- `changed(changes)` 收到 `[(cell, original, final), ...]`，此时所有资源均已提交。它可标记 UI 待同步，也可开启新事务；通知用队列排出，不递归进入通知。
- 同一逻辑所有者的所有 Cell 使用同一个可哈希 owner、同一 persist 和同一 changed 回调，以便跨 RF/流体合并一次。
- 统计回调按 handler owner 和 in/out 合并。通知异常会记录日志，但不回滚已提交资源，也不重放转移。

这里只保证单线程内存事务，不保证多方块 NBT 写盘的崩溃原子性。持久化失败或 UI 回调失败后，不可重试整个已提交交易。脏状态保留在 `api.manager.dirty` 中，可在调试时观察；卸载前调用 `flush()` 并确认真实保存行为。

## 转移与有序分配

```python
api.move_energy(source, target, amount, tx)
api.distribute_energy(source, targets, amount, tx)
api.move_fluid(source, target, fluid_id, amount, tx)
api.distribute_fluid(source, targets, fluid_id, amount, tx)
```

这些方法都返回实际移动量，在传入事务内开启可回滚子层。先在放弃的子层模拟源端提取，再按给定顺序暂存接收，最后只提取实际接收量；最终根事务提交前不产生外部副作用。源端每轮分配的限额对整轮有效。拒收部分留在源端。对于多个目标，请将要优先填充的端口放在 `targets` 列表前面，并先过滤掉查询返回的 `None`。

通过 `storage_ids`（共享 Cell 身份集合）识别别名端口。任何与源或本轮已经考虑的目标相交的端点会被保守跳过；组合能源同样跳过与前一端点重叠的整个后续端点。因此重叠的多 Cell 组合可能少传，但不会重复扣取；应提供不重叠视图或在拓扑层消重。同一槽不能经两个面重复参与。同一个罐内不同槽互转须分别使用只含各自槽的 fluid_view。

不要通过重复创建 Cell 包装同一实际存储来伪装独立端点。控制器和多个 IO 方块必须共享同一 Cell 集合。调用方负责本轮优先级、总预算和下次调用时机，不应拿 insert/extract 的最大限额当作全局公平约束。

## 能力 provider

```python
api.register_provider(api.ENERGY, "example:machine", provider)
handler = api.query(api.ENERGY, dimension, (x, y, z), face)
api.unregister_provider(api.ENERGY, "example:machine", provider)
```

`query(capability, dimension, pos, face=None)` 接受整数维度和三个整数方块坐标。`register_provider` 和 `unregister_provider` 均应在事务外调用。注册成功返回 `None`；同一能力和方块 ID 重复注册同一回调有效，换用其他回调会抛出 `ValueError`。注销时传入原回调，匹配并移除后返回 `True`，未匹配返回 `False`。

`provider(dimension, pos_tuple, face)` 只查宿主的已加载机器表，返回属于当前组件的 handler 或 `None`。区块加载、机器构造、存档读写和资源修改均应在 provider 外完成。

face 是被查询方块的原生绝对面：0 下、1 上、2 北、3 南、4 西、5 东。None 是由 provider 自行决定的无面访问，不自动获得绕过过滤的权限；相邻查询必须由调用方换算成目标面。

query 先 CheckChunkState，再 GetBlockNew 取 name，再选择 provider。无匹配、区块未加载或 provider 返回 None 时返回 None。query 不保存机器缓存。返回的保护代理在操作及提交时重新核验原生方块、区块和失效代数；过期抛 TransactionError，下一调度轮重新 query。

放置/移除/邻居变化和区块加载/卸载会保守地使所有旧保护代理失效。自定义控制器重绑、侧面模式/过滤器变化、机器卸载等仍需调用 `api.invalidate()`；provider/Cell 的 valid 也应检查机器在所属对象池内是否仍是当前实例。不要长期缓存查询代理。库为注册方块启用 BlockRemove 原生监听。

## 原生快照与恢复

`save_energy(handler)` 和 `save_fluid(handler)` 创建完全脱离运行缓存的原生字典。常规机器应把同一 owner 的 RF 与流体快照写进一个字典，再整体赋值：

```python
bdata["example:resources"] = {
    "energy": api.save_energy(energy),
    "fluid": api.save_fluid(tank),
}
```

RF schema 1：`{"schema": 1, "limbs": [低位, ..., 高位]}`，基数为 10^9，每段均为 int32。零编码为 [0]；不写 Python long，不用整个状态 JSON，也不因大整数转 float 损失精度。

流体写入 schema 2：`{"schema": 2, "slots": {"0": {"resource": 身份记录或None, "amount": "0x1.0p+0", "infinite": bool}}}`。`amount` 是 Python `float.hex()` 的规范字符串，逐值保留 binary64，不经过原生 float32 标签；无限流体写零的 hex 字符串，由 infinite 标志恢复。槽位键统一字符串；恢复时必须与配置精确匹配，拒绝超容量、错误资源、未知槽位与不合法无限状态。

无属性身份仍写字符串，有属性身份写 `{"id": 基础ID, "properties": 属性记录}`。属性记录递归使用 `{"type": 类型名, "value": 数据}`；整数用十进制字符串，float 用 hex 字符串，bool 用 `"0"/"1"`，None 用空字符串；dict 的值是属性记录，list 的元素统一是属性记录 dict。快照只有原生 dict/list/字符串/int/bool/None，不含 Python long、非有限 float 或异构 list。

仍可读取 schema 1 的字符串身份和浮点数量。若旧数量超过配置容量，仅当它恰好等于该容量转换为 float32 后的值时，按容量恢复；其他超量仍拒绝。旧数据下一次保存写为 schema 2，1.0 版本无法读取 schema 2，因此升级后不要直接降级库版本。槽位变化、真正的容量缩小仍由宿主迁移，不静默丢弃资源。

使用 `create_*_storage(..., saved=data)` 在初始化阶段恢复，不产生修改通知。仅写了缓存再即时读取不能证明 NBT 落盘；必须保存、退世界、重进并检验原生数据。可传入自己的 persist 回调适配旧存档，但本库不替任何宿主迁移历史数据。

## 游戏内验证

在游戏服务端、没有活动事务时调用 `api.run_self_tests()`。该方法使用独立内存存储，返回含 `ok`、`passed`、`failed` 和 `total` 的字典。验证自己的模组接入时，还需检查无前置启动、按面互通、区块卸载后重新查询、保存退出再进入后的储量。操作步骤见[游戏验收文档](VALIDATION.md)。

# radium

网易我的世界 Python 2.7.13 服务端流体与 RF 事务库，独立于 SkyBlueTech。版本 1.1.0。

第三方模组开发者可从[接口文档](docs/API.md)开始，按机器提供端口或管道搬运资源的示例接入。

本次实现仅包含前置库。**没有修改 SkyBlueTech，没有为其添加强制依赖或迁移任何机器、管道和存档。** SkyBlueTech 接入须等其工作区干净后另行进行。

## 安装与可选获取

将本项目的行为包与资源包导入开发环境。radium 启动时注册并在 levelId 上创建唯一服务端组件：

```python
import mod.server.extraServerApi as serverApi

api = serverApi.GetComponent(serverApi.GetLevelId(), "radium", "transfer")
if api is None:
    # 前置未安装或尚未初始化：使用方继续自己的原有流程。
    pass
elif api.API_VERSION[0] == 1:
    # 使用 radium v1。
    pass
```

使用方不需要导入 `radium_scripts`，不调用 `CreateComponent`，不声明强制 manifest 依赖。请在所有附加包脚本加载结束后获取，或首次业务调用时惰性获取；不要把早期的 `None` 永久缓存。客户端没有资源写入组件。

## 已提供

- 非负整数 RF 存储、组合存储、只入/只出视图、虚空接收端和每次调用限额。
- 流体 ID + 可选不可变属性身份、浮点 mB 存储、稀疏槽位、输入/输出槽过滤、资源过滤、共享存储视图和显式无限源。
- 有限流体按实际可表示的储量差返回数量，精度不足时少接收或返回 0；源端和目标总量严格核对。
- 委托视图可包装查询代理、组合能源、自定义端点和其他视图，保留原端点限制与特殊存取规则。
- RF 与流体共用一个事务：嵌套提交只合并到父事务，最外层提交才统一更新内存、持久化并通知。
- `move_energy`、`move_fluid` 及按调用方给定顺序分配的 `distribute_*`；识别共享 Cell，避免同一控制器的别名端口重复参与。
- 按能力、方块 ID、维度、坐标和目标绝对面查询；只查询已加载区块，不创建机器。
- 原生 NBT 安全快照：RF 大整数分解为 int32 数组，流体 schema 2 用 hex 字符串保留完整浮点数量和属性，兼容读取 schema 1，永不写入 `long` 或 `inf`。
- 仅游戏解释器运行的独立内存自测，不访问或改变真实机器。

本库不维护电线/管道拓扑，不自行搬运资源，不规定 tick 频率、全网预算或公平策略。调用方决定优先级、速率和网络行为。首版不含物品、玩家充电、桶交互或热量能力。

## 最小事务

```python
rf = api.create_energy_storage(10000, amount=1000)
tank = api.create_fluid_storage({0: 4000, 3: 4000})

with api.open_transaction() as tx:
    if (rf.extract(80, tx) == 80 and
            tank.insert("minecraft:water", 250.0, tx, slot=0) == 250.0):
        tx.commit()
# 任一步不足，离开 with 时放弃本次扣费和注水。
```

精确配方必须检查每一步返回的实际数量，只有全部满足才 commit。转移方法返回实际移动量，不返回 overflow。详见 [API 与契约](docs/API.md)、[独立机器示例](examples/third_party_machine.py) 和 [游戏验收](docs/VALIDATION.md)。

## 构建

在项目目录运行 `powershell -ExecutionPolicy Bypass -File .\pack.ps1` 生成 `addon.zip`。打包仅压缩文件，不执行或编译项目 Python。输出已被 .gitignore 排除。

## 验证状态

1.1.0 的核心源码已完成静态解析与审查；游戏内回归用例已补充。项目代码未在系统 Python 上执行或编译。当前 MCDK 游戏端 `localhost:19133` 不可连接，因此 **游戏内自测、真实 NBT 保存重进与加载联动尚未运行**；具体步骤及构建检查记录见 [VALIDATION.md](docs/VALIDATION.md)。

ToolDelta 来自工作区使用的 skybluetech/lite 分支，并独立打包在 `radium_scripts/tooldelta` 下，来源与本地命名空间调整见 [THIRD_PARTY.md](THIRD_PARTY.md)。

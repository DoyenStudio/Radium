# 验证与验收

日期：2026-10-31。版本：1.1.0。

## 当前实际完成

- 通过 minecraft_py 静态审查解析 radium 包内 17 个 Python 文件，0 个解析失败，无 warning/risk；3 条建议仅涉及既有形式的函数参数数量。不导入、执行或编译项目模块。
- 解析两个 manifest JSON，确认 4 个 UUID 唯一，header/module 版本统一为 1.1.0；API_VERSION 与入口版本同步。
- PowerShell 打包成功：103 个归档条目；核对新增 resource.py、自测及两个 manifest，无 Git/Studio 元数据或 Python 字节码缓存。工作区共 98 个 Python 文件，未在系统解释器运行任何项目代码。
- 源码检查动态限额 guard、委托端点与共享身份、精确流体变化及累加、schema 1 恢复边界、schema 2 数量/属性编码。游戏内回归用例已加入，但尚未执行。
- 尝试连接 MCDK 游戏服务端：localhost:19133 无法连接。游戏内测试未运行，下面的用例属于待执行验收，不能视为已通过。
- SkyBlueTech 未接入、未迁移、未修改。现有工作区的用户改动保留。

## 游戏内自测

先导入/启用 radium，使用游戏内 Python 2.7.13 服务端控制台或 MCDK execute_code 执行：

```python
import mod.server.extraServerApi as serverApi
api = serverApi.GetComponent(serverApi.GetLevelId(), "radium", "transfer")
assert api is not None
assert api.API_VERSION >= (1, 1, 0)
_result = api.run_self_tests()
```

预期 `ok=True`、`failed={}`，passed 数量等于 total。自测创建隔离的内存服务和模拟方块查询，不注册实际方块、不改变真实机器、不写世界数据。

共 43 项自测。原 25 项涵盖事务、分配、共享身份、持久化、生命周期和守恒。新增 18 项覆盖：直接替换能源方向/限额、多层视图跟随限额、虚空视图提交后统计、组合/查询能源包装、仅公开协议的自定义能源端点、查询流体分槽身份、保留自定义流体批量路径、禁止外层扩大权限、属性身份规范化与深度脱离、不同属性拒绝混合、视图过滤提交重验、schema 2 数量与属性往返及原生字段类型、schema 1 float32 上溢恢复边界、大储量小变化、跨槽/跨目标累加、实际舍入返回值以及损坏快照拒绝。

## 真实游戏验收（必须另外执行）

| 场景 | 验收标准 | 状态 |
| --- | --- | --- |
| 单独加载 radium | 无 SkyBlueTech 也能获取组件，无客户端脚本错误 | 待运行 |
| 移除前置 | 使用方 GetComponent 返回 None，原有流程可正常启动 | 待运行 |
| 两个不同模组注册 provider | 无需继承 SkyBlueTech；RF/流体按面互通 | 待运行 |
| 普通方块、未加载区块 | query 返回 None，不创建机器或强加载区块 | 待运行 |
| 控制器/IO 多别名 | 同一 Cell 不重复参与分配；无自转移增殖 | 待运行 |
| 模式变更、拆机、区块卸载重载 | 旧 handle 被拒绝，重新 query 后恢复；无残留失效机器 | 待运行 |
| 持久化 | 浮点流体、大于 2^31 的 RF、无限源保存重进后正确恢复 | 待运行 |
| 原生 NBT 检查 | 无 long、inf、混合类型 list；槽位键为字符串 | 待运行 |
| UI/统计 | 同一 owner 一次 changed；失败事务无通知，最终提交才统计 | 待运行 |
| 保存异常 | 内存提交不重放，脏写下 tick 重试，可观察错误日志 | 待运行 |
| 流体 schema 2 | 1000.2 mB 满罐、含大整数/小数/混合列表属性的身份退世界重进后完整恢复 | 待运行 |
| 旧流体快照 | schema 1 满罐 float32 舍入上溢可恢复，真实超量拒绝，后续写 schema 2 | 待运行 |
| 委托端口 | query/组合/自定义端点包装后保留拒收、限额、失效与回调；分槽无身份复制 | 待运行 |
| 有限流体数值边界 | 2**54 mB 储量的小额操作不凭空转移；部分接收、累加失败无残留修改 | 待运行 |

示例宿主适配代码在 examples/third_party_machine.py，需放入测试模组自己的脚本包并由其已验证的机器生命周期调用。该示例不是默认加载的机器定义，不会自动在生产世界里增加方块。

不要用系统 Python 执行自测或编译 .py。打包脚本仅处理文件，不属于运行模组代码。

## ToolDelta 服务端裁剪（2026-11-07）

本次使用包含 radium 1.3.0 开发改动的工作区验收。在游戏服务端 Python 2.7.13 重载行为包后，通过 `GetComponent(levelId, "radium", "transfer")` 取得生产组件，166 项自测全部通过。再次重载后，六个引擎事件仍各有一个监听器，模拟 tick 正常推进。客户端未注册 `radium.TDClient`，也未载入 ToolDelta 客户端模块。

在空测试区放置并移除木桶，收到一次 `BlockRemoveServerEvent`，注册表代数增加 1，随后确认测试区已恢复。游戏内另用独立系统实例连续调用两次 `Destroy`，确认只执行一次收尾 tick 和失效处理，并清空 provider、释放组件引用。裁剪后的归档共 50 个文件，其中 ToolDelta 占 9 个，含来源与许可说明。

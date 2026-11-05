# 来源

## ToolDelta

本库包含一份独立的 ToolDelta 脚本副本，来源为 SkyBlueTech 工作区当前采用的 ToolDeltaMod skybluetech 分支（基于 lite）：

- 上游：https://github.com/SuperScript-PRC/ToolDeltaMod
- 使用的镜像前缀：https://ghfast.top/
- 工作区 gitlink：ee005eb319b74fb9a6b649a9af38ad830cbb7c73
- 原位置：D:/addon/skybluetech/behavior_pack/skybluetech_scripts/tooldelta
- 本地位置：behavior_pack/radium_scripts/tooldelta

复制时不包含 .git、__pycache__。仅把 dropdown.py 中显式指向 skybluetech_scripts 的导入调整为 radium_scripts，使副本独立；SkyBlueTech 原副本没有被修改。当前工作区的许可说明保留在 LICENSE.workspace-source；ToolDelta 副本自身没有单独的 LICENSE 文件，因此该文件只记录工作区提供的许可，不擅自改变上游许可范围。

## 设计参考

参考 D:/addon/jemods 中 NeoForge 26.3.x 的能力 provider、资源 handler 和事务思想（浅克隆 commit 3bb720446f9290c23eaf493a467a3eaaa93efe1b）。本库为网易 Python 2.7 环境重新实现，没有复制 NeoForge Java 源码，也不提供 Java 二进制或 API 兼容性。

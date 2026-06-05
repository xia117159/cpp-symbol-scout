# Godot 符号压测分析

本次压测基于 Godot 项目 `/home/cheng/godotengine/godot-master`，使用 `clangd-18` 和项目根目录下的 `compile_commands.json`。压测覆盖清单见 `benchmarks/godot/symbol_lookup_scenarios.md`，逐项用例见 `benchmarks/godot/godot_symbol_cases.json`，机器可读结果见 `benchmarks/godot/results/godot_symbol_benchmark.jsonl`。

## 覆盖范围

已覆盖 33 个 Godot 典型符号查询用例，场景包括普通类、结构体、嵌套类型、模板类、模板结构体、普通 enum、enum class、枚举成员、命名空间、命名空间函数、自由函数、成员函数实现、重载函数、构造函数、析构函数、运算符重载、虚函数/override、静态成员变量、文件作用域变量、成员字段、constexpr 变量、对象宏、函数宏、多行宏、typedef、using alias 和短名歧义。

其中 25 个为必测语义用例，8 个为边界观察用例。边界观察用例主要用于记录 clangd 对宏、typedef/using、namespace range、字段上下文片段等返回形态的差异。

## 最终结果

- 首次查询语义通过：33/33。
- 首次查询必测通过：25/25。
- 缓存查询语义通过：33/33。
- 首次查询工具耗时：min=1.897ms，p50=6.898ms，max=4024.689ms。
- 缓存查询工具耗时：min=0.002ms，p50=0.003ms，max=0.004ms。

最终逐项明细已写入 `benchmarks/godot/results/godot_symbol_benchmark_summary.md`。

## 性能结论

热 daemon 和缓存命中路径满足 1 秒内返回结果，33 个用例的缓存查询全部低于 1 秒。

冷启动首轮查询中，`Node` 和 `NavigationServer2D` 仍超过 1 秒，原因是 clangd 背景索引和 fallback 文档符号解析在大型项目冷启动时存在初始化成本。该成本不影响后续缓存查询；完成首次命中后，相同查询稳定在毫秒级以下。

## 本次修复

- 函数类符号候选排序增加“实现体优先”，避免 `register_server_types`、`MovieWriter::write_begin` 等查询从 `.cpp` 实现回退到 `.h` 声明。
- fallback 文件名推断支持数字后缀，如 `NavigationServer2D` 推断到 `navigation_server_2d.h`。
- 嵌套类型 fallback 支持限定名各部分共同命中，如 `PhysicsDirectSpaceState3D::RayResult` 优先找到 `physics_server_3d.h` 中的定义。
- document-symbol fallback 不再在没有名称匹配时返回无关符号，避免 `NavigationServer2D` 误返回 `World2D::World2D`。
- class/struct/enum 候选排序降级前置声明，优先返回带 `{ ... }` 类体的定义。

## 剩余边界

- 宏在 clangd 中通常以 `String` 类型返回，片段可能是上下文范围而不是严格宏定义行。
- typedef/using alias 有时会被 clangd 映射为 `Class`，完整片段提取依赖 clangd 返回 range 和本地片段提取器。
- 冷启动首轮查询可能超过 1 秒；高性能目标需要依赖 daemon 常驻、clangd 背景索引预热和工具缓存。

# Godot C++ 符号查询压测场景清单

本清单用于验证 `cpp-symbol-scout` 在大型 C++ 项目中的符号定义/实现定位能力。测试目标不是只证明“能查到某个类”，而是覆盖 C++ 代码实际会遇到的查找场景，并记录当前 clangd/LSP 与源码片段提取的边界。

## 运行前提

- Godot 项目路径：`/home/cheng/godotengine/godot-master`
- Godot 项目存在 `compile_commands.json`
- 本机可用 `clangd-18`
- 使用 daemon 查询路径，重复查询应复用 clangd 进程和工具缓存

## 场景矩阵

| 类别 | 典型问题 | Godot 用例 |
| --- | --- | --- |
| 普通类定义 | 查类名应返回完整 class 定义 | `Node`, `NavigationServer2D` |
| 结构体定义 | 查 struct 应返回完整结构体定义 | `NavMeshGeometryParser2D`, `AudioRBResampler` |
| 嵌套结构体/类型 | 同名短名很多，需要限定作用域 | `PhysicsDirectSpaceState3D::RayResult`, `AudioServer::Bus` |
| 模板类 | 模板参数、模板声明和类体应一起返回 | `Heap`, `SafeNumeric` |
| 模板结构体 | 模板 struct 与调用运算符 | `NoopIndexer` |
| 普通 enum | 命名空间内 enum 和同名 2D/3D enum | `PathfindingAlgorithm`, `NavigationEnums2D::PathfindingAlgorithm` |
| enum class | 强类型枚举 | `InputEventType`, `MouseButton`, `MultiUmaBufferType` |
| 枚举成员 | 查枚举值应定位到枚举成员附近 | `PATHFINDING_ALGORITHM_ASTAR`, `MouseButton::LEFT`, `CACHE_MODE_IGNORE` |
| 命名空间 | 命名空间本体和内部常量 | `NavigationEnums2D`, `NavigationDefaults2D`, `Math` |
| 命名空间函数 | 带 namespace 的函数 | `Math::sin`, `mouse_button_to_mask` |
| 自由函数 | 全局函数声明/实现 | `register_server_types` |
| 成员函数实现 | 类方法实现定位 | `MovieWriter::write_begin`, `NavigationPathQueryParameters2D::get_pathfinding_algorithm` |
| 成员函数重载 | 同一方法名多个类/签名 | `write_begin`, `create`, `StringName::operator==` |
| 构造函数 | 构造函数实现定位 | `EditorLog::EditorLog` |
| 析构函数 | 析构函数实现定位 | `EditorLog::~EditorLog` |
| 运算符重载 | `operator==`、位运算符、函数对象 `operator()` | `StringName::operator==`, `operator==`, `MouseButtonMask::operator|` |
| 虚函数/override | 基类虚函数可能解析到派生实现 | `NavigationServer2D::source_geometry_parser_create` |
| 静态成员变量 | 类静态成员定义 | `NavigationServer2DManager::setting_property_name`, `AudioServer::singleton` |
| 文件作用域变量 | `static` 或全局变量定义 | `navigation_server_2d`, `locale_renames` |
| 成员字段 | 类字段定义和类型 | `debug_navigation_avoidance_enable_obstacles_static` |
| `constexpr` 变量 | 命名空间内编译期常量 | `NavigationDefaults2D::NAV_MESH_CELL_SIZE` |
| 宏定义 | 对象宏和函数宏 | `UNIQUE_NODE_PREFIX`, `SNAME`, `SAFE_NUMERIC_TYPE_PUN_GUARANTEES`, `PROCESS_ALLPASS` |
| typedef | 别名定义 | `Size2`, `WindowID`, `PhysicsServer3DExtensionRayResult` |
| using alias | 别名定义 | `CharString`, `RDG` |
| 作用域歧义 | 同名短名需要返回多个候选或用限定名收敛 | `Node`, `FileSortOption`, `RayResult`, `create` |

## 验收维度

每个用例记录以下信息：

- 是否返回至少一个结果；
- 第一个结果的 `kind_name` 是否符合预期；
- 第一个结果路径是否匹配预期文件片段；
- `full_name` 是否包含期望字符串；
- 源码片段是否包含期望 token；
- 首次查询耗时是否在 1 秒内；
- 重复查询耗时是否在 1 秒内；
- 是否出现当前工具已知薄弱点。

## 当前预期边界

- clangd 可通过 `workspace/symbol` 返回多数宏，但宏的 LSP kind 通常是 `String`，源码片段可能退化为上下文片段。
- typedef/using alias 在 clangd 中可能被映射为 `Class`，当前片段提取器对 alias 的完整行提取不稳定。
- namespace 的 LSP range 可能不覆盖完整 namespace body，当前片段可能只返回附近上下文。
- 未限定的重载或短名查询会返回多个候选，不能保证第一个结果就是用户期望的具体重载。
- 基类虚函数在开启 implementation 解析时可能跳到派生类 override；需要用 `--no-implementation` 对照确认基类本体位置。

# Godot 符号查询压测结果

- 项目：`/home/cheng/godotengine/godot-master`
- 用例文件：`/home/cheng/workspace/cpp-symbol-scout/benchmarks/godot/godot_symbol_cases.json`
- clangd：`/usr/lib/llvm-18/bin/clangd`
- compile_commands_dir：`/home/cheng/godotengine/godot-master`
- daemon：`127.0.0.1:55490`

## 总览

- 首次查询通过：33/33
- 首次查询必测通过：25/25
- 缓存查询通过：33/33
- 首次查询耗时：min=1.897, p50=6.898, max=4024.689
- 缓存查询耗时：min=0.002, p50=0.003, max=0.004

## 首次查询明细

| ID | 类别 | 符号 | 通过 | 结果 | 工具耗时(ms) | 位置 | 首行 |
| --- | --- | --- | --- | --- | ---: | --- | --- |
| class_node | 普通类定义 | `Node` | 是 | Class Node | 4024.689 | `scene/main/node.h:54` | class Node : public Object { |
| class_navigation_server_2d | 普通类定义 | `NavigationServer2D` | 是 | Class NavigationServer2D | 4015.444 | `servers/navigation_2d/navigation_server_2d.h:50` | class NavigationServer2D : public Object { |
| struct_navmesh_geometry_parser_2d | 结构体定义 | `NavMeshGeometryParser2D` | 是 | Class NavMeshGeometryParser2D | 4.596 | `servers/navigation_2d/navigation_server_2d.h:45` | struct NavMeshGeometryParser2D { |
| nested_struct_ray_result | 嵌套结构体/类型 | `PhysicsDirectSpaceState3D::RayResult` | 是 | Class PhysicsDirectSpaceState3D::RayResult | 6.898 | `servers/physics_3d/physics_server_3d.h:155` | struct RayResult { |
| template_class_heap | 模板类 | `Heap` | 是 | Class Heap | 108.645 | `servers/nav_heap.h:46` | template <typename T, typename LessThan = Comparator<T>, typename Indexer = NoopIndexer<T>> |
| template_class_safe_numeric | 模板类 | `SafeNumeric` | 是 | Class SafeNumeric | 8.971 | `core/templates/safe_refcount.h:62` | template <typename T> |
| template_struct_noop_indexer | 模板结构体 | `NoopIndexer` | 是 | Class NoopIndexer | 2.141 | `servers/nav_heap.h:38` | template <typename T> |
| enum_pathfinding_algorithm | 普通 enum | `NavigationEnums2D::PathfindingAlgorithm` | 是 | Enum NavigationEnums2D::PathfindingAlgorithm | 2.984 | `servers/navigation_2d/navigation_constants_2d.h:35` | enum PathfindingAlgorithm { |
| enum_class_input_event_type | enum class | `InputEventType` | 是 | Enum InputEventType | 2.101 | `core/input/input_enums.h:35` | enum class InputEventType { |
| enum_class_multi_uma_buffer_type | enum class | `MultiUmaBufferType` | 是 | Enum MultiUmaBufferType | 3.162 | `servers/rendering/multi_uma_buffer.h:114` | enum class MultiUmaBufferType : uint8_t { |
| enum_member_pathfinding_astar | 枚举成员 | `PATHFINDING_ALGORITHM_ASTAR` | 是 | Enum NavigationEnums2D::PATHFINDING_ALGORITHM_ASTAR | 3.558 | `servers/navigation_2d/navigation_constants_2d.h:36` | #pragma once |
| namespace_navigation_enums | 命名空间 | `NavigationEnums2D` | 是 | Namespace NavigationEnums2D | 1.897 | `servers/navigation_2d/navigation_constants_2d.h:33` | /* SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.                 */ |
| namespace_function_math_sin | 命名空间函数 | `Math::sin` | 是 | Function Math::sin | 54.044 | `core/math/math_funcs.h:44` | _ALWAYS_INLINE_ float sin(float p_x) { |
| inline_free_function_mouse_button_to_mask | 命名空间/自由函数 | `mouse_button_to_mask` | 是 | Function mouse_button_to_mask | 4.834 | `core/input/input_enums.h:156` | inline MouseButtonMask mouse_button_to_mask(MouseButton button) { |
| global_function_register_server_types | 自由函数 | `register_server_types` | 是 | Function register_server_types | 17.631 | `servers/register_server_types.cpp:146` | void register_server_types() { |
| method_movie_writer_write_begin | 成员函数实现 | `MovieWriter::write_begin` | 是 | Method MovieWriter::write_begin | 6.345 | `servers/movie_writer/movie_writer.cpp:72` | Error MovieWriter::write_begin(const Size2i &p_movie_size, uint32_t p_fps, const String &p_base_path) { |
| method_const_get_pathfinding_algorithm | const 成员函数 | `NavigationPathQueryParameters2D::get_pathfinding_algorithm` | 是 | Method NavigationPathQueryParameters2D::get_pathfinding_algorithm | 5.67 | `servers/navigation_2d/navigation_path_query_parameters_2d.cpp:40` | NavigationPathQueryParameters2D::PathfindingAlgorithm NavigationPathQueryParameters2D::get_pathfinding_algorithm() const { |
| overload_write_begin | 成员函数重载 | `write_begin` | 是 | Method MovieWriter::write_begin | 20.868 | `servers/movie_writer/movie_writer.cpp:72` | Error MovieWriter::write_begin(const Size2i &p_movie_size, uint32_t p_fps, const String &p_base_path) { |
| constructor_editor_log | 构造函数 | `EditorLog::EditorLog` | 是 | Constructor EditorLog::EditorLog | 35.504 | `editor/editor_log.cpp:487` | EditorLog::EditorLog() { |
| destructor_editor_log | 析构函数 | `EditorLog::~EditorLog` | 是 | Constructor EditorLog::~EditorLog | 21.865 | `editor/editor_log.cpp:597` | EditorLog::~EditorLog() { |
| operator_string_name_equals | 运算符重载 | `StringName::operator==` | 是 | Method StringName::operator== | 23.86 | `core/string/string_name.cpp:148` | bool StringName::operator==(const char *p_name) const { |
| virtual_base_method_no_implementation | 虚函数/override 对照 | `NavigationServer2D::source_geometry_parser_create` | 是 | Method NavigationServer2D::source_geometry_parser_create | 24.464 | `servers/navigation_2d/navigation_server_2d.cpp:281` | RID NavigationServer2D::source_geometry_parser_create() { |
| static_member_setting_property_name | 静态成员变量 | `NavigationServer2DManager::setting_property_name` | 是 | Property NavigationServer2DManager::setting_property_name | 6.547 | `servers/navigation_2d/navigation_server_2d.cpp:585` | navigation_server_2d->finish(); |
| file_scope_variable_navigation_server_2d | 文件作用域变量 | `navigation_server_2d` | 是 | Variable navigation_server_2d | 5.991 | `servers/navigation_2d/navigation_server_2d.cpp:554` | } |
| static_array_locale_renames | 文件作用域数组变量 | `locale_renames` | 是 | Variable locale_renames | 7.031 | `core/string/locales.h:40` | // identifiers, we override them. |
| member_field_debug_flag | 成员字段 | `debug_navigation_avoidance_enable_obstacles_static` | 是 | Field NavigationServer2D::debug_navigation_avoidance_enable_obstacles_static | 95.759 | `servers/navigation_2d/navigation_server_2d.h:357` | bool debug_navigation_enable_link_connections = true; |
| constexpr_namespace_variable | constexpr 变量 | `NavigationDefaults2D::NAV_MESH_CELL_SIZE` | 是 | Variable NavigationDefaults2D::NAV_MESH_CELL_SIZE | 3.737 | `servers/navigation_2d/navigation_constants_2d.h:65` | namespace NavigationDefaults2D { |
| macro_unique_node_prefix | 宏定义 | `UNIQUE_NODE_PREFIX` | 是 | String UNIQUE_NODE_PREFIX | 2.492 | `core/string/string_name.h:36` | #pragma once |
| macro_sname_function_like | 函数宏 | `SNAME` | 是 | String SNAME | 367.935 | `core/string/string_name.h:212` | * - Comparisons to a StringName in overridden _set and _get methods. |
| macro_safe_numeric_type_pun | 多行函数宏 | `SAFE_NUMERIC_TYPE_PUN_GUARANTEES` | 是 | String SAFE_NUMERIC_TYPE_PUN_GUARANTEES | 2.407 | `core/templates/safe_refcount.h:53` | //   flexible. There's negligible waste in having release semantics for the initial |
| typedef_size2 | typedef alias | `Size2` | 是 | Class Size2 | 292.003 | `core/math/vector2.h:348` | constexpr Vector2 operator*(int64_t p_scalar, const Vector2 &p_vec) { |
| using_char_string | using alias | `CharString` | 是 | Class CharString | 77.885 | `core/string/ustring.h:257` | }; |
| ambiguous_short_name_file_sort_option | 作用域歧义 | `FileSortOption` | 是 | Enum FileSortOption | 4.369 | `editor/file_system/file_info.h:36` | enum class FileSortOption { |

## 缓存查询明细

| ID | 类别 | 符号 | 通过 | 结果 | 工具耗时(ms) | 位置 | 首行 |
| --- | --- | --- | --- | --- | ---: | --- | --- |
| class_node | 普通类定义 | `Node` | 是 | Class Node | 0.003 | `scene/main/node.h:54` | class Node : public Object { |
| class_navigation_server_2d | 普通类定义 | `NavigationServer2D` | 是 | Class NavigationServer2D | 0.004 | `servers/navigation_2d/navigation_server_2d.h:50` | class NavigationServer2D : public Object { |
| struct_navmesh_geometry_parser_2d | 结构体定义 | `NavMeshGeometryParser2D` | 是 | Class NavMeshGeometryParser2D | 0.003 | `servers/navigation_2d/navigation_server_2d.h:45` | struct NavMeshGeometryParser2D { |
| nested_struct_ray_result | 嵌套结构体/类型 | `PhysicsDirectSpaceState3D::RayResult` | 是 | Class PhysicsDirectSpaceState3D::RayResult | 0.003 | `servers/physics_3d/physics_server_3d.h:155` | struct RayResult { |
| template_class_heap | 模板类 | `Heap` | 是 | Class Heap | 0.003 | `servers/nav_heap.h:46` | template <typename T, typename LessThan = Comparator<T>, typename Indexer = NoopIndexer<T>> |
| template_class_safe_numeric | 模板类 | `SafeNumeric` | 是 | Class SafeNumeric | 0.003 | `core/templates/safe_refcount.h:62` | template <typename T> |
| template_struct_noop_indexer | 模板结构体 | `NoopIndexer` | 是 | Class NoopIndexer | 0.003 | `servers/nav_heap.h:38` | template <typename T> |
| enum_pathfinding_algorithm | 普通 enum | `NavigationEnums2D::PathfindingAlgorithm` | 是 | Enum NavigationEnums2D::PathfindingAlgorithm | 0.002 | `servers/navigation_2d/navigation_constants_2d.h:35` | enum PathfindingAlgorithm { |
| enum_class_input_event_type | enum class | `InputEventType` | 是 | Enum InputEventType | 0.002 | `core/input/input_enums.h:35` | enum class InputEventType { |
| enum_class_multi_uma_buffer_type | enum class | `MultiUmaBufferType` | 是 | Enum MultiUmaBufferType | 0.002 | `servers/rendering/multi_uma_buffer.h:114` | enum class MultiUmaBufferType : uint8_t { |
| enum_member_pathfinding_astar | 枚举成员 | `PATHFINDING_ALGORITHM_ASTAR` | 是 | Enum NavigationEnums2D::PATHFINDING_ALGORITHM_ASTAR | 0.002 | `servers/navigation_2d/navigation_constants_2d.h:36` | #pragma once |
| namespace_navigation_enums | 命名空间 | `NavigationEnums2D` | 是 | Namespace NavigationEnums2D | 0.003 | `servers/navigation_2d/navigation_constants_2d.h:33` | /* SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.                 */ |
| namespace_function_math_sin | 命名空间函数 | `Math::sin` | 是 | Function Math::sin | 0.002 | `core/math/math_funcs.h:44` | _ALWAYS_INLINE_ float sin(float p_x) { |
| inline_free_function_mouse_button_to_mask | 命名空间/自由函数 | `mouse_button_to_mask` | 是 | Function mouse_button_to_mask | 0.002 | `core/input/input_enums.h:156` | inline MouseButtonMask mouse_button_to_mask(MouseButton button) { |
| global_function_register_server_types | 自由函数 | `register_server_types` | 是 | Function register_server_types | 0.003 | `servers/register_server_types.cpp:146` | void register_server_types() { |
| method_movie_writer_write_begin | 成员函数实现 | `MovieWriter::write_begin` | 是 | Method MovieWriter::write_begin | 0.002 | `servers/movie_writer/movie_writer.cpp:72` | Error MovieWriter::write_begin(const Size2i &p_movie_size, uint32_t p_fps, const String &p_base_path) { |
| method_const_get_pathfinding_algorithm | const 成员函数 | `NavigationPathQueryParameters2D::get_pathfinding_algorithm` | 是 | Method NavigationPathQueryParameters2D::get_pathfinding_algorithm | 0.003 | `servers/navigation_2d/navigation_path_query_parameters_2d.cpp:40` | NavigationPathQueryParameters2D::PathfindingAlgorithm NavigationPathQueryParameters2D::get_pathfinding_algorithm() const { |
| overload_write_begin | 成员函数重载 | `write_begin` | 是 | Method MovieWriter::write_begin | 0.003 | `servers/movie_writer/movie_writer.cpp:72` | Error MovieWriter::write_begin(const Size2i &p_movie_size, uint32_t p_fps, const String &p_base_path) { |
| constructor_editor_log | 构造函数 | `EditorLog::EditorLog` | 是 | Constructor EditorLog::EditorLog | 0.002 | `editor/editor_log.cpp:487` | EditorLog::EditorLog() { |
| destructor_editor_log | 析构函数 | `EditorLog::~EditorLog` | 是 | Constructor EditorLog::~EditorLog | 0.003 | `editor/editor_log.cpp:597` | EditorLog::~EditorLog() { |
| operator_string_name_equals | 运算符重载 | `StringName::operator==` | 是 | Method StringName::operator== | 0.003 | `core/string/string_name.cpp:148` | bool StringName::operator==(const char *p_name) const { |
| virtual_base_method_no_implementation | 虚函数/override 对照 | `NavigationServer2D::source_geometry_parser_create` | 是 | Method NavigationServer2D::source_geometry_parser_create | 0.003 | `servers/navigation_2d/navigation_server_2d.cpp:281` | RID NavigationServer2D::source_geometry_parser_create() { |
| static_member_setting_property_name | 静态成员变量 | `NavigationServer2DManager::setting_property_name` | 是 | Property NavigationServer2DManager::setting_property_name | 0.003 | `servers/navigation_2d/navigation_server_2d.cpp:585` | navigation_server_2d->finish(); |
| file_scope_variable_navigation_server_2d | 文件作用域变量 | `navigation_server_2d` | 是 | Variable navigation_server_2d | 0.003 | `servers/navigation_2d/navigation_server_2d.cpp:554` | } |
| static_array_locale_renames | 文件作用域数组变量 | `locale_renames` | 是 | Variable locale_renames | 0.002 | `core/string/locales.h:40` | // identifiers, we override them. |
| member_field_debug_flag | 成员字段 | `debug_navigation_avoidance_enable_obstacles_static` | 是 | Field NavigationServer2D::debug_navigation_avoidance_enable_obstacles_static | 0.002 | `servers/navigation_2d/navigation_server_2d.h:357` | bool debug_navigation_enable_link_connections = true; |
| constexpr_namespace_variable | constexpr 变量 | `NavigationDefaults2D::NAV_MESH_CELL_SIZE` | 是 | Variable NavigationDefaults2D::NAV_MESH_CELL_SIZE | 0.003 | `servers/navigation_2d/navigation_constants_2d.h:65` | namespace NavigationDefaults2D { |
| macro_unique_node_prefix | 宏定义 | `UNIQUE_NODE_PREFIX` | 是 | String UNIQUE_NODE_PREFIX | 0.002 | `core/string/string_name.h:36` | #pragma once |
| macro_sname_function_like | 函数宏 | `SNAME` | 是 | String SNAME | 0.002 | `core/string/string_name.h:212` | * - Comparisons to a StringName in overridden _set and _get methods. |
| macro_safe_numeric_type_pun | 多行函数宏 | `SAFE_NUMERIC_TYPE_PUN_GUARANTEES` | 是 | String SAFE_NUMERIC_TYPE_PUN_GUARANTEES | 0.003 | `core/templates/safe_refcount.h:53` | //   flexible. There's negligible waste in having release semantics for the initial |
| typedef_size2 | typedef alias | `Size2` | 是 | Class Size2 | 0.003 | `core/math/vector2.h:348` | constexpr Vector2 operator*(int64_t p_scalar, const Vector2 &p_vec) { |
| using_char_string | using alias | `CharString` | 是 | Class CharString | 0.003 | `core/string/ustring.h:257` | }; |
| ambiguous_short_name_file_sort_option | 作用域歧义 | `FileSortOption` | 是 | Enum FileSortOption | 0.003 | `editor/file_system/file_info.h:36` | enum class FileSortOption { |

## 首次查询失败或薄弱项

无。

## 1 秒性能检查

- 首次查询超过 1 秒：2 个
- 缓存查询超过 1 秒：0 个
- 首次慢查询：`Node`, `NavigationServer2D`

## 说明

- “通过”只统计语义校验，不把 1 秒耗时作为硬性通过条件；耗时单独在性能检查中记录。
- `required=false` 的用例用于记录宏、typedef/using、namespace、字段等当前实现的边界。
- `tool_elapsed_ms` 来自 daemon 返回的结果；`command_elapsed_ms` 包含 CLI 进程启动和 JSON 输出成本。

# Godot 测试报告

测试项目：`/home/cheng/godotengine/godot-master`

clangd：`/usr/bin/clangd-18`

## 测试场景

### 成员函数引用

命令：

```bash
PYTHONPATH=src python3 -B -m cpp_reference_finder find 'Node::get_parent' \
  --project /home/cheng/godotengine/godot-master \
  --clangd /usr/bin/clangd-18 \
  --include-declaration -n 8 --timeout 20 --json
```

结果摘要：

- 符号定位到 `scene/main/node.cpp:2100`。
- 返回 7 个语义引用。
- 包含实现位置、`_duplicate` 内 3 个调用点、`_print_orphan_nodes_routine` 内 2 个调用点、`ClassDB::bind_method` 绑定点。

### 精确位置引用

命令：

```bash
PYTHONPATH=src python3 -B -m cpp_reference_finder at scene/main/node.cpp \
  --line 1711 --column 13 \
  --project /home/cheng/godotengine/godot-master \
  --clangd /usr/bin/clangd-18 \
  --include-declaration -n 8 --timeout 20 --json
```

结果摘要：

- 定义跳转到 `scene/main/node.h:525`。
- 返回 4 个语义引用。
- 包含 `Node::add_child` 实现、`node->add_child(dup)`、`parent->add_child(p_node)`、`ClassDB::bind_method`。

## 边界

- 符号名查询先使用 clangd `workspace/symbol`，找不到时使用通用源码定位 fallback。
- 精确位置查询更稳定，推荐在 AI 已有文件和行列信息时优先使用。

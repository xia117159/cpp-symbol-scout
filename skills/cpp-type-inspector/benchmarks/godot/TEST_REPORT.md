# Godot 测试报告

测试项目：`/home/cheng/godotengine/godot-master`

clangd：`/usr/bin/clangd-18`

## 测试场景

### 成员函数返回类型

命令：

```bash
PYTHONPATH=src python3 -B -m cpp_type_inspector find 'Node::get_parent' \
  --project /home/cheng/godotengine/godot-master \
  --clangd /usr/bin/clangd-18 \
  --timeout 20 --json
```

结果摘要：

- 符号定位到 `scene/main/node.cpp:2100`。
- hover 返回 `public: Node *Node::get_parent() const`。
- definition 返回 `scene/main/node.h:548`。
- typeDefinition 返回 `scene/main/node.h:54` 的 `class Node : public Object`。

### 类类型查看

命令：

```bash
PYTHONPATH=src python3 -B -m cpp_type_inspector at scene/main/node.cpp \
  --line 1711 --column 7 \
  --project /home/cheng/godotengine/godot-master \
  --clangd /usr/bin/clangd-18 \
  --timeout 20 --json
```

结果摘要：

- hover 返回 `class Node`，并提示由 `"node.h"` 提供。
- definition/typeDefinition 都指向 `scene/main/node.h:54`。

## 边界

- `at` 精确位置更适合表达式、变量、返回类型和模板类型查询。
- `find` 先使用 clangd `workspace/symbol`，失败时使用通用源码定位 fallback。

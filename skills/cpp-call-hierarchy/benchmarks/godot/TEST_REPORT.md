# Godot 测试报告

测试项目：`/home/cheng/godotengine/godot-master`

clangd：`/usr/bin/clangd-18`

## 测试场景

### 成员函数调用层级

命令：

```bash
PYTHONPATH=src python3 -B -m cpp_call_hierarchy find 'Node::get_parent' \
  --project /home/cheng/godotengine/godot-master \
  --clangd /usr/bin/clangd-18 \
  --incoming --outgoing -n 8 --timeout 20 --json
```

结果摘要：

- 符号定位到 `scene/main/node.cpp:2100`。
- incoming calls 返回 3 组调用方：
  - `_bind_methods` 中的 `ClassDB::bind_method`；
  - `_duplicate` 中的 3 个 `descendant->get_parent()` 调用点；
  - `_print_orphan_nodes_routine` 中的 2 个调用点。
- `clangd-18` 对 `callHierarchy/outgoingCalls` 返回 `method not found`，工具自动降级到 `fallback-static`。

### 成员函数 outgoing fallback

命令：

```bash
PYTHONPATH=src python3 -B -m cpp_call_hierarchy find 'Node::add_child' \
  --project /home/cheng/godotengine/godot-master \
  --clangd /usr/bin/clangd-18 \
  --incoming --outgoing -n 8 --timeout 20 --json
```

结果摘要：

- incoming calls 返回 `_bind_methods`、`_duplicate`、`replace_by` 等调用方。
- outgoing fallback 从函数体中提取 `ERR_FAIL_COND_MSG`、`Thread::is_main_thread`、`EXTRACT_PARAM_OR_FAIL`、`vformat`、`get_name` 等调用 token。
- 已对字符串和注释做 masking，避免把字符串字面量中的 `call_deferred(...)` 当成真实调用项。

## 边界

- incoming calls 使用 clangd call hierarchy。
- outgoing calls 优先使用 clangd；当前环境的 clangd-18 不支持时，使用静态函数体扫描并标记 `outgoing_resolution=fallback-static`。
- fallback-static 是候选调用提取，不等价于完整 C++ 语义调用图。

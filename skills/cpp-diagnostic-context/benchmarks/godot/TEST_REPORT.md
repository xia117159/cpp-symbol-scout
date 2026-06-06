# Godot 测试报告

测试项目：`/home/cheng/godotengine/godot-master`

## 测试场景

使用 Godot 源码路径构造一份 Clang/GCC 风格编译日志：

```text
In file included from scene/main/node.cpp:34:
scene/main/node.h:525:7: note: candidate declaration is here
scene/main/node.cpp:1716:89: error: no member named 'get_missing_name' in 'Node'
scene/main/node.cpp:1717:37: warning: diagnostic context sample warning
```

命令：

```bash
PYTHONPATH=src python3 -B -m cpp_diagnostic_context analyze /tmp/godot-diagnostic-sample.log \
  --project /home/cheng/godotengine/godot-master --json
```

结果摘要：

- 解析出 2 个 primary diagnostics：1 个 error，1 个 warning。
- 解析出 1 个 note，并归属到后续 error。
- error 包含 include stack：`scene/main/node.cpp:34`。
- error 和 warning 都返回了 Godot 源码上下文片段与 caret 位置。

## 边界

- 工具解析 Clang/GCC 风格日志，不运行编译器。
- 源码片段来自 `--project` 下的真实文件；如果日志路径无法映射到本地文件，snippet 为空。

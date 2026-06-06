# cpp-clangd-service

`cpp-clangd-service` 是一个独立的常驻服务进程。它长期持有一个 clangd 进程，为其他 C++ CLI 工具提供语义查询能力，避免每次运行 CLI 都重新启动和初始化 clangd。

该目录不是 SKILL。

## 启动

```bash
cd /home/cheng/workspace/cpp-symbol-scout/services/cpp-clangd-service
PYTHONPATH=src python3 -B -m cpp_clangd_service start \
  --project /path/to/cpp/project \
  --clangd /usr/bin/clangd-18 \
  --wait
```

查看状态：

```bash
PYTHONPATH=src python3 -B -m cpp_clangd_service status --project /path/to/cpp/project
```

停止：

```bash
PYTHONPATH=src python3 -B -m cpp_clangd_service stop --project /path/to/cpp/project
```

## 被哪些 CLI 使用

以下 CLI 默认连接该服务：

- `cpp-symbol-scout`
- `cpp-reference-finder`
- `cpp-call-hierarchy`
- `cpp-type-inspector`

如果服务未启动，这些 CLI 会提示先启动服务。需要临时绕过服务时，在对应 CLI 中传入 `--direct`。

也可以通过 `cpp-symbol-scout start/status/stop` 转发管理同一个服务，便于继续使用符号查询工具的旧命令习惯。

## 性能说明

第一次查询某个大型翻译单元时，clangd 仍可能需要构建 preamble 和加载索引。服务的价值在于这些成本只发生在常驻进程中，后续查询复用同一个 clangd 进程和已打开文件。

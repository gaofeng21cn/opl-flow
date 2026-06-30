## Tool Preferences

- shell 默认用 `rtk` 前缀；检查 `rtk` 本身、包装器输出疑似不完整、用户要求原生命令、复杂 `find`/pathspec/计数/管道时，可用原生命令复核。
- 需要保留原始输出但仍记录 RTK 使用时，使用 `rtk proxy <cmd>`；查看节省情况用 `rtk gain` 或 `rtk gain --history`。
- 更新或核查 RTK 集成时，使用 `command -v rtk`、`rtk --version`、`rtk init --codex --global --show`、`rtk verify`；若 `rtk init` 建议追加 `@~/.codex/RTK.md`，只把新版模板中的稳定命令规则折叠回本节，不直接接受末尾引用。
- 浏览网页时，优先使用 `agent-browser` skill。
- 涉及 PDF、图片、Office、网页内容提取时，优先使用 `mineru-document-extractor` skill，并优先读取 `MINERU_TOKEN`。
- 官方注入块和 marker block 不要删除，除非确认对应工具不再依赖该注入。

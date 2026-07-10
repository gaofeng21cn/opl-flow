## Tool Preferences

- shell 默认用 `rtk` 前缀；检查 `rtk` 本身、包装器输出疑似不完整、用户要求原生命令、复杂 `find`/pathspec/计数/管道、或需要原生交互/精确流输出时，可用原生命令复核。
- 需要保留原始输出但仍记录 RTK 使用时，使用 `rtk proxy <cmd>`；需要完全绕过过滤与记录时，使用 `rtk run -c '<cmd>'`；查看节省情况用 `rtk gain` 或 `rtk gain --history`。
- 更新或核查 RTK 集成时，使用 `command -v rtk`、`rtk --version`、`rtk init -g --codex --show`、`rtk -v init -g --codex --dry-run`、`rtk verify`；`-v` 必须放在 `init` 前；若 `dry-run` 只建议追加 `@~/.codex/RTK.md`，不直接接受末尾引用，只读取 `~/.codex/RTK.md` 并把官方稳定命令规则折叠回本节。
- 需要判断某条原生命令会被官方 hook 如何改写时，用 `rtk rewrite "<cmd>"` 查看 stdout 映射；该命令可在打印映射时返回非零，不能作为通过/失败 gate，也不替代上面的原生命令复核边界。
- 浏览网页时，优先使用 `agent-browser` skill。
- 涉及 PDF、图片、Office、网页内容提取时，优先使用 `mineru-document-extractor` skill，并优先读取 `MINERU_TOKEN`。
- 官方注入块和 marker block 不要删除，除非确认对应工具不再依赖该注入。

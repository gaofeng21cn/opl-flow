# Code Review 模式

Owner: `opl-flow`
Purpose: 按用户需要启用本机 Codex 审查，同时保持原有开发和交付速度
State: `active_contract`
Machine boundary: `contracts/code-review-policy.json`、`scripts/opl_workflow.py`
和 `develop-and-deliver` Skill 定义行为；GitHub、仓库保护规则和实际交付结果仍由
各自 owner 决定。

## 结论

OPL Flow 不把 Pull Request 或第二个 Codex 设为默认门禁。Code Review 是可选的
风险检查层，不能替代实现者已经执行的测试、CI、签名、发布或部署验证。

| 模式 | 普通行为 | 审查不可用或失败 | 适用场景 |
| --- | --- | --- | --- |
| `off` | 不自动启动独立审查 | 不影响交付 | 追求最短路径，或仓库已有充分验证 |
| `async-risk` | 低风险跳过；中高风险异步交给新的本机 Codex 审查 | 记录后继续交付 | 单人开发的推荐增强模式 |
| `required` | 所有风险级别都必须完成审查 | 阻断交付 | 用户明确要求、受监管任务或特殊仓库 |

无论选择哪种模式，OPL Flow 都不会自行要求创建 PR。独立 Codex 可以审查当前
diff、某个 commit 或已有 PR；开发者不需要为了使用 Code Review 改变原来的
交付形式。

## 启用和回读

```bash
python3 scripts/opl_workflow.py review configure --mode async-risk
python3 scripts/opl_workflow.py review status
```

用户配置位于 `~/.config/opl-flow/code-review.json`，以 `0600` 权限原子写入。
OPL Flow 的公共默认值是 `off`，只有用户明确配置后才启用额外行为。

在实现风险已经明确时，可取得机器可读决策：

```bash
python3 scripts/opl_workflow.py review assess --risk medium
```

`async-risk` 下的结果是 `review_action=async` 且
`delivery_blocked=false`：可以启动额外审查，但原开发、测试和交付路径继续前进。
低风险返回 `skip`。用户明确要求或仓库规则要求审查时，返回 `blocking`。

## 与 GitHub、Linear 的边界

- GitHub Actions 继续负责可重复的构建、测试和策略检查。
- GitHub 是否要求 PR、审批或保护分支，完全由仓库自己的规则决定。
- Linear Code & Reviews 用于阅读 PR 和人工决策，不启动 Linear Cloud Coding
  Sessions，也不替代本机 Codex。
- 审查发现的问题按风险进入原任务或后续任务；异步审查本身不制造新的常规门禁。

## 行为变化

启用 `async-risk` 后，仅中高风险改动多一个后台审查机会。低风险工作、直接提交、
现有 CI、发布和部署流程都不增加步骤；审查排队、失败或暂时不可用也不会迫使交付
等待。只有用户、仓库或真实安全/发布要求明确把审查设为必要条件时，才转为阻断。

# GitHub 开源仓库发布边界与流程

## 一、目的

本文件用于约束 `eorld-labs/rell` GitHub 开源仓库的发布边界，避免将内部技术库、研发记录、专利原始文档、商业策略和证据链材料误推到公开仓库。

## 二、仓库边界

### 2.1 内部仓库

内部仓库用于保存完整研发过程和证据链。

当前内部远端：

```text
origin -> git@gitee-eorld:eorld/worldmodels.git
```

内部仓库可以包含：

1. 技术库。
2. 专利原始文档。
3. 研发记录。
4. 商业策略。
5. 证据链文档。
6. Git 提交规范。

### 2.2 GitHub 开源仓库

GitHub 开源仓库只用于发布第一期开源代码和最小 demo。

当前开源远端：

```text
github-open -> git@github-eorld-labs:eorld-labs/rell.git
```

GitHub 开源仓库只允许包含：

1. `README.md`
2. `.gitignore`
3. `schemas/`
4. `demo_runtime/`
5. 后续明确标记为开源的 `examples/`、`docs/`、`evals/`、`adapters/`

GitHub 开源仓库不得包含：

1. `技术库/`
2. `研发记录/`
3. 专利权利要求书、说明书、FTO、检索结论等原始材料。
4. 商业闭环、授权策略、共创方案等内部商业文档。
5. 敏感凭据、客户信息、未公开合作信息。

## 三、发布方式

不得直接从内部仓库执行：

```powershell
git push github-open master
```

正确方式是创建临时发布仓库，只复制开源文件后推送。

流程：

1. 创建临时目录。
2. 只复制开源白名单文件。
3. 在临时目录中初始化 Git。
4. 提交开源内容。
5. 强制推送到 GitHub 开源仓库。
6. 删除临时目录或保留为短期检查目录。

## 四、开源白名单

第一期白名单：

```text
README.md
.gitignore
schemas/
demo_runtime/
```

后续如需加入目录，必须先更新本文件。

## 五、发布前检查

发布前必须检查：

1. 文件列表不包含 `技术库/`。
2. 文件列表不包含 `研发记录/`。
3. 文件列表不包含专利原始文档。
4. 文件列表不包含商业策略文档。
5. 文件列表不包含凭据和令牌。
6. `README.md` 不引用内部文件路径。
7. demo 可运行。
8. JSON schema 可解析。

## 六、当前修正记录

2026-07-02 已将 GitHub 仓库 `eorld-labs/rell` 从内部全量历史强制覆盖为单根开源提交。

当前 GitHub 远端 `master` 指向：

```text
09adbbd 初始化真实世界经验闭环开源骨架
```

当前公开文件仅包括：

```text
.gitignore
README.md
demo_runtime/
schemas/
```

## 七、结论

内部仓库和 GitHub 开源仓库必须长期分离。

内部仓库保存完整研发和专利证据链，GitHub 仓库只发布经过筛选的开源代码与 demo。


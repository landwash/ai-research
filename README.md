# 具身智能研究报告

跟踪具身学术研究、开源项目与数据集、AI 行业重要动态。研究由 Codex 阅读一手来源后完成，Python 脚本负责时间窗口、去重、完整性及持久状态；脚本本身不调用模型或搜索 API。

本仓库与个人知识库 `brain` 独立。调研资料、报告、证据、研究技能与运行记录保存在这里；`brain` 收录用户明确选择、消化后的知识与方法。日常调研完成后不自动向 brain 复制报告或追加项目记忆；需要沉淀时，由用户指定内容，再提炼并保留来源。

首期已生成：[2026-11-19，第 001 期](reports/2026-11-19-130000-72c58c.md)，覆盖 11 月 12 日 13:00 至 11 月 19 日 13:00（北京时间），收录 8 项进展。对应的 [JSON 清单](reports/2026-11-19-130000-72c58c.json) 保存证据定位和筛选记录。

首次覆盖运行截止时间之前七天。后续从上一期 `covered_until` 衔接，并额外向前重查两天以缓解收录延迟。`completed_at` 仅表示落盘完成时间，不作为下一期起点。时间均以带偏移量的 ISO 8601 记录，默认北京时间。

## 手动运行

需要 Python 3.10+，运行脚本只使用标准库。从仓库根目录执行：

```powershell
python scripts/validate-report.py validate
python scripts/validate-report.py begin
```

`begin` 输出本期 ID 和 `drafts/<ID>/manifest.json` 的位置。读取研究技能，在该目录编写 `report.md`、补全清单里的检索记录和条目。然后执行：

```powershell
python scripts/validate-report.py check --draft drafts/<ID>
python scripts/validate-report.py finalize --draft drafts/<ID>
python scripts/validate-report.py validate
python -m unittest discover -s tests -v
```

若 Windows 的 `python` 指向不能启动的 Store 别名，可用已安装的 Python 完整路径运行同一命令。本机本次验证使用 `C:/Users/nirva/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`。

## 文件与提交规则

`reports/<ID>.md` 是阅读报告；同名 `.json` 保存证据定位、检索记录、未收录候选及报告哈希。`state/collected-items.json` 累计已报道事件，`state/checkpoint.json` 记录覆盖时间和报告顺序。研究范围和条目格式位于 `.agents/skills/embodied-research/references/`。`config/sources.yaml` 使用 JSON 兼容的 YAML 语法，可由标准库读取，避免额外运行依赖。

`begin` 的活动记录阻止第二个研究运行进入；单个状态操作另有命令锁。完成时先验证候选状态，再写入恢复日志，依次保存报告、证据清单、累计索引，最后替换检查点。中断后执行 `python scripts/validate-report.py recover`，它只重放已经校验的内容；重复执行不会再次追加事件。普通研究失败时执行 `python scripts/validate-report.py abort --reason "原因"`，保留草稿与失败记录，不改变检查点。若进程被强制终止留下 `.command.lock`，先确认对应进程已退出，再人工删除这个锁文件；不能按文件年龄自动解锁。

校验检查字段、日期、事件重复、引用是否出现在对应正文、哈希、报告与累计状态一致性及窗口连续性。它不证明论文结论正确，也不验证网页现在仍可访问。技术结论仍需要人工阅读原文；搜索覆盖不等于互联网信息全集。

本次验收包括连续两期不重复收录、同工作新事件可追加、失败不推进覆盖时间、提交中断恢复、同日多期和历史报告不被覆盖。测试只操作临时目录。定时执行及 GitHub 推送留待首期质量确认后配置。

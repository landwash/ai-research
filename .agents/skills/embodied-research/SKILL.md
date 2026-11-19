---
name: embodied-research
description: 'Generate a source-grounded embodied AI research digest in ai-research, covering papers, open projects and datasets, and major AI industry developments; maintain evidence, event deduplication and coverage checkpoints for manual or scheduled runs.'
---

# 具身研究简报

在 ai-research 仓库生成中文报告。先读 [研究范围](references/research-scope.md)、[报告与清单格式](references/report-template.md)、`config/sources.yaml` 及两个 `state/*.json`。历史正文按需读取，索引用于去重。

调研产物及项目记录保存在 ai-research。不要在每次收尾时自动写入 brain 的任何树，也不要为此请求权限。只有用户明确指定需要沉淀的内容，才把消化后的结论或方法保存到 brain，并引用原调研；“保存到 ai-research”不触发 brain 归档。

1. 执行 `python scripts/validate-report.py begin`。使用输出的固定 `window` 检索；首次七天，后续从已覆盖时间接续并重查前两天。活动锁存在时先判断旧运行是否仍在进行，不同时启动另一份研究。
2. 三个板块均做检索，固定来源与中英文开放检索结合。保存实际查询、打开的一手 URL、日期、证据定位和失败情况。搜索引擎过滤只能发现线索，逐项核对原始事件日期；后补收录要标明。检索失败不可写成“没有重要进展”。
3. 对候选阅读论文方法与实验，或发布者的仓库、数据卡、公告。只有摘要的条目标明 `abstract`，不补写未见架构或数据。优先选会改变研究判断或工程选择的内容，数量随证据决定；不为凑版面收录窗口外新闻。
4. 按 `work_id + event_id` 去重。arXiv 的 abs/html/pdf 是同一工作；同一论文的不同转载不是新事件。新版本、代码发布、数据发布可另报，说明相对上次的实质变化。对仅改标题或镜像 URL 的候选继续沿用既有标识。
5. 在 `drafts/<ID>/report.md` 写报告，在 `manifest.json` 维护结构化证据。每条用两三段解释问题、机制、证据与局限、实际用途。作者结果与分析推断分开，不把营销评测推广成真实机器人能力；明确开源代码、开放权重、开放数据与受限授权的区别。
6. 执行 `check --draft drafts/<ID>`。核查所有数字的评测条件、发布日期及引用，确认三板块检索已完成，再执行 `finalize --draft drafts/<ID>` 和 `validate`。失败保留草稿，`abort --reason "原因"`；已有提交日志则 `recover`。不要手改检查点、删历史或覆盖旧报告。

报告与索引完成后，回复摘要和报告路径。定时创建、Git 提交/推送及对外发送遵循当次任务授权，不由本技能自动启用。本技能不依赖私人 brain；若参考私人项目背景，只将可公开的一般研究问题写入报告。

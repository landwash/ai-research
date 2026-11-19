# 报告和机器清单

`begin` 生成 `manifest.json`，保留其 `report_id`、`window` 和 `base_checkpoint_sha256`。正文使用以下顺序，三级标题按内容命名，每个条目放一个唯一 HTML 标记。标题服务于阅读；除三个板块外无需机械增加标签。

```markdown
# 具身研究简报 · 日期 · 第 N 期

覆盖区间、检索区间、时区和证据边界。开头给出本期最有价值的判断。

## 具身学术研究

<!-- item:short-slug -->
### 工作名与关键变化

问题、方法机制与必要背景。

实验条件、数字、局限与分析判断。引用直接放在支持的论断旁。

## 开源项目与数据集

条目或者经实际检索后未收录的原因。

## AI 行业重要动态

条目或者经实际检索后未收录的原因。

## 后续跟踪

值得验证的问题及检索覆盖限制。
```

每项 `items` 的必填字段如下。`sources` 是已打开并读过的资料，不含仅在搜索结果看到的链接。`claims` 是简短转述和精确章节/表格定位，不存整篇原文。

```json
{
  "id": "short-slug",
  "work_id": "arxiv:2611.21607",
  "event_id": "v1",
  "section": "research",
  "title": "工作名称",
  "published_at": "2026-11-16",
  "date_source": "https://arxiv.org/abs/2611.21607",
  "change_summary": "相对历史的具体新增内容；首次报道写明首次发布了什么",
  "late_discovery": false,
  "late_reason": "",
  "sources": [
    {
      "url": "https://arxiv.org/abs/2611.21607",
      "accessed_at": "2026-11-19T13:00:00+08:00",
      "kind": "primary",
      "evidence_level": "full_text",
      "claims": [{"claim": "短句转述", "locator": "Section 3; Table 2"}]
    }
  ]
}
```

`published_at` 为带时区时间或 `YYYY-MM-DD`，以源文精度为准。`work_id` 用 `arxiv:<不带版本的ID>`、`github:<小写owner/repo>` 或 `org:<组织/产品>`，`event_id` 为版本或事件标识。来源 URL 自动去掉跟踪参数，arXiv 的不同链接形式合并；仍需要人工识别同一工作的跨站发布。

`sections` 必须包含 `research`、`open_source`、`industry`，各自填写 `status: complete` 和 `note`。这里的 complete 表示本期计划的检索已完成，不代表全网穷尽。任何关键检索仍失败则填写 `partial` 或 `failed`，只保留草稿，不提交覆盖时间。

`search_log` 每项填写 `section`、`query`、`searched_at`、`status`（`ok` 或 `failed`）、`urls`（实际检查的 URL）和 `note`。允许某次检索失败后以另一条成功记录补足，但不能把未执行的查询记为成功。

`excluded` 保存候选的 `title`、`url`、`reason`，例如发布时间在窗口外、无实质变化、只有二手报道或日期冲突。它们不会进入已报道事件索引。校验脚本不会核对文字与外部网页的事实一致性，必须人工完成此项。

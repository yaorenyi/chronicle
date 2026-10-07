# Chronicle

一个自动化的 AI 日报博客：每天自动抓取 [AI HOT](https://aihot.news) 的日报数据，整理成 Hexo 文章并发布到 GitHub Pages。

- **框架**：Hexo 7.3.0
- **主题**：[hexo-theme-async](https://github.com/MaLuns/hexo-theme-async) 1.2.14
- **数据源**：AI HOT 公开日报接口
- **线上地址**：<https://yaorenyi.github.io/chronicle/>

## 日报长什么样

每篇日报按五个固定版块分类，全局连续编号：

1. 模型发布 / 更新
2. 产品发布 / 更新
3. 行业动态
4. 论文研究
5. 技巧与观点

每条包含标题、来源、摘要与原文链接。

## 目录结构

```
chronicle/
├── _config.yml              # Hexo 站点配置
├── _config.async.yml        # 主题配置覆盖
├── package.json
├── sync_daily.py            # 日报抓取 → Markdown 文章
├── source/
│   ├── _posts/              # 生成的日报文章（会被 git 跟踪，实现归档累积）
│   └── img/
├── scripts/                 # 自定义 Hexo 脚本
└── .github/workflows/
    └── daily.yml            # 每日同步 + 构建 + 发布
```

## 本地使用

```bash
# 安装依赖
npm install

# 生成当日日报文章
python sync_daily.py

# 回补最近 7 天历史日报
python sync_daily.py --backfill 7

# 本地预览
hexo clean && hexo generate && hexo server
```

`sync_daily.py` 参数：

| 参数 | 说明 |
| --- | --- |
| `--date YYYY-MM-DD` | 指定日期生成日报，默认当天 |
| `--backfill N` | 回补最近 N 天，已存在的文章会跳过 |
| `--force` | 覆盖已存在的文章 |

脚本只用 Python 标准库，无需 `pip install`。

## 自动发布

`.github/workflows/daily.yml` 每天北京时间 08:20 触发：

1. 拉取仓库（`fetch-depth: 0`，保证归档累积不会丢历史）
2. 运行 `sync_daily.py` 生成当日文章
3. `hexo generate` 构建
4. 上传 Pages artifact
5. 把新文章提交回 `source/_posts/`（归档累积）
6. 发布到 GitHub Pages

也可以手动触发补历史：

- Actions → Daily Sync → Run workflow
- 输入 `date` 生成指定日期，或输入 `backfill` 回补最近 N 天

> 注意：`backfill` 一次处理多天，但受 workflow `concurrency` 限制，逐个日期触发更可靠。

## 常见问题

**页面渲染失败但退出码是 0**
Hexo 渲染失败时不会返回非零退出码，必须检查构建日志里的 `ERROR Render HTML failed`，并确认 `public/index.html` 不是 0 字节。

**主题配置层级写错**
`_config.async.yml` 的键名与层级必须严格对齐主题默认 `_config.yml`。例如 `cdn.js.head` 是三层嵌套，若把 `js` 写成空值，`theme.cdn.js` 会变成 `null`，导致所有页面渲染报 `Cannot read properties of null`。

## 数据来源与免责

内容来自 AI HOT 公开接口，仅做聚合展示，版权归原作者所有。
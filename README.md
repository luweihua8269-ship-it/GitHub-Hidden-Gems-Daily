# GitHub 冷门好物日报

纯 Python 标准库，默认且当前唯一支持的模式为 **零模型推理**。没有 AI SDK、API Key 读取、模型请求、自动生成媒体或 Codex 定时任务。首次开发占用当前 Codex 会话额度；无法为会话底层实际 Tokens 设置硬上限。日常只运行 GitHub Actions 中的 Python。

## 当前交付状态

已完成本地真实 GitHub 采集、规则筛选、Markdown / HTML 日报、JSON 持久化、资源日志与安全测试。
云端部署与真实发信必须在 GitHub 仓库、SMTP Secrets 配置后验收，不能把本地测试视为上线。
查看 `ACCEPTANCE.md` 中的最新核实状态。

## 一条命令运行

Python 3.9 或以上，无需 pip、数据库、Docker 或付费服务。在项目目录执行：

```bash
python3 -m gems.main
```

没有 SMTP 配置时只生成日报，不发送。输出位于 `reports/北京时间日期/`。
同一天再次运行复用已保存日报，不重复搜索。单独步骤：

```bash
python3 -m gems.main prepare
python3 -m gems.main deliver
python3 -m gems.main summary
python3 -m unittest discover -s tests -v
```

`summary` 只更新统计，不查询 GitHub。程序使用本机时间换算 UTC+8；请保证系统时钟正确。

## 云端部署

1. 在自己的 GitHub 账号新建 **公开**仓库 `GitHub-Hidden-Gems-Daily`，默认分支必须为 `main`。公开的只有代码、推荐与资源记录；邮箱、密码不能提交到仓库。
2. 将本目录内容上传到仓库根目录，包括 `.github/workflows/daily.yml`。如果使用 Git CLI：

   ```bash
   git init -b main
   git add .
   git commit -m "Add zero-model daily discovery"
   git remote add origin https://github.com/YOUR_ACCOUNT/GitHub-Hidden-Gems-Daily.git
   git push -u origin main
   ```

3. 在 Settings → Secrets and variables → Actions → **Secrets** 填入：

   | Secret | 含义 |
   |---|---|
   | `SMTP_USER` | 完整发件邮箱 |
   | `SMTP_PASSWORD` | Gmail 应用专用密码 / 126 SMTP 授权码；不是登录密码 |
   | `MAIL_TO` | 一个完整收件邮箱，可与发件邮箱相同 |

4. 在同一页面 **Variables** 填入：

   | Variable | Gmail 值 |
   |---|---|
   | `SMTP_HOST` | `smtp.gmail.com` |
   | `SMTP_PORT` | `465` |
   | `SMTP_FREE_CONFIRMED` | 确认自己的账号允许 SMTP 且没有超额收费后设为 `true` |
   | `DAILY_ENABLED` | 完成 Secrets 与免费条件核对后设为 `true` |

   126 可用同一程序，改用 `smtp.126.com`、端口 `465` 和网易授权码。Gmail 支持端口 `587` + STARTTLS；不允许明文 SMTP。

5. Settings → Actions → General 确认允许工作流运行、`GITHUB_TOKEN` 可写仓库内容。程序需要提交日报和发送状态。分支保护若禁止机器人直接提交，会阻止发送；不能绕过保护规则。
6. 在 Actions 页面选择 **GitHub Hidden Gems Daily → Run workflow → main**，手动运行一次。检查日志、仓库新增的报告、收件箱和垃圾邮件。
7. SMTP 显示 `accepted` 仅表示邮件服务器接受邮件，仍需用户确认到达收件箱。Actions 执行成功也不能证明邮件实际阅读或安装包安全。

Gmail 应用专用密码需要先开启两步验证，某些组织账号、安全密钥专用账号或高级保护账号不支持。生成密码与开启两步验证由账号持有人在 Google 官方页面自行完成。不要把授权码发给 Codex 或写进公开文件。

## 时间、重试与防重复

- 唯一计划时间：UTC 01:00，即北京时间 09:00。Mac 不用开机。
- GitHub Actions 可能排队、延迟甚至丢弃任务，不提供精确到点送达保证。公开仓库长期无活动也可能停用定时任务；成功每日提交可保持活动，但持续失败后仍需检查。
- 不建立第二个轮询或 Codex 后台补发任务。计划任务漏掉时，在当天手动运行一次；已有日报会复用，不重新采集。同日只允许一封 SMTP DATA 尝试；不自动补发历史日期邮件。
- Workflow `concurrency` 串行执行，`cancel-in-progress: false`。本机同时运行有文件锁。本机和 Actions 不可共用两个独立状态副本同时发信；线上只保留 Actions 为唯一发送端。
- GitHub API 临时网络 / 5xx 故障最多自动重试一次，所有失败尝试也计数；403/429 立即停止，不等配额恢复、不换账号。
- SMTP 连接或登录阶段失败，且 API 尚未用掉当天重试时，Workflow 最多重试一次；不重新搜索。每日重试标记持久化，手动多次运行也不能绕过。
- 发送前先保存并推送 `sending` 状态，然后才发 DATA。SMTP 返回成功后保存 `accepted`。任何 DATA 后连接错误记为 `unknown`；进程崩溃可能保留 `sending`。这两种状态均阻止自动重发。
- SMTP 没有通用的幂等接口，无法同时保证绝不重复和绝不漏信。这里优先防重复。若状态为 `sending/unknown`，先查 Gmail 已发送、收件箱，再人工处理；不要直接删状态重发。
- Git 推送失败就不进入 SMTP DATA。发送成功后若最终推送失败，远端保留 `sending`，后续同日阻止重发，需人工核对。

## 免费与配额保护

GitHub 官方文档确认：**公开仓库使用标准 GitHub-hosted runner** 的计算使用量免费；较大 runner 可能收费。这里固定 `ubuntu-latest`，不上传 Actions artifact，不使用 Actions cache，不开通收费服务。

默认 `DAILY_ENABLED` 未配置时整个 job 不启动；仓库改为私有时 job 同样不启动，防止先启动再检查余额造成费用。运行时再核对仓库可见性。此 MVP 不支持私有仓库运行，因为无法通过现有权限可靠获取账号整体免费计算余额，不能假装已实施余额硬限制。

已运行的标准 runner 的平台账单、共享账号其他任务消耗、邮件服务剩余发送额度 **不可获取**，日志明确留空。若未来免费政策改变，应停用工作流并重新检查，程序无法感知未知的计费政策变化。不要将更换付费 runner、购买额外配额作为自动回退。

默认程序每日 REST 预算 50 次：5 组搜索最多 60 个候选，最多 10 次深查，每次最多仓库信息 / Release / 限长 README 三个请求，加上配额与云端可见性检查、最多一次重试，通常不超过 40 次。不下载源码或安装包。GitHub 平台 checkout、Git 传输、Actions 控制面及首次开发工具请求不计入程序 REST 计数，不能将此数称为整个账号全部 API 使用量。

每次请求前原子写入预算计数，中断也保留已预留的次数。达到预算就停止采集，用已核实项目输出部分日报；没有项目则输出简短失败 / 无推荐报告。HTTP 重定向不自动跟随，避免隐藏请求。仓库改名通过不变的 Repository ID 识别，搜索结果和当天已读取文档存入本地并随 Git 提交，同日不重复查询。没有 ETag 跨天缓存；这是按需读取而非重复全库扫描。

邮件本地限制每天 1 封、每月 31 次 DATA 尝试。Google 官方对个人 Gmail 有每日发送限制；该账号的其他发信也会占用限制。本程序遇限额就停止，不切换收费邮件接口。没有 SMTP Key 时不产生邮件服务调用。

## 搜索与规则边界

搜索按日期轮换桌面、照片、跨设备、音视频和生活工具话题，混合按更新时间 / Stars 排序，只读取 5 组有限结果。默认 Stars 20–5000，排除 fork / archived / disabled、明显开发组件和超过 180 天未推送项目。搜索话题覆盖有盲区，无法保证每天都发现创意好物。

深查要求明确的常见开源许可证、可识别使用场景、安装章节、正式 Release 中的应用包、文档平台信息；检测到付费 / API Key / 高风险安装词则送待审核池。许可证检查是 SPDX 规则，不是完整法律审核；关键词规则有误杀和漏检，不是恶意软件检测。未知软件、浏览器扩展、仅网页 Demo 和硬件项目在保守规则下可能被漏掉。

尽量使用正式 Release 对应 tag 的 README，避免把开发分支计划当作已发布功能。对外只写官方描述和证据化模板，不因 AI / GPT 关键词加分。费用、隐私和实际功能没有可验证证据时保留未知，不宣称亲测或安全。

评分维度按 30 / 30 / 20 / 10 / 10 保留。能由规则解释的最高 64 分，其余 36 分标为待编辑确认，不填造精确创意分。自动通过最低分 48。`has_visual_markers` 只说明 README 出现图片 / 视频语法，可能只是徽章，**不能证明截图真实可见**；邮件会保留这个边界，视频潜力待看片。

Repository ID 去重 90 天，fork 排除，近期 7 天同类 / 高词汇相似度抑制，当天不重复类别。类别算法不能可靠识别所有“换壳”和跨语言相似工具。宁可 0–2 个，不凑 3 个。

## 历史、日志与维护

- `data/state.json`：推荐历史、仓库 ID / 名称别名 / 分数依据、每日预算、邮件状态。**不能删除以绕过预算或重发限制**。
- `data/candidates.json`：最近一期初筛快照。
- `reports/YYYY-MM-DD/daily.md` / `daily.html`：正文。
- `reports/YYYY-MM-DD/selection.json`：推荐项目与事实依据。
- `reports/YYYY-MM-DD/review-pool.json`：深查池，包括未通过者；保留风险提示，不代表推荐。
- `reports/YYYY-MM-DD/usage.json`：REST 请求、候选与深查数、模型零调用、程序计时、SMTP 状态、停止原因。
- `reports/YYYY-MM-summary.json`：本系统本月可确认的累计值。Actions job 总时长和最终账单从 Actions UI 查，程序计时不等于计费时长。
- 每次云端运行由同一工作流提交到 `main`；没有依赖可丢失或过期的 Actions cache。首次上传前确保没有 `.env`、真实地址或授权码。
- GitHub 工作流失败后，在 Actions 页面查看红色运行记录及 Job Summary。GitHub 自带失败通知需要在个人 Settings → Notifications 启用；其实际到达情况未自动核实。SMTP 自身故障不能依赖同一路 SMTP 再发故障通知。

停止：把 Repository Variable `DAILY_ENABLED` 改为 `false`，或在 Actions 中 Disable workflow。撤销 Gmail 应用专用密码可同时禁用该发送凭证。

调预算：修改 `config.json`。程序硬限制每日 REST ≤50、候选 ≤60、深查 ≤10、推荐 ≤3；只能降低这些上限，不能用手动重跑突破。调整 Stars、维护日期、同类去重窗口及评分阈值后，手动检查首期结果。`AI_EDITOR_ENABLED=false` 保持关闭。可选 AI 编辑尚未实现；设为 true 会直接报错，不会读取 OpenAI Key、计费或隐式回退。

## 官方依据（开发时核查，政策可能变化）

- [GitHub Actions 计费](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
- [GitHub 定时触发与延迟限制](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [GitHub REST 配额](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)
- [Gmail 应用专用密码与账号限制](https://support.google.com/accounts/answer/185833?hl=zh-Hans)
- [Gmail 发送限制](https://support.google.com/mail/answer/22839?hl=zh-Hans)
- [Google SMTP 协议及端口](https://developers.google.com/workspace/gmail/imap/imap-smtp)

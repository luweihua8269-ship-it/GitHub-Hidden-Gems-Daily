# 首次验收记录

核实日期：2026-10-29 12:07（北京时间）。

**当前状态：2026-10-30 的126真实发信验收通过；用户确认收件且内容正常，每日任务已启用。**

## 2026-10-30 成功验收补充

- 成功运行：https://github.com/luweihua8269-ship-it/GitHub-Hidden-Gems-Daily/actions/runs/40983007181
- 云端15项安全测试、真实采集、准备与发送状态持久化、邮件发送均成功。SMTP结果accepted，阶段completed；用户明确回复“已收到，内容正常”。
- 60个候选、深查10个、推荐2个：sidebandstudio/EternalMonitor、duartebarbosadev/PhotoSort。
- 日常程序GitHub REST请求38次，SMTP尝试1次，没有触发重试，没有超预算。
- LLM调用0、输入与输出Tokens均0、AI API费用0元。首次Codex开发/维护消耗不包含在这些日常程序计数里。
- 邮箱与授权码仅在GitHub Secrets；运行时SMTP_HOST=smtp.126.com、SMTP_PORT=465。
- DAILY_ENABLED=true，工作流已恢复；cron已核对为UTC 01:00，即北京时间09:00。下一次配置触发为2026-10-31 09:00，实际调度可能延迟，下一次自然定时触发尚未发生、未声称已实测。
- 历史与最终accepted状态已从main读回确认，Mac不用开机。Actions完整job在UI显示22秒；平台最终账单和邮件服务剩余额度不可获取。
- 失败通知到达、真实设备安装体验与跨邮件客户端外观未测试；不以SMTP成功代替这些测试。

以下记录保留首次开发及Gmail失败的历史状态；涉及当前上线状态时，以本补充和最新usage.json为准。

|验收项目|结果与证据|
|---|---|
|真实 GitHub 数据|通过；59 个不重复候选，深查 10 个，推荐 1 个|
|首期推荐|nsh07/Tomato，正式 Release v2.0.1 的 README；不声称亲测|
|Markdown 与 HTML|已生成 reports/2026-10-29/daily.md / daily.html|
|GitHub REST 请求计量|程序累计 38 次，包含开发排错时的一次配额查询和正式版 README 的额外核对；预算 50 次|
|开发连接检查|程序外另有一次成功的公开 REST 配额探测；另用连接器查询一次登录账号，连接器后端请求数不可见；未将全账号请求量冒充程序计数|
|零模型模式|LLM 调用 0，输入 Tokens 0，输出 Tokens 0，AI API 费用 0 元；程序未实现模型调用路径|
|Codex 首次开发消耗|本次会话有消耗，精确 Tokens 与订阅扣量不可获取；不把日常零模型等同于首次开发免费|
|历史去重|ID / 仓库改名 / fork / 90天窗口 / 7天同类抑制的测试通过|
|同日真实重跑|通过；再次运行完整命令后 API 计数仍为38，SMTP 尝试仍为0|
|预算与重试|针对性测试通过；最多一次全局重试，429不重试，计数重新加载后仍有效|
|邮件防重发|模拟 SMTP 接受、DATA后断线、远端保存失败的测试通过；不代表真实 Gmail 发信通过|
|测试|14项单元测试通过；并在 GITHUB_ACTIONS=true / PERSIST_STATE=git 环境下复核|
|Actions配置|已写好唯一每天01:00 UTC的计划，等于北京时间09:00；仅公开仓库标准Ubuntu runner，默认尚未启用|
|下一次配置时间|若已部署启用，应为 2026-10-30 09:00 北京时间；当前未实际安排、未触发验证，GitHub可能延迟或漏触发|
|免费条件|已核查官方公开仓库标准runner免费政策；没有缓存/附件存储。账号实际余额、最终账单与邮件剩余额度不可获取|
|真实邮件|未测试；缺少 Gmail 应用专用密码及仓库 Secrets，SMTP尝试0次|
|云端持久化提交|已实现、未在真实Actions测试；需仓库创建与工作流运行后确认|
|失败通知|日志与失败工作流状态已实现；GitHub个人通知开关及实际通知到达尚未测试|

## 已知限制

- 本次选择一个番茄钟，属于实用线索，无法据此保证长期编辑品味或每天都有惊喜型项目。
- 规则分最高64分，另36分待编辑确认；不是客观质量认证。README媒体标记不能代替真实截图检查。
- 开源许可证、安装包、说明和推送时间均来自公开元数据，不代表安装包安全或功能可用。
- 首次排错发现查询参数中的Stars范围被路径校验误拦，已修复并补回归测试；请求保留在累计数内，没有清零重算。
- SMTP无法通用实现端到端exactly-once；不确定时停止重发，需人工核对。
- 私有仓库不启动工作流，避免在无法确认全账号余额时产生费用；未来GitHub免费政策变化需人工重新核查。

## 待完成

最新测试：https://github.com/luweihua8269-ship-it/GitHub-Hidden-Gems-Daily/actions/runs/40842575173 。云端离线测试通过，但SMTP连接在DATA之前断开，错误类型SMTPServerDisconnected；尝试2次后停止，未发送正文。程序REST累计40次、LLM调用0。仅凭现有日志不能判断密码是否正确。每日工作流已显示“This workflow was disabled manually”。本地邮件阶段诊断与CRLF编码修复的15项测试通过，修复和测试已同步仓库；未再次在线连接SMTP，没有清零重试记录。

更新：下面第1、2项已于2026-10-29完成。公开仓库已创建；一次性云端任务校验压缩包、通过14项离线测试并成功推送源码和报告。真实邮件及每日触发仍待验收。部署记录：https://github.com/luweihua8269-ship-it/GitHub-Hidden-Gems-Daily/actions/runs/40840971154

1. 用户在Chrome登录GitHub后创建已授权公开仓库。
2. 推送全部程序与报告，核实工作流存在于main。
3. 用户把SMTP_USER、SMTP_PASSWORD、MAIL_TO填入GitHub Secrets；邮箱不提交公开代码。
4. 设置SMTP_FREE_CONFIRMED、DAILY_ENABLED，执行一次真实云端手动测试。
5. 用户确认收件箱到达；核实Git提交持久化、Actions记录、后续计划状态。

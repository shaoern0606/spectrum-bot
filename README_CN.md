# 🛰️ SpectrumBot - UM SPeCTRUM Telegram 智能助手

> 自动监控马来亚大学 (UM) SPeCTRUM 最新课件（PDF、讲义 Slides）、论坛最新公告、作业与测验截止时间看板与倒计时预警，支持 Telegram 手机一键调取和下载课件。

[📖 English Version](README.md) | [🛠️ 技术架构文档 (TECHNICAL.md)](TECHNICAL.md)

---

## 🛡️ 安全与隐私说明

SpectrumBot 使用 Playwright 通过官方浏览器认证流程与马大 SPeCTRUM 系统进行交互。

- **密码安全**：你的 SiswaMail 账号密码始终直接在官方弹出的微软登录页面中输入，绝对不要在 Telegram、非官方表单或配置文件中填写明文密码。程序本身不会记录、拦截或存储你的明文密码。
- **登录凭证 (`auth_state.json`)**：完成登录后，浏览器 Cookie 与会话令牌会保存在本地的 `auth_state.json` 文件中。该文件用于免去每次重复登录的繁琐步骤。**请像对待密码一样保护 `auth_state.json`，严禁外传或提交到公开仓库。**
- **Telegram 通信**：程序直接与 Telegram 官方 Bot API 通信，用于发送提醒通知和传输文件。
- **本地运行**：程序完全跑在你自己的电脑本地，没有任何外部第三方中转服务器。

**安全注意事项**：
- 切勿公开分享或泄露你的 `.env` 或 `auth_state.json` 文件。
- 在输入大学账号前，建议审查开源代码以保安心。
- 分享课程资料请严格遵守马来亚大学的相关学术规范。

---

## ✨ 功能特性

| 分类 | 功能描述 |
| :--- | :--- |
| 📚 **课程监控** | 自动抓取已选课程中的最新讲义、Slides、PDF 文件及文件夹资源。 |
| 📢 **论坛与新公告** | 即时推送讲师发布的新公告与论坛主题（智能过滤往年遗留的陈旧帖子）。 |
| 📝 **作业与测验截止看板** | 汇总追踪作业与测验截止时间，并在截止前 **48小时** 与 **24小时** 自动发送倒计时预警。 |
| 🔍 **资源访问与调取** | 支持课件标题检索 (`/search <关键词>`)、按周次章节浏览资料 (`📚 My Courses`) 以及手机一键下载课件 (`[📥 Send File Here]`)。 |
| 👥 **Telegram 交互** | 提供常驻控制键盘、常用指令支持，以及针对新增订阅者的管理员审核批准机制。 |
| ⚙️ **自动化调度** | 默认每 30 分钟进行一次静默检查（无新文件时不打扰，拒绝消息刷屏）。 |

---

## 🎮 Telegram 常用指令与按钮

| 命令 / 按钮 | 类型 | 功能说明 |
| :--- | :--- | :--- |
| **`/start`** | 命令 | 启动机器人并显示交互式控制菜单 |
| **`📝 Deadlines`** (或 `/deadlines`) | 按钮 / 命令 | 查看作业与测验看板（已逾期、48h 内紧急、未来作业、已提交） |
| **`🔍 Check Now`** | 按钮 | 立即强制执行一次全科目更新扫描 |
| **`📚 My Courses`** (或 `/courses`) | 按钮 / 命令 | 按科目与周次章节浏览往期课件并随时下载 |
| **`/search <关键词>`** | 命令 | 按标题搜索已收录的课件（例如 `/search lecture 1`） |
| **`⚙️ Status`** (或 `/status`) | 按钮 / 命令 | 查看当前会话状态、数据库统计与下次检查倒计时 |
| **`/login`** | 命令 | 显示重新登录认证指令指引 |
| **`❓ Help`** (或 `/help`) | 按钮 / 命令 | 查看操作指引与所有可用命令 |

---

## 🛠️ 极速上手安装指南

### 1. 环境准备与依赖安装

#### 运行环境需求：
- **Python 3.10 或更高版本**：
  - **🪟 Windows 用户**：前往 [python.org](https://www.python.org/downloads/) 下载安装。**重要提醒**：在安装首屏务必勾选 **☑️ "Add python.exe to PATH"**。
    - *自测方法*：按 `Win + R` 键输入 `cmd` 回车，输入 `python --version`。若找不到，重新打开安装包选择 **Modify** 补勾环境变量。
  - **🍎 macOS 用户**：推荐通过 Homebrew 安装 `brew install python@3.11` 或从官网下载安装。

#### 运行一键配置脚本：
- **🪟 Windows**: 双击运行 `setup.bat`（或在命令行输入 `setup.bat`）。
- **🍎 macOS**: 打开终端运行：`chmod +x setup.sh && ./setup.sh`。

*(脚本会自动创建虚拟环境 `.venv`、安装 Python 依赖库，并下载 Playwright Chromium 浏览器引擎)*。

> **🔍 怎么确认这步做对了？**：终端末尾输出 `Setup complete!`，且根目录下生成了 `.venv` 文件夹。

---

### 2. 配置 Telegram 机器人与 `.env`

1. **申请机器人 Token**：
   - 打开 Telegram 搜索 **`@BotFather`**，发送 `/newbot`。
   - 按提示设置名称与用户名（以 `bot` 结尾），复制生成的 `HTTP API Token`。
2. **生成 `.env` 配置文件**：
   - 复制模板文件：
     - **Windows (命令行)**: `copy .env.example .env`
     - **macOS / Linux**: `cp .env.example .env`
   - 用文本编辑器打开 `.env`，填入刚刚获取的 Token：
     ```env
     TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
     ```
3. **在 Telegram 激活机器人**：
   - 在 Telegram 搜索找到你的机器人，点击底部的 **Start**（或发送任意消息如 `hi`）。
4. **自动捕获 Chat ID**：
   - 运行自动捕获命令：
     - **Windows**: `.venv\Scripts\python main.py --get-chat-id`
     - **macOS**: `./.venv/bin/python main.py --get-chat-id`
   - 程序会自动读取你发出的 `/start` 消息并将 `TELEGRAM_CHAT_ID` 写入 `.env`。
5. **测试连通性**：
   - **Windows**: `.venv\Scripts\python main.py --test-tg`
   - **macOS**: `./.venv/bin/python main.py --test-tg`

> **🔍 怎么确认这步做对了？**：手机 Telegram 收到了一条带有交互控制键盘的欢迎卡片消息！

*(可选进阶：默认会自动监控 SPeCTRUM 上的全部科目。若只想监控特定课程，可随时在 `.env` 中指定 `MONITORED_COURSES=WIA2001,WIA2006`)*。

---

### 3. 首次 SPeCTRUM 认证登录

在电脑上运行一次官方浏览器登录向导：

- **Windows**: `.venv\Scripts\python main.py --login`
- **macOS**: `./.venv/bin/python main.py --login`

1. 电脑会自动弹出一个 Chromium 浏览器窗口，显示马大 SPeCTRUM 微软单点登录页面。
2. 输入你的 SiswaMail 账号密码，并在手机 Microsoft Authenticator 上确认批准 2FA。
3. 登录成功跳转至 SPeCTRUM 仪表盘后，程序会自动保存登录凭据至 `auth_state.json` 并关闭浏览器。

> **🔍 怎么确认这步做对了？**：终端显示 `[OK] Authentication state saved to auth_state.json`。

---

### 4. 运行服务与开机自启

#### 🪟 Windows 用户：
- **开启开机自启（推荐）**：双击运行 **`enable_autostart_windows.bat`**。  
  会在启动目录创建快捷方式，每次开机后使用 `pythonw.exe` 默默在后台运行（无黑框命令行）。
  - 停止后台服务：双击 `stop_background.bat`。
  - 取消开机自启：双击 `disable_autostart_windows.bat`。
  - 查看实时日志：打开 `spectrumbot.log`，或在 PowerShell 运行 `Get-Content -Wait spectrumbot.log`。
  - 前台调试窗口：双击 `run_watch.bat`。

#### 🍎 macOS 用户：
- **开启开机自启（推荐）**：在终端运行：
  ```bash
  ./start_background.sh
  ```
  注册为系统级原生 LaunchAgent 守护进程 (`com.um.spectrumbot.plist`)，登录系统后自动常驻，关闭终端或 VS Code 均不影响。
  - 停止后台服务：运行 `./stop_background.sh`。
  - 查看实时日志：终端运行 `tail -f spectrumbot.log`。
  - 前台调试窗口：终端运行 `bash run_watch.sh`（或 `./.venv/bin/python main.py --watch`）。

> **🔍 怎么确认这步做对了？**：在手机 Telegram 点击 **`⚙️ Status`** 或 **`📝 Deadlines`**，机器人能在数秒内回复即说明后台服务正在稳定运行！

---

## 👥 邀请好友订阅

你可以将你的 Telegram 机器人用户名分享给同学：

- **订阅机制**：新同学打开机器人发送 `/start` 后，若开启了审核机制，管理员手机会收到一条带按钮的提示卡片 (`[✅ Approve] / [❌ Deny]`)，点击批准即可放行。
- **关于共享账号的重要说明**：SpectrumBot 统一使用配置好的单个 SPeCTRUM 主机账号抓取资料。订阅者接收到的更新与课件下载**仅限于该主机账号所选修的科目**。分享 Telegram 机器人并不会赋予同学独立的 SPeCTRUM 登录凭证或额外科目的访问权。
- 请在遵守马来亚大学规章制度的前提下分享课件资料。

---

## ⚠️ 已知局限性

- **电脑开机要求**：本地运行的 Bot 依赖电脑处于开机并联网的状态。电脑完全关机或处于深度睡眠时监控会暂时挂起。
- **会话时效限制**：SPeCTRUM 与微软的登录 Cookie 随时间可能失效。失效时只需在电脑上重新运行一次登录命令（Windows: `.venv\Scripts\python main.py --login`；macOS: `./.venv/bin/python main.py --login`）重新刷新凭证即可。
- **教务平台样式变动**：作为自动化爬虫，若马大未来对 SPeCTRUM Moodle 页面结构进行大规模改版，可能需要更新提取选择器。
- **Telegram 50MB 上传限制**：受 Telegram Bot API 限制，大于 50MB 的超大文件将直接附带 SPeCTRUM 网页直达下载链接，而非直接发送附件。
- **搜索范围**：`/search` 命令检索的是已收录的文件名、标题与周次元数据，不支持对二进制 PDF/PPT 内部页面正文进行全文 OCR 检索。

---

## 🛠️ 常见故障排查

| 异常现象 | 可能原因 | 解决办法 |
| :--- | :--- | :--- |
| `'python' 不是内部或外部命令` | 未安装 Python 或未勾选 PATH | 安装 Python 3.10+ 并确保勾选 **"Add python.exe to PATH"**。 |
| 无法启动 Chromium 浏览器 | 未下载浏览器二进制内核 | 重新运行 `setup.bat` (Windows) 或 `./setup.sh` (Mac)，或手动运行 `playwright install chromium`。 |
| 登录失败 / 窗口过早关闭 | 未能在限时内完成手机 2FA 批准 | 重新运行 `.venv\Scripts\python main.py --login` (Win) 或 `./.venv/bin/python main.py --login` (Mac) 并批准登录。 |
| Telegram 机器人无响应 | Token 错误或未在 Telegram 点击 Start | 检查 `.env` 中的 `TELEGRAM_BOT_TOKEN`，并确认在 Telegram 找到机器人并点击了 **Start**。 |
| Mac 关盖睡眠后无推送 | Mac 处于深度休眠 | 属于正常休眠现象，Mac 唤醒或开机后 `launchd` 服务会自动恢复监控。 |
| 日志频繁提示 Session expired | SPeCTRUM 会话过期 | 在电脑上重新运行 `--login` 即可快速刷新本地登录凭证。 |

---

## 📖 技术架构与开发者文档

如需了解完整的系统数据流图、各模块源码分工、SQLite 数据库表结构设计及开发者 CLI 命令：  
👉 请阅读 **[TECHNICAL.md](TECHNICAL.md)**

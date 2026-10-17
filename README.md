# 🛰️ SpectrumBot - UM SPeCTRUM Telegram Assistant

> Automatically monitors Universiti Malaya (UM) SPeCTRUM for new course materials (PDFs, lecture slides), forum announcements, and upcoming assignment/quiz deadlines — delivering notifications, deadline countdowns, and on-demand file downloads directly to your Telegram.

[📖 简体中文文档 (Chinese Version)](README_CN.md) | [🛠️ Technical Documentation (TECHNICAL.md)](TECHNICAL.md)

---

## 🛡️ Security & Privacy

SpectrumBot uses Playwright to interact with UM SPeCTRUM through your browser's official authentication flow.

- **Password Safety**: Your SiswaMail credentials should always be entered directly into the official UM/Microsoft login portal in the browser window, never into Telegram, a third-party form, or a config file. The application code does not log or store your plaintext password.
- **Session Tokens (`auth_state.json`)**: After you authenticate, browser cookies and session tokens are saved locally to `auth_state.json`. This file enables the scraper to access your courses without prompting you every time. **Treat `auth_state.json` like a password: never share it or commit it to a public repository.**
- **Telegram Communication**: SpectrumBot communicates with the official Telegram Bot API to deliver notifications and file downloads to your authorized chat.
- **Local Execution**: The monitor runs locally on your own machine. There are no external third-party backend servers.

**Security Precautions**:
- Never publish or share your `.env` or `auth_state.json` files.
- Always review source code before entering your university credentials.
- Only share course materials in ways permitted by Universiti Malaya.

---

## ✨ Features

| Category | Features |
| :--- | :--- |
| 📚 **Course Monitoring** | Scrapes accessible course sections for new lecture slides, notes, PDFs, and folders. |
| 📢 **Announcements** | Detects newly posted forum topics and announcements (filters out recycled posts from prior years). |
| 📝 **Deadline Tracking** | Tracks upcoming assignment deadlines and quizzes, sending countdown reminders at **48 hours** and **24 hours** before cutoff. |
| 🔍 **Resource Access** | Search indexed course materials by title (`/search <keyword>`), browse materials by week (`📚 My Courses`), and request direct file delivery (`[📥 Send File Here]`). |
| 👥 **Telegram Interface** | Interactive keyboard menu, command handling, and admin approval for subscriber requests. |
| ⚙️ **Scheduled Automation** | Runs periodic checks every 30 minutes by default with silent deduplication (zero spam on unchanged checks). |

---

## 🎮 Telegram Command Reference

| Command / Button | Type | Description |
| :--- | :--- | :--- |
| **`/start`** | Command | Display welcome message and activate the interactive menu |
| **`📝 Deadlines`** (or `/deadlines`) | Button / Command | View categorized assignments: Overdue, Due Soon (<48h), Upcoming, Submitted |
| **`🔍 Check Now`** | Button | Trigger an immediate scrape of all configured courses |
| **`📚 My Courses`** (or `/courses`) | Button / Command | Browse monitored courses by weekly topic and download past slides |
| **`/search <keyword>`** | Command | Search indexed course file titles (e.g. `/search lecture 1`) |
| **`⚙️ Status`** (or `/status`) | Button / Command | View session health, database stats, and next check countdown |
| **`/login`** | Command | Display re-authentication instructions |
| **`❓ Help`** (or `/help`) | Button / Command | View usage instructions and available commands |

---

## 🛠️ Quick Start Guide

### 1. Prerequisites & Environment Setup

#### Requirements:
- **Python 3.10 or higher**:
  - **🪟 Windows**: Download from [python.org](https://www.python.org/downloads/). **CRITICAL**: Check **☑️ "Add python.exe to PATH"** on the first installation screen.
    - *Quick check*: Press `Win + R`, type `cmd`, press Enter, and run `python --version`. If not found, rerun the installer, select **Modify**, and check "Add Python to environment variables".
  - **🍎 macOS**: Install via Homebrew (`brew install python@3.11`) or download from [python.org](https://www.python.org/downloads/).

#### Run Setup Script:
- **🪟 Windows**: Double-click `setup.bat` (or run `setup.bat` in Command Prompt).
- **🍎 macOS**: Run in Terminal: `chmod +x setup.sh && ./setup.sh`.

*(The script automatically creates a `.venv` virtual environment, installs Python dependencies, and downloads the Playwright Chromium browser engine)*.

> **Verification**: The terminal displays `Setup complete!`, and a `.venv` directory exists in the project root.

---

### 2. Configure Telegram Bot & `.env`

1. **Create Bot Token**:
   - Open Telegram, search for `@BotFather`, and send `/newbot`.
   - Choose a bot name and username (must end in `bot`). Copy the generated `HTTP API Token`.
2. **Create `.env` File**:
   - Copy the template file:
     - **Windows (Command Prompt)**: `copy .env.example .env`
     - **macOS / Linux**: `cp .env.example .env`
   - Open `.env` in a text editor and paste your token:
     ```env
     TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
     ```
3. **Start the Bot in Telegram**:
   - Open Telegram, search for your new bot's username, and send `/start` (or `hi`).
4. **Auto-Detect Chat ID**:
   - Run the automatic capture tool:
     - **Windows**: `.venv\Scripts\python main.py --get-chat-id`
     - **macOS**: `./.venv/bin/python main.py --get-chat-id`
   - The tool detects your `/start` message and automatically writes `TELEGRAM_CHAT_ID` into `.env`.
5. **Verify Connection**:
   - **Windows**: `.venv\Scripts\python main.py --test-tg`
   - **macOS**: `./.venv/bin/python main.py --test-tg`

> **Verification**: You receive a welcome message with interactive menu buttons on Telegram.

*(Optional: By default, SpectrumBot monitors all enrolled courses on your dashboard. To restrict to specific course codes, edit `MONITORED_COURSES=WIA2001,WIA2006` in `.env`).*

---

### 3. SPeCTRUM Authentication

You have two convenient, passwordless ways to authenticate:

#### 📱 Option A: Remote via Telegram (Passwordless QR Code - Recommended)
1. In `.env`, set your SiswaMail:
   ```env
   SISWA_EMAIL=s21xxxxx@siswa.um.edu.my
   ```
2. Start the bot and send `/login` on Telegram (or send `/login s21xxxxx@siswa.um.edu.my`).
3. The bot launches a headless browser, enters your email into UM Microsoft SSO, and sends you a screenshot of the **Sign-In QR Code / Authenticator Prompt** directly in Telegram.
4. Open the **Microsoft Authenticator** app on your phone, scan the QR code or approve the prompt.
5. The bot automatically detects the completed login, saves `auth_state.json`, and starts monitoring!

#### 💻 Option B: Interactive Browser Wizard on Computer
If you prefer logging in via an open browser window on your desktop:
- **Windows**: `.venv\Scripts\python main.py --login`
- **macOS**: `./.venv/bin/python main.py --login`

1. A Chromium browser window will open to the UM SPeCTRUM Microsoft SSO portal.
2. Enter your SiswaMail credentials and approve the Microsoft Authenticator prompt on your phone.
3. Upon reaching the SPeCTRUM dashboard, your session cookies are automatically saved to `auth_state.json`.

> **Verification**: The terminal displays `[OK] Authentication state saved to auth_state.json`.

---

### 4. Running the Monitor & Auto-Start on Boot

#### 🪟 On Windows:
- **Auto-Start on Boot (Recommended)**: Double-click `enable_autostart_windows.bat`.  
  Creates a startup shortcut in `shell:startup` that launches `start_background.bat` silently via `pythonw.exe`.
  - To stop the background monitor: Double-click `stop_background.bat`.
  - To cancel auto-start on boot: Double-click `disable_autostart_windows.bat`.
  - To view live logs: Open `spectrumbot.log` in Notepad, or in PowerShell: `Get-Content -Wait spectrumbot.log`.
  - Foreground debug console: Double-click `run_watch.bat`.

#### 🍎 On macOS:
- **Auto-Start System Service (Recommended)**: In Terminal, run:
  ```bash
  ./start_background.sh
  ```
  Registers a macOS user LaunchAgent daemon (`com.um.spectrumbot.plist`). The service runs when you are logged into your Mac and survives Terminal/VS Code closures.
  - To stop the service: `./stop_background.sh`.
  - To view live logs: `tail -f spectrumbot.log`.
  - Foreground debug console: `bash run_watch.sh` (or `./.venv/bin/python main.py --watch`).

> **Verification**: On Telegram, tap **`⚙️ Status`** or **`📝 Deadlines`**. If the bot replies within a few seconds, background monitoring is active!

---

## 👥 Inviting Classmates

You can share your Telegram bot username with your classmates.

- **How Subscriptions Work**: If multi-user access is enabled, other students can send `/start` to your bot. If subscriber approval is enabled, you (the admin) will receive a Telegram approval prompt (`[✅ Approve] / [❌ Deny]`).
- **Important Note on Shared Access**: SpectrumBot retrieves course data through its single configured SPeCTRUM host account. Subscribers receive updates and can download materials **only for courses that the host account is enrolled in**. Sharing the bot does not grant subscribers independent SPeCTRUM credentials or access to different subjects.
- Please ensure you share course materials only in compliance with Universiti Malaya policies.

---

## ⚠️ Known Limitations

- **Computer Availability**: The bot must be running on a machine that is powered on and connected to the internet. Monitoring pauses if your computer is shut down or in deep sleep.
- **Session Expiry**: SPeCTRUM / Microsoft authentication sessions expire over time. If your session expires, rerun the official login command on your computer (`.venv\Scripts\python main.py --login` on Windows or `./.venv/bin/python main.py --login` on macOS).
- **LMS Layout Changes**: Like any web scraper, major structural updates to the UM SPeCTRUM Moodle theme may require updates to scraping selectors.
- **Telegram 50MB File Limit**: Telegram restricts bot uploads to 50MB. Files exceeding 50MB will include a direct SPeCTRUM link instead of an attached file.
- **Search Scope**: The `/search` command indexes discovered resource names, titles, and section metadata—it does not index the internal text content of binary PDF/PPTX files.

---

## 🛠️ Troubleshooting

| Problem | Cause | Solution |
| :--- | :--- | :--- |
| `'python' is not recognized` | Python is missing or not in PATH | Install Python 3.10+ and check **"Add python.exe to PATH"** in the installer. |
| Chromium fails to launch | Browser binaries not installed | Rerun `setup.bat` (Windows) or `./setup.sh` (macOS), or run `playwright install chromium`. |
| Login fails / browser closes early | 2FA was not approved in time | Run `.venv\Scripts\python main.py --login` (Win) or `./.venv/bin/python main.py --login` (Mac) and complete MFA. |
| Bot does not reply on Telegram | Invalid token or bot not started | Verify `TELEGRAM_BOT_TOKEN` in `.env` and make sure you tapped **Start** in Telegram. |
| Background process stops on Mac | Mac entered sleep or logged out | The launchd service pauses when the Mac sleeps and automatically resumes upon wake/login. |
| Session expired in logs | SPeCTRUM cookies timed out | Rerun `--login` on your computer to refresh your session state. |

---

## 📖 Technical Architecture & Developer Docs

For detailed system architecture, component diagrams, database schema, and developer CLI options, see:  
👉 **[TECHNICAL.md](TECHNICAL.md)**

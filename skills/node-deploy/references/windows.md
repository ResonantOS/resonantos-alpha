# Windows Deployment Reference

## Known Issues (from BeeAMD deployment 2026-02-28)

### Critical: Python Unicode
Windows default encoding is CP1252. Any Python script with emoji (print statements,
Flask routes) will crash with `UnicodeEncodeError`.

**Fix:** Always set environment variable before running Python:
```powershell
$env:PYTHONIOENCODING = "utf-8"
```
For persistent: add to System Environment Variables or prefix every python command.

### Critical: python3 doesn't exist
Windows only has `python`. The installer handles this, but any script that
hardcodes `python3` will fail.

**Fix:** install.js detects this automatically. For manual runs: use `python` not `python3`.

### Critical: PowerShell Execution Policy
Default policy blocks scripts. Must bypass per-session or per-machine.

```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
```

### Medium: Windows Store App Execution Aliases
Windows Store intercepts `python` and `python3` commands, opening the Store instead.

**Fix:** Settings → Apps → Advanced App Settings → App Execution Aliases → disable Python entries.

### Medium: OpenSSH Server
May or may not be installed. Required for SSH tunnel (if using tunnel architecture).

```powershell
# Check
Get-WindowsCapability -Online | Where-Object Name -like 'OpenSSH.Server*'
# Install
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic
```

### Low: chflags/sudo
macOS-specific commands used by file_guard.py. Windows equivalent is `icacls`.
The fixed file_guard.py handles this automatically (uses `icacls /deny Everyone:(W)` on Windows).

## Installation Sequence

```powershell
# 1. Prerequisites (as Admin)
winget install OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
winget install Python.Python.3.12 --accept-source-agreements --accept-package-agreements
winget install Git.Git --accept-source-agreements --accept-package-agreements

# 2. Refresh PATH
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# 3. Set Python encoding
$env:PYTHONIOENCODING = "utf-8"

# 4. Install OpenClaw
npm install -g openclaw

# 5. Clone and install ResonantOS
git clone https://github.com/ResonantOS/resonantos-alpha.git $HOME\resonantos-alpha
node $HOME\resonantos-alpha\install.js

# 6. Start OpenClaw node (connects to orchestrator)
openclaw node run --gateway-url ws://ORCHESTRATOR_IP:18789 --token TOKEN
```

## OpenClaw Node as Windows Service

Create a Scheduled Task that auto-starts the node on boot:

```powershell
$action = New-ScheduledTaskAction -Execute "node" -Argument "$(npm root -g)\openclaw\bin\openclaw.js node run --gateway-url ws://ORCHESTRATOR_IP:18789 --token TOKEN"
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "OpenClaw-Node" -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest
```

## Verification Commands

```powershell
# Check node is running
Get-ScheduledTask -TaskName "OpenClaw-Node" | Select-Object State

# Check OpenClaw version
openclaw --version

# Check Python works
python -c "print('OK')"

# Check dashboard starts
$env:PYTHONIOENCODING = "utf-8"
cd $HOME\resonantos-alpha\dashboard
python server_v2.py
# Should see "Running on http://127.0.0.1:19100"
```

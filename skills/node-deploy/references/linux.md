# Linux Deployment Reference

## Ubuntu/Debian Specifics

### Prerequisites

```bash
sudo apt update
sudo apt install -y curl git python3 python3-pip

# Node.js 20 (distro default is often too old)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Verify
node --version   # Must be 18+
python3 --version
git --version
pip3 --version
```

### Install OpenClaw

```bash
sudo npm install -g openclaw
```

### Install ResonantOS

```bash
git clone https://github.com/ResonantOS/resonantos-alpha.git ~/resonantos-alpha
node ~/resonantos-alpha/install.js
```

### Dashboard Dependencies

install.js handles this, but manually:
```bash
pip3 install flask flask-cors psutil websocket-client solana solders
```

## OpenClaw Node as systemd Service

```bash
sudo tee /etc/systemd/system/openclaw-node.service << 'UNIT'
[Unit]
Description=OpenClaw Node
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=DEPLOY_USER
Environment=HOME=/home/DEPLOY_USER
ExecStart=/usr/bin/openclaw node run --gateway-url ws://ORCHESTRATOR_IP:18789 --token TOKEN
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable openclaw-node
sudo systemctl start openclaw-node
```

Replace `DEPLOY_USER`, `ORCHESTRATOR_IP`, and `TOKEN` with actual values.

## VM Deployment on Windows Host

When deploying Ubuntu as a VM on a Windows machine:

### Option A: Hyper-V (Windows Pro/Enterprise)

```powershell
# Enable Hyper-V (requires reboot)
Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V -All

# Create VM
New-VM -Name "ResonantOS-Ubuntu" -MemoryStartupBytes 4GB -NewVHDPath "C:\VMs\ubuntu.vhdx" -NewVHDSizeBytes 40GB -Generation 2
Set-VMProcessor -VMName "ResonantOS-Ubuntu" -Count 4
Add-VMDvdDrive -VMName "ResonantOS-Ubuntu" -Path "C:\path\to\ubuntu-24.04-server.iso"

# Network: Default Switch (NAT) for internet access
Connect-VMNetworkAdapter -VMName "ResonantOS-Ubuntu" -SwitchName "Default Switch"

# Start
Start-VM -VMName "ResonantOS-Ubuntu"
```

### Option B: VirtualBox (Any Windows Edition)

```powershell
# Install VirtualBox
winget install Oracle.VirtualBox

# Create VM via VBoxManage
& "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe" createvm --name "ResonantOS-Ubuntu" --ostype Ubuntu_64 --register
& "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe" modifyvm "ResonantOS-Ubuntu" --memory 4096 --cpus 4 --nic1 nat
& "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe" createhd --filename "C:\VMs\ubuntu.vdi" --size 40000
# Attach storage and ISO, then start
```

### VM Networking for Node Connection

**NAT mode (default):** VM gets internet via host. To reach orchestrator gateway:
- If orchestrator is on the same LAN as host: use host's LAN IP
- If orchestrator is the host itself: use host-only adapter IP or NAT port forward

**Port forwarding (VirtualBox NAT):**
```powershell
VBoxManage modifyvm "ResonantOS-Ubuntu" --natpf1 "ssh,tcp,,2222,,22"
VBoxManage modifyvm "ResonantOS-Ubuntu" --natpf1 "openclaw,tcp,,18791,,18789"
```

**Bridged mode:** VM gets its own LAN IP. Simplest for node connectivity.

### Ubuntu Server Minimal Setup (Post-ISO Install)

```bash
# Update
sudo apt update && sudo apt upgrade -y

# Install SSH (for backup access)
sudo apt install -y openssh-server
sudo systemctl enable ssh

# Set timezone
sudo timedatectl set-timezone UTC

# Enable NTP (critical for OpenClaw signatures)
sudo timedatectl set-ntp true

# Then proceed with Prerequisites section above
```

## Known Linux Issues

| Issue | Symptom | Fix |
|-------|---------|-----|
| Old Node.js | `SyntaxError` on OpenClaw | Use NodeSource repo |
| pip externally-managed | `error: externally-managed-environment` | Use `pip3 install --break-system-packages` or venv |
| Firewall blocks node | Connection timeout | `sudo ufw allow 18789/tcp` |
| systemd service user | Permission denied | Set correct `User=` in unit file |
| NTP not running | Signature expired errors | `timedatectl set-ntp true` |

## Verification Commands

```bash
# Node service status
sudo systemctl status openclaw-node

# OpenClaw version
openclaw --version

# Dashboard test
cd ~/resonantos-alpha/dashboard && python3 server_v2.py &
curl -s http://localhost:19100 | head -5
kill %1

# Extensions check
ls ~/.openclaw/agents/main/agent/extensions/
```

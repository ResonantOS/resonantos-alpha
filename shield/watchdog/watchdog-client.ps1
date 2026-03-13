<#
.SYNOPSIS
    Watchdog Client — Monitors Mac Mini orchestrator health from a node machine.
    Runs as a Windows Scheduled Task every 5 minutes.

.DESCRIPTION
    1. Checks orchestrator health via SSH (forced-command: health sensors)
    2. If critical: attempts restart via SSH (forced-command: restart-gateway / restart-dashboard)
    3. If restart fails after retries: alerts via Telegram
    4. Logs everything to local file with structured data

.PARAMETER OrchestratorIP
    IP address of the orchestrator (default: 10.0.0.2 via Ethernet)

.PARAMETER SSHKey
    Path to the watchdog SSH private key

.PARAMETER TelegramBotToken
    Bot token for alert notifications (optional)

.PARAMETER TelegramChatId
    Chat ID for alert notifications (optional)

.PARAMETER MaxRestartAttempts
    Maximum restart attempts before alerting (default: 3)
#>

param(
    [string]$OrchestratorIP = "10.0.0.1",
    [string]$SSHUser = "watchdog",
    [string]$SSHKey = "$env:USERPROFILE\.ssh\watchdog_ed25519",
    [string]$TelegramBotToken = "",
    [string]$TelegramChatId = "",
    [int]$MaxRestartAttempts = 3,
    [string]$LogFile = "$env:USERPROFILE\watchdog\watchdog.log"
)

$ErrorActionPreference = "Continue"

# --- Logging ---
function Write-Log {
    param([string]$Level, [string]$Message)
    $ts = Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ" -AsUTC
    $entry = "[$ts] [$Level] $Message"
    
    $logDir = Split-Path $LogFile -Parent
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
    Add-Content -Path $LogFile -Value $entry
    
    if ($Level -eq "ERROR" -or $Level -eq "CRITICAL") {
        Write-Host $entry -ForegroundColor Red
    } elseif ($Level -eq "WARN") {
        Write-Host $entry -ForegroundColor Yellow
    } else {
        Write-Host $entry
    }
}

# --- SSH Command ---
function Invoke-WatchdogSSH {
    param([string]$Action)
    
    $sshArgs = @(
        "-i", $SSHKey,
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
        "-o", "StrictHostKeyChecking=accept-new",
        "${SSHUser}@${OrchestratorIP}",
        $Action
    )
    
    try {
        $result = & ssh @sshArgs 2>&1
        $exitCode = $LASTEXITCODE
        
        if ($exitCode -eq 0) {
            return @{ Success = $true; Output = ($result -join "`n"); ExitCode = $exitCode }
        } else {
            return @{ Success = $false; Output = ($result -join "`n"); ExitCode = $exitCode }
        }
    } catch {
        return @{ Success = $false; Output = $_.Exception.Message; ExitCode = -1 }
    }
}

# --- Telegram Alert ---
function Send-TelegramAlert {
    param([string]$Message)
    
    if ([string]::IsNullOrEmpty($TelegramBotToken) -or [string]::IsNullOrEmpty($TelegramChatId)) {
        Write-Log "WARN" "Telegram not configured — alert not sent: $Message"
        return
    }
    
    try {
        $body = @{
            chat_id = $TelegramChatId
            text = "🚨 *Watchdog Alert*`n`n$Message"
            parse_mode = "Markdown"
        } | ConvertTo-Json
        
        Invoke-RestMethod -Uri "https://api.telegram.org/bot$TelegramBotToken/sendMessage" `
            -Method Post -Body $body -ContentType "application/json" -TimeoutSec 10 | Out-Null
        
        Write-Log "INFO" "Telegram alert sent"
    } catch {
        Write-Log "ERROR" "Failed to send Telegram alert: $($_.Exception.Message)"
    }
}

# --- State File ---
$stateFile = "$env:USERPROFILE\watchdog\watchdog-state.json"

function Get-WatchdogState {
    if (Test-Path $stateFile) {
        return Get-Content $stateFile | ConvertFrom-Json
    }
    return @{
        consecutiveFailures = 0
        lastHealthy = $null
        lastAlert = $null
        restartAttempts = 0
    }
}

function Save-WatchdogState {
    param($State)
    $State | ConvertTo-Json | Set-Content $stateFile
}

function Test-SensorCritical {
    param(
        $Sensors,
        [string]$Name
    )

    $sensorProp = $Sensors.PSObject.Properties[$Name]
    if ($null -eq $sensorProp -or $null -eq $sensorProp.Value) {
        return $false
    }

    return $sensorProp.Value.status -eq "critical"
}

# --- Main Logic ---
Write-Log "INFO" "Watchdog check starting"

$state = Get-WatchdogState

# Step 1: Check connectivity (ping)
$pingResult = Test-Connection -ComputerName $OrchestratorIP -Count 1 -TimeoutSeconds 3 -ErrorAction SilentlyContinue

if (-not $pingResult) {
    Write-Log "ERROR" "Orchestrator unreachable (ping failed to $OrchestratorIP)"
    $state.consecutiveFailures++
    
    if ($state.consecutiveFailures -ge ($MaxRestartAttempts * 2)) {
        Send-TelegramAlert "Orchestrator at $OrchestratorIP is UNREACHABLE (network down). ${($state.consecutiveFailures)} consecutive failures. Cannot SSH to diagnose — physical check required."
        $state.lastAlert = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ" -AsUTC)
    }
    
    Save-WatchdogState $state
    exit 2
}

# Step 2: Get health status via SSH
$healthResult = Invoke-WatchdogSSH -Action "health"

if (-not $healthResult.Success) {
    Write-Log "ERROR" "SSH health check failed (exit $($healthResult.ExitCode)): $($healthResult.Output)"
    $state.consecutiveFailures++
    
    if ($state.consecutiveFailures -ge $MaxRestartAttempts) {
        Send-TelegramAlert "Cannot reach orchestrator health sensors via SSH.`nExit code: $($healthResult.ExitCode)`nOutput: $($healthResult.Output)"
        $state.lastAlert = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ" -AsUTC)
    }
    
    Save-WatchdogState $state
    exit 1
}

# Step 3: Parse health JSON
try {
    $health = $healthResult.Output | ConvertFrom-Json
} catch {
    Write-Log "ERROR" "Failed to parse health JSON: $($healthResult.Output)"
    Save-WatchdogState $state
    exit 1
}

$overall = $health.overall
Write-Log "INFO" "Health check result: $overall"

# Step 4: React based on health status
switch ($overall) {
    "ok" {
        Write-Log "INFO" "All sensors healthy"
        $state.consecutiveFailures = 0
        $state.restartAttempts = 0
        $state.lastHealthy = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ" -AsUTC)
    }
    
    "degraded" {
        Write-Log "WARN" "System degraded — monitoring"
        # Log which sensors are degraded
        $health.sensors.PSObject.Properties | ForEach-Object {
            if ($_.Value.status -ne "ok") {
                Write-Log "WARN" "  Sensor $($_.Name): [$($_.Value.status)] $($_.Value.reason)"
            }
        }
        # Don't restart for degraded — just monitor
        $state.consecutiveFailures = 0
    }
    
    "critical" {
        Write-Log "CRITICAL" "System CRITICAL"
        $state.consecutiveFailures++
        
        # Log critical sensors
        $criticalSensors = @()
        $health.sensors.PSObject.Properties | ForEach-Object {
            if ($_.Value.status -eq "critical") {
                Write-Log "CRITICAL" "  Sensor $($_.Name): $($_.Value.reason)"
                $criticalSensors += "$($_.Name): $($_.Value.reason)"
            }
        }
        
        # Restartable service checks
        $gatewayDown = (Test-SensorCritical -Sensors $health.sensors -Name "gateway_process") -or
                       (Test-SensorCritical -Sensors $health.sensors -Name "gateway_http")
        $dashboardDown = Test-SensorCritical -Sensors $health.sensors -Name "dashboard"
        
        if ($gatewayDown -and $state.restartAttempts -lt $MaxRestartAttempts) {
            Write-Log "INFO" "Attempting gateway restart ($($state.restartAttempts + 1)/$MaxRestartAttempts)"
            $restartResult = Invoke-WatchdogSSH -Action "restart-gateway"
            $state.restartAttempts++
            
            if ($restartResult.Success) {
                Write-Log "INFO" "Restart command sent: $($restartResult.Output)"
                # Wait and re-check
                Start-Sleep -Seconds 10
                $recheck = Invoke-WatchdogSSH -Action "health"
                if ($recheck.Success) {
                    $recheckHealth = $recheck.Output | ConvertFrom-Json
                    if ($recheckHealth.overall -ne "critical") {
                        Write-Log "INFO" "Gateway recovered after restart!"
                        $state.consecutiveFailures = 0
                        $state.restartAttempts = 0
                        $state.lastHealthy = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ" -AsUTC)
                        Send-TelegramAlert "Gateway was down and has been automatically restarted. System recovered.`nSensors: $($criticalSensors -join ', ')"
                    }
                }
            } else {
                Write-Log "ERROR" "Restart command failed: $($restartResult.Output)"
            }
        }

        if ($dashboardDown -and $state.restartAttempts -lt $MaxRestartAttempts) {
            Write-Log "INFO" "Attempting dashboard restart ($($state.restartAttempts + 1)/$MaxRestartAttempts)"
            $restartResult = Invoke-WatchdogSSH -Action "restart-dashboard"
            $state.restartAttempts++

            if ($restartResult.Success) {
                Write-Log "INFO" "Restart command sent: $($restartResult.Output)"
                # Wait and re-check
                Start-Sleep -Seconds 10
                $recheck = Invoke-WatchdogSSH -Action "health"
                if ($recheck.Success) {
                    $recheckHealth = $recheck.Output | ConvertFrom-Json
                    if ($recheckHealth.overall -ne "critical") {
                        Write-Log "INFO" "Dashboard recovered after restart!"
                        $state.consecutiveFailures = 0
                        $state.restartAttempts = 0
                        $state.lastHealthy = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ" -AsUTC)
                        Send-TelegramAlert "Dashboard was down and has been automatically restarted. System recovered.`nSensors: $($criticalSensors -join ', ')"
                    }
                }
            } else {
                Write-Log "ERROR" "Restart command failed: $($restartResult.Output)"
            }
        }
        
        # If max retries exceeded, alert
        if ($state.restartAttempts -ge $MaxRestartAttempts) {
            $timeSinceAlert = if ($state.lastAlert) { 
                (New-TimeSpan -Start ([datetime]$state.lastAlert) -End (Get-Date)).TotalMinutes 
            } else { 999 }
            
            # Don't spam — alert at most every 30 minutes
            if ($timeSinceAlert -ge 30) {
                $sensorReport = ($criticalSensors | ForEach-Object { "• $_" }) -join "`n"
                Send-TelegramAlert "Orchestrator CRITICAL — automatic restart failed after $MaxRestartAttempts attempts.`n`nCritical sensors:`n$sensorReport`n`nLast healthy: $($state.lastHealthy)`nManual intervention required."
                $state.lastAlert = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ" -AsUTC)
            }
        }
    }
}

Save-WatchdogState $state
Write-Log "INFO" "Watchdog check complete"

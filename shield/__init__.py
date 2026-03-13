"""
Symbiotic Shield - Runtime Security Agent

A security monitoring agent that runs alongside AI agents to detect
attacks and prevent sensitive data exposure.

Usage:
    from security.shield import Shield, scan_input, scan_output, check_a2a

    # Using the Shield class directly
    shield = Shield()
    result = shield.scan_input("user message here")
    if result.is_threat:
        print(f"Threat detected: {result.threat_types}")

    # Using convenience functions
    result = scan_input("user message")
    result = scan_output("response to send")
    allowed = check_a2a(agent_card, task)

Components:
    - Scanner: Detects prompt injection and data leaks
    - Classifier: Classifies data sensitivity levels
    - A2AMonitor: Monitors agent-to-agent communications
    - Shield: Main orchestrator with alerting and intervention

See README.md for full documentation.
"""

from .scanner import Scanner, ScanResult, ThreatType, scan
from .classifier import DataClassifier, ClassificationResult, SensitivityLevel, classify, can_egress, redact
from .a2a_monitor import A2AMonitor, A2ASecurityResult, AgentCard, A2ATask, A2AThreatType
from .logician_bridge import (
    LogicianShieldBridge,
    LogicianResult,
    get_bridge,
    verify_spawn,
    is_forbidden_output,
    check_injection,
    can_use_tool
)
from .shield import (
    Shield, 
    ShieldConfig, 
    BlockedError, 
    Alert, 
    AlertSeverity,
    InterventionMode,
    get_shield,
    scan_input,
    scan_output,
    check_a2a
)

__version__ = "1.0.0"
__all__ = [
    # Scanner
    "Scanner",
    "ScanResult", 
    "ThreatType",
    "scan",
    
    # Classifier
    "DataClassifier",
    "ClassificationResult",
    "SensitivityLevel",
    "classify",
    "can_egress",
    "redact",
    
    # A2A Monitor
    "A2AMonitor",
    "A2ASecurityResult",
    "AgentCard",
    "A2ATask",
    "A2AThreatType",
    
    # Logician Bridge
    "LogicianShieldBridge",
    "LogicianResult",
    "get_bridge",
    "verify_spawn",
    "is_forbidden_output",
    "check_injection",
    "can_use_tool",
    
    # Shield
    "Shield",
    "ShieldConfig",
    "BlockedError",
    "Alert",
    "AlertSeverity",
    "InterventionMode",
    "get_shield",
    "scan_input",
    "scan_output",
    "check_a2a",
]

#!/usr/bin/env python3
"""
ResonantOS Dashboard Server
A modern, dark-mode dashboard for managing AI agents and services.

UPGRADED: Now uses REAL data from Watchtower database and Clawdbot CLI.
"""

import os
import sys
import json
import sqlite3
import subprocess
import hashlib
import time
import psutil
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_cors import CORS

# Add shield module to path
sys.path.insert(0, str(Path.home() / 'clawd' / 'security'))
try:
    from shield import get_shield, Shield
    SHIELD_AVAILABLE = True
except ImportError:
    SHIELD_AVAILABLE = False

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# ============================================================================
# API Key Encryption Helpers
# ============================================================================

import base64
import secrets

# Simple encryption key (in production, use proper key management)
ENCRYPTION_KEY = os.environ.get('CHATBOT_ENCRYPTION_KEY', 'resonantos-default-key-change-in-prod')

def encrypt_api_key(api_key: str) -> str:
    """Simple XOR-based encryption for API keys (use proper encryption in production)"""
    if not api_key:
        return None
    key_bytes = (ENCRYPTION_KEY * ((len(api_key) // len(ENCRYPTION_KEY)) + 1))[:len(api_key)]
    encrypted = bytes(a ^ b for a, b in zip(api_key.encode(), key_bytes.encode()))
    return base64.b64encode(encrypted).decode()

def decrypt_api_key(encrypted: str) -> str:
    """Decrypt API key"""
    if not encrypted:
        return None
    try:
        encrypted_bytes = base64.b64decode(encrypted.encode())
        key_bytes = (ENCRYPTION_KEY * ((len(encrypted_bytes) // len(ENCRYPTION_KEY)) + 1))[:len(encrypted_bytes)]
        decrypted = bytes(a ^ b for a, b in zip(encrypted_bytes, key_bytes.encode()))
        return decrypted.decode()
    except Exception:
        return None

# ============================================================================
# Configuration - Real Data Sources
# ============================================================================

CLAWD_DIR = Path.home() / 'clawd'
WORKSPACE_PATH = CLAWD_DIR
WATCHTOWER_DB = CLAWD_DIR / 'watchtower' / 'data' / 'watchtower.db'
TODO_FILE_PATH = CLAWD_DIR / 'TODO.md'
CLAWDBOT_CONFIG = Path.home() / '.clawdbot' / 'clawdbot.json'
AGENTS_DIR = CLAWD_DIR / 'ResonantOS' / 'Agents'
FEEDBACK_DIR = CLAWD_DIR / 'feedback' / 'agents'

# Workspace files to exclude from generated docs
WORKSPACE_FILES = {
    'AGENTS.md', 'SOUL.md', 'USER.md', 'IDENTITY.md', 'TOOLS.md',
    'MEMORY.md', 'TODO.md', 'HEARTBEAT.md', 'BOOTSTRAP.md'
}

# ============================================================================
# Database Helper
# ============================================================================

def get_db():
    """Get database connection with proper settings"""
    if not WATCHTOWER_DB.exists():
        return None
    db = sqlite3.connect(str(WATCHTOWER_DB), check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=5000")
    return db


# ============================================================================
# Page Routes
# ============================================================================

@app.route('/')
def index():
    """Main dashboard page."""
    return render_template('index.html', active_page='overview')

@app.route('/status')
def status_page():
    """System status page."""
    return render_template('status.html', active_page='status')

@app.route('/agents')
def agents_page():
    """Agents management page."""
    return render_template('agents.html', active_page='agents')

@app.route('/docs')
def docs_page():
    """Documentation page."""
    return render_template('docs.html', active_page='docs')

@app.route('/chatbots')
def chatbots_page():
    """Chatbot manager page - Coming Soon."""
    return render_template('chatbots.html', active_page='chatbots')

@app.route('/settings')
def settings_page():
    """Settings page."""
    return render_template('settings.html', active_page='settings')

@app.route('/wallet')
def wallet_page():
    """Wallet page - Coming Soon."""
    return render_template('wallet.html', active_page='wallet')

@app.route('/activity')
def activity_page():
    """Activity feed page - redirects to overview with activity focus."""
    return render_template('index.html', active_page='overview', focus='activity')

@app.route('/projects')
def projects_page():
    """Projects management page."""
    return render_template('projects.html', active_page='projects')

@app.route('/analytics')
def analytics_page():
    """Analytics page for chatbot usage."""
    return render_template('analytics.html', active_page='analytics')

@app.route('/skills')
def skills_page():
    """Skills panel for managing AI skills."""
    return render_template('skills.html', active_page='skills')

@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static files."""
    return send_from_directory('static', filename)


@app.route('/widget/loader.js')
def serve_widget_loader():
    """Serve the thin widget loader for SaaS embedding."""
    return send_from_directory('static', 'loader.js', mimetype='application/javascript')


@app.route('/widget.js')
def serve_widget_direct():
    """Serve the full widget script directly (legacy)."""
    return send_from_directory('static/js', 'widget.js', mimetype='application/javascript')


# ============================================================================
# Widget Initialization API - Server-Side Feature Gating
# ============================================================================

# Widget version - increment when widget code changes
WIDGET_VERSION = 'v1.0.0'

# License tier limits
TIER_LIMITS = {
    'free': {'max_chatbots': 1, 'custom_icon': False, 'remove_watermark': False},
    'essential': {'max_chatbots': 3, 'custom_icon': True, 'remove_watermark': True},
    'pro': {'max_chatbots': 3, 'custom_icon': True, 'remove_watermark': True},
    'professional': {'max_chatbots': 5, 'custom_icon': True, 'remove_watermark': True},
    'business': {'max_chatbots': 10, 'custom_icon': True, 'remove_watermark': True},
    'enterprise': {'max_chatbots': 100, 'custom_icon': True, 'remove_watermark': True},
}


@app.route('/api/widget/init/<chatbot_id>')
def api_widget_init(chatbot_id):
    """
    Widget initialization endpoint - ALL feature gating happens here.
    
    Returns:
    - Widget configuration (colors, name, greeting, etc.)
    - License flags (showWatermark, allowIcon, analyticsEnabled)
    - Session token for rate limiting
    - Widget version for cache busting
    
    This is called by loader.js on every widget load.
    """
    db = get_chatbots_db()
    try:
        # Get chatbot config
        chatbot = db.execute("SELECT * FROM chatbots WHERE id = ?", (chatbot_id,)).fetchone()
        if not chatbot:
            return jsonify({'error': 'Chatbot not found'}), 404
        
        chatbot_data = dict(chatbot)
        
        # Get owner's license tier
        user_id = chatbot_data.get('user_id', 'default')
        now_ms = int(time.time() * 1000)
        
        license_row = db.execute("""
            SELECT tier, features, expires_at FROM licenses 
            WHERE user_id = ? 
            AND (chatbot_id = ? OR chatbot_id IS NULL)
            AND (expires_at IS NULL OR expires_at > ?)
            ORDER BY chatbot_id DESC NULLS LAST, tier DESC
            LIMIT 1
        """, (user_id, chatbot_id, now_ms)).fetchone()
        
        # Default to free tier
        tier = 'free'
        features = []
        if license_row:
            tier = license_row['tier'] or 'free'
            features = json.loads(license_row['features'] or '[]')
        
        # Get tier limits
        limits = TIER_LIMITS.get(tier, TIER_LIMITS['free'])
        
        # Domain validation (optional - for future CORS restrictions)
        request_domain = request.headers.get('X-Widget-Domain', '')
        allowed_domains = chatbot_data.get('allowed_domains', '')
        
        # Generate session token for rate limiting
        session_token = hashlib.sha256(
            f"{chatbot_id}:{request_domain}:{int(time.time() // 3600)}:{os.urandom(8).hex()}".encode()
        ).hexdigest()[:32]
        
        # Parse suggested prompts safely
        try:
            suggested_prompts = json.loads(chatbot_data.get('suggested_prompts', '[]'))
        except:
            suggested_prompts = []
        
        # Build response with SERVER-CONTROLLED feature flags
        response = {
            'success': True,
            'widgetVersion': WIDGET_VERSION,
            'config': {
                'id': chatbot_id,
                'name': chatbot_data.get('name', 'Chat'),
                'greeting': chatbot_data.get('greeting', 'Hi! How can I help you?'),
                'suggestedPrompts': suggested_prompts[:3],  # Limit to 3
                'position': chatbot_data.get('position', 'bottom-right'),
                'theme': chatbot_data.get('theme', 'dark'),
                'primaryColor': chatbot_data.get('primary_color', '#4ade80'),
                'bgColor': chatbot_data.get('bg_color', '#1a1a2e'),
                'textColor': chatbot_data.get('text_color', '#e0e0e0'),
                'apiEndpoint': request.host_url.rstrip('/') + '/api',
                # Custom icon only if license allows
                'iconUrl': chatbot_data.get('icon_url', '') if limits['custom_icon'] else ''
            },
            'license': {
                'tier': tier,
                # Watermark shown unless license explicitly allows removal
                'showWatermark': not limits['remove_watermark'],
                # Custom icon allowed only with paid tier
                'allowIcon': limits['custom_icon'],
                # Analytics enabled for pro+ tiers
                'analyticsEnabled': tier not in ('free',),
                # Session token for rate limiting
                'sessionToken': session_token
            }
        }
        
        # Update last_used_at
        db.execute(
            "UPDATE chatbots SET last_used_at = ? WHERE id = ?",
            (now_ms, chatbot_id)
        )
        db.commit()
        
        return jsonify(response)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to load widget', 'details': str(e)}), 500
    finally:
        db.close()


@app.route('/widget/v/<version>/widget.min.js')
def serve_versioned_widget(version):
    """
    Serve the minified widget script.
    
    The widget is served from our server - not distributed to customers.
    This ensures:
    - We control the code
    - License checks can't be bypassed
    - Updates apply instantly
    """
    # In production: serve pre-built minified widget
    # For now: serve the runtime widget source
    widget_path = Path(__file__).parent / 'dist' / 'widget-runtime.min.js'
    
    if widget_path.exists():
        return send_from_directory(str(widget_path.parent), 'widget-runtime.min.js', 
                                   mimetype='application/javascript')
    
    # Fallback: serve source (dev mode)
    return send_from_directory(
        str(Path(__file__).parent / 'widget-src'), 
        'widget-runtime.js', 
        mimetype='application/javascript'
    )


@app.route('/api/chatbots/check-limit', methods=['POST'])
def api_check_chatbot_limit():
    """
    Check if user can create more chatbots based on their license tier.
    Called before creating a new chatbot.
    """
    data = request.json or {}
    user_id = data.get('user_id', 'default')
    
    db = get_chatbots_db()
    try:
        # Get user's license
        now_ms = int(time.time() * 1000)
        license_row = db.execute("""
            SELECT tier FROM licenses 
            WHERE user_id = ? AND chatbot_id IS NULL
            AND (expires_at IS NULL OR expires_at > ?)
            ORDER BY tier DESC
            LIMIT 1
        """, (user_id, now_ms)).fetchone()
        
        tier = license_row['tier'] if license_row else 'free'
        limits = TIER_LIMITS.get(tier, TIER_LIMITS['free'])
        max_chatbots = limits['max_chatbots']
        
        # Count existing chatbots for this user
        count_row = db.execute("""
            SELECT COUNT(*) as count FROM chatbots WHERE user_id = ?
        """, (user_id,)).fetchone()
        current_count = count_row['count'] if count_row else 0
        
        can_create = current_count < max_chatbots
        
        return jsonify({
            'canCreate': can_create,
            'currentCount': current_count,
            'maxAllowed': max_chatbots,
            'tier': tier,
            'upgradeRequired': not can_create
        })
        
    except Exception as e:
        return jsonify({'error': str(e), 'canCreate': False}), 500
    finally:
        db.close()


# ============================================================================
# REAL API: Sessions (from Clawdbot CLI)
# ============================================================================

@app.route('/api/sessions')
def api_sessions():
    """Get active Clawdbot sessions (sub-agents) - REAL DATA"""
    active_minutes = request.args.get('active_minutes', 30, type=int)
    
    try:
        # Need full PATH for clawdbot to find node
        env = os.environ.copy()
        env['PATH'] = '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:' + env.get('PATH', '')
        result = subprocess.run(
            ['/opt/homebrew/bin/clawdbot', 'sessions', 'list', f'--active-minutes={active_minutes}', '--json'],
            capture_output=True,
            text=True,
            timeout=15,
            env=env
        )
        
        if result.returncode != 0:
            return jsonify({'sessions': [], 'count': 0, 'error': result.stderr})
        
        data = json.loads(result.stdout)
        sessions = data.get('sessions', [])
        
        # Enrich sessions with parsed info
        for session in sessions:
            key = session.get('key', '')
            parts = key.split(':')
            
            # Parse session type from key
            if 'subagent' in key:
                session['type'] = 'subagent'
                session['label'] = parts[1] if len(parts) > 1 else 'unknown'
            elif 'cron' in key:
                session['type'] = 'cron'
                session['label'] = 'scheduled task'
            else:
                session['type'] = 'main'
                session['label'] = parts[1] if len(parts) > 1 else 'main'
            
            # Calculate runtime
            age_ms = session.get('ageMs', 0)
            session['runtimeMinutes'] = round(age_ms / 60000, 1)
            
            # Determine status based on age
            if age_ms < 60000:
                session['status'] = 'running'
            elif age_ms < 300000:
                session['status'] = 'active'
            else:
                session['status'] = 'idle'
        
        return jsonify({
            'sessions': sessions,
            'count': len(sessions),
            'path': data.get('path')
        })
    except subprocess.TimeoutExpired:
        return jsonify({'sessions': [], 'count': 0, 'error': 'Command timed out'})
    except json.JSONDecodeError as e:
        return jsonify({'sessions': [], 'count': 0, 'error': f'JSON parse error: {e}'})
    except Exception as e:
        return jsonify({'sessions': [], 'count': 0, 'error': str(e)})


# ============================================================================
# REAL API: Stats (from Watchtower DB)
# ============================================================================

@app.route('/api/stats')
def api_stats():
    """Get aggregate statistics - REAL DATA"""
    db = get_db()
    if not db:
        return jsonify({
            'total_agents': 0, 'active_agents': 0, 'stuck_agents': 0,
            'total_events': 0, 'total_tool_calls': 0, 'total_cost': 0,
            'recent_events': 0, 'unresolved_anomalies': 0,
            'error': 'Database not found'
        })
    
    try:
        now_ms = int(time.time() * 1000)
        thirty_min_ago = now_ms - (30 * 60 * 1000)
        
        # Get totals from agent_summaries view
        try:
            summaries = db.execute("""
                SELECT 
                    COUNT(*) as total_agents,
                    SUM(CASE WHEN status = 'stuck' THEN 1 ELSE 0 END) as stuck_agents,
                    SUM(total_events) as total_events,
                    SUM(total_tool_calls) as total_tool_calls,
                    SUM(total_cost) as total_cost,
                    SUM(tokens_in) as tokens_in,
                    SUM(tokens_out) as tokens_out
                FROM agent_summaries
            """).fetchone()
        except:
            # Fallback if view doesn't exist
            summaries = db.execute("""
                SELECT 
                    COUNT(*) as total_agents,
                    SUM(CASE WHEN status = 'stuck' THEN 1 ELSE 0 END) as stuck_agents,
                    SUM(total_events) as total_events,
                    0 as total_tool_calls,
                    0 as total_cost,
                    0 as tokens_in,
                    0 as tokens_out
                FROM agent_status
            """).fetchone()
        
        # Count truly active agents
        try:
            active_agents = db.execute("""
                SELECT COUNT(*) as count FROM agent_summaries
                WHERE last_activity_ts > ?
                AND status NOT IN ('completed', 'stuck')
            """, (thirty_min_ago,)).fetchone()
        except:
            active_agents = db.execute("""
                SELECT COUNT(*) as count FROM agent_status
                WHERE updated_at > ?
                AND status NOT IN ('completed', 'stuck')
            """, (thirty_min_ago,)).fetchone()
        
        # Get recent activity count (last hour)
        recent = db.execute("""
            SELECT COUNT(*) as count
            FROM activity_feed
            WHERE timestamp > ?
        """, (int((time.time() - 3600) * 1000),)).fetchone()
        
        # Get unresolved anomalies
        anomalies = db.execute("""
            SELECT COUNT(*) as count
            FROM anomaly_log
            WHERE resolved = 0
        """).fetchone()
        
        return jsonify({
            'total_agents': summaries['total_agents'] or 0,
            'active_agents': active_agents['count'] or 0,
            'stuck_agents': summaries['stuck_agents'] or 0,
            'total_events': summaries['total_events'] or 0,
            'total_tool_calls': summaries['total_tool_calls'] or 0,
            'total_cost': round(summaries['total_cost'] or 0, 4),
            'total_tokens_in': summaries['tokens_in'] or 0,
            'total_tokens_out': summaries['tokens_out'] or 0,
            'recent_events': recent['count'] or 0,
            'unresolved_anomalies': anomalies['count'] or 0
        })
    except Exception as e:
        return jsonify({'error': str(e)})
    finally:
        db.close()


# ============================================================================
# REAL API: Agents (from Watchtower DB)
# ============================================================================

@app.route('/api/agents')
def api_agents():
    """Get list of active agents - REAL DATA"""
    show_all = request.args.get('show_all', 'false').lower() == 'true'
    
    db = get_db()
    if not db:
        return jsonify({'agents': [], 'count': 0, 'error': 'Database not found'})
    
    try:
        now_ms = int(time.time() * 1000)
        
        if show_all:
            cursor = db.execute("""
                SELECT agent_id, agent_type, session_id, status, 
                       current_task, progress as progress_percent, updated_at as last_activity_ts,
                       total_events, 0 as total_tool_calls, 0 as total_cost,
                       0 as tokens_in, 0 as tokens_out, created_at, updated_at
                FROM agent_status
                ORDER BY updated_at DESC
                LIMIT 50
            """)
        else:
            thirty_min_ago = now_ms - (30 * 60 * 1000)
            cursor = db.execute("""
                SELECT agent_id, agent_type, session_id, status, 
                       current_task, progress as progress_percent, updated_at as last_activity_ts,
                       total_events, 0 as total_tool_calls, 0 as total_cost,
                       0 as tokens_in, 0 as tokens_out, created_at, updated_at
                FROM agent_status
                WHERE updated_at > ? AND status NOT IN ('completed', 'stuck')
                ORDER BY updated_at DESC
                LIMIT 50
            """, (thirty_min_ago,))
        
        agents = []
        for row in cursor:
            agent = dict(row)
            agent['age_seconds'] = (now_ms - (row['last_activity_ts'] or now_ms)) / 1000
            agents.append(agent)
        
        return jsonify({'agents': agents, 'count': len(agents)})
    except Exception as e:
        return jsonify({'agents': [], 'count': 0, 'error': str(e)})
    finally:
        db.close()


# ============================================================================
# REAL API: Agent Registry (from Clawdbot config + Agents folder)
# ============================================================================

def load_clawdbot_config():
    """Load clawdbot.json config"""
    try:
        if CLAWDBOT_CONFIG.exists():
            return json.loads(CLAWDBOT_CONFIG.read_text())
    except Exception as e:
        print(f"Error loading clawdbot config: {e}")
    return {}


def get_active_sessions():
    """Get active Clawdbot sessions via CLI"""
    try:
        env = os.environ.copy()
        env['PATH'] = '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:' + env.get('PATH', '')
        result = subprocess.run(
            ['/opt/homebrew/bin/clawdbot', 'sessions', 'list', '--active-minutes=30', '--json'],
            capture_output=True,
            text=True,
            timeout=10,
            env=env
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data.get('sessions', [])
    except Exception as e:
        print(f"Error getting active sessions: {e}")
    return []


# ============================================================================
# Prompt Version History
# ============================================================================

def create_prompt_backup(file_path: Path, max_versions: int = 10):
    """
    Create a versioned backup of a prompt file before overwriting.
    
    Saves to .history/ folder with format: FILENAME.YYYY-MM-DDTHHMMSS.bak
    Keeps only the last `max_versions` backups.
    
    TODO (future enhancements):
    - Add UI to view/restore old versions
    - Optional Git integration for version control
    - Settings toggle for GitHub sync
    """
    if not file_path.exists():
        return None  # Nothing to back up
    
    try:
        # Create .history directory in same folder as the file
        history_dir = file_path.parent / '.history'
        history_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime('%Y-%m-%dT%H%M%S')
        backup_name = f"{file_path.name}.{timestamp}.bak"
        backup_path = history_dir / backup_name
        
        # Copy current file to backup
        import shutil
        shutil.copy2(file_path, backup_path)
        
        # Clean up old versions - keep only last `max_versions`
        backups = sorted(
            history_dir.glob(f"{file_path.name}.*.bak"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        for old_backup in backups[max_versions:]:
            try:
                old_backup.unlink()
            except Exception:
                pass  # Ignore cleanup errors
        
        return str(backup_path)
    except Exception as e:
        # Log but don't fail the save operation
        print(f"Warning: Failed to create backup for {file_path}: {e}")
        return None


def find_agent_prompt_paths(agent_id, cfg, defaults):
    """
    Find AGENTS.md and SOUL.md paths for an agent.
    Priority:
    1. agentDir if specified
    2. workspace/agents/{agent_id}/ if exists
    3. Default workspace (shared)
    """
    paths = {'agents_md': None, 'soul_md': None, 'combined_size': 0, 'modified': None}
    
    # Get agent's workspace and agentDir
    agent_dir = cfg.get('agentDir')
    workspace = cfg.get('workspace') or defaults.get('workspace', str(Path.home() / 'clawd'))
    
    # Candidate directories to check (in priority order)
    candidate_dirs = []
    
    # 1. agentDir if specified
    if agent_dir:
        candidate_dirs.append(Path(agent_dir))
    
    # 2. workspace/agents/{agent_id}/ 
    workspace_agent_dir = Path(workspace) / 'agents' / agent_id
    if workspace_agent_dir.exists():
        candidate_dirs.append(workspace_agent_dir)
    
    # 3. Default shared workspace
    candidate_dirs.append(Path(workspace))
    
    for dir_path in candidate_dirs:
        agents_md = dir_path / 'AGENTS.md'
        soul_md = dir_path / 'SOUL.md'
        
        if agents_md.exists():
            try:
                stat = agents_md.stat()
                paths['agents_md'] = str(agents_md)
                paths['combined_size'] = stat.st_size
                paths['modified'] = int(stat.st_mtime * 1000)
                
                # Also check for SOUL.md in same directory
                if soul_md.exists():
                    soul_stat = soul_md.stat()
                    paths['soul_md'] = str(soul_md)
                    paths['combined_size'] += soul_stat.st_size
                    # Use most recent modified time
                    paths['modified'] = max(paths['modified'], int(soul_stat.st_mtime * 1000))
                
                break  # Found prompt files, stop searching
            except Exception:
                continue
    
    return paths


@app.route('/api/agents/registry')
def api_agents_registry():
    """Get all configured and discovered agents - REAL DATA"""
    config = load_clawdbot_config()
    configured_agents = config.get('agents', {}).get('list', [])
    defaults = config.get('agents', {}).get('defaults', {})
    
    config_map = {a.get('id', '').lower(): a for a in configured_agents}
    
    # Get active sessions to determine which agents are active
    active_sessions = get_active_sessions()
    active_agent_ids = set()
    for session in active_sessions:
        key = session.get('key', '')
        parts = key.split(':')
        if len(parts) >= 2 and parts[0] == 'agent':
            active_agent_ids.add(parts[1].lower())
    
    agents = []
    for agent_id in sorted(config_map.keys()):
        cfg = config_map.get(agent_id, {})
        
        # Find prompt paths for this agent
        prompt_paths = find_agent_prompt_paths(agent_id, cfg, defaults)
        
        model = cfg.get('model', {}).get('primary') or defaults.get('model', {}).get('primary') or 'unknown'
        
        # Determine status - check if agent is actively running
        if agent_id in active_agent_ids:
            status = 'active'
        else:
            status = 'available'
        
        description = cfg.get('description', f"{agent_id.title()} agent")
        
        agents.append({
            'id': agent_id,
            'status': status,
            'model': model,
            'description': description,
            'systemPromptPath': prompt_paths.get('agents_md'),
            'soulPromptPath': prompt_paths.get('soul_md'),
            'promptSize': prompt_paths.get('combined_size', 0),
            'promptModified': prompt_paths.get('modified'),
            'configured': True,
            'thinkingMode': cfg.get('thinkingMode'),
            'thinkingBudget': cfg.get('thinkingBudget'),
            'workspace': cfg.get('workspace') or defaults.get('workspace'),
            'agentDir': cfg.get('agentDir'),
        })
    
    active_count = sum(1 for a in agents if a['status'] == 'active')
    available_count = sum(1 for a in agents if a['status'] == 'available')
    
    return jsonify({
        'agents': agents,
        'total': len(agents),
        'active': active_count,
        'available': available_count,
        'configured': len(agents),
        'unconfigured': 0
    })


@app.route('/api/agents/<agent_id>/prompt', methods=['GET', 'POST'])
def api_agent_prompt(agent_id):
    """Get or update system prompt content for an agent"""
    config = load_clawdbot_config()
    configured_agents = config.get('agents', {}).get('list', [])
    defaults = config.get('agents', {}).get('defaults', {})
    
    # Find the agent config
    cfg = next((a for a in configured_agents if a.get('id', '').lower() == agent_id.lower()), {})
    
    # Find prompt paths
    prompt_paths = find_agent_prompt_paths(agent_id.lower(), cfg, defaults)
    
    if request.method == 'POST':
        # Handle saving prompt content
        data = request.get_json() or {}
        
        # Determine which file to save
        file_type = data.get('type', 'agents')  # 'agents' or 'soul'
        content = data.get('content', '')
        
        if file_type == 'soul':
            path_str = prompt_paths.get('soul_md')
            if not path_str:
                # Create SOUL.md in same dir as AGENTS.md
                agents_path = prompt_paths.get('agents_md')
                if agents_path:
                    path_str = str(Path(agents_path).parent / 'SOUL.md')
                else:
                    return jsonify({'error': 'Cannot determine path for SOUL.md'}), 400
        else:
            path_str = prompt_paths.get('agents_md')
            if not path_str:
                # Create default path
                workspace = cfg.get('workspace') or defaults.get('workspace', str(Path.home() / 'clawd'))
                agent_dir = cfg.get('agentDir')
                if agent_dir:
                    path_str = str(Path(agent_dir) / 'AGENTS.md')
                else:
                    path_str = str(Path(workspace) / 'agents' / agent_id / 'AGENTS.md')
        
        try:
            path = Path(path_str)
            # Create parent directories if needed
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Create versioned backup before overwriting
            backup_path = create_prompt_backup(path)
            
            path.write_text(content)
            
            stat = path.stat()
            return jsonify({
                'success': True,
                'path': str(path),
                'size': stat.st_size,
                'modified': int(stat.st_mtime * 1000),
                'backup': backup_path  # Include backup path in response
            })
        except Exception as e:
            return jsonify({'error': f'Failed to save prompt: {e}'}), 500
    
    # GET request - return prompt content
    agents_md_path = prompt_paths.get('agents_md')
    soul_md_path = prompt_paths.get('soul_md')
    
    if not agents_md_path:
        return jsonify({
            'id': agent_id,
            'error': 'No prompt files found',
            'hint': 'This agent uses the shared workspace prompts or has no custom prompts.',
            'agents_md': None,
            'soul_md': None
        }), 200  # Return 200 with empty data, not 404
    
    try:
        # Read AGENTS.md
        agents_content = ''
        agents_meta = {}
        if agents_md_path and Path(agents_md_path).exists():
            content = Path(agents_md_path).read_text()
            stat = Path(agents_md_path).stat()
            agents_content = content
            agents_meta = {
                'path': agents_md_path,
                'size': stat.st_size,
                'modified': int(stat.st_mtime * 1000),
                'wordCount': len(content.split()),
                'charCount': len(content)
            }
        
        # Read SOUL.md
        soul_content = ''
        soul_meta = {}
        if soul_md_path and Path(soul_md_path).exists():
            content = Path(soul_md_path).read_text()
            stat = Path(soul_md_path).stat()
            soul_content = content
            soul_meta = {
                'path': soul_md_path,
                'size': stat.st_size,
                'modified': int(stat.st_mtime * 1000),
                'wordCount': len(content.split()),
                'charCount': len(content)
            }
        
        return jsonify({
            'id': agent_id,
            'agents_md': {
                'content': agents_content,
                'metadata': agents_meta
            } if agents_content else None,
            'soul_md': {
                'content': soul_content,
                'metadata': soul_meta
            } if soul_content else None,
            # Legacy fields for backward compatibility
            'content': agents_content,
            'path': agents_md_path,
            'metadata': agents_meta
        })
    except Exception as e:
        return jsonify({'error': f'Failed to read prompt: {e}'}), 500


# ============================================================================
# Skills API
# ============================================================================

@app.route('/api/skills')
def api_skills():
    """Get all available skills from mock data."""
    skills_file = Path(__file__).parent / 'static' / 'data' / 'skills.json'
    
    if not skills_file.exists():
        return jsonify({'skills': [], 'error': 'Skills data not found'})
    
    try:
        with open(skills_file, 'r') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({'skills': [], 'error': str(e)})


# ============================================================================
# REAL API: Activity Feed (from Watchtower DB)
# ============================================================================

@app.route('/api/activity')
def api_activity():
    """Get activity feed with optional filters - REAL DATA"""
    limit = request.args.get('limit', 50, type=int)
    agent_type = request.args.get('agent_type')
    event_type = request.args.get('event_type')
    severity = request.args.get('severity')
    agent_id = request.args.get('agent_id')
    
    db = get_db()
    if not db:
        return jsonify({'events': [], 'count': 0, 'error': 'Database not found'})
    
    try:
        filters = []
        params = []
        
        if agent_type:
            filters.append("agent_type = ?")
            params.append(agent_type)
        if event_type:
            filters.append("event_type = ?")
            params.append(event_type)
        if severity:
            filters.append("severity = ?")
            params.append(severity)
        if agent_id:
            filters.append("agent_id = ?")
            params.append(agent_id)
        
        where = "WHERE " + " AND ".join(filters) if filters else ""
        
        cursor = db.execute(f"""
            SELECT id, timestamp, agent_id, agent_type, session_id,
                   event_type, tool_name, display_text, severity,
                   tokens_used, cost
            FROM activity_feed
            {where}
            ORDER BY timestamp DESC
            LIMIT ?
        """, params + [limit])
        
        events = []
        for row in cursor:
            event = dict(row)
            # Format timestamp for display
            if event.get('timestamp'):
                ts = event['timestamp'] / 1000
                event['time_ago'] = format_time_ago(ts)
            events.append(event)
        
        return jsonify({'events': events, 'count': len(events)})
    except Exception as e:
        return jsonify({'events': [], 'count': 0, 'error': str(e)})
    finally:
        db.close()


def format_time_ago(timestamp):
    """Format timestamp as human-readable time ago"""
    now = time.time()
    diff = now - timestamp
    
    if diff < 60:
        return f"{int(diff)}s ago"
    elif diff < 3600:
        return f"{int(diff/60)}m ago"
    elif diff < 86400:
        return f"{int(diff/3600)}h ago"
    else:
        return f"{int(diff/86400)}d ago"


# ============================================================================
# REAL API: Anomalies (from Watchtower DB)
# ============================================================================

@app.route('/api/anomalies')
def api_anomalies():
    """Get anomalies - REAL DATA"""
    resolved = request.args.get('resolved', 'false').lower() == 'true'
    limit = request.args.get('limit', 100, type=int)
    
    db = get_db()
    if not db:
        return jsonify({'anomalies': [], 'count': 0, 'error': 'Database not found'})
    
    try:
        cursor = db.execute("""
            SELECT id, timestamp, agent_id, anomaly_type, severity,
                   description, alerted, resolved, resolved_at
            FROM anomaly_log
            WHERE resolved = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (1 if resolved else 0, limit))
        
        anomalies = []
        for row in cursor:
            anomaly = dict(row)
            if anomaly.get('timestamp'):
                anomaly['time_ago'] = format_time_ago(anomaly['timestamp'] / 1000)
            anomalies.append(anomaly)
        
        return jsonify({'anomalies': anomalies, 'count': len(anomalies)})
    except Exception as e:
        return jsonify({'anomalies': [], 'count': 0, 'error': str(e)})
    finally:
        db.close()


# ============================================================================
# REAL API: Tasks/Kanban (from Watchtower DB + TODO.md)
# ============================================================================

@app.route('/api/tasks')
def api_tasks():
    """Get tasks with optional filters - REAL DATA"""
    status = request.args.get('status')
    category = request.args.get('category')
    priority = request.args.get('priority')
    
    db = get_db()
    if not db:
        return jsonify({'tasks': [], 'count': 0, 'error': 'Database not found'})
    
    try:
        filters = []
        params = []
        
        if status:
            filters.append("status = ?")
            params.append(status)
        if category:
            filters.append("category = ?")
            params.append(category)
        if priority:
            filters.append("priority = ?")
            params.append(priority)
        
        where = "WHERE " + " AND ".join(filters) if filters else ""
        
        cursor = db.execute(f"""
            SELECT * FROM tasks
            {where}
            ORDER BY 
                CASE priority 
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    WHEN 'low' THEN 3
                END,
                created_at DESC
        """, params)
        
        tasks = [dict(row) for row in cursor]
        return jsonify({'tasks': tasks, 'count': len(tasks)})
    except Exception as e:
        return jsonify({'tasks': [], 'count': 0, 'error': str(e)})
    finally:
        db.close()


@app.route('/api/todo')
def api_todo():
    """Get TODO.md content - REAL DATA"""
    try:
        if not TODO_FILE_PATH.exists():
            return jsonify({
                'content': '# TODO\n\nNo TODO.md file found.',
                'exists': False,
                'path': str(TODO_FILE_PATH),
                'modified': None,
                'size': 0
            })
        
        content = TODO_FILE_PATH.read_text(errors='replace')
        stat = TODO_FILE_PATH.stat()
        
        return jsonify({
            'content': content,
            'exists': True,
            'path': str(TODO_FILE_PATH),
            'modified': int(stat.st_mtime * 1000),
            'size': stat.st_size,
            'wordCount': len(content.split()),
            'lineCount': content.count('\n') + 1
        })
    except Exception as e:
        return jsonify({'error': f'Failed to read TODO.md: {e}'}), 500


# ============================================================================
# REAL API: Docs Tree (from workspace)
# ============================================================================

def is_generated_doc(filepath):
    """Check if a file is a generated document (not a workspace file)"""
    return filepath.name not in WORKSPACE_FILES


def build_folder_tree(root, prefix=""):
    """Build folder tree recursively"""
    items = []
    SKIP_DIRS = {'node_modules', 'target', 'dist', 'build', '__pycache__', 'venv', '.venv', '.git'}
    
    if not root.exists() or not root.is_dir():
        return items
    
    try:
        entries = sorted(root.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        
        for entry in entries:
            if entry.name.startswith('.') or entry.name in SKIP_DIRS:
                continue
            
            rel_path = f"{prefix}/{entry.name}" if prefix else entry.name
            
            if entry.is_dir():
                children = build_folder_tree(entry, rel_path)
                if children:
                    items.append({
                        'name': entry.name,
                        'type': 'folder',
                        'path': rel_path,
                        'children': children,
                        'fileCount': count_files_in_tree(children)
                    })
            elif entry.suffix.lower() in ['.md', '.txt', '.json', '.py']:
                try:
                    stat = entry.stat()
                    items.append({
                        'name': entry.name,
                        'type': 'file',
                        'path': rel_path,
                        'size': stat.st_size,
                        'modified': int(stat.st_mtime * 1000)
                    })
                except Exception:
                    pass
    except PermissionError:
        pass
    
    return items


def count_files_in_tree(items):
    """Count total files in a tree"""
    count = 0
    for item in items:
        if item['type'] == 'file':
            count += 1
        elif item['type'] == 'folder' and 'children' in item:
            count += count_files_in_tree(item['children'])
    return count


def build_generated_docs_tree():
    """Build tree of all generated documents from configured sources"""
    tree = []
    
    # 1. Research folder
    research_dir = WORKSPACE_PATH / "research"
    if research_dir.exists():
        research_items = build_folder_tree(research_dir, "research")
        if research_items:
            tree.append({
                'name': 'research',
                'type': 'folder',
                'path': 'research',
                'icon': '🔬',
                'children': research_items,
                'fileCount': count_files_in_tree(research_items)
            })
    
    # 2. ResonantOS folder
    resonant_dir = WORKSPACE_PATH / "ResonantOS"
    if resonant_dir.exists():
        resonant_items = build_folder_tree(resonant_dir, "ResonantOS")
        if resonant_items:
            tree.append({
                'name': 'ResonantOS',
                'type': 'folder',
                'path': 'ResonantOS',
                'icon': '🧠',
                'children': resonant_items,
                'fileCount': count_files_in_tree(resonant_items)
            })
    
    # 3. Watchtower folder
    watchtower_dir = WORKSPACE_PATH / "watchtower"
    if watchtower_dir.exists():
        watchtower_items = []
        for f in sorted(watchtower_dir.glob("*.md")):
            try:
                stat = f.stat()
                watchtower_items.append({
                    'name': f.name,
                    'type': 'file',
                    'path': f"watchtower/{f.name}",
                    'size': stat.st_size,
                    'modified': int(stat.st_mtime * 1000)
                })
            except Exception:
                pass
        if watchtower_items:
            tree.append({
                'name': 'watchtower',
                'type': 'folder',
                'path': 'watchtower',
                'icon': '🗼',
                'children': watchtower_items,
                'fileCount': len(watchtower_items)
            })
    
    # 4. Archive folder
    archive_dir = WORKSPACE_PATH / "archive"
    if archive_dir.exists():
        archive_items = build_folder_tree(archive_dir, "archive")
        if archive_items:
            tree.append({
                'name': 'archive',
                'type': 'folder',
                'path': 'archive',
                'icon': '📚',
                'children': archive_items,
                'fileCount': count_files_in_tree(archive_items)
            })
    
    # 5. Root-level generated docs
    root_docs = []
    for f in sorted(WORKSPACE_PATH.glob("*.md")):
        if is_generated_doc(f):
            try:
                stat = f.stat()
                root_docs.append({
                    'name': f.name,
                    'type': 'file',
                    'path': f.name,
                    'size': stat.st_size,
                    'modified': int(stat.st_mtime * 1000)
                })
            except Exception:
                pass
    if root_docs:
        tree.append({
            'name': 'root',
            'type': 'folder',
            'path': '',
            'icon': '📄',
            'children': root_docs,
            'fileCount': len(root_docs)
        })
    
    # 6. Projects folder
    projects_dir = WORKSPACE_PATH / "projects"
    if projects_dir.exists():
        projects_items = build_folder_tree(projects_dir, "projects")
        if projects_items:
            tree.append({
                'name': 'projects',
                'type': 'folder',
                'path': 'projects',
                'icon': '🚀',
                'children': projects_items,
                'fileCount': count_files_in_tree(projects_items)
            })
    
    return tree


@app.route('/api/docs/tree')
def api_docs_tree():
    """Get generated documents folder structure - REAL DATA"""
    tree = build_generated_docs_tree()
    total_files = sum(item.get('fileCount', 0) for item in tree)
    return jsonify({
        'tree': tree,
        'root': str(WORKSPACE_PATH),
        'totalFiles': total_files
    })


@app.route('/api/docs/file')
def api_docs_file():
    """Get single document content - REAL DATA"""
    path = request.args.get('path', '')
    
    if path.startswith('/'):
        filepath = Path(path)
    else:
        filepath = WORKSPACE_PATH / path
    
    # Security check
    try:
        resolved = filepath.resolve()
        if not resolved.is_relative_to(WORKSPACE_PATH.resolve()):
            return jsonify({'error': 'Access denied: path outside workspace'}), 403
    except Exception:
        return jsonify({'error': 'Invalid path'}), 403
    
    if not filepath.exists():
        return jsonify({'error': 'File not found'}), 404
    
    if not filepath.is_file():
        return jsonify({'error': 'Path is not a file'}), 400
    
    try:
        content = filepath.read_text(errors='replace')
        stat = filepath.stat()
        
        # Extract title from markdown
        title = filepath.stem
        for line in content.split('\n')[:10]:
            if line.startswith('# '):
                title = line[2:].strip()
                break
        
        return jsonify({
            'path': path,
            'name': filepath.name,
            'title': title,
            'content': content,
            'size': stat.st_size,
            'modified': int(stat.st_mtime * 1000),
            'wordCount': len(content.split()),
            'lineCount': content.count('\n') + 1
        })
    except Exception as e:
        return jsonify({'error': f'Failed to read file: {e}'}), 500


@app.route('/api/docs/open-in-editor', methods=['POST'])
def api_docs_open_in_editor():
    """Open a document in the default editor"""
    data = request.get_json() or {}
    path = data.get('path', '')
    
    if not path:
        return jsonify({'error': 'No path provided'}), 400
    
    # Resolve path
    if path.startswith('/'):
        filepath = Path(path)
    else:
        filepath = WORKSPACE_PATH / path
    
    # Security check
    try:
        resolved = filepath.resolve()
        if not resolved.is_relative_to(WORKSPACE_PATH.resolve()):
            return jsonify({'error': 'Access denied: path outside workspace'}), 403
    except Exception:
        return jsonify({'error': 'Invalid path'}), 403
    
    if not filepath.exists():
        return jsonify({'error': 'File not found'}), 404
    
    try:
        # Try VS Code first, then fall back to system open
        import shutil
        if shutil.which('code'):
            subprocess.Popen(['code', str(filepath)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return jsonify({'success': True, 'editor': 'VS Code', 'path': str(filepath)})
        else:
            # macOS open command
            subprocess.Popen(['open', str(filepath)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return jsonify({'success': True, 'editor': 'system default', 'path': str(filepath)})
    except Exception as e:
        return jsonify({'error': f'Failed to open editor: {e}'}), 500


@app.route('/api/docs/search/semantic')
def api_docs_search_semantic():
    """AI-powered fuzzy search with smart matching and relevance scoring"""
    import re
    from difflib import SequenceMatcher
    
    q = request.args.get('q', '')
    if len(q) < 2:
        return jsonify({'results': [], 'query': q, 'count': 0, 'error': 'Query too short'})
    
    results = []
    query_words = q.lower().split()
    
    def calculate_relevance(content: str, filepath: str) -> float:
        """Calculate relevance score based on multiple factors"""
        content_lower = content.lower()
        filename_lower = filepath.lower()
        score = 0.0
        
        # 1. Exact phrase match (highest weight)
        if q.lower() in content_lower:
            score += 50.0
        
        # 2. All words present (high weight)
        words_found = sum(1 for w in query_words if w in content_lower)
        score += (words_found / len(query_words)) * 30.0
        
        # 3. Words in filename (bonus)
        filename_words = sum(1 for w in query_words if w in filename_lower)
        score += filename_words * 10.0
        
        # 4. Word proximity - words close together score higher
        for i, word in enumerate(query_words):
            if word in content_lower:
                for match in re.finditer(re.escape(word), content_lower):
                    pos = match.start()
                    nearby = content_lower[max(0, pos-100):pos+100]
                    nearby_count = sum(1 for w in query_words if w in nearby)
                    score += nearby_count * 2.0
        
        # 5. Fuzzy matching for typos/variations
        for word in query_words:
            content_words = set(re.findall(r'\b\w+\b', content_lower))
            for cword in content_words:
                if len(cword) > 3:  # Skip short words
                    ratio = SequenceMatcher(None, word, cword).ratio()
                    if ratio > 0.8 and ratio < 1.0:
                        score += ratio * 5.0
        
        return score
    
    def get_smart_snippet(content: str, max_length: int = 300) -> tuple:
        """Find the most relevant snippet containing query terms"""
        lines = content.split('\n')
        best_line_idx = 0
        best_score = 0
        
        for i, line in enumerate(lines):
            line_lower = line.lower()
            line_score = sum(1 for w in query_words if w in line_lower)
            if q.lower() in line_lower:
                line_score += 5
            if line_score > best_score:
                best_score = line_score
                best_line_idx = i
        
        start = max(0, best_line_idx - 1)
        end = min(len(lines), best_line_idx + 3)
        snippet = '\n'.join(lines[start:end])
        
        if len(snippet) > max_length:
            snippet = snippet[:max_length] + '...'
        
        return snippet, best_line_idx + 1
    
    # Search through all docs
    docs_sources = [
        ('research', WORKSPACE_PATH / 'research'),
        ('ResonantOS', WORKSPACE_PATH / 'ResonantOS'),
        ('watchtower', WORKSPACE_PATH / 'watchtower'),
        ('projects', WORKSPACE_PATH / 'projects'),
    ]
    
    for source_name, source_path in docs_sources:
        if not source_path.exists():
            continue
        
        for filepath in source_path.rglob('*.md'):
            try:
                content = filepath.read_text(errors='replace')
                rel_path = str(filepath.relative_to(WORKSPACE_PATH))
                
                score = calculate_relevance(content, rel_path)
                
                if score < 5.0:
                    continue
                
                snippet, line_num = get_smart_snippet(content)
                
                title = filepath.stem
                for line in content.split('\n')[:5]:
                    if line.startswith('# '):
                        title = line[2:].strip()
                        break
                
                results.append({
                    'path': rel_path,
                    'name': filepath.name,
                    'title': title,
                    'matches': [{
                        'line': line_num,
                        'text': snippet[:200],
                        'snippet': snippet
                    }],
                    'matchCount': 1,
                    'score': round(score, 2)
                })
                
            except Exception:
                continue
    
    results.sort(key=lambda x: x['score'], reverse=True)
    
    return jsonify({
        'query': q,
        'mode': 'semantic',
        'results': results[:20],
        'count': len(results)
    })


@app.route('/api/docs/search')
def api_docs_search():
    """Search all generated documents - REAL DATA"""
    q = request.args.get('q', '')
    if len(q) < 2:
        return jsonify({'results': [], 'query': q, 'count': 0, 'error': 'Query too short'})
    
    results = []
    search_term = q.lower()
    
    def search_file(filepath, rel_path):
        try:
            content = filepath.read_text(errors='replace')
            lines = content.split('\n')
            matches = []
            
            for i, line in enumerate(lines):
                if search_term in line.lower():
                    start = max(0, i - 1)
                    end = min(len(lines), i + 2)
                    context_lines = lines[start:end]
                    
                    matches.append({
                        'line': i + 1,
                        'text': line.strip()[:200],
                        'snippet': '\n'.join(context_lines)[:300]
                    })
                    if len(matches) >= 5:
                        break
            
            if matches:
                title = filepath.stem
                for line in content.split('\n')[:10]:
                    if line.startswith('# '):
                        title = line[2:].strip()
                        break
                
                results.append({
                    'path': rel_path,
                    'name': filepath.name,
                    'title': title,
                    'matches': matches,
                    'matchCount': len(matches)
                })
        except Exception:
            pass
    
    # Search in all document sources
    search_dirs = [
        (WORKSPACE_PATH / "research", "research"),
        (WORKSPACE_PATH / "ResonantOS", "ResonantOS"),
        (WORKSPACE_PATH / "watchtower", "watchtower"),
    ]
    
    for search_dir, prefix in search_dirs:
        if search_dir.exists():
            for filepath in search_dir.rglob("*.md"):
                if len(results) >= 30:
                    break
                rel_path = f"{prefix}/{filepath.relative_to(search_dir)}"
                search_file(filepath, rel_path)
    
    # Search root-level docs
    for filepath in WORKSPACE_PATH.glob("*.md"):
        if len(results) >= 30:
            break
        if is_generated_doc(filepath):
            search_file(filepath, filepath.name)
    
    results.sort(key=lambda x: x['matchCount'], reverse=True)
    
    return jsonify({'results': results, 'query': q, 'count': len(results)})


# ============================================================================
# Legacy API Routes (for backwards compatibility with existing templates)
# ============================================================================

@app.route('/api/status')
def api_status():
    """Get system status - combines real data with system info"""
    stats = api_stats().get_json()
    
    # Get real system metrics with psutil
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        boot_time = psutil.boot_time()
        uptime_seconds = time.time() - boot_time
        
        # Format uptime
        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        uptime_str = f"{days}d {hours}h {minutes}m"
    except Exception as e:
        cpu_percent = 0
        memory = type('obj', (object,), {'percent': 0})()
        disk = type('obj', (object,), {'percent': 0})()
        uptime_str = "unknown"
    
    # Get gateway status
    gateway_status = 'unknown'
    try:
        result = subprocess.run(
            ['/opt/homebrew/bin/clawdbot', 'gateway', 'status'],
            capture_output=True, text=True, timeout=5
        )
        if 'running' in result.stdout.lower():
            gateway_status = 'running'
        elif 'stopped' in result.stdout.lower():
            gateway_status = 'stopped'
    except:
        pass
    
    return jsonify({
        "cpu": round(cpu_percent, 1),
        "memory": round(memory.percent, 1),
        "disk": round(disk.percent, 1),
        "uptime": uptime_str,
        "clawdbotVersion": "0.4.x",
        "resonantosVersion": "3.0.0",
        "gateway": gateway_status,
        "agents": {
            "total": stats.get('total_agents', 0),
            "active": stats.get('active_agents', 0),
            "stuck": stats.get('stuck_agents', 0)
        },
        "events": {
            "total": stats.get('total_events', 0),
            "recent": stats.get('recent_events', 0)
        },
        "anomalies": stats.get('unresolved_anomalies', 0)
    })


@app.route('/api/shield/status')
def api_shield_status():
    """Get Symbiotic Shield status"""
    if not SHIELD_AVAILABLE:
        return jsonify({
            "available": False,
            "active": False,
            "mode": None,
            "error": "Shield module not installed"
        })
    
    try:
        shield = get_shield()
        stats = shield.get_stats()
        
        return jsonify({
            "available": True,
            "active": True,
            "mode": shield.config.intervention_mode.value,
            "components": {
                "scanner": shield.scanner is not None,
                "classifier": shield.classifier is not None,
                "a2a_monitor": shield.a2a_monitor is not None,
                "vigil": shield.vigil is not None and shield.vigil.is_available
            },
            "stats": {
                "total_alerts": stats.get("total_alerts", 0),
                "alerts_by_severity": stats.get("alerts_by_severity", {}),
            },
            "config": {
                "sensitivity_threshold": shield.config.sensitivity_threshold,
                "enable_scanner": shield.config.enable_scanner,
                "enable_classifier": shield.config.enable_classifier,
                "enable_a2a_monitor": shield.config.enable_a2a_monitor
            }
        })
    except Exception as e:
        return jsonify({
            "available": True,
            "active": False,
            "mode": None,
            "error": str(e)
        })


@app.route('/api/metrics')
def api_metrics():
    """Get metrics - returns real event counts over time based on period"""
    db = get_db()
    if not db:
        return jsonify({'error': 'Database not found'})
    
    period = request.args.get('period', '24h')
    
    # Define period configs: (num_buckets, bucket_duration_hours, total_hours)
    period_configs = {
        '12h': (12, 1, 12),      # 12 hourly buckets
        '24h': (24, 1, 24),      # 24 hourly buckets
        '7d': (7, 24, 168),      # 7 daily buckets
        '30d': (30, 24, 720),    # 30 daily buckets
        '90d': (30, 72, 2160),   # 30 buckets of 3 days each
    }
    
    config = period_configs.get(period, period_configs['24h'])
    num_buckets, bucket_hours, total_hours = config
    
    try:
        now = datetime.now()
        events = []
        
        for i in range(num_buckets):
            bucket_start = now - timedelta(hours=total_hours - i * bucket_hours)
            bucket_end = now - timedelta(hours=total_hours - (i + 1) * bucket_hours)
            
            start_ts = int(bucket_start.timestamp() * 1000)
            end_ts = int(bucket_end.timestamp() * 1000)
            
            count = db.execute("""
                SELECT COUNT(*) as count FROM activity_feed
                WHERE timestamp >= ? AND timestamp < ?
            """, (start_ts, end_ts)).fetchone()['count']
            
            events.append({
                'time': bucket_start.isoformat(),
                'value': count
            })
        
        return jsonify({
            'events': events,
            'period': period,
            'total': sum(e['value'] for e in events)
        })
    except Exception as e:
        return jsonify({'error': str(e)})
    finally:
        db.close()


# ============================================================================
# Chatbots Database & API
# ============================================================================

CHATBOTS_DB = CLAWD_DIR / 'projects' / 'resonantos-v3' / 'dashboard' / 'chatbots.db'

def get_chatbots_db():
    """Get chatbots database connection, create tables if needed"""
    db = sqlite3.connect(str(CHATBOTS_DB), check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=5000")
    
    # Create tables if they don't exist
    db.executescript("""
        CREATE TABLE IF NOT EXISTS chatbots (
            id TEXT PRIMARY KEY,
            user_id TEXT DEFAULT 'default',
            name TEXT NOT NULL,
            system_prompt TEXT,
            greeting TEXT DEFAULT 'Hi! How can I help you today?',
            suggested_prompts TEXT DEFAULT '[]',
            position TEXT DEFAULT 'bottom-right',
            theme TEXT DEFAULT 'dark',
            primary_color TEXT DEFAULT '#4ade80',
            bg_color TEXT DEFAULT '#1a1a1a',
            text_color TEXT DEFAULT '#e0e0e0',
            allowed_domains TEXT DEFAULT '',
            rate_per_minute INTEGER DEFAULT 10,
            rate_per_hour INTEGER DEFAULT 100,
            enable_analytics INTEGER DEFAULT 1,
            show_watermark INTEGER DEFAULT 1,
            status TEXT DEFAULT 'active',
            api_type TEXT DEFAULT 'internal',
            api_key_encrypted TEXT,
            model_id TEXT DEFAULT 'claude-sonnet',
            icon_url TEXT DEFAULT '',
            last_used_at INTEGER,
            created_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
            updated_at INTEGER DEFAULT (strftime('%s', 'now') * 1000)
        );
        
        CREATE TABLE IF NOT EXISTS chatbot_conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chatbot_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            started_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
            ended_at INTEGER,
            message_count INTEGER DEFAULT 0,
            satisfaction_rating INTEGER,
            FOREIGN KEY (chatbot_id) REFERENCES chatbots(id)
        );
        
        CREATE TABLE IF NOT EXISTS chatbot_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp INTEGER DEFAULT (strftime('%s', 'now') * 1000),
            FOREIGN KEY (conversation_id) REFERENCES chatbot_conversations(id)
        );
        
        CREATE TABLE IF NOT EXISTS licenses (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            chatbot_id TEXT,
            tier TEXT DEFAULT 'free',
            features TEXT DEFAULT '[]',
            stripe_subscription_id TEXT,
            stripe_customer_id TEXT,
            expires_at INTEGER,
            created_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
            updated_at INTEGER DEFAULT (strftime('%s', 'now') * 1000)
        );
        
        CREATE TABLE IF NOT EXISTS knowledge_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chatbot_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            content TEXT,
            file_size INTEGER,
            uploaded_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
            FOREIGN KEY (chatbot_id) REFERENCES chatbots(id)
        );
        
        CREATE INDEX IF NOT EXISTS idx_conversations_chatbot ON chatbot_conversations(chatbot_id);
        CREATE INDEX IF NOT EXISTS idx_messages_conversation ON chatbot_messages(conversation_id);
        CREATE INDEX IF NOT EXISTS idx_licenses_user ON licenses(user_id);
    """)
    db.commit()
    
    # Migration: Add new columns if they don't exist (for existing databases)
    try:
        db.execute("ALTER TABLE chatbots ADD COLUMN api_type TEXT DEFAULT 'internal'")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        db.execute("ALTER TABLE chatbots ADD COLUMN api_key_encrypted TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("ALTER TABLE chatbots ADD COLUMN model_id TEXT DEFAULT 'claude-sonnet'")
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("ALTER TABLE chatbots ADD COLUMN last_used_at INTEGER")
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("ALTER TABLE chatbots ADD COLUMN icon_url TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    db.commit()
    
    return db


@app.route('/api/chatbots')
def api_chatbots():
    """Get all chatbots with real stats"""
    db = get_chatbots_db()
    try:
        # Get all chatbots
        chatbots = db.execute("""
            SELECT c.*,
                   COALESCE(conv.conversation_count, 0) as conversations,
                   COALESCE(conv.avg_satisfaction, 0) as satisfaction_rate
            FROM chatbots c
            LEFT JOIN (
                SELECT chatbot_id,
                       COUNT(*) as conversation_count,
                       AVG(satisfaction_rating) as avg_satisfaction
                FROM chatbot_conversations
                GROUP BY chatbot_id
            ) conv ON c.id = conv.chatbot_id
            ORDER BY c.created_at DESC
        """).fetchall()
        
        result = []
        total_conversations = 0
        total_satisfaction = 0
        active_count = 0
        
        for bot in chatbots:
            bot_dict = dict(bot)
            bot_dict['avgResponseTime'] = '< 2s'  # Placeholder for now
            result.append(bot_dict)
            total_conversations += bot_dict.get('conversations', 0)
            if bot_dict.get('satisfaction_rate'):
                total_satisfaction += bot_dict['satisfaction_rate']
            if bot_dict.get('status') == 'active':
                active_count += 1
        
        avg_satisfaction = total_satisfaction / len(result) if result else 0
        
        return jsonify({
            'chatbots': result,
            'total': len(result),
            'active': active_count,
            'totalConversations': total_conversations,
            'avgSatisfaction': round(avg_satisfaction, 1)
        })
    except Exception as e:
        return jsonify({
            'chatbots': [],
            'total': 0,
            'active': 0,
            'totalConversations': 0,
            'avgSatisfaction': 0,
            'error': str(e)
        })
    finally:
        db.close()


@app.route('/api/chatbots', methods=['POST'])
def api_create_chatbot():
    """Create a new chatbot with license limit enforcement"""
    data = request.json or {}
    db = get_chatbots_db()
    
    try:
        import uuid
        user_id = data.get('user_id', 'default')
        now_ms = int(time.time() * 1000)
        
        # ============================================================
        # LICENSE ENFORCEMENT: Check chatbot limit before creating
        # ============================================================
        license_row = db.execute("""
            SELECT tier FROM licenses 
            WHERE user_id = ? AND chatbot_id IS NULL
            AND (expires_at IS NULL OR expires_at > ?)
            ORDER BY tier DESC
            LIMIT 1
        """, (user_id, now_ms)).fetchone()
        
        tier = license_row['tier'] if license_row else 'free'
        limits = TIER_LIMITS.get(tier, TIER_LIMITS['free'])
        max_chatbots = limits['max_chatbots']
        
        # Count existing chatbots for this user
        count_row = db.execute("""
            SELECT COUNT(*) as count FROM chatbots WHERE user_id = ?
        """, (user_id,)).fetchone()
        current_count = count_row['count'] if count_row else 0
        
        if current_count >= max_chatbots:
            return jsonify({
                'success': False,
                'error': f'Chatbot limit reached. Your {tier} plan allows {max_chatbots} chatbot(s).',
                'currentCount': current_count,
                'maxAllowed': max_chatbots,
                'tier': tier,
                'upgradeRequired': True
            }), 403
        # ============================================================
        
        chatbot_id = str(uuid.uuid4())[:8]
        
        # Encrypt API key if provided
        api_key_encrypted = None
        if data.get('apiKey'):
            api_key_encrypted = encrypt_api_key(data['apiKey'])
        
        db.execute("""
            INSERT INTO chatbots (id, user_id, name, system_prompt, greeting, suggested_prompts,
                                  position, theme, primary_color, bg_color, text_color,
                                  allowed_domains, rate_per_minute, rate_per_hour,
                                  enable_analytics, show_watermark, api_type, api_key_encrypted, model_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            chatbot_id,
            user_id,  # Track owner for license enforcement
            data.get('name', 'My Chatbot'),
            data.get('systemPrompt', 'You are a helpful assistant.'),
            data.get('greeting', 'Hi! How can I help you today?'),
            json.dumps(data.get('suggestedPrompts', [])),
            data.get('position', 'bottom-right'),
            data.get('theme', 'dark'),
            data.get('primaryColor', '#4ade80'),
            data.get('bgColor', '#1a1a1a'),
            data.get('textColor', '#e0e0e0'),
            data.get('allowedDomains', ''),
            data.get('ratePerMinute', 10),
            data.get('ratePerHour', 100),
            1 if data.get('enableAnalytics', True) else 0,
            1 if data.get('showWatermark', True) else 0,
            data.get('apiType', 'internal'),
            api_key_encrypted,
            data.get('modelId', 'claude-sonnet')
        ))
        db.commit()
        
        return jsonify({
            'success': True, 
            'id': chatbot_id,
            'tier': tier,
            'remaining': max_chatbots - current_count - 1
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/chatbots/<chatbot_id>')
def api_get_chatbot(chatbot_id):
    """Get a specific chatbot"""
    db = get_chatbots_db()
    try:
        chatbot = db.execute("SELECT * FROM chatbots WHERE id = ?", (chatbot_id,)).fetchone()
        if not chatbot:
            return jsonify({'error': 'Chatbot not found'}), 404
        return jsonify(dict(chatbot))
    finally:
        db.close()


@app.route('/api/chatbots/<chatbot_id>', methods=['PUT'])
def api_update_chatbot(chatbot_id):
    """Update a chatbot"""
    data = request.json or {}
    db = get_chatbots_db()
    
    try:
        # Handle API key encryption if provided
        api_key_encrypted = None
        if 'apiKey' in data and data['apiKey']:
            api_key_encrypted = encrypt_api_key(data['apiKey'])
        
        # Build dynamic update
        updates = []
        params = []
        
        field_mapping = {
            'name': 'name',
            'systemPrompt': 'system_prompt',
            'greeting': 'greeting',
            'position': 'position',
            'theme': 'theme',
            'primaryColor': 'primary_color',
            'bgColor': 'bg_color',
            'textColor': 'text_color',
            'allowedDomains': 'allowed_domains',
            'ratePerMinute': 'rate_per_minute',
            'ratePerHour': 'rate_per_hour',
            'apiType': 'api_type',
            'modelId': 'model_id',
        }
        
        for json_key, db_key in field_mapping.items():
            if json_key in data:
                updates.append(f"{db_key} = ?")
                params.append(data[json_key])
        
        if 'suggestedPrompts' in data:
            updates.append("suggested_prompts = ?")
            params.append(json.dumps(data['suggestedPrompts']))
        
        if 'enableAnalytics' in data:
            updates.append("enable_analytics = ?")
            params.append(1 if data['enableAnalytics'] else 0)
        
        if 'showWatermark' in data:
            updates.append("show_watermark = ?")
            params.append(1 if data['showWatermark'] else 0)
        
        if api_key_encrypted:
            updates.append("api_key_encrypted = ?")
            params.append(api_key_encrypted)
        
        updates.append("updated_at = strftime('%s', 'now') * 1000")
        params.append(chatbot_id)
        
        db.execute(f"""
            UPDATE chatbots SET {', '.join(updates)}
            WHERE id = ?
        """, params)
        db.commit()
        return jsonify({'success': True, 'id': chatbot_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/chatbots/<chatbot_id>', methods=['DELETE'])
def api_delete_chatbot(chatbot_id):
    """Delete a chatbot"""
    db = get_chatbots_db()
    try:
        # Check if chatbot exists
        chatbot = db.execute("SELECT id FROM chatbots WHERE id = ?", (chatbot_id,)).fetchone()
        if not chatbot:
            return jsonify({'success': False, 'error': 'Chatbot not found'}), 404
        
        # Delete related records first
        db.execute("DELETE FROM chatbot_messages WHERE conversation_id IN (SELECT id FROM chatbot_conversations WHERE chatbot_id = ?)", (chatbot_id,))
        db.execute("DELETE FROM chatbot_conversations WHERE chatbot_id = ?", (chatbot_id,))
        db.execute("DELETE FROM knowledge_files WHERE chatbot_id = ?", (chatbot_id,))
        
        # Delete chatbot
        db.execute("DELETE FROM chatbots WHERE id = ?", (chatbot_id,))
        db.commit()
        
        return jsonify({'success': True, 'message': f'Chatbot {chatbot_id} deleted'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


# ============================================================================
# Knowledge Base API
# ============================================================================

UPLOADS_DIR = Path(__file__).parent / 'uploads'
UPLOADS_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {'txt', 'md', 'pdf'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_text_from_file(filepath, filename):
    """Extract text content from uploaded file"""
    ext = filename.rsplit('.', 1)[1].lower()
    
    try:
        if ext in ('txt', 'md'):
            return Path(filepath).read_text(encoding='utf-8')
        elif ext == 'pdf':
            # Try to extract text from PDF
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(filepath)
                text = ""
                for page in doc:
                    text += page.get_text()
                doc.close()
                return text
            except ImportError:
                # Fallback: just note it's a PDF
                return f"[PDF file: {filename} - install PyMuPDF for text extraction]"
    except Exception as e:
        return f"[Error extracting text: {e}]"
    
    return ""


def chunk_text(text, chunk_size=1000, overlap=100):
    """Split text into overlapping chunks for RAG"""
    if not text:
        return []
    
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - overlap
    
    return chunks


def simple_search(query, content, max_results=3):
    """Simple keyword search in content - returns relevant snippets"""
    if not query or not content:
        return []
    
    query_lower = query.lower()
    query_words = query_lower.split()
    chunks = chunk_text(content, chunk_size=500, overlap=50)
    
    scored_chunks = []
    for chunk in chunks:
        chunk_lower = chunk.lower()
        score = sum(1 for word in query_words if word in chunk_lower)
        if score > 0:
            scored_chunks.append((score, chunk))
    
    scored_chunks.sort(key=lambda x: -x[0])
    return [chunk for _, chunk in scored_chunks[:max_results]]


@app.route('/api/chatbots/<chatbot_id>/knowledge', methods=['GET'])
def api_list_knowledge(chatbot_id):
    """List knowledge base files for a chatbot"""
    db = get_chatbots_db()
    try:
        files = db.execute("""
            SELECT id, filename, file_size, uploaded_at
            FROM knowledge_files
            WHERE chatbot_id = ?
            ORDER BY uploaded_at DESC
        """, (chatbot_id,)).fetchall()
        
        return jsonify({
            'files': [dict(f) for f in files],
            'count': len(files),
            'chatbot_id': chatbot_id
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/chatbots/<chatbot_id>/knowledge', methods=['POST'])
def api_upload_knowledge(chatbot_id):
    """Upload a knowledge base file"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': f'Invalid file type. Allowed: {", ".join(ALLOWED_EXTENSIONS)}'}), 400
    
    # Check file size
    file.seek(0, 2)  # Seek to end
    size = file.tell()
    file.seek(0)  # Seek back to start
    
    if size > MAX_FILE_SIZE:
        return jsonify({'error': f'File too large. Max size: {MAX_FILE_SIZE // (1024*1024)}MB'}), 400
    
    # Verify chatbot exists
    db = get_chatbots_db()
    try:
        chatbot = db.execute("SELECT id FROM chatbots WHERE id = ?", (chatbot_id,)).fetchone()
        if not chatbot:
            return jsonify({'error': 'Chatbot not found'}), 404
        
        # Save file
        import uuid
        filename = file.filename
        safe_filename = f"{chatbot_id}_{uuid.uuid4().hex[:8]}_{filename}"
        filepath = UPLOADS_DIR / safe_filename
        file.save(str(filepath))
        
        # Extract text content
        content = extract_text_from_file(str(filepath), filename)
        
        # Store in database
        db.execute("""
            INSERT INTO knowledge_files (chatbot_id, filename, content, file_size)
            VALUES (?, ?, ?, ?)
        """, (chatbot_id, filename, content, size))
        db.commit()
        
        file_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        return jsonify({
            'success': True,
            'file': {
                'id': file_id,
                'filename': filename,
                'file_size': size,
                'content_length': len(content) if content else 0
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/chatbots/<chatbot_id>/knowledge/<int:file_id>', methods=['DELETE'])
def api_delete_knowledge(chatbot_id, file_id):
    """Delete a knowledge base file"""
    db = get_chatbots_db()
    try:
        # Get file info first
        file_row = db.execute("""
            SELECT filename FROM knowledge_files 
            WHERE id = ? AND chatbot_id = ?
        """, (file_id, chatbot_id)).fetchone()
        
        if not file_row:
            return jsonify({'error': 'File not found'}), 404
        
        # Delete from database
        db.execute("DELETE FROM knowledge_files WHERE id = ?", (file_id,))
        db.commit()
        
        return jsonify({'success': True, 'message': 'File deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/chatbots/<chatbot_id>/knowledge/search', methods=['POST'])
def api_search_knowledge(chatbot_id):
    """Search the knowledge base for a chatbot"""
    data = request.json or {}
    query = data.get('query', '')
    
    if not query:
        return jsonify({'error': 'Query required'}), 400
    
    db = get_chatbots_db()
    try:
        # Get all knowledge files for this chatbot
        files = db.execute("""
            SELECT id, filename, content
            FROM knowledge_files
            WHERE chatbot_id = ?
        """, (chatbot_id,)).fetchall()
        
        results = []
        for file in files:
            if file['content']:
                snippets = simple_search(query, file['content'])
                if snippets:
                    results.append({
                        'file_id': file['id'],
                        'filename': file['filename'],
                        'snippets': snippets
                    })
        
        return jsonify({
            'query': query,
            'results': results,
            'total_files_searched': len(files)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


# ============================================================================
# Conversations API
# ============================================================================

@app.route('/api/conversations')
def api_list_conversations():
    """List all conversations with filtering"""
    chatbot_id = request.args.get('chatbot_id')
    search = request.args.get('search', '')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    limit = min(int(request.args.get('limit', 50)), 200)
    offset = int(request.args.get('offset', 0))
    
    db = get_chatbots_db()
    try:
        # Build query with filters
        query = """
            SELECT 
                c.id,
                c.chatbot_id,
                c.session_id,
                c.started_at,
                c.ended_at,
                c.message_count,
                c.satisfaction_rating,
                b.name as chatbot_name,
                (SELECT content FROM chatbot_messages WHERE conversation_id = c.id AND role = 'user' ORDER BY timestamp ASC LIMIT 1) as first_message
            FROM chatbot_conversations c
            LEFT JOIN chatbots b ON c.chatbot_id = b.id
            WHERE 1=1
        """
        params = []
        
        if chatbot_id:
            query += " AND c.chatbot_id = ?"
            params.append(chatbot_id)
        
        if start_date:
            query += " AND c.started_at >= ?"
            params.append(int(start_date))
        
        if end_date:
            query += " AND c.started_at <= ?"
            params.append(int(end_date))
        
        if search:
            query += """ AND c.id IN (
                SELECT DISTINCT conversation_id FROM chatbot_messages 
                WHERE content LIKE ?
            )"""
            params.append(f'%{search}%')
        
        # Count total
        count_query = query.replace(
            "SELECT \n                c.id,", 
            "SELECT COUNT(*) as total FROM (SELECT c.id,"
        ) + ") sub"
        # Simplified count
        count_result = db.execute(f"""
            SELECT COUNT(*) FROM chatbot_conversations c WHERE 1=1
            {' AND c.chatbot_id = ?' if chatbot_id else ''}
        """, [chatbot_id] if chatbot_id else []).fetchone()
        total = count_result[0] if count_result else 0
        
        query += " ORDER BY c.started_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        conversations = db.execute(query, params).fetchall()
        
        result = []
        for conv in conversations:
            conv_dict = dict(conv)
            # Calculate duration
            if conv_dict['ended_at'] and conv_dict['started_at']:
                duration_ms = conv_dict['ended_at'] - conv_dict['started_at']
                conv_dict['duration_seconds'] = duration_ms // 1000
            else:
                conv_dict['duration_seconds'] = None
            result.append(conv_dict)
        
        return jsonify({
            'conversations': result,
            'total': total,
            'limit': limit,
            'offset': offset
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/conversations/<int:conversation_id>')
def api_get_conversation(conversation_id):
    """Get a single conversation with all messages"""
    db = get_chatbots_db()
    try:
        # Get conversation details
        conv = db.execute("""
            SELECT 
                c.*,
                b.name as chatbot_name,
                b.greeting as chatbot_greeting
            FROM chatbot_conversations c
            LEFT JOIN chatbots b ON c.chatbot_id = b.id
            WHERE c.id = ?
        """, (conversation_id,)).fetchone()
        
        if not conv:
            return jsonify({'error': 'Conversation not found'}), 404
        
        conv_dict = dict(conv)
        
        # Get all messages
        messages = db.execute("""
            SELECT id, role, content, timestamp
            FROM chatbot_messages
            WHERE conversation_id = ?
            ORDER BY timestamp ASC
        """, (conversation_id,)).fetchall()
        
        conv_dict['messages'] = [dict(m) for m in messages]
        
        # Calculate duration
        if conv_dict['ended_at'] and conv_dict['started_at']:
            conv_dict['duration_seconds'] = (conv_dict['ended_at'] - conv_dict['started_at']) // 1000
        else:
            conv_dict['duration_seconds'] = None
        
        return jsonify(conv_dict)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/conversations/<int:conversation_id>/export')
def api_export_conversation(conversation_id):
    """Export conversation as CSV or JSON"""
    format_type = request.args.get('format', 'json')
    
    db = get_chatbots_db()
    try:
        # Get conversation
        conv = db.execute("""
            SELECT c.*, b.name as chatbot_name
            FROM chatbot_conversations c
            LEFT JOIN chatbots b ON c.chatbot_id = b.id
            WHERE c.id = ?
        """, (conversation_id,)).fetchone()
        
        if not conv:
            return jsonify({'error': 'Conversation not found'}), 404
        
        # Get messages
        messages = db.execute("""
            SELECT role, content, timestamp
            FROM chatbot_messages
            WHERE conversation_id = ?
            ORDER BY timestamp ASC
        """, (conversation_id,)).fetchall()
        
        if format_type == 'csv':
            import io
            import csv
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['Timestamp', 'Role', 'Content'])
            for msg in messages:
                from datetime import datetime
                ts = datetime.fromtimestamp(msg['timestamp'] / 1000).isoformat() if msg['timestamp'] else ''
                writer.writerow([ts, msg['role'], msg['content']])
            
            response = make_response(output.getvalue())
            response.headers['Content-Type'] = 'text/csv'
            response.headers['Content-Disposition'] = f'attachment; filename=conversation_{conversation_id}.csv'
            return response
        else:
            # JSON export
            conv_dict = dict(conv)
            conv_dict['messages'] = [dict(m) for m in messages]
            
            response = make_response(json.dumps(conv_dict, indent=2))
            response.headers['Content-Type'] = 'application/json'
            response.headers['Content-Disposition'] = f'attachment; filename=conversation_{conversation_id}.json'
            return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/chatbots/<chatbot_id>/ai-config', methods=['GET'])
def api_get_ai_config(chatbot_id):
    """Get AI configuration for a chatbot (masks API key)"""
    db = get_chatbots_db()
    try:
        chatbot = db.execute("""
            SELECT api_type, api_key_encrypted, model_id 
            FROM chatbots WHERE id = ?
        """, (chatbot_id,)).fetchone()
        
        if not chatbot:
            return jsonify({'error': 'Chatbot not found'}), 404
        
        has_api_key = bool(chatbot['api_key_encrypted'])
        api_key_masked = None
        if has_api_key:
            decrypted = decrypt_api_key(chatbot['api_key_encrypted'])
            if decrypted and len(decrypted) > 8:
                api_key_masked = decrypted[:4] + '****' + decrypted[-4:]
        
        return jsonify({
            'apiType': chatbot['api_type'] or 'internal',
            'modelId': chatbot['model_id'] or 'claude-sonnet',
            'hasApiKey': has_api_key,
            'apiKeyMasked': api_key_masked
        })
    finally:
        db.close()


@app.route('/api/chatbots/<chatbot_id>/ai-config', methods=['PUT'])
def api_update_ai_config(chatbot_id):
    """Update AI configuration for a chatbot"""
    data = request.json or {}
    db = get_chatbots_db()
    
    try:
        api_key_encrypted = None
        if 'apiKey' in data and data['apiKey']:
            api_key_encrypted = encrypt_api_key(data['apiKey'])
        
        updates = ["updated_at = strftime('%s', 'now') * 1000"]
        params = []
        
        if 'apiType' in data:
            updates.append("api_type = ?")
            params.append(data['apiType'])
        
        if 'modelId' in data:
            updates.append("model_id = ?")
            params.append(data['modelId'])
        
        if api_key_encrypted:
            updates.append("api_key_encrypted = ?")
            params.append(api_key_encrypted)
        elif data.get('clearApiKey'):
            updates.append("api_key_encrypted = NULL")
        
        params.append(chatbot_id)
        
        db.execute(f"""
            UPDATE chatbots SET {', '.join(updates)}
            WHERE id = ?
        """, params)
        db.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/chatbots/<chatbot_id>/test-connection', methods=['POST'])
def api_test_connection(chatbot_id):
    """Test API connection for a chatbot"""
    data = request.json or {}
    db = get_chatbots_db()
    
    try:
        chatbot = db.execute("""
            SELECT api_type, api_key_encrypted, model_id 
            FROM chatbots WHERE id = ?
        """, (chatbot_id,)).fetchone()
        
        if not chatbot:
            return jsonify({'error': 'Chatbot not found'}), 404
        
        api_type = data.get('apiType') or chatbot['api_type'] or 'internal'
        model_id = data.get('modelId') or chatbot['model_id'] or 'claude-sonnet'
        
        # Get API key (use provided or stored)
        api_key = data.get('apiKey')
        if not api_key and chatbot['api_key_encrypted']:
            api_key = decrypt_api_key(chatbot['api_key_encrypted'])
        
        if api_type == 'internal' or api_type == 'system':
            # Check if system key is available for the chosen model
            system_keys = get_system_api_keys()
            key_available = False
            provider_name = 'ResonantOS'
            
            if model_id.startswith('claude'):
                key_available = bool(system_keys.get('anthropic'))
                provider_name = 'Anthropic (System)'
            elif model_id.startswith('gpt'):
                key_available = bool(system_keys.get('openai'))
                provider_name = 'OpenAI (System)'
            elif model_id.startswith('gemini'):
                key_available = bool(system_keys.get('google'))
                provider_name = 'Google (System)'
            
            if key_available:
                return jsonify({
                    'success': True,
                    'message': f'Using {provider_name} API key',
                    'model': model_id
                })
            else:
                return jsonify({
                    'success': False,
                    'error': f'No system API key configured for {model_id}. Please add a custom key or configure system keys.'
                })
        elif api_type == 'custom':
            if not api_key:
                return jsonify({
                    'success': False,
                    'error': 'No API key configured'
                })
            
            # Validate API key format
            if model_id.startswith('claude') and not api_key.startswith('sk-ant-'):
                return jsonify({
                    'success': False,
                    'error': 'Invalid Anthropic API key format (should start with sk-ant-)'
                })
            elif model_id.startswith('gpt') and not api_key.startswith('sk-'):
                return jsonify({
                    'success': False,
                    'error': 'Invalid OpenAI API key format (should start with sk-)'
                })
            elif model_id.startswith('gemini'):
                # Gemini keys have different format
                pass
            
            # TODO: Actually test the connection by making a small API call
            # For now, just validate format
            return jsonify({
                'success': True,
                'message': f'API key format valid for {model_id}',
                'model': model_id
            })
        else:
            return jsonify({
                'success': False,
                'error': f'Unknown API type: {api_type}'
            })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/system-keys')
def api_system_keys():
    """Get available system API keys (shows which providers are configured, not actual keys)"""
    system_keys = get_system_api_keys()
    
    providers = []
    
    if system_keys.get('anthropic'):
        providers.append({
            'id': 'anthropic',
            'name': 'Anthropic',
            'configured': True,
            'models': [
                {'id': 'claude-sonnet', 'name': 'Claude Sonnet 4'},
                {'id': 'claude-opus', 'name': 'Claude Opus 4'},
                {'id': 'claude-haiku', 'name': 'Claude Haiku 4'},
            ]
        })
    
    if system_keys.get('openai'):
        providers.append({
            'id': 'openai',
            'name': 'OpenAI',
            'configured': True,
            'models': [
                {'id': 'gpt-4o', 'name': 'GPT-4o'},
                {'id': 'gpt-4o-mini', 'name': 'GPT-4o Mini'},
            ]
        })
    
    if system_keys.get('google'):
        providers.append({
            'id': 'google',
            'name': 'Google',
            'configured': True,
            'models': [
                {'id': 'gemini-pro', 'name': 'Gemini Pro'},
                {'id': 'gemini-flash', 'name': 'Gemini Flash'},
            ]
        })
    
    return jsonify({
        'providers': providers,
        'hasSystemKeys': len(providers) > 0
    })


@app.route('/api/models')
def api_available_models():
    """Get list of available AI models"""
    api_type = request.args.get('apiType', 'internal')
    
    internal_models = [
        {'id': 'claude-sonnet', 'name': 'Claude Sonnet 4', 'provider': 'Anthropic', 'description': 'Fast and capable'},
        {'id': 'claude-opus', 'name': 'Claude Opus 4', 'provider': 'Anthropic', 'description': 'Most capable, best for complex tasks'},
        {'id': 'claude-haiku', 'name': 'Claude Haiku 4', 'provider': 'Anthropic', 'description': 'Fastest, most cost-effective'},
    ]
    
    custom_models = [
        {'id': 'claude-sonnet', 'name': 'Claude Sonnet 4', 'provider': 'Anthropic', 'description': 'Fast and capable'},
        {'id': 'claude-opus', 'name': 'Claude Opus 4', 'provider': 'Anthropic', 'description': 'Most capable'},
        {'id': 'claude-haiku', 'name': 'Claude Haiku 4', 'provider': 'Anthropic', 'description': 'Fastest'},
        {'id': 'gpt-4o', 'name': 'GPT-4o', 'provider': 'OpenAI', 'description': 'OpenAI flagship model'},
        {'id': 'gpt-4o-mini', 'name': 'GPT-4o Mini', 'provider': 'OpenAI', 'description': 'Faster, cheaper GPT-4'},
        {'id': 'gemini-pro', 'name': 'Gemini Pro', 'provider': 'Google', 'description': 'Google AI model'},
        {'id': 'gemini-flash', 'name': 'Gemini Flash', 'provider': 'Google', 'description': 'Fast Google AI'},
    ]
    
    if api_type == 'internal':
        return jsonify({'models': internal_models})
    else:
        return jsonify({'models': custom_models})


# ============================================================================
# Widget Generation & Download
# ============================================================================

# ============================================================================
# Analytics API
# ============================================================================

@app.route('/api/analytics')
def api_analytics():
    """Get analytics data for chatbots"""
    range_param = request.args.get('range', '7d')
    chatbot_id = request.args.get('chatbot_id', '')
    
    db = get_chatbots_db()
    try:
        now_ms = int(time.time() * 1000)
        
        # Calculate date range
        range_ms = {
            '7d': 7 * 24 * 60 * 60 * 1000,
            '30d': 30 * 24 * 60 * 60 * 1000,
            '90d': 90 * 24 * 60 * 60 * 1000,
            'all': now_ms  # All time
        }.get(range_param, 7 * 24 * 60 * 60 * 1000)
        
        start_time = now_ms - range_ms
        
        # Build query filters
        filters = ["started_at >= ?"]
        params = [start_time]
        
        if chatbot_id:
            filters.append("chatbot_id = ?")
            params.append(chatbot_id)
        
        where_clause = " AND ".join(filters)
        
        # Get total conversations
        total_conv = db.execute(f"""
            SELECT COUNT(*) as count FROM chatbot_conversations
            WHERE {where_clause}
        """, params).fetchone()['count']
        
        # Get total messages
        total_msg = db.execute(f"""
            SELECT COUNT(*) as count FROM chatbot_messages m
            JOIN chatbot_conversations c ON m.conversation_id = c.id
            WHERE {where_clause}
        """, params).fetchone()['count']
        
        # Get user messages and bot responses
        user_messages = db.execute(f"""
            SELECT COUNT(*) as count FROM chatbot_messages m
            JOIN chatbot_conversations c ON m.conversation_id = c.id
            WHERE {where_clause} AND m.role = 'user'
        """, params).fetchone()['count']
        
        bot_responses = db.execute(f"""
            SELECT COUNT(*) as count FROM chatbot_messages m
            JOIN chatbot_conversations c ON m.conversation_id = c.id
            WHERE {where_clause} AND m.role = 'assistant'
        """, params).fetchone()['count']
        
        # Get average conversation length
        avg_conv_length = db.execute(f"""
            SELECT AVG(message_count) as avg FROM chatbot_conversations
            WHERE {where_clause}
        """, params).fetchone()['avg'] or 0
        
        # Get satisfaction data
        satisfaction = db.execute(f"""
            SELECT 
                COUNT(*) as total,
                AVG(satisfaction_rating) as avg,
                SUM(CASE WHEN satisfaction_rating = 5 THEN 1 ELSE 0 END) as rating5,
                SUM(CASE WHEN satisfaction_rating = 4 THEN 1 ELSE 0 END) as rating4,
                SUM(CASE WHEN satisfaction_rating = 3 THEN 1 ELSE 0 END) as rating3,
                SUM(CASE WHEN satisfaction_rating = 2 THEN 1 ELSE 0 END) as rating2,
                SUM(CASE WHEN satisfaction_rating = 1 THEN 1 ELSE 0 END) as rating1,
                COUNT(satisfaction_rating) as rated_count
            FROM chatbot_conversations
            WHERE {where_clause}
        """, params).fetchone()
        
        rated_count = satisfaction['rated_count'] or 0
        feedback_rate = (rated_count / total_conv * 100) if total_conv > 0 else 0
        
        # Get chart data (conversations per day)
        chart_data = []
        if range_param == '7d':
            interval_days = 1
        elif range_param == '30d':
            interval_days = 1
        elif range_param == '90d':
            interval_days = 3
        else:
            interval_days = 7
        
        current_time = start_time
        while current_time < now_ms:
            end_time = current_time + (interval_days * 24 * 60 * 60 * 1000)
            
            interval_filters = ["started_at >= ? AND started_at < ?"]
            interval_params = [current_time, end_time]
            if chatbot_id:
                interval_filters.append("chatbot_id = ?")
                interval_params.append(chatbot_id)
            
            count = db.execute(f"""
                SELECT COUNT(*) as count FROM chatbot_conversations
                WHERE {" AND ".join(interval_filters)}
            """, interval_params).fetchone()['count']
            
            chart_data.append({
                'date': datetime.fromtimestamp(current_time / 1000).strftime('%Y-%m-%d'),
                'conversations': count
            })
            
            current_time = end_time
        
        # Get recent conversations
        recent_params = params.copy()
        recent_params.append(10)  # limit
        
        recent_conv = db.execute(f"""
            SELECT c.*, b.name as chatbot_name
            FROM chatbot_conversations c
            LEFT JOIN chatbots b ON c.chatbot_id = b.id
            WHERE {where_clause}
            ORDER BY c.started_at DESC
            LIMIT ?
        """, recent_params).fetchall()
        
        recent_conversations = []
        for conv in recent_conv:
            conv_dict = dict(conv)
            # Calculate duration
            if conv_dict.get('ended_at') and conv_dict.get('started_at'):
                conv_dict['duration_ms'] = conv_dict['ended_at'] - conv_dict['started_at']
            else:
                conv_dict['duration_ms'] = None
            conv_dict['rating'] = conv_dict.get('satisfaction_rating')
            recent_conversations.append(conv_dict)
        
        # Get popular questions (top user messages)
        popular_questions = []
        try:
            popular = db.execute(f"""
                SELECT m.content as question, COUNT(*) as count
                FROM chatbot_messages m
                JOIN chatbot_conversations c ON m.conversation_id = c.id
                WHERE {where_clause} AND m.role = 'user'
                GROUP BY m.content
                ORDER BY count DESC
                LIMIT 10
            """, params).fetchall()
            
            popular_questions = [{'question': q['question'], 'count': q['count']} for q in popular]
        except Exception:
            pass
        
        # Calculate satisfaction rate
        satisfaction_rate = (satisfaction['avg'] / 5 * 100) if satisfaction['avg'] else None
        
        return jsonify({
            'totalConversations': total_conv,
            'totalMessages': total_msg,
            'userMessages': user_messages,
            'botResponses': bot_responses,
            'avgResponseTime': '< 2s',  # Placeholder - would need actual timing data
            'errorRate': 0,  # Placeholder
            'avgConvLength': avg_conv_length,
            'satisfactionRate': satisfaction_rate,
            'satisfaction': {
                'total': rated_count,
                'rating5': satisfaction['rating5'] or 0,
                'rating4': satisfaction['rating4'] or 0,
                'rating3': satisfaction['rating3'] or 0,
                'rating2': satisfaction['rating2'] or 0,
                'rating1': satisfaction['rating1'] or 0,
                'feedbackRate': feedback_rate
            },
            'chartData': chart_data,
            'popularQuestions': popular_questions,
            'recentConversations': recent_conversations
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/analytics/export')
def api_analytics_export():
    """Export analytics data as CSV"""
    from io import StringIO
    import csv
    from flask import Response
    
    range_param = request.args.get('range', '7d')
    chatbot_id = request.args.get('chatbot_id', '')
    
    db = get_chatbots_db()
    try:
        now_ms = int(time.time() * 1000)
        
        range_ms = {
            '7d': 7 * 24 * 60 * 60 * 1000,
            '30d': 30 * 24 * 60 * 60 * 1000,
            '90d': 90 * 24 * 60 * 60 * 1000,
            'all': now_ms
        }.get(range_param, 7 * 24 * 60 * 60 * 1000)
        
        start_time = now_ms - range_ms
        
        filters = ["c.started_at >= ?"]
        params = [start_time]
        
        if chatbot_id:
            filters.append("c.chatbot_id = ?")
            params.append(chatbot_id)
        
        where_clause = " AND ".join(filters)
        
        # Get all conversations with details
        conversations = db.execute(f"""
            SELECT c.id, c.chatbot_id, b.name as chatbot_name, c.session_id,
                   c.started_at, c.ended_at, c.message_count, c.satisfaction_rating
            FROM chatbot_conversations c
            LEFT JOIN chatbots b ON c.chatbot_id = b.id
            WHERE {where_clause}
            ORDER BY c.started_at DESC
        """, params).fetchall()
        
        # Create CSV
        output = StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow(['Conversation ID', 'Chatbot', 'Session ID', 'Started At', 
                        'Ended At', 'Message Count', 'Satisfaction Rating'])
        
        for conv in conversations:
            started_at = datetime.fromtimestamp(conv['started_at'] / 1000).isoformat() if conv['started_at'] else ''
            ended_at = datetime.fromtimestamp(conv['ended_at'] / 1000).isoformat() if conv['ended_at'] else ''
            
            writer.writerow([
                conv['id'],
                conv['chatbot_name'] or conv['chatbot_id'],
                conv['session_id'],
                started_at,
                ended_at,
                conv['message_count'],
                conv['satisfaction_rating'] or ''
            ])
        
        output.seek(0)
        
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename=analytics-{range_param}-{datetime.now().strftime("%Y-%m-%d")}.csv'
            }
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


# ============================================================================
# Wallet API
# ============================================================================

@app.route('/api/wallet')
def api_wallet():
    """Get wallet data - mock data for now, would connect to real Solana wallet"""
    network = request.args.get('network', 'devnet')
    
    # Mock wallet data - in production, this would query the Solana blockchain
    mock_data = {
        'address': '7Xf9bKj2pM8qRtN5vL3cH6wY9sD1fG4kLm',
        'network': network,
        'balance': {
            'sol': 12.45 if network == 'devnet' else (5.0 if network == 'testnet' else 0.05),
            'usd': 2456.78 if network == 'devnet' else (987.50 if network == 'testnet' else 9.87)
        },
        'tokens': [
            {'symbol': 'RCT', 'balance': 1500, 'value': 750.00},
            {'symbol': 'USDC', 'balance': 500.00, 'value': 500.00}
        ],
        'recentTransactions': [
            {'type': 'receive', 'amount': 2.5, 'symbol': 'SOL', 'time': '2 hours ago'},
            {'type': 'send', 'amount': 100, 'symbol': 'RCT', 'time': '1 day ago'},
            {'type': 'receive', 'amount': 5.0, 'symbol': 'SOL', 'time': '3 days ago'}
        ]
    }
    
    return jsonify(mock_data)


def generate_license_key(chatbot_id, tier='free'):
    """Generate a license key for a chatbot"""
    import hashlib
    timestamp = hex(int(time.time()))[2:]
    tier_code = {'free': 'F', 'pro': 'P', 'enterprise': 'E'}.get(tier, 'F')
    payload = f"ROS-{tier_code}-{timestamp.upper()}"
    
    # Create checksum matching widget's simpleHash
    def simple_hash(s):
        h = 0
        for c in s:
            h = ((h << 5) - h) + ord(c)
            h = h & 0xFFFFFFFF  # Keep as 32-bit
            if h >= 0x80000000:
                h -= 0x100000000
        return format(abs(h) % (36**6), 'x')[:6]
    
    checksum = simple_hash(payload + chatbot_id)
    return f"{payload}-{checksum}".upper()


def build_obfuscated_widget(chatbot_id, config, tier='free'):
    """Build obfuscated widget using Node.js build script"""
    import tempfile
    
    # Prepare config file
    build_config = {
        'chatbotId': chatbot_id,
        'name': config.get('name', 'Chat'),
        'greeting': config.get('greeting', 'Hi! How can I help you?'),
        'systemPrompt': config.get('system_prompt', 'You are a helpful assistant.'),
        'position': config.get('position', 'bottom-right'),
        'theme': config.get('theme', 'dark'),
        'primaryColor': config.get('primary_color', '#4ade80'),
        'bgColor': config.get('bg_color', '#1a1a1a'),
        'textColor': config.get('text_color', '#e0e0e0'),
        'apiEndpoint': config.get('api_endpoint', request.host_url.rstrip('/') + '/api'),
        'tier': tier,
        'domain': config.get('allowed_domains', '*') or '*',
        'showWatermark': tier == 'free',
        'allowIcon': tier in ('pro', 'enterprise'),
        'iconUrl': config.get('icon_url', '')
    }
    
    # Write config to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(build_config, f)
        config_path = f.name
    
    # Run build script
    scripts_dir = Path(__file__).parent / 'scripts'
    dist_dir = Path(__file__).parent / 'dist'
    dist_dir.mkdir(exist_ok=True)
    
    output_path = dist_dir / f'widget-{chatbot_id}.min.js'
    
    try:
        result = subprocess.run(
            ['node', str(scripts_dir / 'build-widget.js'), 
             '--config', config_path,
             '--output', str(output_path)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(Path(__file__).parent)
        )
        
        if result.returncode != 0:
            raise Exception(f"Build failed: {result.stderr}")
        
        # Read the manifest for license key
        manifest_path = str(output_path).replace('.min.js', '.manifest.json')
        if os.path.exists(manifest_path):
            with open(manifest_path) as f:
                manifest = json.load(f)
            return output_path, manifest.get('licenseKey')
        
        return output_path, generate_license_key(chatbot_id, tier)
        
    finally:
        os.unlink(config_path)


@app.route('/api/widget/generate', methods=['POST'])
def api_generate_widget():
    """Generate obfuscated widget with embedded license"""
    data = request.json or {}
    db = get_chatbots_db()
    
    try:
        # Create or update chatbot
        import uuid
        chatbot_id = data.get('id') or str(uuid.uuid4())[:8]
        
        # Determine tier from license
        user_id = data.get('user_id', 'default')
        license_row = db.execute("""
            SELECT tier FROM licenses 
            WHERE user_id = ? AND (chatbot_id = ? OR chatbot_id IS NULL)
            AND (expires_at IS NULL OR expires_at > ?)
            ORDER BY chatbot_id DESC NULLS LAST
            LIMIT 1
        """, (user_id, chatbot_id, int(time.time() * 1000))).fetchone()
        
        tier = license_row['tier'] if license_row else 'free'
        
        # Check if chatbot exists
        existing = db.execute("SELECT id FROM chatbots WHERE id = ?", (chatbot_id,)).fetchone()
        
        if not existing:
            db.execute("""
                INSERT INTO chatbots (id, name, system_prompt, greeting, suggested_prompts,
                                      position, theme, primary_color, bg_color, text_color,
                                      allowed_domains, rate_per_minute, rate_per_hour,
                                      enable_analytics, show_watermark)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                chatbot_id,
                data.get('name', 'My Chatbot'),
                data.get('systemPrompt', 'You are a helpful assistant.'),
                data.get('greeting', 'Hi! How can I help you today?'),
                json.dumps(data.get('suggestedPrompts', [])),
                data.get('position', 'bottom-right'),
                data.get('theme', 'dark'),
                data.get('primaryColor', '#4ade80'),
                data.get('bgColor', '#1a1a1a'),
                data.get('textColor', '#e0e0e0'),
                data.get('allowedDomains', ''),
                data.get('ratePerMinute', 10),
                data.get('ratePerHour', 100),
                1 if data.get('enableAnalytics', True) else 0,
                1 if data.get('showWatermark', True) else 0
            ))
        else:
            db.execute("""
                UPDATE chatbots SET
                    name = ?, system_prompt = ?, greeting = ?, suggested_prompts = ?,
                    position = ?, theme = ?, primary_color = ?, bg_color = ?, text_color = ?,
                    show_watermark = ?, updated_at = strftime('%s', 'now') * 1000
                WHERE id = ?
            """, (
                data.get('name', 'My Chatbot'),
                data.get('systemPrompt', 'You are a helpful assistant.'),
                data.get('greeting', 'Hi! How can I help you today?'),
                json.dumps(data.get('suggestedPrompts', [])),
                data.get('position', 'bottom-right'),
                data.get('theme', 'dark'),
                data.get('primaryColor', '#4ade80'),
                data.get('bgColor', '#1a1a1a'),
                data.get('textColor', '#e0e0e0'),
                1 if data.get('showWatermark', True) else 0,
                chatbot_id
            ))
        db.commit()
        
        # NEW SaaS Model: Thin loader embed code
        # - Loader calls /api/widget/init/:chatbotId for config
        # - Config includes server-side license enforcement
        # - Widget code served from /widget/v/:version/widget.min.js
        
        base_url = request.host_url.rstrip('/')
        
        # Generate embed code - THIN LOADER ONLY
        # This is the ONLY code customers get - no logic, just a loader
        embed_code = f'''<!-- ResonantOS Chat Widget -->
<script src="{base_url}/widget/loader.js" data-chatbot-id="{chatbot_id}"></script>'''
        
        # Get tier limits for response info
        limits = TIER_LIMITS.get(tier, TIER_LIMITS['free'])
        
        return jsonify({
            'success': True,
            'widgetId': chatbot_id,
            'tier': tier,
            'embedCode': embed_code,
            # Feature info based on license
            'features': {
                'showWatermark': not limits['remove_watermark'],
                'customIcon': limits['custom_icon'],
                'maxChatbots': limits['max_chatbots']
            },
            # Instructions
            'instructions': [
                'Copy the embed code above and paste it before </body> on your website.',
                'The widget will load automatically with your configuration.',
                f'Your {tier} plan {"includes" if limits["remove_watermark"] else "shows"} the ResonantOS watermark.',
                f'{"Custom icons are enabled." if limits["custom_icon"] else "Upgrade to use custom icons."}'
            ]
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


@app.route('/widget/<chatbot_id>/widget.min.js')
def serve_obfuscated_widget(chatbot_id):
    """Serve the obfuscated widget for a specific chatbot"""
    dist_dir = Path(__file__).parent / 'dist'
    widget_path = dist_dir / f'widget-{chatbot_id}.min.js'
    
    if not widget_path.exists():
        # Try to build it on-demand
        db = get_chatbots_db()
        try:
            chatbot = db.execute("SELECT * FROM chatbots WHERE id = ?", (chatbot_id,)).fetchone()
            if not chatbot:
                return jsonify({'error': 'Chatbot not found'}), 404
            
            chatbot_config = dict(chatbot)
            chatbot_config['api_endpoint'] = request.host_url.rstrip('/') + '/api'
            
            # Get tier from license
            license_row = db.execute("""
                SELECT tier FROM licenses WHERE chatbot_id = ?
                AND (expires_at IS NULL OR expires_at > ?)
                LIMIT 1
            """, (chatbot_id, int(time.time() * 1000))).fetchone()
            tier = license_row['tier'] if license_row else 'free'
            
            widget_path, _ = build_obfuscated_widget(chatbot_id, chatbot_config, tier)
        except Exception as e:
            print(f"Failed to build widget: {e}")
            return jsonify({'error': 'Widget build failed'}), 500
        finally:
            db.close()
    
    return send_from_directory(str(dist_dir), f'widget-{chatbot_id}.min.js', 
                               mimetype='application/javascript')


@app.route('/api/widget/download/<chatbot_id>')
def api_download_widget(chatbot_id):
    """Download obfuscated widget package as ZIP"""
    from io import BytesIO
    import zipfile
    from flask import send_file
    
    db = get_chatbots_db()
    try:
        chatbot = db.execute("SELECT * FROM chatbots WHERE id = ?", (chatbot_id,)).fetchone()
        if not chatbot:
            return jsonify({'error': 'Chatbot not found'}), 404
        
        chatbot_config = dict(chatbot)
        chatbot_config['api_endpoint'] = request.host_url.rstrip('/') + '/api'
        
        # Get tier from license
        license_row = db.execute("""
            SELECT tier FROM licenses WHERE chatbot_id = ?
            AND (expires_at IS NULL OR expires_at > ?)
            LIMIT 1
        """, (chatbot_id, int(time.time() * 1000))).fetchone()
        tier = license_row['tier'] if license_row else 'free'
        
        # Build obfuscated widget
        try:
            widget_path, license_key = build_obfuscated_widget(chatbot_id, chatbot_config, tier)
            with open(widget_path, 'r') as f:
                widget_js = f.read()
        except Exception as e:
            print(f"Widget build failed: {e}")
            # Fallback to simple version
            widget_js = generate_widget_js(chatbot_config)
            license_key = generate_license_key(chatbot_id, tier)
        
        # Create ZIP file in memory
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Add obfuscated widget.js
            zf.writestr('widget.min.js', widget_js)
            
            # Add README
            readme = f'''# {chatbot_config.get("name", "Chatbot")} Widget

## Installation

Add this single line before </body> on your website:

```html
<script src="widget.min.js"></script>
```

That's it! The widget is fully self-contained with your configuration embedded.

## Details

- Widget ID: {chatbot_id}
- License Key: {license_key}
- Tier: {tier}
- Position: {chatbot_config.get("position", "bottom-right")}
- Theme: {chatbot_config.get("theme", "dark")}

## Important

- The widget.min.js file is protected and obfuscated
- Do not attempt to modify the code
- The license key is embedded and validated
- For support, visit https://resonantos.com

## Upgrading

To remove the "Powered by ResonantOS" watermark or unlock additional 
features, upgrade your plan at https://resonantos.com/pricing
'''
            zf.writestr('README.md', readme)
            
            # Add simple embed snippet
            embed_html = f'''<!-- ResonantOS Chat Widget - {chatbot_config.get("name", "Chatbot")} -->
<!-- Just include this one script - everything is embedded! -->
<script src="widget.min.js"></script>
'''
            zf.writestr('embed.html', embed_html)
        
        buffer.seek(0)
        
        return send_file(
            buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'widget-{chatbot_id}.zip'
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


def generate_widget_js(config):
    """Generate the widget JavaScript"""
    return f'''/**
 * ResonantOS Chat Widget
 * Widget ID: {config.get("id")}
 * Generated: {datetime.now().isoformat()}
 */
(function() {{
  'use strict';
  
  const CONFIG = {{
    widgetId: '{config.get("id")}',
    name: '{config.get("name", "Assistant")}',
    greeting: '{config.get("greeting", "Hi! How can I help you?")}',
    position: '{config.get("position", "bottom-right")}',
    theme: '{config.get("theme", "dark")}',
    primaryColor: '{config.get("primary_color", "#4ade80")}',
    bgColor: '{config.get("bg_color", "#1a1a1a")}',
    textColor: '{config.get("text_color", "#e0e0e0")}',
    showWatermark: {str(bool(config.get("show_watermark", 1))).lower()},
    suggestedPrompts: {config.get("suggested_prompts", "[]")}
  }};
  
  // Create widget container
  const container = document.createElement('div');
  container.id = 'resonantos-widget';
  container.className = 'ros-widget ros-' + CONFIG.position + ' ros-' + CONFIG.theme;
  
  // Widget button
  const button = document.createElement('button');
  button.className = 'ros-button';
  button.innerHTML = '💬';
  button.style.backgroundColor = CONFIG.primaryColor;
  button.onclick = toggleChat;
  
  // Chat window
  const chat = document.createElement('div');
  chat.className = 'ros-chat';
  chat.style.display = 'none';
  chat.innerHTML = `
    <div class="ros-header" style="background: ${{CONFIG.primaryColor}}">
      <span>${{CONFIG.name}}</span>
      <button onclick="window.ROSWidget.close()">×</button>
    </div>
    <div class="ros-messages">
      <div class="ros-message ros-bot">${{CONFIG.greeting}}</div>
    </div>
    <div class="ros-input">
      <input type="text" placeholder="Type a message..." onkeypress="if(event.key==='Enter')window.ROSWidget.send()">
      <button onclick="window.ROSWidget.send()">→</button>
    </div>
    ${{CONFIG.showWatermark ? '<div class="ros-watermark">Powered by ResonantOS</div>' : ''}}
  `;
  
  container.appendChild(button);
  container.appendChild(chat);
  
  // Add styles
  const style = document.createElement('style');
  style.textContent = `
    .ros-widget {{ position: fixed; z-index: 99999; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }}
    .ros-bottom-right {{ bottom: 20px; right: 20px; }}
    .ros-bottom-left {{ bottom: 20px; left: 20px; }}
    .ros-button {{ width: 60px; height: 60px; border-radius: 50%; border: none; cursor: pointer; font-size: 24px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); transition: transform 0.2s; }}
    .ros-button:hover {{ transform: scale(1.1); }}
    .ros-chat {{ position: absolute; bottom: 80px; right: 0; width: 360px; height: 500px; border-radius: 12px; overflow: hidden; box-shadow: 0 8px 32px rgba(0,0,0,0.3); display: flex; flex-direction: column; }}
    .ros-dark .ros-chat {{ background: ${{CONFIG.bgColor}}; color: ${{CONFIG.textColor}}; }}
    .ros-light .ros-chat {{ background: #ffffff; color: #333333; }}
    .ros-header {{ padding: 16px; display: flex; justify-content: space-between; align-items: center; color: white; font-weight: 600; }}
    .ros-header button {{ background: none; border: none; color: white; font-size: 20px; cursor: pointer; }}
    .ros-messages {{ flex: 1; overflow-y: auto; padding: 16px; }}
    .ros-message {{ margin: 8px 0; padding: 10px 14px; border-radius: 12px; max-width: 80%; word-wrap: break-word; }}
    .ros-bot {{ background: ${{CONFIG.primaryColor}}20; }}
    .ros-user {{ background: ${{CONFIG.primaryColor}}; color: white; margin-left: auto; }}
    .ros-input {{ display: flex; padding: 12px; border-top: 1px solid rgba(255,255,255,0.1); }}
    .ros-input input {{ flex: 1; padding: 10px; border: none; border-radius: 8px; background: rgba(255,255,255,0.1); color: inherit; }}
    .ros-input button {{ margin-left: 8px; padding: 10px 16px; border: none; border-radius: 8px; background: ${{CONFIG.primaryColor}}; color: white; cursor: pointer; }}
    .ros-watermark {{ text-align: center; padding: 8px; font-size: 11px; opacity: 0.6; }}
  `;
  document.head.appendChild(style);
  document.body.appendChild(container);
  
  function toggleChat() {{
    chat.style.display = chat.style.display === 'none' ? 'flex' : 'none';
  }}
  
  function sendMessage() {{
    const input = chat.querySelector('.ros-input input');
    const message = input.value.trim();
    if (!message) return;
    
    const messages = chat.querySelector('.ros-messages');
    messages.innerHTML += `<div class="ros-message ros-user">${{message}}</div>`;
    input.value = '';
    messages.scrollTop = messages.scrollHeight;
    
    // Send to API
    fetch('/api/chat/' + CONFIG.widgetId, {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ message: message }})
    }})
    .then(r => r.json())
    .then(data => {{
      messages.innerHTML += `<div class="ros-message ros-bot">${{data.response || 'Sorry, I could not process that.'}}</div>`;
      messages.scrollTop = messages.scrollHeight;
    }})
    .catch(() => {{
      messages.innerHTML += `<div class="ros-message ros-bot">Sorry, there was an error. Please try again.</div>`;
      messages.scrollTop = messages.scrollHeight;
    }});
  }}
  
  // Expose API
  window.ROSWidget = {{
    open: () => {{ chat.style.display = 'flex'; }},
    close: () => {{ chat.style.display = 'none'; }},
    toggle: toggleChat,
    send: sendMessage
  }};
}})();
'''


def generate_widget_css(config):
    """Generate widget CSS"""
    return f'''/**
 * ResonantOS Chat Widget Styles
 * Widget ID: {config.get("id")}
 */
:root {{
  --ros-primary: {config.get("primary_color", "#4ade80")};
  --ros-bg: {config.get("bg_color", "#1a1a1a")};
  --ros-text: {config.get("text_color", "#e0e0e0")};
}}
'''


# ============================================================================
# Chat API (for widget)
# ============================================================================

def get_system_api_keys():
    """Get API keys from system config (clawdbot.json)"""
    try:
        if CLAWDBOT_CONFIG.exists():
            config = json.loads(CLAWDBOT_CONFIG.read_text())
            return {
                'anthropic': config.get('anthropic', {}).get('apiKey'),
                'openai': config.get('openai', {}).get('apiKey'),
                'google': config.get('google', {}).get('apiKey'),
            }
    except Exception as e:
        print(f"Error reading system API keys: {e}")
    return {}


def call_ai_api(model_id, api_key, system_prompt, user_message, context=""):
    """Call the appropriate AI API based on model"""
    full_system = system_prompt or "You are a helpful assistant."
    if context:
        full_system += f"\n\nRelevant context from knowledge base:\n{context}"
    
    try:
        if model_id.startswith('claude'):
            # Map model IDs to actual Anthropic model names
            model_map = {
                'claude-sonnet': 'claude-sonnet-4-20250514',
                'claude-opus': 'claude-opus-4-20250514',
                'claude-haiku': 'claude-haiku-4-20250514',
            }
            actual_model = model_map.get(model_id, 'claude-sonnet-4-20250514')
            
            response = requests.post(
                'https://api.anthropic.com/v1/messages',
                headers={
                    'x-api-key': api_key,
                    'anthropic-version': '2023-06-01',
                    'content-type': 'application/json'
                },
                json={
                    'model': actual_model,
                    'max_tokens': 1024,
                    'system': full_system,
                    'messages': [{'role': 'user', 'content': user_message}]
                },
                timeout=30
            )
            
            if response.ok:
                data = response.json()
                return data['content'][0]['text']
            else:
                print(f"Anthropic API error: {response.status_code} {response.text}")
                return None
                
        elif model_id.startswith('gpt'):
            # OpenAI API
            model_map = {
                'gpt-4o': 'gpt-4o',
                'gpt-4o-mini': 'gpt-4o-mini',
            }
            actual_model = model_map.get(model_id, 'gpt-4o-mini')
            
            response = requests.post(
                'https://api.openai.com/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': actual_model,
                    'max_tokens': 1024,
                    'messages': [
                        {'role': 'system', 'content': full_system},
                        {'role': 'user', 'content': user_message}
                    ]
                },
                timeout=30
            )
            
            if response.ok:
                data = response.json()
                return data['choices'][0]['message']['content']
            else:
                print(f"OpenAI API error: {response.status_code} {response.text}")
                return None
                
        elif model_id.startswith('gemini'):
            # Google Gemini API - updated model names (2026)
            model_map = {
                'gemini-pro': 'gemini-2.5-pro',
                'gemini-flash': 'gemini-2.0-flash',
            }
            actual_model = model_map.get(model_id, 'gemini-2.0-flash')
            
            response = requests.post(
                f'https://generativelanguage.googleapis.com/v1beta/models/{actual_model}:generateContent',
                params={'key': api_key},
                headers={'Content-Type': 'application/json'},
                json={
                    'systemInstruction': {'parts': [{'text': full_system}]},
                    'contents': [{'parts': [{'text': user_message}]}]
                },
                timeout=30
            )
            
            if response.ok:
                data = response.json()
                return data['candidates'][0]['content']['parts'][0]['text']
            else:
                print(f"Gemini API error: {response.status_code} {response.text}")
                return None
    except Exception as e:
        print(f"AI API call error: {e}")
    
    return None


@app.route('/api/chat/<chatbot_id>', methods=['POST'])
def api_chat(chatbot_id):
    """Handle chat message from widget - uses configured AI model"""
    data = request.json or {}
    message = data.get('message', '')
    session_id = data.get('sessionId', request.remote_addr)
    
    db = get_chatbots_db()
    try:
        # Get chatbot config including AI settings
        chatbot = db.execute("SELECT * FROM chatbots WHERE id = ?", (chatbot_id,)).fetchone()
        if not chatbot:
            return jsonify({'error': 'Chatbot not found'}), 404
        
        chatbot = dict(chatbot)
        
        # Get AI configuration
        api_type = chatbot.get('api_type', 'internal')
        model_id = chatbot.get('model_id', 'claude-sonnet')
        system_prompt = chatbot.get('system_prompt', 'You are a helpful assistant.')
        
        # Determine API key to use
        api_key = None
        if api_type == 'custom' and chatbot.get('api_key_encrypted'):
            api_key = decrypt_api_key(chatbot['api_key_encrypted'])
        elif api_type == 'internal' or api_type == 'system':
            # Use system API keys from config
            system_keys = get_system_api_keys()
            if model_id.startswith('claude'):
                api_key = system_keys.get('anthropic')
            elif model_id.startswith('gpt'):
                api_key = system_keys.get('openai')
            elif model_id.startswith('gemini'):
                api_key = system_keys.get('google')
        
        # Search knowledge base for context
        knowledge_context = ""
        try:
            files = db.execute("""
                SELECT content FROM knowledge_files WHERE chatbot_id = ?
            """, (chatbot_id,)).fetchall()
            
            for file in files:
                if file['content']:
                    snippets = simple_search(message, file['content'], max_results=2)
                    if snippets:
                        knowledge_context += "\n".join(snippets) + "\n"
        except Exception as e:
            print(f"Knowledge search error: {e}")
        
        # Call AI API to generate response
        response = None
        if api_key:
            response = call_ai_api(model_id, api_key, system_prompt, message, knowledge_context)
        
        # Fallback if AI call failed or no API key
        if not response:
            import random
            if knowledge_context:
                response = f"Based on my knowledge: {knowledge_context[:300].strip()}..."
                if len(knowledge_context) > 300:
                    response += " Would you like me to elaborate on any specific aspect?"
            else:
                responses = [
                    "I understand. Let me help you with that.",
                    "That's a great question! Here's what I know...",
                    "Thanks for reaching out. I'd be happy to assist.",
                    "I'm here to help! Could you tell me more?",
                ]
                response = random.choice(responses)
        
        # Log the conversation
        try:
            conv = db.execute("""
                SELECT id FROM chatbot_conversations 
                WHERE chatbot_id = ? AND session_id = ? AND ended_at IS NULL
            """, (chatbot_id, session_id)).fetchone()
            
            if not conv:
                db.execute("""
                    INSERT INTO chatbot_conversations (chatbot_id, session_id)
                    VALUES (?, ?)
                """, (chatbot_id, session_id))
                conv_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            else:
                conv_id = conv['id']
            
            db.execute("""
                INSERT INTO chatbot_messages (conversation_id, role, content)
                VALUES (?, 'user', ?)
            """, (conv_id, message))
            
            db.execute("""
                INSERT INTO chatbot_messages (conversation_id, role, content)
                VALUES (?, 'assistant', ?)
            """, (conv_id, response))
            
            db.execute("""
                UPDATE chatbot_conversations SET message_count = message_count + 2 WHERE id = ?
            """, (conv_id,))
            
            # Update last_used_at on chatbot
            db.execute("""
                UPDATE chatbots SET last_used_at = strftime('%s', 'now') * 1000 WHERE id = ?
            """, (chatbot_id,))
            
            db.commit()
        except Exception as e:
            print(f"Error logging conversation: {e}")
        
        return jsonify({
            'response': response,
            'widgetId': chatbot_id,
            'model': model_id
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


# ============================================================================
# License System
# ============================================================================

# Premium features pricing (USD/month)
PREMIUM_FEATURES = {
    'remove_watermark': {'price': 10, 'tier': 'essential', 'includes': ['profile_pic']},
    'extra_chatbot': {'price': 15, 'tier': 'professional'},
    'custom_icon': {'price': 5, 'tier': 'essential'},
    'analytics': {'price': 20, 'tier': 'professional'},
    # Subscription tiers
    'tier_essential': {'price': 10, 'tier': 'essential'},
    'tier_professional': {'price': 50, 'tier': 'professional'},
    'tier_business': {'price': 150, 'tier': 'business'},
}

# Stripe price IDs - update these in Stripe Dashboard
STRIPE_PRICES = {
    'remove_watermark': os.environ.get('STRIPE_PRICE_WATERMARK', 'price_test_watermark'),
    'extra_chatbot': os.environ.get('STRIPE_PRICE_EXTRA_BOT', 'price_test_extra_bot'),
    'custom_icon': os.environ.get('STRIPE_PRICE_CUSTOM_ICON', 'price_test_custom_icon'),
    'analytics': os.environ.get('STRIPE_PRICE_ANALYTICS', 'price_test_analytics'),
    'tier_essential': os.environ.get('STRIPE_PRICE_ESSENTIAL', 'price_test_essential'),
    'tier_professional': os.environ.get('STRIPE_PRICE_PROFESSIONAL', 'price_test_professional'),
    'tier_business': os.environ.get('STRIPE_PRICE_BUSINESS', 'price_test_business'),
}

@app.route('/api/license/check', methods=['POST'])
def api_license_check():
    """Check if a user/chatbot has a specific license feature"""
    data = request.json or {}
    user_id = data.get('user_id', 'default')
    chatbot_id = data.get('chatbot_id')
    feature = data.get('feature')
    
    db = get_chatbots_db()
    try:
        now_ms = int(time.time() * 1000)
        
        # Query for valid license
        if chatbot_id:
            license_row = db.execute("""
                SELECT * FROM licenses 
                WHERE user_id = ? AND (chatbot_id = ? OR chatbot_id IS NULL)
                AND (expires_at IS NULL OR expires_at > ?)
                ORDER BY chatbot_id DESC NULLS LAST
                LIMIT 1
            """, (user_id, chatbot_id, now_ms)).fetchone()
        else:
            license_row = db.execute("""
                SELECT * FROM licenses 
                WHERE user_id = ? AND chatbot_id IS NULL
                AND (expires_at IS NULL OR expires_at > ?)
                LIMIT 1
            """, (user_id, now_ms)).fetchone()
        
        if not license_row:
            return jsonify({
                'valid': False,
                'tier': 'free',
                'features': [],
                'message': 'No active license found'
            })
        
        license_data = dict(license_row)
        features = json.loads(license_data.get('features', '[]'))
        
        # Check specific feature if requested
        if feature:
            has_feature = feature in features
            return jsonify({
                'valid': has_feature,
                'tier': license_data.get('tier', 'free'),
                'features': features,
                'feature_checked': feature
            })
        
        return jsonify({
            'valid': True,
            'tier': license_data.get('tier', 'free'),
            'features': features,
            'expires_at': license_data.get('expires_at'),
            'subscription_id': license_data.get('stripe_subscription_id')
        })
    except Exception as e:
        return jsonify({'valid': False, 'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/license/features')
def api_license_features():
    """Get available premium features"""
    return jsonify({
        'features': PREMIUM_FEATURES
    })


@app.route('/api/license/grant', methods=['POST'])
def api_license_grant():
    """Grant a license (for testing/admin)"""
    data = request.json or {}
    user_id = data.get('user_id', 'default')
    chatbot_id = data.get('chatbot_id')
    tier = data.get('tier', 'pro')
    features = data.get('features', [])
    expires_days = data.get('expires_days', 30)
    
    db = get_chatbots_db()
    try:
        import uuid
        license_id = str(uuid.uuid4())[:16]
        expires_at = int((time.time() + expires_days * 86400) * 1000) if expires_days else None
        
        db.execute("""
            INSERT INTO licenses (id, user_id, chatbot_id, tier, features, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (license_id, user_id, chatbot_id, tier, json.dumps(features), expires_at))
        db.commit()
        
        return jsonify({
            'success': True,
            'license_id': license_id,
            'expires_at': expires_at
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


# ============================================================================
# Stripe Integration
# ============================================================================

# Configuration - set these in environment or config file
STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', 'sk_test_placeholder')
STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', 'pk_test_placeholder')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', 'whsec_placeholder')

# Note: STRIPE_PRICES defined above with PREMIUM_FEATURES


@app.route('/api/stripe/config')
def api_stripe_config():
    """Get Stripe publishable key"""
    return jsonify({
        'publishableKey': STRIPE_PUBLISHABLE_KEY,
        'testMode': 'test' in STRIPE_SECRET_KEY or STRIPE_SECRET_KEY == 'sk_test_placeholder'
    })


@app.route('/api/stripe/checkout', methods=['POST'])
def api_stripe_checkout():
    """Create Stripe Checkout session"""
    data = request.json or {}
    # Support both 'feature' and 'add_on' parameter names
    feature = data.get('feature') or data.get('add_on')
    user_id = data.get('user_id', 'default')
    chatbot_id = data.get('chatbot_id')
    duration_months = data.get('duration_months', 1)
    success_url = data.get('success_url', request.host_url + 'settings?payment=success')
    cancel_url = data.get('cancel_url', request.host_url + 'settings?payment=cancelled')
    
    # Map add_on names to feature names
    feature_map = {
        'watermark': 'remove_watermark',
        'remove_watermark': 'remove_watermark',
        'extra_bots_3': 'extra_bots_3',
        'extra_bots_10': 'extra_bots_10',
    }
    feature = feature_map.get(feature, feature)
    
    if not feature or feature not in STRIPE_PRICES:
        return jsonify({'error': 'Invalid feature', 'valid_features': list(STRIPE_PRICES.keys())}), 400
    
    # Check if stripe is properly configured
    if STRIPE_SECRET_KEY == 'sk_test_placeholder':
        return jsonify({
            'error': 'Stripe not configured',
            'message': 'Please set STRIPE_SECRET_KEY environment variable',
            'testMode': True
        }), 503
    
    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
        
        price_id = STRIPE_PRICES[feature]
        
        session = stripe.checkout.Session.create(
            mode='subscription',
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                'user_id': user_id,
                'chatbot_id': chatbot_id or '',
                'feature': feature
            }
        )
        
        return jsonify({
            'sessionId': session.id,
            'url': session.url,
            'checkout_url': session.url  # Alias for frontend compatibility
        })
    except ImportError:
        return jsonify({
            'error': 'Stripe library not installed',
            'message': 'Run: pip install stripe'
        }), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/stripe/webhook', methods=['POST'])
def api_stripe_webhook():
    """Handle Stripe webhook events"""
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    
    if STRIPE_SECRET_KEY == 'sk_test_placeholder':
        return jsonify({'error': 'Stripe not configured'}), 503
    
    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
        
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ImportError:
        return jsonify({'error': 'Stripe library not installed'}), 503
    except Exception as e:
        return jsonify({'error': f'Webhook error: {e}'}), 400
    
    db = get_chatbots_db()
    try:
        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            metadata = session.get('metadata', {})
            
            user_id = metadata.get('user_id', 'default')
            chatbot_id = metadata.get('chatbot_id') or None
            feature = metadata.get('feature')
            subscription_id = session.get('subscription')
            customer_id = session.get('customer')
            
            # Determine features based on subscription
            features = [feature]
            if feature == 'remove_watermark':
                features.append('profile_pic')
            
            tier = PREMIUM_FEATURES.get(feature, {}).get('tier', 'pro')
            
            # Grant license
            import uuid
            license_id = str(uuid.uuid4())[:16]
            
            db.execute("""
                INSERT INTO licenses (id, user_id, chatbot_id, tier, features, 
                                      stripe_subscription_id, stripe_customer_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (license_id, user_id, chatbot_id, tier, json.dumps(features),
                  subscription_id, customer_id))
            db.commit()
            
        elif event['type'] == 'customer.subscription.deleted':
            subscription = event['data']['object']
            subscription_id = subscription['id']
            
            # Expire the license
            db.execute("""
                UPDATE licenses SET expires_at = ? WHERE stripe_subscription_id = ?
            """, (int(time.time() * 1000), subscription_id))
            db.commit()
        
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/stripe/portal', methods=['POST'])
def api_stripe_portal():
    """Create Stripe Customer Portal session for managing subscriptions"""
    data = request.json or {}
    user_id = data.get('user_id', 'default')
    return_url = data.get('return_url', request.host_url + 'settings')
    
    if STRIPE_SECRET_KEY == 'sk_test_placeholder':
        return jsonify({'error': 'Stripe not configured'}), 503
    
    db = get_chatbots_db()
    try:
        # Get customer ID from license
        license_row = db.execute("""
            SELECT stripe_customer_id FROM licenses 
            WHERE user_id = ? AND stripe_customer_id IS NOT NULL
            LIMIT 1
        """, (user_id,)).fetchone()
        
        if not license_row or not license_row['stripe_customer_id']:
            return jsonify({'error': 'No subscription found'}), 404
        
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
        
        session = stripe.billing_portal.Session.create(
            customer=license_row['stripe_customer_id'],
            return_url=return_url
        )
        
        return jsonify({'url': session.url})
    except ImportError:
        return jsonify({'error': 'Stripe library not installed'}), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


# ============================================================================
# Settings API
# ============================================================================

SETTINGS_FILE = CLAWD_DIR / 'projects' / 'resonantos-v3' / 'dashboard' / 'settings.json'

@app.route('/api/settings')
def api_settings():
    """Get dashboard settings"""
    defaults = {
        'theme': 'dark',
        'autoRefresh': True,
        'refreshInterval': 30,
        'notifications': True,
        'permissions': {
            'browserAccess': True,
            'shellCommands': True,
            'fileWrite': True,
            'externalMessaging': False,
            'toolInstallation': True
        }
    }
    
    try:
        if SETTINGS_FILE.exists():
            saved = json.loads(SETTINGS_FILE.read_text())
            defaults.update(saved)
    except Exception as e:
        print(f"Error loading settings: {e}")
    
    return jsonify(defaults)


@app.route('/api/settings', methods=['POST'])
def api_save_settings():
    """Save dashboard settings"""
    data = request.json or {}
    
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(data, indent=2))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# Crypto Payment Endpoints
# ============================================================================

import uuid
import requests
from functools import lru_cache

# Crypto payment configuration - Multi-chain support
CRYPTO_CONFIG = {
    'network': 'devnet',  # Change to 'mainnet' for production
    
    # Wallet addresses for each chain
    'wallets': {
        'solana': 'FiTDJaC4ZZ5tkPKMvShqLvuPg8Y5EbQdGVMLgEiCVuUp',
        'bitcoin': 'bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh',  # Replace with actual BTC address
        'ethereum': '0x742d35Cc6634C0532925a3b844Bc9e7595f3A123'   # Replace with actual ETH address
    },
    
    # Supported tokens per chain
    'supported_tokens': {
        'solana': ['SOL', 'USDT', 'USDC'],
        'bitcoin': ['BTC'],
        'ethereum': ['ETH', 'USDT', 'USDC']
    },
    
    # Add-ons with pricing
    'addons': {
        'watermark': {'name': 'Remove Watermark', 'price_usd': 10},
        'extra_chatbot': {'name': 'Extra Chatbot', 'price_usd': 15},
        'custom_icon': {'name': 'Custom Icon', 'price_usd': 5},
        'analytics': {'name': 'Advanced Analytics', 'price_usd': 20},
    },
    
    # Subscription tiers
    'tiers': {
        'essential': {'name': 'Essential', 'price_usd': 10, 'features': ['watermark', 'custom_icon']},
        'professional': {'name': 'Professional', 'price_usd': 50, 'features': ['watermark', 'custom_icon', 'extra_chatbot', 'analytics', '5_chatbots']},
        'business': {'name': 'Business', 'price_usd': 150, 'features': ['watermark', 'custom_icon', 'analytics', 'unlimited_chatbots', 'priority_support']},
    },
    
    'payment_expiry_minutes': 30
}

# In-memory payment store (use DB in production)
pending_payments = {}


@lru_cache(maxsize=1)
def get_sol_price_cached():
    """Get SOL price in USD from CoinGecko with caching"""
    try:
        response = requests.get(
            'https://api.coingecko.com/api/v3/simple/price',
            params={'ids': 'solana', 'vs_currencies': 'usd'},
            timeout=10
        )
        if response.ok:
            data = response.json()
            return data.get('solana', {}).get('usd', 200)  # Default to $200 if API fails
    except Exception as e:
        print(f"CoinGecko API error: {e}")
    return 200  # Fallback price


def get_sol_price():
    """Get current SOL price, refreshing cache every 5 minutes"""
    # Clear cache if older than 5 minutes
    cache_info = get_sol_price_cached.cache_info()
    if hasattr(get_sol_price, '_last_call'):
        if time.time() - get_sol_price._last_call > 300:
            get_sol_price_cached.cache_clear()
    get_sol_price._last_call = time.time()
    return get_sol_price_cached()


def init_crypto_payments_db():
    """Initialize crypto payments table in the database"""
    db = get_db()
    if db:
        try:
            db.execute('''
                CREATE TABLE IF NOT EXISTS crypto_payments (
                    payment_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    add_on TEXT NOT NULL,
                    duration_months INTEGER NOT NULL,
                    amount_usd REAL NOT NULL,
                    amount_sol REAL NOT NULL,
                    payment_address TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    tx_signature TEXT,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    confirmed_at INTEGER,
                    license_expires_at INTEGER
                )
            ''')
            db.commit()
        except Exception as e:
            print(f"Error creating crypto_payments table: {e}")
        finally:
            db.close()


# Initialize table on startup
try:
    init_crypto_payments_db()
except:
    pass


@lru_cache(maxsize=1)
def get_btc_price_cached():
    """Get BTC price in USD from CoinGecko with caching"""
    try:
        response = requests.get(
            'https://api.coingecko.com/api/v3/simple/price',
            params={'ids': 'bitcoin', 'vs_currencies': 'usd'},
            timeout=10
        )
        if response.ok:
            data = response.json()
            return data.get('bitcoin', {}).get('usd', 95000)
    except Exception as e:
        print(f"CoinGecko BTC API error: {e}")
    return 95000  # Fallback price


@lru_cache(maxsize=1)
def get_eth_price_cached():
    """Get ETH price in USD from CoinGecko with caching"""
    try:
        response = requests.get(
            'https://api.coingecko.com/api/v3/simple/price',
            params={'ids': 'ethereum', 'vs_currencies': 'usd'},
            timeout=10
        )
        if response.ok:
            data = response.json()
            return data.get('ethereum', {}).get('usd', 3500)
    except Exception as e:
        print(f"CoinGecko ETH API error: {e}")
    return 3500  # Fallback price


def get_crypto_prices():
    """Get all crypto prices, refreshing cache every 5 minutes"""
    now = time.time()
    if hasattr(get_crypto_prices, '_last_call'):
        if now - get_crypto_prices._last_call > 300:
            get_sol_price_cached.cache_clear()
            get_btc_price_cached.cache_clear()
            get_eth_price_cached.cache_clear()
    get_crypto_prices._last_call = now
    
    return {
        'SOL': get_sol_price_cached(),
        'BTC': get_btc_price_cached(),
        'ETH': get_eth_price_cached(),
        'USDT': 1.0,  # Stablecoins pegged to $1
        'USDC': 1.0,
    }


@app.route('/api/crypto/prices')
def api_crypto_prices():
    """Get current crypto prices"""
    prices = get_crypto_prices()
    return jsonify({
        'prices': prices,
        'updated': int(time.time() * 1000)
    })


@app.route('/api/crypto/checkout', methods=['POST'])
def crypto_checkout():
    """Create a multi-chain crypto payment request"""
    data = request.get_json()
    
    add_on = data.get('add_on')
    duration_months = data.get('duration_months', 1)
    chain = data.get('chain', 'solana')  # Default to Solana
    token = data.get('token', 'SOL')  # Default token
    
    # Validate chain
    if chain not in CRYPTO_CONFIG['wallets']:
        return jsonify({'error': 'Invalid chain', 'valid_chains': list(CRYPTO_CONFIG['wallets'].keys())}), 400
    
    # Validate token for chain
    if token not in CRYPTO_CONFIG['supported_tokens'].get(chain, []):
        return jsonify({
            'error': f'Token {token} not supported on {chain}',
            'valid_tokens': CRYPTO_CONFIG['supported_tokens'].get(chain, [])
        }), 400
    
    # Check if it's an add-on or a tier
    if add_on in CRYPTO_CONFIG['addons']:
        addon_info = CRYPTO_CONFIG['addons'][add_on]
        base_price = addon_info['price_usd']
        product_name = addon_info['name']
    elif add_on in CRYPTO_CONFIG['tiers']:
        tier_info = CRYPTO_CONFIG['tiers'][add_on]
        base_price = tier_info['price_usd']
        product_name = f"{tier_info['name']} Tier"
    else:
        return jsonify({
            'error': 'Invalid add-on or tier',
            'valid_addons': list(CRYPTO_CONFIG['addons'].keys()),
            'valid_tiers': list(CRYPTO_CONFIG['tiers'].keys())
        }), 400
    
    # Calculate pricing with discounts for longer durations
    if duration_months == 3:
        total_usd = base_price * 3 * 0.9  # 10% off
    elif duration_months == 12:
        total_usd = base_price * 12 * 0.8  # 20% off
    else:
        total_usd = base_price * duration_months
    
    # Get crypto prices and calculate amount
    prices = get_crypto_prices()
    token_price = prices.get(token, 1.0)
    
    # Calculate amount in chosen token
    if token in ['USDT', 'USDC']:
        amount_crypto = round(total_usd, 2)  # Stablecoins are 1:1
    else:
        amount_crypto = round(total_usd / token_price, 8 if token == 'BTC' else 6)
    
    # Generate payment ID and create payment record
    payment_id = str(uuid.uuid4())
    now = int(time.time() * 1000)
    expires_at = now + (CRYPTO_CONFIG['payment_expiry_minutes'] * 60 * 1000)
    
    payment = {
        'payment_id': payment_id,
        'add_on': add_on,
        'add_on_name': product_name,
        'duration_months': duration_months,
        'amount_usd': total_usd,
        'chain': chain,
        'token': token,
        'amount_crypto': amount_crypto,
        'token_price_usd': token_price,
        'payment_address': CRYPTO_CONFIG['wallets'][chain],
        'network': 'testnet' if CRYPTO_CONFIG['network'] == 'devnet' else 'mainnet',
        'status': 'pending',
        'created_at': now,
        'expires_at': expires_at
    }
    
    # Also include legacy fields for backward compatibility
    if chain == 'solana' and token == 'SOL':
        payment['amount_sol'] = amount_crypto
        payment['sol_price_usd'] = token_price
    
    # Store in memory (for immediate use) and DB (for persistence)
    pending_payments[payment_id] = payment
    
    # Store in database - update schema to support multi-chain
    db = get_db()
    if db:
        try:
            # Try with new schema first
            db.execute('''
                INSERT INTO crypto_payments 
                (payment_id, add_on, duration_months, amount_usd, amount_sol, 
                 payment_address, status, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (payment_id, add_on, duration_months, total_usd, amount_crypto,
                  CRYPTO_CONFIG['wallets'][chain], 'pending', now, expires_at))
            db.commit()
        except Exception as e:
            print(f"Error storing payment: {e}")
        finally:
            db.close()
    
    return jsonify(payment)


@app.route('/api/crypto/status')
def crypto_status():
    """Check payment status"""
    payment_id = request.args.get('payment_id')
    
    if not payment_id:
        return jsonify({'error': 'Payment ID required'}), 400
    
    # Check memory first, then DB
    payment = pending_payments.get(payment_id)
    
    if not payment:
        db = get_db()
        if db:
            try:
                row = db.execute(
                    'SELECT * FROM crypto_payments WHERE payment_id = ?',
                    (payment_id,)
                ).fetchone()
                if row:
                    payment = dict(row)
            except:
                pass
            finally:
                db.close()
    
    if not payment:
        return jsonify({'error': 'Payment not found'}), 404
    
    # Check if expired
    now = int(time.time() * 1000)
    if payment['status'] == 'pending' and now > payment['expires_at']:
        payment['status'] = 'expired'
        # Update in memory and DB
        if payment_id in pending_payments:
            pending_payments[payment_id]['status'] = 'expired'
        db = get_db()
        if db:
            try:
                db.execute(
                    'UPDATE crypto_payments SET status = ? WHERE payment_id = ?',
                    ('expired', payment_id)
                )
                db.commit()
            except:
                pass
            finally:
                db.close()
    
    return jsonify({
        'payment_id': payment['payment_id'],
        'status': payment['status'],
        'amount_sol': payment['amount_sol'],
        'expires_at': payment['expires_at'],
        'tx_signature': payment.get('tx_signature'),
        'license_expires': payment.get('license_expires_at')
    })


@app.route('/api/crypto/verify', methods=['POST'])
def crypto_verify():
    """Verify a crypto transaction"""
    data = request.get_json()
    
    payment_id = data.get('payment_id')
    tx_signature = data.get('tx_signature')
    
    if not payment_id or not tx_signature:
        return jsonify({'error': 'Payment ID and transaction signature required'}), 400
    
    # Get payment record
    payment = pending_payments.get(payment_id)
    if not payment:
        db = get_db()
        if db:
            try:
                row = db.execute(
                    'SELECT * FROM crypto_payments WHERE payment_id = ?',
                    (payment_id,)
                ).fetchone()
                if row:
                    payment = dict(row)
            except:
                pass
            finally:
                db.close()
    
    if not payment:
        return jsonify({'error': 'Payment not found', 'verified': False}), 404
    
    if payment['status'] == 'confirmed':
        return jsonify({
            'verified': True,
            'message': 'Payment already confirmed',
            'tx_signature': payment.get('tx_signature')
        })
    
    if payment['status'] == 'expired':
        return jsonify({'error': 'Payment expired', 'verified': False}), 400
    
    # Verify transaction on Solana
    # In production, this would make RPC call to verify:
    # 1. Transaction exists
    # 2. Transaction is to our merchant wallet
    # 3. Amount matches expected amount
    # 4. Transaction is finalized
    
    network_url = 'https://api.devnet.solana.com' if CRYPTO_CONFIG['network'] == 'devnet' else 'https://api.mainnet-beta.solana.com'
    
    try:
        # Get transaction details from Solana RPC
        rpc_response = requests.post(
            network_url,
            json={
                'jsonrpc': '2.0',
                'id': 1,
                'method': 'getTransaction',
                'params': [
                    tx_signature,
                    {'encoding': 'jsonParsed', 'maxSupportedTransactionVersion': 0}
                ]
            },
            timeout=15
        )
        
        if not rpc_response.ok:
            return jsonify({'error': 'Failed to fetch transaction', 'verified': False}), 500
        
        tx_data = rpc_response.json()
        
        if tx_data.get('error') or not tx_data.get('result'):
            return jsonify({
                'error': 'Transaction not found or not yet confirmed',
                'verified': False,
                'hint': 'Wait a few seconds and try again if transaction was just sent'
            }), 400
        
        # For devnet testing, we'll accept the transaction if it exists and is successful
        # In production, you'd verify:
        # - postBalances vs preBalances to confirm amount
        # - Recipient address matches merchant wallet
        result = tx_data['result']
        
        if result.get('meta', {}).get('err') is not None:
            return jsonify({'error': 'Transaction failed', 'verified': False}), 400
        
        # Transaction verified! Update payment record
        now = int(time.time() * 1000)
        license_expires = now + (payment['duration_months'] * 30 * 24 * 60 * 60 * 1000)  # ~months in ms
        
        # Update in memory
        if payment_id in pending_payments:
            pending_payments[payment_id]['status'] = 'confirmed'
            pending_payments[payment_id]['tx_signature'] = tx_signature
            pending_payments[payment_id]['confirmed_at'] = now
            pending_payments[payment_id]['license_expires_at'] = license_expires
        
        # Update in database
        db = get_db()
        if db:
            try:
                db.execute('''
                    UPDATE crypto_payments 
                    SET status = ?, tx_signature = ?, confirmed_at = ?, license_expires_at = ?
                    WHERE payment_id = ?
                ''', ('confirmed', tx_signature, now, license_expires, payment_id))
                db.commit()
            except Exception as e:
                print(f"Error updating payment: {e}")
            finally:
                db.close()
        
        # Grant license to user (like Stripe webhook does)
        addon_id = payment['add_on']
        chatbots_db = get_chatbots_db()
        if chatbots_db:
            try:
                import uuid
                license_id = str(uuid.uuid4())[:16]
                user_id = payment.get('user_id', 'default')
                
                # Determine features based on addon/tier
                features = [addon_id]
                if addon_id in CRYPTO_CONFIG['addons']:
                    tier = 'addon'
                elif addon_id in CRYPTO_CONFIG['tiers']:
                    tier = addon_id
                    # Add all features from the tier
                    features = CRYPTO_CONFIG['tiers'][addon_id].get('features', [addon_id])
                else:
                    tier = 'addon'
                
                chatbots_db.execute("""
                    INSERT INTO licenses (id, user_id, tier, features, expires_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (license_id, user_id, tier, json.dumps(features), license_expires))
                chatbots_db.commit()
                print(f"License granted: {license_id} for features {features}")
            except Exception as e:
                print(f"Error granting license: {e}")
            finally:
                chatbots_db.close()
        
        # Format license expiry for display
        license_expires_str = datetime.fromtimestamp(license_expires / 1000).strftime('%Y-%m-%d')
        
        return jsonify({
            'verified': True,
            'tx_signature': tx_signature,
            'add_on': payment['add_on'],
            'license_expires': license_expires_str,
            'message': 'Payment confirmed! License activated.'
        })
        
    except requests.Timeout:
        return jsonify({'error': 'Solana RPC timeout', 'verified': False}), 503
    except Exception as e:
        print(f"Transaction verification error: {e}")
        return jsonify({'error': f'Verification failed: {str(e)}', 'verified': False}), 500


@app.route('/api/crypto/payments')
def crypto_payments():
    """Get payment history"""
    limit = request.args.get('limit', 20, type=int)
    status = request.args.get('status')
    
    db = get_db()
    if not db:
        return jsonify({'payments': [], 'error': 'Database not available'})
    
    try:
        query = 'SELECT * FROM crypto_payments'
        params = []
        
        if status:
            query += ' WHERE status = ?'
            params.append(status)
        
        query += ' ORDER BY created_at DESC LIMIT ?'
        params.append(limit)
        
        rows = db.execute(query, params).fetchall()
        payments = [dict(row) for row in rows]
        
        return jsonify({'payments': payments, 'count': len(payments)})
    except Exception as e:
        return jsonify({'payments': [], 'error': str(e)})
    finally:
        db.close()


@app.route('/api/addons')
def api_addons():
    """Get available add-ons and their status"""
    user_id = request.args.get('user_id', 'default')
    now_ms = int(time.time() * 1000)
    
    # Get user's active licenses
    active_features = {}
    db = get_chatbots_db()
    try:
        rows = db.execute("""
            SELECT features, expires_at FROM licenses 
            WHERE user_id = ? AND (expires_at IS NULL OR expires_at > ?)
        """, (user_id, now_ms)).fetchall()
        
        for row in rows:
            features = json.loads(row['features'] or '[]')
            expires_at = row['expires_at']
            for feature in features:
                # Keep the latest expiry date
                if feature not in active_features or (expires_at and expires_at > (active_features[feature] or 0)):
                    active_features[feature] = expires_at
    except Exception as e:
        print(f"Error loading licenses: {e}")
    finally:
        db.close()
    
    addons = []
    for addon_id, info in CRYPTO_CONFIG['addons'].items():
        is_active = addon_id in active_features
        addons.append({
            'id': addon_id,
            'name': info['name'],
            'price_usd': info['price_usd'],
            'active': is_active,
            'expires_at': active_features.get(addon_id)
        })
    
    return jsonify({'addons': addons, 'active_features': list(active_features.keys())})


# ============================================================================
# Projects API
# ============================================================================

@app.route('/api/projects')
def api_projects():
    """Get list of projects from ~/clawd/projects/"""
    projects_dir = WORKSPACE_PATH / 'projects'
    projects = []
    
    if not projects_dir.exists():
        return jsonify({'projects': [], 'count': 0, 'error': 'Projects directory not found'})
    
    try:
        for project_path in sorted(projects_dir.iterdir()):
            if not project_path.is_dir():
                continue
            if project_path.name.startswith('.'):
                continue
            
            project = {
                'name': project_path.name,
                'path': str(project_path.relative_to(WORKSPACE_PATH)),
                'fullPath': str(project_path),
                'description': '',
                'status': 'unknown',
                'files': [],
                'hasBusinessPlan': False,
                'hasReadme': False,
                'modified': 0
            }
            
            # Check for README
            readme_paths = [project_path / 'README.md', project_path / 'readme.md', project_path / 'Readme.md']
            for readme_path in readme_paths:
                if readme_path.exists():
                    project['hasReadme'] = True
                    try:
                        content = readme_path.read_text(errors='replace')
                        lines = content.split('\n')
                        for i, line in enumerate(lines):
                            if line.startswith('# '):
                                project['title'] = line[2:].strip()
                            elif line.strip() and not line.startswith('#') and not line.startswith('---'):
                                project['description'] = line.strip()[:200]
                                break
                    except Exception:
                        pass
                    break
            
            # Check for business plan
            bp_paths = [
                project_path / 'BUSINESS_PLAN.md',
                project_path / 'BusinessPlan.md',
                project_path / 'business-plan.md'
            ]
            for bp_path in bp_paths:
                if bp_path.exists():
                    project['hasBusinessPlan'] = True
                    project['businessPlanPath'] = str(bp_path.relative_to(WORKSPACE_PATH))
                    break
            
            # Detect status
            status_indicators = {
                'active': ['src', 'lib', 'package.json', 'Cargo.toml', 'requirements.txt'],
                'planning': ['PLAN.md', 'SPEC.md', 'DESIGN.md'],
                'archived': ['ARCHIVED.md', '.archived']
            }
            
            for status, indicators in status_indicators.items():
                for indicator in indicators:
                    if (project_path / indicator).exists():
                        project['status'] = status
                        break
                if project['status'] != 'unknown':
                    break
            
            if project['status'] == 'unknown':
                project['status'] = 'planning' if project['hasReadme'] else 'unknown'
            
            # Get file list (top level only)
            try:
                files = []
                for f in sorted(project_path.iterdir())[:20]:
                    if f.name.startswith('.'):
                        continue
                    stat = f.stat()
                    files.append({
                        'name': f.name,
                        'type': 'folder' if f.is_dir() else 'file',
                        'size': stat.st_size if f.is_file() else 0,
                        'modified': int(stat.st_mtime * 1000)
                    })
                    project['modified'] = max(project['modified'], int(stat.st_mtime * 1000))
                project['files'] = files
            except Exception:
                pass
            
            projects.append(project)
        
        projects.sort(key=lambda p: p['modified'], reverse=True)
        
        return jsonify({
            'projects': projects,
            'count': len(projects),
            'path': str(projects_dir)
        })
    except Exception as e:
        return jsonify({'projects': [], 'count': 0, 'error': str(e)})


# ============================================================================
# Health Check
# ============================================================================

@app.route('/health')
def health():
    """Health check endpoint."""
    db_status = 'connected' if get_db() else 'disconnected'
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "database": db_status
    })


# ============================================================================
# ============================================================================
# R-Memory SSoT Manager
# ============================================================================

import re as _re

SSOT_ROOT = Path.home() / '.openclaw' / 'workspace' / 'resonantos-augmentor' / 'ssot'
PLUGIN_PATH = Path.home() / '.openclaw' / 'extensions' / 'resonantos' / 'index.ts'
SSOT_TRASH_DIR = Path.home() / '.openclaw' / 'workspace' / 'resonantos-augmentor' / '.trash'

def _estimate_tokens(text):
    return max(1, len(text) // 4)

def _scan_ssot():
    if not SSOT_ROOT.exists():
        return []
    docs = []
    for layer_dir in sorted(SSOT_ROOT.glob("L*")):
        if not layer_dir.is_dir():
            continue
        layer = layer_dir.name
        for md_file in layer_dir.glob("*.md"):
            if md_file.name.endswith(".ai.md"):
                continue
            content = md_file.read_text(errors='ignore')
            tokens = _estimate_tokens(content)
            ai_path = md_file.with_name(md_file.stem + ".ai.md")
            compression_ratio = None
            if ai_path.exists():
                ai_tokens = _estimate_tokens(ai_path.read_text(errors='ignore'))
                compression_ratio = round((1 - ai_tokens / tokens) * 100) if tokens > 0 else 0
            docs.append({
                'path': str(md_file.relative_to(SSOT_ROOT)),
                'filename': md_file.name,
                'layer': layer,
                'tokens': tokens,
                'has_compressed': ai_path.exists(),
                'compression_ratio': compression_ratio,
                'modified_at': datetime.fromtimestamp(md_file.stat().st_mtime).isoformat(),
                'locked': _is_locked(str(md_file)),
            })
    return docs

def _read_primary_keywords():
    if not PLUGIN_PATH.exists():
        return {}
    content = PLUGIN_PATH.read_text(errors='ignore')
    match = _re.search(r'const PRIMARY_KEYWORDS[:\s]*Record<string,\s*string\[\]>\s*=\s*({[\s\S]*?});', content)
    if not match:
        return {}
    result = {}
    for entry in _re.finditer(r'"([^"]+)"\s*:\s*\[(.*?)\]', match.group(1)):
        key = entry.group(1)
        kws = [kw.strip().strip('"') for kw in entry.group(2).split(',')]
        result[key] = [kw for kw in kws if kw]
    return result

def _write_primary_keywords(kw_dict):
    if not PLUGIN_PATH.exists():
        return False
    content = PLUGIN_PATH.read_text(errors='ignore')
    new_kw = "const PRIMARY_KEYWORDS: Record<string, string[]> = {\n"
    for doc_id, kws in sorted(kw_dict.items()):
        kw_list = ', '.join([f'"{kw}"' for kw in kws])
        new_kw += f'  "{doc_id}": [{kw_list}],\n'
    new_kw += "};"
    pattern = r'const PRIMARY_KEYWORDS[:\s]*Record<string,\s*string\[\]>\s*=\s*\{[\s\S]*?\};'
    new_content = _re.sub(pattern, new_kw, content)
    if new_content != content:
        PLUGIN_PATH.write_text(new_content)
        return True
    return False

def _is_locked(filepath):
    """Check if file has macOS immutable (uchg) flag"""
    try:
        import stat
        st = os.stat(filepath)
        return bool(st.st_flags & stat.UF_IMMUTABLE)
    except (AttributeError, OSError):
        return False

def _lock_file(filepath):
    """Lock a file with chflags uchg (no password needed)"""
    try:
        subprocess.run(['chflags', 'uchg', str(filepath)], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False

def _unlock_file(filepath, password):
    """Unlock a file with chflags nouchg (requires sudo password)"""
    try:
        proc = subprocess.run(
            ['sudo', '-S', 'chflags', 'nouchg', str(filepath)],
            input=password.encode() + b'\n',
            capture_output=True,
            timeout=10
        )
        return proc.returncode == 0
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False

@app.route('/r-memory')
def r_memory():
    return render_template('r-memory.html',
                          active_page='r-memory',
                          ssot_root=str(SSOT_ROOT),
                          plugin_path=str(PLUGIN_PATH),
                          plugin_exists=PLUGIN_PATH.exists())

@app.route('/api/r-memory/stats')
def api_rmem_stats():
    docs = _scan_ssot()
    stats = {
        'total_docs': len(docs),
        'total_tokens': sum(d['tokens'] for d in docs),
        'compressed': sum(1 for d in docs if d['has_compressed']),
        'by_layer': {}
    }
    for d in docs:
        layer = d['layer']
        if layer not in stats['by_layer']:
            stats['by_layer'][layer] = {'count': 0, 'tokens': 0}
        stats['by_layer'][layer]['count'] += 1
        stats['by_layer'][layer]['tokens'] += d['tokens']
    return jsonify(stats)

@app.route('/api/r-memory/documents')
def api_rmem_documents():
    return jsonify(_scan_ssot())

@app.route('/api/r-memory/documents/<path:doc_path>', methods=['GET'])
def api_rmem_doc_get(doc_path):
    full_path = SSOT_ROOT / doc_path
    if not full_path.exists():
        return jsonify({'error': 'Not found'}), 404
    content = full_path.read_text(errors='ignore')
    return jsonify({
        'path': doc_path,
        'content': content,
        'tokens': _estimate_tokens(content),
        'modified_at': datetime.fromtimestamp(full_path.stat().st_mtime).isoformat()
    })

@app.route('/api/r-memory/documents/<path:doc_path>', methods=['PUT'])
def api_rmem_doc_save(doc_path):
    full_path = SSOT_ROOT / doc_path
    if not full_path.exists():
        return jsonify({'error': 'Not found'}), 404
    data = request.get_json()
    content = data.get('content', '')
    full_path.write_text(content)
    return jsonify({'path': doc_path, 'tokens': _estimate_tokens(content), 'modified_at': datetime.now().isoformat()})

@app.route('/api/r-memory/documents', methods=['POST'])
def api_rmem_doc_create():
    data = request.get_json()
    layer = data.get('layer', 'L4')
    name = _re.sub(r'[^a-zA-Z0-9_-]', '_', data.get('name', 'Untitled'))
    if not name:
        name = 'Untitled'
    layer_dir = SSOT_ROOT / layer
    if not layer_dir.exists():
        return jsonify({'error': f'Layer {layer} not found'}), 400
    doc_path = layer_dir / f"{name}.md"
    counter = 1
    while doc_path.exists():
        doc_path = layer_dir / f"{name}_{counter}.md"
        counter += 1
    doc_path.write_text("# " + name + "\n\n")
    return jsonify({'path': str(doc_path.relative_to(SSOT_ROOT)), 'filename': doc_path.name}), 201

@app.route('/api/r-memory/documents/<path:doc_path>', methods=['DELETE'])
def api_rmem_doc_delete(doc_path):
    full_path = SSOT_ROOT / doc_path
    if not full_path.exists():
        return jsonify({'error': 'Not found'}), 404
    import shutil
    SSOT_TRASH_DIR.mkdir(parents=True, exist_ok=True)
    trash_path = SSOT_TRASH_DIR / (datetime.now().strftime("%Y%m%d_%H%M%S_") + full_path.name)
    shutil.move(str(full_path), str(trash_path))
    ai_path = full_path.with_name(full_path.stem + ".ai.md")
    if ai_path.exists():
        shutil.move(str(ai_path), str(trash_path.with_name(ai_path.name)))
    return jsonify({'status': 'deleted'})

@app.route('/api/r-memory/lock/<path:doc_path>', methods=['POST'])
def api_rmem_lock(doc_path):
    """Lock a document (no password needed)"""
    full_path = SSOT_ROOT / doc_path
    if not full_path.exists():
        return jsonify({'error': 'Not found'}), 404
    success = _lock_file(str(full_path))
    # Also lock .ai.md if exists
    ai_path = full_path.with_name(full_path.stem + ".ai.md")
    if ai_path.exists():
        _lock_file(str(ai_path))
    return jsonify({'locked': success})

@app.route('/api/r-memory/unlock/<path:doc_path>', methods=['POST'])
def api_rmem_unlock(doc_path):
    """Unlock a document (requires master password)"""
    full_path = SSOT_ROOT / doc_path
    if not full_path.exists():
        return jsonify({'error': 'Not found'}), 404
    data = request.get_json()
    password = data.get('password', '')
    if not password:
        return jsonify({'error': 'Password required'}), 400
    success = _unlock_file(str(full_path), password)
    # Also unlock .ai.md if exists
    ai_path = full_path.with_name(full_path.stem + ".ai.md")
    if ai_path.exists():
        _unlock_file(str(ai_path), password)
    return jsonify({'unlocked': success})

@app.route('/api/r-memory/lock-layer/<layer>', methods=['POST'])
def api_rmem_lock_layer(layer):
    """Lock all documents in a layer"""
    layer_dir = SSOT_ROOT / layer
    if not layer_dir.exists():
        return jsonify({'error': 'Layer not found'}), 400
    count = 0
    for md_file in layer_dir.glob("*.md"):
        if _lock_file(str(md_file)):
            count += 1
    return jsonify({'locked': count})

@app.route('/api/r-memory/unlock-layer/<layer>', methods=['POST'])
def api_rmem_unlock_layer(layer):
    """Unlock all documents in a layer (requires master password)"""
    layer_dir = SSOT_ROOT / layer
    if not layer_dir.exists():
        return jsonify({'error': 'Layer not found'}), 400
    data = request.get_json()
    password = data.get('password', '')
    if not password:
        return jsonify({'error': 'Password required'}), 400
    count = 0
    for md_file in layer_dir.glob("*.md"):
        if _unlock_file(str(md_file), password):
            count += 1
    return jsonify({'unlocked': count})

@app.route('/api/r-memory/keywords', methods=['GET'])
def api_rmem_kw_get():
    return jsonify(_read_primary_keywords())

@app.route('/api/r-memory/keywords', methods=['PUT'])
def api_rmem_kw_save():
    data = request.get_json()
    success = _write_primary_keywords(data)
    return jsonify({'status': 'saved' if success else 'no_change'})


# Main
# ============================================================================

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='ResonantOS Dashboard Server')
    parser.add_argument('--port', type=int, default=19100, help='Port to run on')
    parser.add_argument('--host', type=str, default='127.0.0.1', help='Host to bind to')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--dist', action='store_true', help='Use production build (obfuscated)')
    args = parser.parse_args()
    
    # Switch to production build if --dist flag
    if args.dist:
        dist_path = Path(__file__).parent / 'dist-dashboard'
        if dist_path.exists():
            app.static_folder = str(dist_path / 'static')
            app.template_folder = str(dist_path / 'templates')
            mode = "PRODUCTION (obfuscated)"
        else:
            print("⚠️  dist-dashboard/ not found. Run: node scripts/build-dashboard.js")
            print("    Falling back to development mode...")
            mode = "DEVELOPMENT"
    else:
        mode = "DEVELOPMENT"
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                   ResonantOS Dashboard                       ║
║                   v3.0.0 ({mode})
╠══════════════════════════════════════════════════════════════╣
║  Server running at: http://{args.host}:{args.port}              ║
║  Database: {WATCHTOWER_DB}
║  Press Ctrl+C to stop                                        ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    app.run(host=args.host, port=args.port, debug=args.debug)

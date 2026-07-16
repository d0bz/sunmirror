#!/usr/bin/env python3
import os
import json
import sys
import subprocess
import traceback
import signal
import time
import uuid
import threading
import datetime as dt
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs
import tempfile
import argparse


# ── CLI: detect --simulation flag before the server starts ─────────────────
_arg_parser = argparse.ArgumentParser(add_help=False)
_arg_parser.add_argument('--simulation', action='store_true',
                          help='Run without hardware (no servos, no GPIO)')
_arg_parser.add_argument('--port', type=int, default=80)
_known_args, _ = _arg_parser.parse_known_args()

SIMULATION_MODE = _known_args.simulation
SERVER_PORT     = _known_args.port

if SIMULATION_MODE:
    print("⚙️  SIMULATION MODE — no hardware required")

# Add parent directory to path to access main.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# In simulation mode write a stub that replaces main.py
_SIM_MAIN_PATH = os.path.join(tempfile.gettempdir(), 'sunmirror_sim_main.py')
if SIMULATION_MODE:
    _stub = '''#!/usr/bin/env python3
"""Simulation stub – prints animation frames instead of moving servos."""
import argparse, json, time, sys, signal

ap = argparse.ArgumentParser()
ap.add_argument('--file', required=True)
ap.add_argument('--step-size', type=float, default=1.0)
ap.add_argument('--loop', action='store_true')
args = ap.parse_args()

def run_once():
    with open(args.file) as f:
        frames = json.load(f)
    for i, frame in enumerate(frames):
        angles = frame.get('angles', frame)
        values = list(angles.values())
        mn = min(float(v) for v in values)
        mx = max(float(v) for v in values)
        bar_len = 40
        bar = int((mx - mn) / 90 * bar_len)
        print(f"\\r[SIM] frame {i+1:>3}/{len(frames)} | min={mn:5.1f} max={mx:5.1f}  |{\"█\"*bar:{bar_len}}|", end="", flush=True)
        time.sleep(0.016)
    print()

signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

if args.loop:
    while True:
        run_once()
else:
    run_once()
'''
    with open(_SIM_MAIN_PATH, 'w') as _f:
        _f.write(_stub)
    print(f"[SIM] Stub written to {_SIM_MAIN_PATH}")

# Global variables to track the current animation process
current_process = None
PID_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'animation_pid.txt')
SHUTDOWN_IN_PROGRESS = False

# Shared animation state - controlled by both the physical toggle button and the web UI
animation_running = False          # True when an animation loop is active
current_animation_file = None      # Path to the animation JSON currently playing

_SERVER_DIR = os.path.dirname(os.path.abspath(__file__))

# Preset animation sets cycled by short-press of the physical button (or UI)
ANIMATION_PRESETS = [
    {"name": "Sync Pulse",       "file": os.path.join(_SERVER_DIR, "anim-pulse.json")},
    {"name": "Ring Ripple",      "file": os.path.join(_SERVER_DIR, "anim-ripple.json")},
    {"name": "Alternating Fan",  "file": os.path.join(_SERVER_DIR, "anim-alternating.json")},
]
current_animation_index = 0        # Which preset is selected

DEFAULT_LOOP_ANIMATION = ANIMATION_PRESETS[0]["file"]  # fallback / startup

# ---------------------------------------------------------------------------
# Schedule globals
# ---------------------------------------------------------------------------
SCHEDULE_FILE = os.path.join(_SERVER_DIR, 'schedule.json')
SCHEDULE_LOG  = os.path.join(_SERVER_DIR, 'logs', 'schedule.log')

def _sched_log(msg: str):
    """Append a timestamped line to logs/schedule.log, keeping last 500 lines."""
    try:
        os.makedirs(os.path.dirname(SCHEDULE_LOG), exist_ok=True)
        line = f"[{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n"
        # Append
        with open(SCHEDULE_LOG, 'a') as f:
            f.write(line)
        # Trim to last 500 lines
        with open(SCHEDULE_LOG, 'r') as f:
            lines = f.readlines()
        if len(lines) > 500:
            with open(SCHEDULE_LOG, 'w') as f:
                f.writelines(lines[-500:])
    except Exception as e:
        print(f"[Schedule] Log write error: {e}")

schedule_data = {
    "festival_start": None,   # ISO date string "YYYY-MM-DD"
    "festival_end":   None,   # ISO date string "YYYY-MM-DD"
    "enabled": False,
    "slots": []               # list of {id, day(0-N), start_minutes, end_minutes, animation_file}
}
schedule_enabled = False          # master on/off
schedule_started_by_runner = False  # True when runner owns the current process

# ---------------------------------------------------------------------------
# Animation library
# ---------------------------------------------------------------------------
ANIMATIONS_DIR = os.path.join(_SERVER_DIR, 'animations')
os.makedirs(ANIMATIONS_DIR, exist_ok=True)

def _get_all_animations():
    """Return unified list: built-in presets first, then user-saved animations.
    Each entry: {index, name, file, is_preset, frame_count}"""
    result = []
    for i, p in enumerate(ANIMATION_PRESETS):
        fc = 0
        try:
            with open(p['file']) as f:
                fc = len(json.load(f))
        except Exception:
            pass
        result.append({'index': i, 'name': p['name'], 'file': p['file'],
                        'is_preset': True, 'frame_count': fc})

    offset = len(ANIMATION_PRESETS)
    try:
        for fname in sorted(os.listdir(ANIMATIONS_DIR)):
            if not fname.endswith('.json'):
                continue
            fpath = os.path.join(ANIMATIONS_DIR, fname)
            name  = fname[:-5]  # strip .json
            fc = 0
            try:
                with open(fpath) as f:
                    fc = len(json.load(f))
            except Exception:
                pass
            result.append({'index': offset, 'name': name, 'file': fpath,
                            'is_preset': False, 'frame_count': fc})
            offset += 1
    except Exception as e:
        print(f"[Animations] Error scanning directory: {e}")
    return result

class AnimationServer(SimpleHTTPRequestHandler):
    def do_POST(self):
        """Handle POST requests to play animations"""
        global current_process, animation_running, current_animation_file, current_animation_index, schedule_enabled, schedule_data, schedule_started_by_runner
        if self.path == '/play_animation':
            try:
                # Get content length
                content_length = int(self.headers['Content-Length'])
                # Read post data as bytes
                post_data_bytes = self.rfile.read(content_length)
                # Convert bytes to string and parse JSON
                post_data_str = post_data_bytes.decode('utf-8')
                post_data = json.loads(post_data_str)
                
                # Extract animation frames and loop parameter
                animation_data = post_data.get('frames', post_data)
                loop = post_data.get('loop', False)
                
                # Create a temporary file to store the animation data
                temp_fd, temp_filename = tempfile.mkstemp(suffix='.json')
                try:
                    with os.fdopen(temp_fd, 'w') as temp_file:
                        json.dump(animation_data, temp_file)
                    
                    print(f"Animation data saved to temporary file: {temp_filename}")
                    
                    # Execute main.py with the temporary file
                    if SIMULATION_MODE:
                        main_py_path = _SIM_MAIN_PATH
                    else:
                        main_py_path = '/home/pi/sunmirror/main.py'
                    cmd = [sys.executable, main_py_path, '--file', temp_filename, '--step-size', '1.0']
                    
                    # Add loop parameter if enabled
                    if loop:
                        cmd.append('--l')
                    
                    # Kill any existing animation process
                    self._kill_existing_process()
                    
                    # Create log directory if it doesn't exist
                    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
                    os.makedirs(log_dir, exist_ok=True)
                    
                    log_file_path = os.path.join(log_dir, f'animation.log')
                    
                    # Execute the command in a separate process
                    global current_process
                    print(f"Executing command: {' '.join(cmd)}")
                    print(f"Output will be logged to: {log_file_path}")
                    
                    try:
                        # Open log file
                        log_file = open(log_file_path, 'w')
                        
                        # Write command to log file
                        log_file.write(f"Command: {' '.join(cmd)}\n")
                        log_file.write(f"Timestamp: {dt.datetime.now().isoformat()}\n\n")
                        log_file.flush()
                        
                        process = subprocess.Popen(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            preexec_fn=os.setsid,  # Use process group for easier termination
                            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Set working directory to project root
                        )
                        print(f"Process started with PID: {process.pid}")
                        
                        # Start threads to capture and log output
                        
                        def log_output(stream, prefix):
                            for line in iter(stream.readline, b''):
                                line_str = line.decode('utf-8', errors='replace').rstrip()
                                print(f"{prefix}: {line_str}")
                                log_file.write(f"{prefix}: {line_str}\n")
                                log_file.flush()
                        
                        # Start threads to handle stdout and stderr
                        threading.Thread(target=log_output, args=(process.stdout, "STDOUT"), daemon=True).start()
                        threading.Thread(target=log_output, args=(process.stderr, "STDERR"), daemon=True).start()
                        
                    except Exception as e:
                        print(f"Error starting process: {e}")
                        traceback.print_exc()
                        if 'log_file' in locals():
                            log_file.write(f"Error: {e}\n")
                            #log_file.close()
                        raise
                    
                    # Store the process globally
                    current_process = process
                    
                    # Store log file reference for later cleanup
                    current_process.log_file = log_file
                    
                    # Save PID to file
                    with open(PID_FILE, 'w') as pid_file:
                        pid_file.write(str(process.pid))
                    
                    # For long-running animations, don't wait for completion
                    if loop:
                        # Update shared state
                        animation_running = True
                        current_animation_file = None  # custom frames, not a named file

                        # Return immediately with process info
                        response_dict = {
                            'status': 'running',
                            'message': 'Animation started successfully',
                            'pid': process.pid,
                            'animation_running': True
                        }
                        
                        # Convert response dict to JSON string
                        response_json = json.dumps(response_dict)
                        # Convert JSON string to bytes
                        response_bytes = response_json.encode('utf-8')
                        
                        # Send success response
                        self.send_response(200)
                        self.send_header('Content-type', 'application/json')
                        self.send_header('Content-Length', str(len(response_bytes)))
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()
                        
                        # Write bytes to response
                        self.wfile.write(response_bytes)
                        return
                    else:
                        # For non-looping animations, wait for completion
                        stdout_bytes, stderr_bytes = process.communicate()
                    
                    # Decode bytes to strings
                    stdout_str = stdout_bytes.decode('utf-8', errors='replace')
                    stderr_str = stderr_bytes.decode('utf-8', errors='replace')
                    
                    # Create response with process output
                    response_dict = {
                        'status': 'success',
                        'message': 'Animation played successfully',
                        'stdout': stdout_str,
                        'stderr': stderr_str,
                        'exit_code': process.returncode
                    }
                    
                    # Convert response dict to JSON string
                    response_json = json.dumps(response_dict)
                    # Convert JSON string to bytes
                    response_bytes = response_json.encode('utf-8')
                    
                    # Send success response
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.send_header('Content-Length', str(len(response_bytes)))
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    
                    # Write bytes to response
                    self.wfile.write(response_bytes)
                    
                finally:
                    # Clean up the temporary file
                    try:
                        if loop == False:
                            print(f"Unlink temp file: {temp_filename}")
                            os.unlink(temp_filename)
                    except:
                        pass
                        
            except Exception as e:
                # Print the full exception traceback for debugging
                print("Error in server:")
                traceback.print_exc()
                
                # Create error response
                error_dict = {
                    'status': 'error',
                    'message': str(e),
                    'traceback': traceback.format_exc()
                }
                
                # Convert error dict to JSON string
                error_json = json.dumps(error_dict)
                # Convert JSON string to bytes
                error_bytes = error_json.encode('utf-8')
                
                # Send error response
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.send_header('Content-Length', str(len(error_bytes)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                
                # Write bytes to response
                self.wfile.write(error_bytes)
        elif self.path == '/toggle_animation':
            """
            Toggle the animation on/off (long-press action).
            When toggled ON  → start the currently selected preset animation in a loop.
            When toggled OFF → kill any running animation (motors return to initial angle).
            If the scheduler owned the process, it gives up control until the next slot boundary.
            """
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length > 0:
                    self.rfile.read(content_length)  # drain

                if animation_running:
                    # ---- STOP ----
                    self._kill_existing_process()
                    animation_running = False
                    current_animation_file = None
                    schedule_started_by_runner = False  # user explicitly stopped it – scheduler backs off
                    response_dict = {
                        'status': 'stopped',
                        'message': 'Animation stopped and motors returning to initial angle',
                        'animation_running': False,
                        'animation_index': current_animation_index,
                        'animation_name': ANIMATION_PRESETS[current_animation_index]['name'],
                        'presets': [p['name'] for p in ANIMATION_PRESETS],
                    }
                else:
                    # ---- START ----
                    anim_file = ANIMATION_PRESETS[current_animation_index]['file']
                    process = play_animation_from_file(full_path=anim_file, loop=True)
                    if process:
                        animation_running = True
                        current_animation_file = anim_file
                        schedule_started_by_runner = False  # user owns this process
                        response_dict = {
                            'status': 'started',
                            'message': f"Animation started: {ANIMATION_PRESETS[current_animation_index]['name']}",
                            'animation_running': True,
                            'animation_index': current_animation_index,
                            'animation_name': ANIMATION_PRESETS[current_animation_index]['name'],
                            'presets': [p['name'] for p in ANIMATION_PRESETS],
                            'pid': process.pid,
                        }
                    else:
                        response_dict = {
                            'status': 'error',
                            'message': 'Failed to start animation',
                            'animation_running': False,
                        }

                response_json = json.dumps(response_dict)
                response_bytes = response_json.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Content-Length', str(len(response_bytes)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(response_bytes)
            except Exception as e:
                traceback.print_exc()
                error_bytes = json.dumps({'status': 'error', 'message': str(e)}).encode('utf-8')
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.send_header('Content-Length', str(len(error_bytes)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(error_bytes)

        elif self.path == '/next_animation':
            """
            Cycle to the next preset animation (short-press action).
            If the animation is currently running, restarts it with the new preset.
            Clears scheduler ownership so the scheduler doesn't override the user's choice.
            """
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length > 0:
                    self.rfile.read(content_length)  # drain

                current_animation_index = (current_animation_index + 1) % len(ANIMATION_PRESETS)
                preset = ANIMATION_PRESETS[current_animation_index]

                if animation_running:
                    # Restart with new preset; user now owns the process
                    self._kill_existing_process()
                    process = play_animation_from_file(full_path=preset['file'], loop=True)
                    if process:
                        current_animation_file = preset['file']
                        schedule_started_by_runner = False  # user made this choice
                    animation_running = bool(process)

                response_dict = {
                    'status': 'ok',
                    'animation_running': animation_running,
                    'animation_index': current_animation_index,
                    'animation_name': preset['name'],
                    'presets': [p['name'] for p in ANIMATION_PRESETS],
                }
                response_json = json.dumps(response_dict)
                response_bytes = response_json.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Content-Length', str(len(response_bytes)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(response_bytes)
            except Exception as e:
                traceback.print_exc()
                error_bytes = json.dumps({'status': 'error', 'message': str(e)}).encode('utf-8')
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.send_header('Content-Length', str(len(error_bytes)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(error_bytes)

        # POST /animations – save a new (or overwrite) user animation
        elif self.path == '/animations':
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                body = json.loads(self.rfile.read(content_length).decode('utf-8'))
                name   = body.get('name', '').strip()
                frames = body.get('frames', [])
                if not name:
                    raise ValueError('Animation name is required')
                # Sanitise filename
                safe_name = ''.join(c if c.isalnum() or c in '-_ ' else '_' for c in name).strip()
                fpath = os.path.join(ANIMATIONS_DIR, safe_name + '.json')
                with open(fpath, 'w') as f:
                    json.dump(frames, f, indent=2)
                anims = _get_all_animations()
                resp = json.dumps({'status': 'saved', 'name': safe_name,
                                   'animations': anims}).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Content-Length', str(len(resp)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(resp)
                print(f"[Animations] Saved '{safe_name}' ({len(frames)} frames)")
            except Exception as e:
                traceback.print_exc()
                err = json.dumps({'status': 'error', 'message': str(e)}).encode('utf-8')
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.send_header('Content-Length', str(len(err)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(err)

        # POST /animations/delete – remove a user animation
        elif self.path == '/animations/delete':
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                body = json.loads(self.rfile.read(content_length).decode('utf-8'))
                name  = body.get('name', '').strip()
                fpath = os.path.join(ANIMATIONS_DIR, name + '.json')
                if os.path.isfile(fpath):
                    os.remove(fpath)
                    deleted = True
                else:
                    deleted = False
                anims = _get_all_animations()
                resp = json.dumps({'status': 'ok', 'deleted': deleted,
                                   'animations': anims}).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Content-Length', str(len(resp)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                err = json.dumps({'status': 'error', 'message': str(e)}).encode('utf-8')
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.send_header('Content-Length', str(len(err)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(err)

        # POST /schedule – save full schedule
        elif self.path == '/schedule':
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length).decode('utf-8')
                incoming = json.loads(body)
                # Merge incoming fields
                if 'festival_start' in incoming:
                    schedule_data['festival_start'] = incoming['festival_start']
                if 'festival_end' in incoming:
                    schedule_data['festival_end'] = incoming['festival_end']
                if 'slots' in incoming:
                    schedule_data['slots'] = incoming['slots']
                if 'enabled' in incoming:
                    schedule_enabled = bool(incoming['enabled'])
                    schedule_data['enabled'] = schedule_enabled
                _save_schedule()
                # Run a tick immediately so changes take effect within a second
                threading.Thread(target=_schedule_tick, daemon=True).start()
                resp = json.dumps({'status': 'saved', 'slot_count': len(schedule_data['slots']), 'enabled': schedule_enabled})
                resp_bytes = resp.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Content-Length', str(len(resp_bytes)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(resp_bytes)
            except Exception as e:
                traceback.print_exc()
                err = json.dumps({'status': 'error', 'message': str(e)}).encode('utf-8')
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.send_header('Content-Length', str(len(err)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(err)

        # POST /schedule/enable  and  /schedule/disable
        elif self.path in ('/schedule/enable', '/schedule/disable'):
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length > 0:
                    self.rfile.read(content_length)
                schedule_enabled = (self.path == '/schedule/enable')
                schedule_data['enabled'] = schedule_enabled
                _save_schedule()
                threading.Thread(target=_schedule_tick, daemon=True).start()
                resp = json.dumps({'status': 'ok', 'enabled': schedule_enabled}).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Content-Length', str(len(resp)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                err = json.dumps({'status': 'error', 'message': str(e)}).encode('utf-8')
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.send_header('Content-Length', str(len(err)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(err)

        elif self.path == '/shutdown':
            try:
                # Get content length
                content_length = int(self.headers['Content-Length'])
                # Read post data as bytes
                post_data_bytes = self.rfile.read(content_length)
                # Convert bytes to string and parse JSON
                post_data_str = post_data_bytes.decode('utf-8')
                post_data = json.loads(post_data_str)
                
                # Extract confirmation parameter (optional security measure)
                confirmation = post_data.get('confirmation', '')
                
                if confirmation == 'CONFIRM_SHUTDOWN':
                    # Execute the shutdown command
                    print("Executing Raspberry Pi shutdown command...")
                    
                    # Kill any existing animation process first
                    self._kill_existing_process()
                    
                    # Create response before shutting down
                    response_dict = {
                        'status': 'success',
                        'message': 'Shutdown command sent to Raspberry Pi. The device will power off shortly.'
                    }
                    
                    # Convert response dict to JSON string
                    response_json = json.dumps(response_dict)
                    # Convert JSON string to bytes
                    response_bytes = response_json.encode('utf-8')
                    
                    # Send success response
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.send_header('Content-Length', str(len(response_bytes)))
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    
                    # Write bytes to response
                    self.wfile.write(response_bytes)
                    
                    # Schedule the shutdown command to run after response is sent
                    def delayed_shutdown():
                        time.sleep(2)  # Give time for the response to be sent
                        subprocess.run(['sudo', 'shutdown', '-h', 'now'])
                    
                    # Start shutdown in a separate thread to allow response to be sent
                    from threading import Thread
                    shutdown_thread = Thread(target=delayed_shutdown)
                    shutdown_thread.daemon = True
                    shutdown_thread.start()
                    
                else:
                    # Invalid confirmation
                    error_dict = {
                        'status': 'error',
                        'message': 'Invalid confirmation code. Shutdown aborted.'
                    }
                    
                    # Convert error dict to JSON string
                    error_json = json.dumps(error_dict)
                    # Convert JSON string to bytes
                    error_bytes = error_json.encode('utf-8')
                    
                    # Send error response
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.send_header('Content-Length', str(len(error_bytes)))
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    
                    # Write bytes to response
                    self.wfile.write(error_bytes)
                    
            except Exception as e:
                # Print the full exception traceback for debugging
                print("Error in shutdown endpoint:")
                traceback.print_exc()
                
                # Create error response
                error_dict = {
                    'status': 'error',
                    'message': str(e),
                    'traceback': traceback.format_exc()
                }
                
                # Convert error dict to JSON string
                error_json = json.dumps(error_dict)
                # Convert JSON string to bytes
                error_bytes = error_json.encode('utf-8')
                
                # Send error response
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.send_header('Content-Length', str(len(error_bytes)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                
                # Write bytes to response
                self.wfile.write(error_bytes)
        else:
            # For all other paths, use the default handler
            SimpleHTTPRequestHandler.do_POST(self)
    
    def _kill_existing_process(self):
        """Kill any existing animation process"""
        global current_process
        killed_something = False
        
        # Check if we have a process in memory
        if current_process and current_process.poll() is None:
            try:
                # Close log file if it exists
                if hasattr(current_process, 'log_file'):
                    try:
                        print(f"Closing log file for process {current_process.pid}")
                        current_process.log_file.write("\nProcess terminated by server\n")
                        #current_process.log_file.close()
                    except Exception as log_err:
                        print(f"Error closing log file: {log_err}")
                
                # Kill the entire process group
                os.killpg(os.getpgid(current_process.pid), signal.SIGINT)
                print(f"Killed existing process with PID {current_process.pid}")
                current_process = None
                killed_something = True
                return killed_something
            except Exception as e:
                print(f"Error killing process: {e}")
                # Still try to close the log file if there was an error killing the process
                if current_process and hasattr(current_process, 'log_file'):
                    try:
                        current_process.log_file.write(f"\nError terminating process: {e}\n")
                        #current_process.log_file.close()
                    except:
                        pass

        # If no process in memory, check PID file
        if os.path.exists(PID_FILE):
            try:
                with open(PID_FILE, 'r') as pid_file:
                    pid = int(pid_file.read().strip())

                # Try to kill the process
                try:
                    os.killpg(os.getpgid(pid), signal.SIGINT)
                    print(f"Killed existing process with PID {pid} from file")
                    killed_something = True
                except ProcessLookupError:
                    # Process doesn't exist anymore
                    print(f"Process with PID {pid} not found")
                except Exception as e:
                    print(f"Error killing process from PID file: {e}")

                # Clean up PID file
                os.unlink(PID_FILE)
            except Exception as e:
                print(f"Error reading PID file: {e}")

        
        return killed_something
    
    def do_GET(self):
        """Handle GET requests - serve static files or handle API endpoints"""
        global current_process, animation_running, current_animation_file, current_animation_index

        # Strip query string first so all route checks work regardless of cache-busting params
        self.path = self.path.split('?')[0]

        # /api redirect
        if self.path in ('/api', '/api/'):
            self.send_response(302)
            self.send_header('Location', '/api-docs.html')
            self.end_headers()
            return

        # Check for kill endpoint
        if self.path == '/kill_animation':
            killed = self._kill_existing_process()
            animation_running = False
            
            # Create response
            response_dict = {
                'status': 'success' if killed else 'info',
                'message': 'Animation process killed' if killed else 'No running animation found',
                'animation_running': animation_running
            }
            
            # Convert response dict to JSON string
            response_json = json.dumps(response_dict)
            # Convert JSON string to bytes
            response_bytes = response_json.encode('utf-8')
            
            # Send response
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Content-Length', str(len(response_bytes)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            # Write bytes to response
            self.wfile.write(response_bytes)
            return
        
        # Check for animation status endpoint
        if self.path == '/animation_status':
            # Also reflect whether the subprocess is still alive
            is_alive = (
                animation_running
                and current_process is not None
                and current_process.poll() is None
            )
            if not is_alive:
                animation_running = False  # self-heal if process died
            response_dict = {
                'animation_running': is_alive,
                'animation_index': current_animation_index,
                'animation_name': ANIMATION_PRESETS[current_animation_index]['name'],
                'presets': [p['name'] for p in ANIMATION_PRESETS],
            }
            response_json = json.dumps(response_dict)
            response_bytes = response_json.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Content-Length', str(len(response_bytes)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(response_bytes)
            return

        # GET /animations – list all animations (presets + user-saved)
        if self.path == '/animations':
            anims = _get_all_animations()
            resp = json.dumps({'animations': anims}).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Content-Length', str(len(resp)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(resp)
            return

        # GET /animations/frames/<name> – return full frames of any animation (preset or user)
        if self.path.startswith('/animations/frames/'):
            from urllib.parse import unquote
            anim_name = unquote(self.path[len('/animations/frames/'):])
            # Search across all animations (presets first, then user-saved)
            all_anims = _get_all_animations()
            match = next((a for a in all_anims if a['name'] == anim_name), None)
            if not match or not os.path.isfile(match['file']):
                self.send_response(404)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                return
            with open(match['file']) as f:
                data = f.read().encode('utf-8')
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(data)
            return

        # GET /schedule – return full schedule + active slot
        if self.path == '/schedule':
            now = dt.datetime.now()
            active = _get_active_slot()
            payload = {
                **schedule_data,
                'enabled': schedule_enabled,
                'server_time': now.strftime('%Y-%m-%dT%H:%M:%S'),
                'now_minutes': now.hour * 60 + now.minute,
                'today_day_index': (
                    (now.date() - dt.date.fromisoformat(schedule_data['festival_start'])).days
                    if schedule_data.get('festival_start') else None
                ),
                'active_slot_id': active['id'] if active else None,
                'presets': [{'name': p['name']} for p in ANIMATION_PRESETS],
            }
            resp = json.dumps(payload).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Content-Length', str(len(resp)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(resp)
            return

        # GET /schedule/log – tail the schedule debug log
        if self.path.startswith('/schedule/log'):
            try:
                # Allow ?lines=N
                n_lines = 100
                if '?' in self.path:
                    qs = self.path.split('?', 1)[1]
                    for part in qs.split('&'):
                        if part.startswith('lines='):
                            try:
                                n_lines = int(part.split('=', 1)[1])
                            except ValueError:
                                pass
                if os.path.isfile(SCHEDULE_LOG):
                    with open(SCHEDULE_LOG, 'r') as f:
                        all_lines = f.readlines()
                    tail = ''.join(all_lines[-n_lines:])
                else:
                    tail = '(log file does not exist yet — no tick has run)\n'
                body = tail.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-type', 'text/plain; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                err = str(e).encode('utf-8')
                self.send_response(500)
                self.send_header('Content-type', 'text/plain')
                self.send_header('Content-Length', str(len(err)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(err)
            return

        # For all other paths, use the default static-file handler
        return SimpleHTTPRequestHandler.do_GET(self)
    
    def do_OPTIONS(self):
        """Handle OPTIONS requests for CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

def play_animation_from_file(animation_file=None, wait_for_completion=False, full_path=None, loop=False):
    """Play an animation from a JSON file.
    
    Args:
        animation_file: Filename relative to the server directory (optional).
        wait_for_completion: If True, block until the process finishes.
        full_path: Absolute path to the animation JSON. Takes precedence over animation_file.
        loop: If True, pass --loop to main.py so the animation repeats indefinitely.
    """
    if full_path:
        animation_path = full_path
    elif animation_file:
        animation_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), animation_file)
    else:
        print("play_animation_from_file: no file specified")
        return None

    if os.path.exists(animation_path):
        print(f"Playing animation from {animation_path}...")
        try:
            # Read the animation data
            with open(animation_path, 'r') as f:
                animation_data = json.load(f)

            # Choose the right main script
            if SIMULATION_MODE:
                main_py_path = _SIM_MAIN_PATH
            else:
                main_py_path = '/home/pi/sunmirror/main.py'
                if not os.path.exists(main_py_path):
                    # Fall back to relative path for development
                    main_py_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'main.py')
            
            # Create a temporary file to store the animation data
            temp_fd, temp_filename = tempfile.mkstemp(suffix='.json')
            with os.fdopen(temp_fd, 'w') as temp_file:
                json.dump(animation_data, temp_file)
            
            # Execute main.py with the temporary file
            cmd = [sys.executable, main_py_path, '--file', temp_filename, '--step-size', '1.0']
            if loop:
                cmd.append('--loop')
            
            # Execute the command in a separate process
            global current_process
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid,  # Use process group for easier termination
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Set working directory to project root
            )
            current_process = process
            
            # Save the PID to file
            with open(PID_FILE, 'w') as f:
                f.write(str(process.pid))
                
            print(f"Started animation with PID: {process.pid}")
            
            # If wait_for_completion is True, wait for the process to complete
            if wait_for_completion:
                process.wait()
                print(f"Animation completed with return code: {process.returncode}")
                
            return process
        except Exception as e:
            print(f"Error playing animation: {e}")
            traceback.print_exc()
            return None
    else:
        print(f"Animation file not found: {animation_path}")
        return None

# ---------------------------------------------------------------------------
# Home-position helper
# ---------------------------------------------------------------------------

# All 54 mirror names in the same order that main.py/setup_mirrors() uses.
_INNER_COUNT  = 6
_MIDDLE_COUNT = 18
_OUTER_COUNT  = 30
_ALL_MIRROR_NAMES = (
    [f"inner{i}"  for i in range(1, _INNER_COUNT  + 1)] +
    [f"middle{i}" for i in range(1, _MIDDLE_COUNT + 1)] +
    [f"outer{i}"  for i in range(1, _OUTER_COUNT  + 1)]
)

def _play_home_position():
    """Move all mirrors to the initial position (90 degrees) by playing a
    single-frame non-looping animation and waiting for it to complete."""
    try:
        _sched_log("[Home] Moving all mirrors to 90° (home position)")
        print("[Home] Moving all mirrors to 90° (home position)")

        # Build a single animation frame with every mirror at 90°
        home_frame = [{"angles": {name: 90.0 for name in _ALL_MIRROR_NAMES}}]

        # Write to a temp file
        temp_fd, temp_path = tempfile.mkstemp(suffix='_home.json')
        try:
            with os.fdopen(temp_fd, 'w') as tf:
                json.dump(home_frame, tf)

            if SIMULATION_MODE:
                main_py_path = _SIM_MAIN_PATH
            else:
                main_py_path = '/home/pi/sunmirror/main.py'
                if not os.path.exists(main_py_path):
                    main_py_path = os.path.join(
                        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'main.py'
                    )

            cmd = [sys.executable, main_py_path, '--file', temp_path, '--step-size', '1.0']
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            _sched_log(f"[Home] Home-position process PID {proc.pid} started, waiting...")
            proc.wait(timeout=30)  # Should complete quickly — one frame
            _sched_log(f"[Home] Home-position process exited (rc={proc.returncode})")
            print(f"[Home] Home-position complete (rc={proc.returncode})")
        finally:
            try:
                os.unlink(temp_path)
            except Exception:
                pass
    except Exception as e:
        _sched_log(f"[Home] ERROR moving to home position: {e}")
        print(f"[Home] ERROR: {e}")
        traceback.print_exc()


def play_startup_animation():
    """Play the start-wave.json animation on server startup"""
    return play_animation_from_file('start-wave.json')

def play_shutdown_animation():
    """Play the shutdown-wave.json animation on server shutdown"""
    # Wait for completion since we're shutting down
    return play_animation_from_file('shutdown-wave.json', wait_for_completion=True)

def handle_shutdown_signal(signum, frame):
    """Handle shutdown signals by playing shutdown animation"""
    global SHUTDOWN_IN_PROGRESS
    
    if SHUTDOWN_IN_PROGRESS:
        return  # Avoid handling the signal multiple times
    
    SHUTDOWN_IN_PROGRESS = True
    print(f"\nReceived shutdown signal {signum}. Playing shutdown animation...")
    
    # Kill any existing animation process
    if current_process and current_process.poll() is None:
        try:
            os.killpg(os.getpgid(current_process.pid), signal.SIGTERM)
            print(f"Terminated existing animation process with PID: {current_process.pid}")
        except Exception as e:
            print(f"Error terminating existing process: {e}")
    
    # Play shutdown animation and wait for it to complete
    play_shutdown_animation()
    
    print("Shutdown animation completed. Exiting...")
    sys.exit(0)

# ---------------------------------------------------------------------------
# GPIO Button Handler (runs as a daemon thread inside the server process)
# ---------------------------------------------------------------------------
BUTTON_GPIO_PIN     = 17    # BCM numbering – GPIO 17 = physical pin 11
BUTTON_DEBOUNCE_MS  = 300   # ms – ignore bounces after initial edge
LONG_PRESS_S        = 2.0   # seconds – threshold between short and long press

def _do_toggle():
    """Long-press action: start/stop animation using the current preset."""
    global animation_running, current_animation_file, current_process
    if animation_running:
        if current_process and current_process.poll() is None:
            try:
                os.killpg(os.getpgid(current_process.pid), signal.SIGINT)
            except Exception as e:
                print(f"[Button] Error killing process: {e}")
        animation_running = False
        current_animation_file = None
        print("[Button] Long-press → animation STOPPED")
    else:
        preset = ANIMATION_PRESETS[current_animation_index]
        process = play_animation_from_file(full_path=preset['file'], loop=True)
        if process:
            animation_running = True
            current_animation_file = preset['file']
            print(f"[Button] Long-press → animation STARTED: {preset['name']} (PID {process.pid})")
        else:
            print("[Button] Long-press → failed to start animation")

def _do_next_animation():
    """Short-press action: cycle to next preset. Restart if already running."""
    global animation_running, current_animation_file, current_animation_index, current_process
    current_animation_index = (current_animation_index + 1) % len(ANIMATION_PRESETS)
    preset = ANIMATION_PRESETS[current_animation_index]
    print(f"[Button] Short-press → selected preset {current_animation_index}: {preset['name']}")

    if animation_running:
        # Restart with new preset
        if current_process and current_process.poll() is None:
            try:
                os.killpg(os.getpgid(current_process.pid), signal.SIGINT)
            except Exception as e:
                print(f"[Button] Error killing process on preset change: {e}")
        process = play_animation_from_file(full_path=preset['file'], loop=True)
        if process:
            current_animation_file = preset['file']
            animation_running = True
            print(f"[Button] Restarted with new preset (PID {process.pid})")
        else:
            animation_running = False

def _start_gpio_button_thread():
    """Start a background daemon thread that monitors the physical toggle button."""

    def gpio_thread():
        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            # Internal pull-up: button connects GPIO pin to GND when pressed
            GPIO.setup(BUTTON_GPIO_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            print(f"[Button] Listening on GPIO {BUTTON_GPIO_PIN} (BCM) — "
                  f"short-press cycles preset, long-press (≥{LONG_PRESS_S}s) toggles on/off")

            press_time = [None]  # mutable container for the closure

            def on_edge(channel):
                if GPIO.input(channel) == GPIO.LOW:
                    # ---- Button pressed (FALLING) ----
                    press_time[0] = time.monotonic()
                else:
                    # ---- Button released (RISING) ----
                    if press_time[0] is None:
                        return
                    duration = time.monotonic() - press_time[0]
                    press_time[0] = None
                    if duration < LONG_PRESS_S:
                        _do_next_animation()   # short press → cycle
                    else:
                        _do_toggle()           # long press  → on/off

            GPIO.add_event_detect(
                BUTTON_GPIO_PIN,
                GPIO.BOTH,
                callback=on_edge,
                bouncetime=BUTTON_DEBOUNCE_MS
            )

            # Keep the thread alive; GPIO callbacks fire in their own thread
            while True:
                time.sleep(1)

        except ImportError:
            print("[Button] RPi.GPIO not available – physical button disabled (dev mode)")
        except Exception as e:
            print(f"[Button] GPIO thread error: {e}")

    t = threading.Thread(target=gpio_thread, name="gpio-button", daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# Schedule helpers
# ---------------------------------------------------------------------------

def _load_schedule():
    """Load schedule from disk into schedule_data."""
    global schedule_data, schedule_enabled
    if os.path.isfile(SCHEDULE_FILE):
        try:
            with open(SCHEDULE_FILE, 'r') as f:
                loaded = json.load(f)
            schedule_data.update(loaded)
            schedule_enabled = loaded.get('enabled', False)
            print(f"[Schedule] Loaded {len(schedule_data['slots'])} slot(s), enabled={schedule_enabled}")
        except Exception as e:
            print(f"[Schedule] Failed to load schedule: {e}")

def _save_schedule():
    """Persist schedule_data to disk."""
    try:
        with open(SCHEDULE_FILE, 'w') as f:
            payload = dict(schedule_data)
            payload['enabled'] = schedule_enabled
            json.dump(payload, f, indent=2)
    except Exception as e:
        print(f"[Schedule] Failed to save schedule: {e}")

def _get_active_slot():
    """Return the slot that should be playing right now, or None."""
    if not schedule_enabled:
        _sched_log("_get_active_slot: schedule is DISABLED — skipping")
        return None
    if not schedule_data.get('festival_start'):
        _sched_log("_get_active_slot: no festival_start set — skipping")
        return None
    try:
        festival_start = dt.date.fromisoformat(schedule_data['festival_start'])
    except Exception as e:
        _sched_log(f"_get_active_slot: bad festival_start value — {e}")
        return None

    # Compute the last valid day from festival_end (inclusive), falling back to 3 (4 days)
    try:
        festival_end = dt.date.fromisoformat(schedule_data['festival_end'])
        max_day_index = (festival_end - festival_start).days
    except Exception:
        max_day_index = 3  # default: 4-day window

    now = dt.datetime.now()
    today = now.date()
    day_index = (today - festival_start).days  # 0-based
    now_minutes = now.hour * 60 + now.minute

    _sched_log(
        f"_get_active_slot: today={today}, day_index={day_index} (max={max_day_index}), "
        f"now={now.strftime('%H:%M')} ({now_minutes} min), "
        f"slots_total={len(schedule_data.get('slots', []))}"
    )

    if day_index < 0 or day_index > max_day_index:
        _sched_log(f"_get_active_slot: day_index {day_index} outside window [0..{max_day_index}] — no match")
        return None

    for slot in schedule_data.get('slots', []):
        s_day   = slot.get('day')
        start_m = slot.get('start_minutes', 0)
        end_m   = slot.get('end_minutes', 0)
        anim    = slot.get('animation_file') or f"index:{slot.get('animation_index','?')}"
        _sched_log(
            f"  checking slot id={slot.get('id','?')} day={s_day} "
            f"{start_m//60:02d}:{start_m%60:02d}–{end_m//60:02d}:{end_m%60:02d} anim={anim}"
        )
        if s_day == day_index:
            if start_m <= now_minutes < end_m:
                _sched_log(f"  → MATCH: slot {slot.get('id','?')}")
                return slot
            else:
                _sched_log(f"  → time {now_minutes} not in [{start_m}, {end_m})")
        else:
            _sched_log(f"  → day mismatch (slot day={s_day}, today={day_index})")

    _sched_log("_get_active_slot: no matching slot found")
    return None

def _schedule_tick():
    """Check the schedule and start/stop animation accordingly."""
    global animation_running, current_animation_file, current_animation_index
    global schedule_started_by_runner, current_process

    proc_alive = (current_process is not None and current_process.poll() is None)
    _sched_log(
        f"--- TICK --- animation_running={animation_running}, "
        f"proc_alive={proc_alive}, "
        f"schedule_started_by_runner={schedule_started_by_runner}, "
        f"current_file={os.path.basename(current_animation_file) if current_animation_file else 'None'}"
    )

    # Self-heal: if the process has exited externally, clear the stale flag
    if animation_running and not proc_alive:
        msg = "[Schedule] Process exited externally — resetting animation_running"
        print(msg)
        _sched_log(msg)
        animation_running = False
        if schedule_started_by_runner:
            current_animation_file = None
            schedule_started_by_runner = False

    slot = _get_active_slot()
    if slot:
        # Resolve which file to play — prefer animation_file, fall back to index
        anim_file = slot.get('animation_file')
        if not anim_file:
            all_anims = _get_all_animations()
            idx = slot.get('animation_index', 0)
            if 0 <= idx < len(all_anims):
                anim_file = all_anims[idx]['file']
                anim_name = all_anims[idx]['name']
            else:
                _sched_log(f"Slot has bad animation_index={idx}, skipping")
                return  # bad index, skip
        else:
            anim_name = os.path.splitext(os.path.basename(anim_file))[0]

        _sched_log(
            f"Active slot found: {anim_name} | animation_running={animation_running}, "
            f"current_file={os.path.basename(current_animation_file) if current_animation_file else 'None'}, "
            f"target_file={os.path.basename(anim_file)}"
        )

        play_once = bool(slot.get('play_once', False))
        loop      = not play_once   # loop unless play_once is set

        if not animation_running or current_animation_file != anim_file:
            # Need to start or switch
            if animation_running:
                _sched_log(f"Stopping current animation to switch to: {anim_name}")
                try:
                    os.killpg(os.getpgid(current_process.pid), signal.SIGINT)
                except Exception as e:
                    _sched_log(f"  kill error: {e}")
            _sched_log(f"Starting animation: {anim_file} (loop={loop}, play_once={play_once})")
            process = play_animation_from_file(full_path=anim_file, loop=loop)
            if process:
                animation_running = True
                current_animation_file = anim_file
                schedule_started_by_runner = True
                msg = f"[Schedule] Started: {anim_name} (PID {process.pid}, {'once' if play_once else 'loop'})"
                print(msg)
                _sched_log(msg)
            else:
                _sched_log(f"ERROR: play_animation_from_file returned None for {anim_file}")
        elif play_once and not proc_alive and schedule_started_by_runner:
            # play_once animation finished naturally — don't restart, just wait for slot to end
            _sched_log(f"play_once animation finished naturally, holding position until slot ends")
            animation_running = False
        else:
            _sched_log(f"Correct animation already running ({anim_name}), no action needed")
    else:
        _sched_log("No active slot right now")
        # No active slot → stop only if we started it
        if animation_running and schedule_started_by_runner:
            _sched_log("Stopping animation (end of slot)")
            try:
                os.killpg(os.getpgid(current_process.pid), signal.SIGINT)
            except Exception as e:
                _sched_log(f"  kill error: {e}")
            animation_running = False
            current_animation_file = None
            schedule_started_by_runner = False
            msg = "[Schedule] Stopped (end of slot)"
            print(msg)
            _sched_log(msg)
            # Move all mirrors back to the initial (home) position of 90°
            _play_home_position()

def _start_schedule_thread():
    """Start the background schedule runner thread (ticks every 30 s)."""
    def runner():
        while True:
            try:
                _schedule_tick()
            except Exception as e:
                print(f"[Schedule] Tick error: {e}")
            time.sleep(30)
    t = threading.Thread(target=runner, name="schedule-runner", daemon=True)
    t.start()
    print("[Schedule] Runner started (30 s interval)")


def run_server(port=None):
    """Run the animation server on the specified port"""
    port = port or SERVER_PORT

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, handle_shutdown_signal)  # Ctrl+C
    signal.signal(signal.SIGTERM, handle_shutdown_signal)  # kill command

    # Load persisted schedule
    _load_schedule()

    if SIMULATION_MODE:
        print("[SIM] GPIO button disabled (no hardware)")
        print("[SIM] Startup animation skipped (no hardware)")
    else:
        # Start the physical toggle button listener in the background
        _start_gpio_button_thread()
        # Play startup animation
        play_startup_animation()

    # Start the schedule runner (works in both modes)
    _start_schedule_thread()

    server_address = ('', port)
    httpd = HTTPServer(server_address, AnimationServer)
    mode_tag = " [SIMULATION]" if SIMULATION_MODE else ""
    print(f"Starting animation server on port {port}{mode_tag}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        # This should be caught by the signal handler, but just in case
        if not SHUTDOWN_IN_PROGRESS:
            handle_shutdown_signal(signal.SIGINT, None)
    finally:
        if not SHUTDOWN_IN_PROGRESS:
            handle_shutdown_signal(signal.SIGTERM, None)

if __name__ == '__main__':
    run_server()

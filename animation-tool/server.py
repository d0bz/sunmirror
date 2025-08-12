#!/usr/bin/env python3
import os
import json
import sys
import subprocess
import traceback
import signal
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs
import tempfile
import datetime


# Add parent directory to path to access main.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Global variables to track the current animation process
current_process = None
PID_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'animation_pid.txt')

class AnimationServer(SimpleHTTPRequestHandler):
    def do_GET(self):
        """Handle GET requests - serve static files or API documentation"""
        self.path = self.path.split('?')[0]  # Remove query parameters
        
        # Handle API documentation routes
        if self.path == '/api' or self.path == '/api/':
            # Redirect to API documentation page
            self.send_response(302)
            self.send_header('Location', '/api-docs.html')
            self.end_headers()
            return
        
        return SimpleHTTPRequestHandler.do_GET(self)
    
    def do_POST(self):
        """Handle POST requests to play animations"""
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
                    # Use absolute path for Raspberry Pi deployment
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
                        log_file.write(f"Timestamp: {datetime.datetime.now().isoformat()}\n\n")
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
                        import threading
                        
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
                        # Return immediately with process info
                        response_dict = {
                            'status': 'running',
                            'message': 'Animation started successfully',
                            'pid': process.pid
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
        # Check for kill endpoint
        if self.path == '/kill_animation':
            killed = self._kill_existing_process()
            
            # Create response
            response_dict = {
                'status': 'success' if killed else 'info',
                'message': 'Animation process killed' if killed else 'No running animation found'
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
        
        # For all other paths, use the default handler
        self.path = self.path.split('?')[0]  # Remove query parameters
        return SimpleHTTPRequestHandler.do_GET(self)
    
    def do_OPTIONS(self):
        """Handle OPTIONS requests for CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

def run_server(port=80):
    """Run the animation server on the specified port"""
    server_address = ('', port)
    httpd = HTTPServer(server_address, AnimationServer)
    print(f"Starting animation server on port {port}...")
    httpd.serve_forever()

if __name__ == '__main__':
    run_server()

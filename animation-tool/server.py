#!/usr/bin/env python3
import os
import json
import sys
import subprocess
import traceback
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs
import tempfile

# Add parent directory to path to access main.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class AnimationServer(SimpleHTTPRequestHandler):
    def do_GET(self):
        """Handle GET requests - serve static files"""
        self.path = self.path.split('?')[0]  # Remove query parameters
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
                animation_data = json.loads(post_data_str)
                
                # Create a temporary file to store the animation data
                temp_fd, temp_filename = tempfile.mkstemp(suffix='.json')
                try:
                    with os.fdopen(temp_fd, 'w') as temp_file:
                        json.dump(animation_data, temp_file)
                    
                    print(f"Animation data saved to temporary file: {temp_filename}")
                    
                    # Execute main.py with the temporary file
                    main_py_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'main.py')
                    cmd = [sys.executable, main_py_path, '--file', temp_filename, '--step-size', '1.0']
                    
                    # Execute the command in a separate process
                    process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    
                    # Wait for the process to complete and get output
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
        else:
            # For all other paths, use the default handler
            SimpleHTTPRequestHandler.do_POST(self)
    
    def do_OPTIONS(self):
        """Handle OPTIONS requests for CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

def run_server(port=8002):
    """Run the animation server on the specified port"""
    server_address = ('', port)
    httpd = HTTPServer(server_address, AnimationServer)
    print(f"Starting animation server on port {port}...")
    httpd.serve_forever()

if __name__ == '__main__':
    run_server()

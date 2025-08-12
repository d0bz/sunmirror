import time
import math
from movement_generator import MovementGenerator
from adafruit_servokit import ServoKit
import busio
from board import SCL, SDA

class MockI2C:
    """Mock I2C class to simulate I2C bus without hardware"""
    def __init__(self, scl=None, sda=None):
        self.scl = scl
        self.sda = sda
        self._locked = False
        print("Initialized MockI2C bus")
        
    def try_lock(self):
        """Simulate locking the I2C bus"""
        self._locked = True
        return True
        
    def unlock(self):
        """Simulate unlocking the I2C bus"""
        self._locked = False
        
    def scan(self):
        """Return a list of fake I2C device addresses"""
        if not self._locked:
            raise RuntimeError("I2C bus must be locked before scanning")
        return [0x40, 0x41, 0x42, 0x43]
    
    def writeto(self, address, buffer, stop=True, start=0, end=None):
        """Simulate writing to an I2C device"""
        # Handle start and end parameters
        if end is None:
            end = len(buffer)
        actual_buffer = buffer[start:end]
        
        if isinstance(actual_buffer, (bytes, bytearray)):
            print(f"Mock I2C write to address 0x{address:02x}: {len(actual_buffer)} bytes")
        else:
            print(f"Mock I2C write to address 0x{address:02x}: {actual_buffer}")
        return len(actual_buffer)
    
    def readfrom_into(self, address, buffer, stop=True, start=0, end=None):
        """Simulate reading from an I2C device"""
        if end is None:
            end = len(buffer)
            
        print(f"Mock I2C read from address 0x{address:02x} into buffer of size {end-start}")
        
        # Fill buffer with dummy data
        for i in range(start, end):
            buffer[i] = i & 0xFF
            
        return end - start
    
    def writeto_then_readfrom(self, address, buffer_out, buffer_in, out_start=0, out_end=None, 
                             in_start=0, in_end=None, stop=True):
        """Simulate writing to then reading from an I2C device"""
        self.writeto(address, buffer_out, stop=False, start=out_start, end=out_end)
        self.readfrom_into(address, buffer_in, stop=stop, start=in_start, end=in_end)
        
        if in_end is None:
            in_end = len(buffer_in)
        return in_end - in_start
        
    def write_then_readinto(self, out_buffer, in_buffer, *args, **kwargs):
        """Alias for writeto_then_readfrom for compatibility"""
        address = kwargs.get('address', 0)
        out_start = kwargs.get('out_start', 0)
        out_end = kwargs.get('out_end', None)
        in_start = kwargs.get('in_start', 0)
        in_end = kwargs.get('in_end', None)
        stop = kwargs.get('stop', True)
        
        return self.writeto_then_readfrom(
            address, out_buffer, in_buffer,
            out_start=out_start, out_end=out_end,
            in_start=in_start, in_end=in_end,
            stop=stop
        )
    
    def write(self, buf, *args, **kwargs):
        """Simulate writing bytes to I2C device"""
        address = kwargs.get('address', 0)
        start = kwargs.get('start', 0)
        end = kwargs.get('end', None)
        stop = kwargs.get('stop', True)
        return self.writeto(address, buf, stop=stop, start=start, end=end)
    
    def readinto(self, buf, *args, **kwargs):
        """Simulate reading bytes from I2C device"""
        address = kwargs.get('address', 0)
        start = kwargs.get('start', 0)
        end = kwargs.get('end', None)
        stop = kwargs.get('stop', True)
        return self.readfrom_into(address, buf, stop=stop, start=start, end=end)

class SimulatedServo:
    def __init__(self, channel=0, debug=False):
        self.channel = channel
        self._angle = 90
        self.debug = debug
        
    @property
    def angle(self):
        return self._angle
        
    @angle.setter
    def angle(self, value):
        # Handle both direct value and dict with force_smooth
        if isinstance(value, dict):
            angle_value = value.get('angle', 90)
            self._angle = float(angle_value)
        else:
            self._angle = float(value)
            
        if self.debug:
            print(f"[DEBUG] Channel {self.channel} set to {self._angle}")

class SimulatedKit:
    def __init__(self, channels, debug=False):
        self.debug = debug
        if self.debug:
            print(f"[DEBUG] Initializing SimulatedKit with {channels} channels")
        self.servo = [SimulatedServo(channel=i, debug=debug) for i in range(channels)]

class ServoTable:
    def __init__(self, channel, kit, kit_index=0, board_channel=0, center_angle=90, radius=70, speed_ms=10, inverted=False, debug=False):
        self.channel = channel
        self.board_channel = board_channel
        self.kit = kit
        self.kit_index = kit_index
        self.center = center_angle
        self.radius = min(radius, center_angle, 180 - center_angle)
        self.last_position = self.center
        self.speed_ms = speed_ms  # Time in milliseconds to move through full amplitude
        self.debug = debug
        self.total_movement_time = 0  # For measuring performance
        self._stop = False  # Simple flag for stopping path following
        self.inverted = inverted  # Whether servo movement should be inverted
    
    def correct_angle(self, angle):
        """
        Corrects the angle value to account for non-linear servo behavior.
        For angles below 90 degrees:
        - 30 degrees should actually move to 60 degrees
        - 60 degrees should actually move to 75 degrees
        - Values in between are interpolated
        - 90 degrees and above remain unchanged
        
        Args:
            angle: The input angle in degrees
            
        Returns:
            The corrected angle in degrees
        """
        # Start with the original angle
        normalized_angle = angle
        
        # Angles 90 and above remain unchanged
        if angle >= 90:
            normalized_angle = angle
        # Angles between 60 and 90 are mapped to 75-90
        elif angle > 60 and angle < 90:
            normalized = (angle - 60) / 30
            normalized_angle = 75 + normalized * 15
        # Angles between 30 and 60 are mapped to 45-75
        elif angle >= 30 and angle <= 60:
            normalized = (angle - 30) / 30
            normalized_angle = 45 + normalized * 30
        # Angles below 30 need special handling
        elif angle < 30:
            # Linear mapping for angles below 30
            normalized = (angle) / 30
            normalized_angle = normalized * 45
        
        if self.debug:
            print(f"DEBUG - normalized angle from={angle} to={normalized_angle}")

        return normalized_angle

    def _execute_move(self, target_angle, force_smooth=True):
        """Execute the actual servo movement
        
        Args:
            target_angle: Target angle to move to
            force_smooth: If True, always use interpolation even for small movements
        """
        target_angle = float(target_angle)
        angle_diff = abs(target_angle - self.last_position)
        
        # Skip if movement is too small, unless force_smooth is True
        if angle_diff < 0.1 and not force_smooth:
            return
            
        total_time_ms = angle_diff * self.speed_ms
        STEP_INTERVAL_MS = 20
        # Always use at least 5 steps when force_smooth is True
        min_steps = 20 if force_smooth else 1
        steps = max(min_steps, round(total_time_ms / STEP_INTERVAL_MS))
        step_delay = STEP_INTERVAL_MS / 1000

        if self.debug:
            print(f"DEBUG - board_channel={self.board_channel+1} angle_diff={angle_diff:.2f}, total_time_ms={total_time_ms:.0f}, steps={steps}, delay={step_delay:.3f}")

        start_angle = float(self.last_position)
        for i in range(1, steps + 1):
            if self._stop:
                break
            ratio = i / steps
            # Use sine interpolation for smoother acceleration/deceleration
            smooth_ratio = (1 - math.cos(ratio * math.pi)) / 2
            angle = start_angle + (target_angle - start_angle) * smooth_ratio
            # Invert angle if needed
            if self.inverted:
                angle = 180 - angle 
            angle = self.correct_angle(angle)
            # For real servos, just set the angle directly
            if isinstance(self.kit, ServoKit):
                self.kit.servo[self.channel].angle = float(angle)
            else:
                # For simulated servos, pass the force_smooth parameter
                self.kit.servo[self.channel].angle = {'angle': float(angle), 'force_smooth': force_smooth}
            time.sleep(step_delay)

        if not self._stop:
            self.last_position = target_angle

    def move_to(self, target_angle):
        """Move to target angle"""
        start_time = time.time()
        self._execute_move(target_angle)
        
        end_time = time.time()
        self.total_movement_time += (end_time - start_time)
        
        if self.debug:
            print(f"[PERF] Average movement time: {self.total_movement_time*1000:.2f}ms")
            
    def move_to_smooth(self, target_angle):
        """Move to target angle with forced smooth movement"""
        start_time = time.time()
        self._execute_move(target_angle, force_smooth=True)
        
        end_time = time.time()
        self.total_movement_time += (end_time - start_time)
        
    def move_to_start(self, target_angle, steps=10, delay=0.05):
        """
        Smoothly moves from center to the target angle.
        """
        for i in range(1, steps + 1):
            ratio = i / steps
            angle = self.center + (target_angle - self.center) * ratio
            self.kit.servo[self.channel].angle = self.correct_angle(angle)
            time.sleep(delay)

    def follow_path(self, path, delay=0.05):
        start_time = time.time()
        
        for angle in path:
            if self._stop:
                break
            self.kit.servo[self.channel].angle = self.correct_angle(angle)
            self.last_position = angle
            time.sleep(delay)
            
        # Track performance for path following
        end_time = time.time()
        self.total_movement_time += (end_time - start_time)
        
        if self.debug:
            print(f"[PERF] Average movement time: {self.total_movement_time*1000:.2f}ms")

    def stop(self):
        self._stop = True

class MainController(MovementGenerator):
    def __init__(self, simulation=True, debug=False):
        self.debug = debug
        num_channels=16
        if simulation:
            self.kits = [SimulatedKit(num_channels, debug=debug)]
        else:
            i2c_bus = busio.I2C(SCL, SDA)
            # Initialize 4 ServoKit modules with different addresses
            self.kits = [
                ServoKit(channels=num_channels, i2c=i2c_bus, address=0x40),
                ServoKit(channels=num_channels, i2c=i2c_bus, address=0x41),
                ServoKit(channels=num_channels, i2c=i2c_bus, address=0x42),
                ServoKit(channels=num_channels, i2c=i2c_bus, address=0x43)
            ]
        self.tables = {}
        self.channels_per_kit = num_channels

    def add_table(self, name, channel, **kwargs):
        """Register a new single-axis servo table by name.
        
        Args:
            name: Name of the table
            channel: Global channel number (0-63 for 4 kits with 16 channels each)
            **kwargs: Additional arguments for ServoTable
        """
        kit_index = channel // self.channels_per_kit
        local_channel = channel % self.channels_per_kit
        print(kit_index, local_channel)
        if kit_index >= len(self.kits):
            raise ValueError(f"Channel {channel} is invalid. Maximum channel is {len(self.kits) * self.channels_per_kit - 1}")
        kwargs['debug'] = self.debug  # Pass debug flag to ServoTable
        kwargs['kit_index'] = kit_index  # Pass kit index to ServoTable
        kwargs['board_channel'] = channel  # Pass kit index to ServoTable

        self.tables[name] = ServoTable(local_channel, self.kits[kit_index], **kwargs)

    def move_table(self, name, angle):
        """Move one table to a specific angle smoothly.
        
        Args:
            name: Name of the table to move
            angle: Target angle to move to
        """
        if name in self.tables:
            self.tables[name].move_to(angle)

    def follow_path_on_table(self, name, path, delay=0.05):
        """Send a path to a specific table."""
        if name in self.tables:
            self.tables[name].follow_path(path, delay)
            
    def move_servos_to_angle(self, servo_names, target_angle):
        """Move multiple servos to a specific angle.
        
        Args:
            servo_names: List of servo names to move (e.g. ['outer1', 'outer2', ...] or ['middle1', 'middle2', ...])
            target_angle: Target angle to move all servos to
        """
        for name in servo_names:
            if name in self.tables:
                self.tables[name].move_to(target_angle)
            
    def cleanup(self):
        """Clean up and center all mirrors before shutdown"""
        if self.debug:
            print("[INFO] Cleaning up and centering all mirrors...")
        
        # Create a dictionary of target angles (center position for each servo)
        target_angles = {name: table.center for name, table in self.tables.items()}
        
        try:
            # Use interpolate_servo_moves to smoothly move all servos to center
            self.interpolate_servo_moves(target_angles, steps=20, delay=0.02)
            if self.debug:
                print("[INFO] All mirrors centered successfully")
        except Exception as e:
            if self.debug:
                print(f"[ERROR] Failed to center mirrors: {e}")
    
    def interpolate_servo_moves(self, target_angles, steps=20, delay=0.02):
        current_angles = {name: table.last_position for name, table in self.tables.items()}

        if self.debug:
            print(f"[INFO] interpolate_servo_moves {steps} " )
        
        for step in range(1, steps + 1):
            ratio = step / steps
            smooth_ratio = (1 - math.cos(ratio * math.pi)) / 2
            for name, table in self.tables.items():
                if name in target_angles:
                    start = current_angles[name]
                    end = target_angles[name]
                    angle = start + (end - start) * smooth_ratio
                    # Apply inversion if the servo is configured as inverted
                    if table.inverted:
                        angle = 180 - angle
                    table.kit.servo[table.channel].angle = angle
            #time.sleep(delay)

        for name, table in self.tables.items():
            if name in target_angles:
                table.last_position = target_angles[name]


    def play_frame_path(self, frame_path):
        """
        Play a path of frames, where each frame is a dict of table_name:angle pairs.
        
        Args:
            frame_path: List of frames, where each frame is a dict mapping table names to angles
        """
        for frame_idx, frame in enumerate(frame_path, 1):
            if self.debug:
                print(f"[DEBUG] Playing frame {frame_idx}/{len(frame_path)}")
                print(f"[DEBUG] Frame content: {frame}")
                
            # Move each table in the frame
            self.interpolate_servo_moves(frame, steps=1, delay=0.02)

            if self.debug:
                print(f"[DEBUG] Frame {frame_idx} complete")

# movement_generator.py
import math

class MovementGenerator:   
    @staticmethod
    def generate_wave_animation(
        table_names,
        center=90,
        amplitude=45,
        step_size=4,
        wave_delay_ms=50,
        loops=1,
        direction='inout'
    ):
        """
        Generate a continuous frame-based wave animation for multiple tables.

        Args:
            table_names: List of table names to generate path for
            center: Center angle
            amplitude: Max deviation from center (e.g., 45)
            step_size: Degrees per frame step (affects smoothness)
            wave_delay_ms: Delay in ms between table wave offsets
            loops: How many full sine wave cycles to generate
            direction: 'inward', 'outward', 'pulse', or 'inout'

        Returns:
            List of frames: [{table_name: angle}, ...]
        """
        num_tables = len(table_names)
        frames = []

        steps_per_loop = int(360 / step_size)  # full sine wave cycle
        total_steps = steps_per_loop * loops

        # Full repeated wave path
        wave_path = [
            center + amplitude * math.sin(math.radians(i * step_size))
            for i in range(total_steps + 1)
        ]

        # Table movement order
        if direction == 'outward':
            order = list(range(num_tables))
        elif direction == 'inward':
            order = list(reversed(range(num_tables)))
        elif direction == 'pulse':
            order = list(range(num_tables)) + list(reversed(range(num_tables)))
        elif direction == 'inout':
            half = num_tables // 2
            left = list(reversed(range(half)))
            right = list(range(half, num_tables))
            order = [i for pair in zip(left, right) for i in pair if i < num_tables]
        else:
            raise ValueError("Unknown direction: use 'inward', 'outward', 'pulse', or 'inout'")

        frame_delay = int(wave_delay_ms / (step_size * 10)) or 1  # frames between table waves

        max_frame_idx = (len(wave_path) - 1) + (len(order) - 1) * frame_delay

        for frame_idx in range(max_frame_idx + 1):
            frame = {}
            for offset, table_idx in enumerate(order):
                start_frame = offset * frame_delay
                wave_idx = frame_idx - start_frame
                if 0 <= wave_idx < len(wave_path):
                    table_name = table_names[table_idx]
                    frame[table_name] = wave_path[wave_idx]
            frames.append(frame)

        # Add final frame to ensure all return to center
        frames.append({name: center for name in table_names})
        return frames

    @staticmethod
    def append_return_to_center(path, table_names, last_positions, center=90, steps=20):
        """
        Append frames that return all table angles to center smoothly.
        """
        for step in range(1, steps + 1):
            frame = {}
            ratio = step / steps
            for name in table_names:
                if name in last_positions:
                    last_angle = last_positions[name]
                    angle = math.floor(last_angle + (center - last_angle) * ratio)
                    frame[name] = angle
            path.append(frame)
        return path

    @staticmethod
    def move_all_rings_to_angle(first_ring, second_ring, third_ring, target_angle, step_size=1, center=90):
        """
        Generate frames to move rings to a specific angle in sequence: outer, then middle, then inner.
        
        Args:
            first_ring: List of first ring servo names
            second_ring: List of second ring servo names
            third_ring: List of third ring servo names
            target_angle: Target angle to move all servos to
            step_size: Size of each step in degrees (smaller = smoother)
            center: Center angle to interpolate from
            
        Returns:
            List of frames where each frame is a dict mapping servo names to angles
        """
        frames = []
        total_movement = abs(target_angle - center)
        steps = int(total_movement / step_size)
        
        # Move first ring first
        for i in range(steps + 1):
            frame = {}

            # Keep last two rings at target
            for name in second_ring + third_ring:
                frame[name] = center

            ratio = i / steps if steps > 0 else 1
            # Use sine interpolation for smoother acceleration/deceleration
            smooth_ratio = (1 - math.cos(ratio * math.pi)) / 2
            angle = center + (target_angle - center) * smooth_ratio
            
            for name in first_ring:
                frame[name] = angle
            frames.append(frame)
            
        # Then move second ring
        for i in range(steps + 1):
            frame = {}
            # Keep first ring at target
            for name in first_ring:
                frame[name] = target_angle

            for name in third_ring:
                frame[name] = center
                
            # Move second ring with smooth interpolation
            ratio = i / steps if steps > 0 else 1
            smooth_ratio = (1 - math.cos(ratio * math.pi)) / 2
            angle = center + (target_angle - center) * smooth_ratio
            
            for name in second_ring:
                frame[name] = angle
            frames.append(frame)
            
        # Finally move third ring
        for i in range(steps + 1):
            frame = {}
            # Keep first and second rings at target
            for name in first_ring + second_ring:
                frame[name] = target_angle
                
            # Move third ring with smooth interpolation
            ratio = i / steps if steps > 0 else 1
            smooth_ratio = (1 - math.cos(ratio * math.pi)) / 2
            angle = center + (target_angle - center) * smooth_ratio
            
            for name in third_ring:
                frame[name] = angle
            frames.append(frame)
            
        return frames



    @staticmethod
    def generate_sequential_wave(inner_tables,middle_tables ,outer_tables, center=90, amplitude=45, step_size=4, wave_delay_ms=50, loops=1):
        """Generate a sequential wave animation where inner parts move first, followed by middle parts,
        and finally outer parts, with overlapping return movements.
        
        Args:
            inner_tables: List of inner table names to generate path for
            middle_tables: List of middle table names to generate path for
            outer_tables: List of outer table names to generate path for
            center: Center angle
            amplitude: Movement amplitude (max deviation from center)
            step_size: Size of each step in degrees
            wave_delay_ms: Delay in ms between movements
        
        Returns:
            List of frames: [{table_name: angle}, ...]
        """

        # Generate sine wave path for full cycle
        steps = int(360 / step_size)  # full sine wave cycle
        wave_path = [
            math.floor(center + amplitude * math.sin(math.radians(i * step_size)))
            for i in range(steps + 1)
        ]
        
        frames = []
        frame_delay = int(wave_delay_ms / (step_size * 10)) or 1
        
        # Calculate total frames for all loops
        frames_per_loop = len(wave_path)
        total_frames = (frames_per_loop * loops) + (2 * frame_delay)  # All loops plus delays
        
        # Store last positions before final phase
        last_positions = {}
        final_phase_start = (frames_per_loop * loops) - (frames_per_loop // 8)
        
        # Generate frames for all positions
        for frame_idx in range(total_frames):
            # Calculate current loop and position within loop
            current_loop = frame_idx // frames_per_loop
            loop_position = frame_idx % frames_per_loop
            frame = {}
            final_phase = frame_idx >= final_phase_start
            
            # Inner tables movement
            for table in inner_tables:
                if current_loop < loops and loop_position < len(wave_path):
                    frame[table] = wave_path[loop_position]
                else:
                    frame[table] = center
                
            # Middle tables movement (starts when inner reaches max amplitude)
            middle_start = len(wave_path) // 4  # Start at 90 degrees (max amplitude)
            
            for table in middle_tables:
                wave_idx = frame_idx - middle_start
                if frame_idx == final_phase_start - 1:
                    # Store position just before final phase
                    current_wave_idx = wave_idx % len(wave_path)
                    if 0 <= current_wave_idx < len(wave_path):
                        last_positions[table] = wave_path[current_wave_idx]
                    else:
                        last_positions[table] = center
                        
                if final_phase:
                    # Linear interpolation to center
                    steps_remaining = total_frames - frame_idx
                    if steps_remaining > 0:
                        start_pos = last_positions.get(table, center)
                        progress = (frame_idx - final_phase_start) / (total_frames - final_phase_start)
                        frame[table] = math.floor(start_pos + (center - start_pos) * progress)
                elif 0 <= wave_idx < len(wave_path):
                    frame[table] = wave_path[wave_idx]
                else:
                    frame[table] = center
                    
            # Outer tables movement (starts when middle reaches max amplitude)
            outer_start = middle_start + (len(wave_path) // 4)  # Start when middle reaches max
            for table in outer_tables:
                wave_idx = frame_idx - outer_start
                if frame_idx == final_phase_start - 1:
                    # Store position just before final phase
                    current_wave_idx = wave_idx % len(wave_path)
                    if 0 <= current_wave_idx < len(wave_path):
                        last_positions[table] = wave_path[current_wave_idx]
                    else:
                        last_positions[table] = center
                        
                if final_phase:
                    # Use same interpolation as middle tables
                    steps_remaining = total_frames - frame_idx
                    if steps_remaining > 0:
                        start_pos = last_positions.get(table, center)
                        progress = (frame_idx - final_phase_start) / (total_frames - final_phase_start)
                        frame[table] = math.floor(start_pos + (center - start_pos) * progress)
                elif 0 <= wave_idx < len(wave_path):
                    frame[table] = wave_path[wave_idx]
                else:
                    frame[table] = center
                    
            frames.append(frame)
            
        # Ensure all tables return to center
        frames.append({name: center for name in inner_tables+middle_tables+outer_tables})
        return frames
        
    @staticmethod
    def generate_sync_inout_path(table_names, center=90, amplitude=45, step_size=1.0, loops=1):
        """Generate a synchronized in-out movement path for multiple tables.
        
        Args:
            table_names: List of table names to generate path for
            center: Center angle
            amplitude: Movement amplitude (max deviation from center)
            step_size: Size of each step in degrees
            loops: Number of times to repeat the pattern
        
        Returns:
            List of frames, where each frame is a dict mapping table names to angles
        """
        path = []
        
        # Calculate number of steps based on step_size
        
        for _ in range(loops):
            # Move outward from center
            current = center
            while current < center + amplitude:
                frame = {name: current for name in table_names}
                path.append(frame)
                current += step_size
            
            # Move inward to center - amplitude
            while current > center - amplitude:
                frame = {name: current for name in table_names}
                path.append(frame)
                current -= step_size
            
            # Move back to center
            while current <= center:
                frame = {name: current for name in table_names}
                path.append(frame)
                current += step_size
        
        return path
    @staticmethod
    def generate_path_from_animation_frames(frames_data, step_size=1.0):
        """
        Convert animation tool JSON frames to a movement path with configurable step size.
        
        Args:
            frames_data: List of frame dictionaries from animation tool JSON
                         Each frame has 'id' and 'angles' keys, where 'angles' maps table names to angle values
            step_size: Size of each step in degrees (default: 1.0)
            
        Returns:
            List of frames, where each frame is a dict mapping table names to angles
        """
        if not frames_data or len(frames_data) < 2:
            return []
            
        # Extract table names from the first frame
        first_frame = frames_data[0]
        if 'angles' not in first_frame:
            return []
            
        table_names = list(first_frame['angles'].keys())
        if not table_names:
            return []
            
        # Initialize the path
        path = []
        
        # Create initial 90-degree frame
        initial_frame = {table: 90.0 for table in table_names}
        
        if not frames_data:
            # If no frames data, just return the initial frame
            path.append(initial_frame)
            return path
            
        # Get the first frame from animation data
        first_animation_frame = frames_data[0]
        if 'angles' not in first_animation_frame:
            # If first frame has no angles, just return the initial frame
            path.append(initial_frame)
            return path
            
        # Create angles dict for first animation frame
        first_angles = {}
        for table in table_names:
            if table in first_animation_frame['angles']:
                first_angles[table] = first_animation_frame['angles'][table]
            else:
                first_angles[table] = 90.0  # Default to 90 if not specified
        
        # Interpolate from initial 90-degree frame to first animation frame
        initial_to_first = MovementGenerator._interpolate_frames(
            initial_frame, first_angles, step_size)
        path.extend(initial_to_first)
        
        # Process each pair of consecutive frames
        for i in range(len(frames_data) - 1):
            current_frame = frames_data[i]
            next_frame = frames_data[i + 1]
            
            # Skip if frames don't have angles
            if 'angles' not in current_frame or 'angles' not in next_frame:
                continue
                
            current_angles = {}
            next_angles = {}
            
            # Create intermediate frames for each table
            for table in table_names:
                if table not in current_frame['angles'] or table not in next_frame['angles']:
                    continue
                    
                current_angles[table] = current_frame['angles'][table]
                next_angles[table] = next_frame['angles'][table]
                
            # Add intermediate frames between current and next frame
            # Skip the first frame as it's already included from the previous interpolation
            intermediate_frames = MovementGenerator._interpolate_frames(
                current_angles, next_angles, step_size)
            if i > 0:  # For all pairs except the first one
                path.extend(intermediate_frames)
            else:  # For the first pair, skip the first frame as it's already in the path
                path.extend(intermediate_frames[1:])
        
        # Get the last frame from animation data
        last_animation_frame = frames_data[-1]
        if 'angles' in last_animation_frame:
            # Create angles dict for last animation frame
            last_angles = {}
            for table in table_names:
                if table in last_animation_frame['angles']:
                    last_angles[table] = last_animation_frame['angles'][table]
                else:
                    last_angles[table] = 90.0  # Default to 90 if not specified
            
            # Create final 90-degree frame
            final_frame = {table: 90.0 for table in table_names}
            
            # Interpolate from last animation frame to final 90-degree frame
            last_to_final = MovementGenerator._interpolate_frames(
                last_angles, final_frame, step_size)
            # Skip the first frame as it's already included from the previous interpolation
            path.extend(last_to_final[1:])
        
        return path
    
    @staticmethod
    def _interpolate_frames(start_angles, end_angles, step_size=1.0):
        """
        Helper method to interpolate between two sets of angles with the given step size.
        
        Args:
            start_angles: Dictionary mapping table names to starting angles
            end_angles: Dictionary mapping table names to ending angles
            step_size: Size of each step in degrees
            
        Returns:
            List of frames with interpolated angles
        """
        frames = []
        
        # Find the maximum angle difference to determine the number of steps
        max_diff = 0
        for table in start_angles:
            if table in end_angles:
                diff = abs(end_angles[table] - start_angles[table])
                max_diff = max(max_diff, diff)
        
        # Calculate number of intermediate steps
        num_steps = max(1, int(max_diff / step_size))
        
        # Generate intermediate frames
        for step in range(num_steps + 1):
            progress = step / num_steps if num_steps > 0 else 1
            frame = {}
            
            for table in start_angles:
                if table in end_angles:
                    start = start_angles[table]
                    end = end_angles[table]
                    frame[table] = start + (end - start) * progress
                else:
                    frame[table] = start_angles[table]
            
            frames.append(frame)
        
        return frames

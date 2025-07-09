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
                    angle = last_angle + (center - last_angle) * ratio
                    frame[name] = angle
            path.append(frame)
        return path

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
            while current <= center + amplitude:
                frame = {name: current for name in table_names}
                path.append(frame)
                current += step_size
            
            # Move inward to center - amplitude
            while current >= center - amplitude:
                frame = {name: current for name in table_names}
                path.append(frame)
                current -= step_size
            
            # Move back to center
            while current <= center:
                frame = {name: current for name in table_names}
                path.append(frame)
                current += step_size
        
        return path

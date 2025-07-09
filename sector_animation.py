from servo_controller import MainController
from sector_mapping import SECTORS
import time
import math

# Mirrors that are installed in inverted orientation
INVERTED_MIRRORS = {
    7, 10, 13, 16, 19, 22,  # Middle ring
    25, 27, 30, 32, 35, 37, 40, 42, 45, 47, 50, 52  # Outer ring
}

def process_inverted_frames(frames, center_angle=90):
    """Process a list of frames to handle inverted mirrors.
    For inverted mirrors, the angle will be inverted around the center_angle.
    Example: if normal mirror goes to 120° (30° up from 90°),
    inverted mirror will go to 60° (30° down from 90°)"""
    processed_frames = []
    
    for frame in frames:
        new_frame = {}
        for mirror_name, angle in frame.items():
            channel = int(mirror_name.split('_')[1])
            if channel in INVERTED_MIRRORS:
                # Invert the angle around center_angle
                delta = angle - center_angle
                new_frame[mirror_name] = center_angle - delta
            else:
                new_frame[mirror_name] = angle
        processed_frames.append(new_frame)
    
    return processed_frames

def create_sector_sequence(controller, center_angle=90, move_amplitude=45, steps=30):
    """Creates a sequence of movements for sectors in pairs"""
    
    # Movement sequence: inside (min angle) -> outside (max angle) -> center
    def create_sector_movement(sector_channels):
        # Create frames without worrying about inverted mirrors
        frame_inside = {f"mirror_{ch}": center_angle - move_amplitude for ch in sector_channels}
        frame_outside = {f"mirror_{ch}": center_angle + move_amplitude for ch in sector_channels}
        frame_center = {f"mirror_{ch}": center_angle for ch in sector_channels}
        return [frame_inside, frame_outside, frame_center]

    # Sequence: sectors 2&5, then 3&6, then 1&4
    sequence_pairs = [
        (SECTORS[2] + SECTORS[5]),  # Middle sectors
        (SECTORS[3] + SECTORS[6]),  # Bottom right & Top left
        (SECTORS[1] + SECTORS[4]),  # Top right & Bottom left
    ]

    all_frames = []
    
    # Create frames for each sector pair
    for sector_pair in sequence_pairs:
        movement_frames = create_sector_movement(sector_pair)
        all_frames.extend(movement_frames)
        # Add a small pause frame between sector movements
        pause_frame = {f"mirror_{ch}": center_angle for ch in sector_pair}
        all_frames.append(pause_frame)

    # Process frames to handle inverted mirrors
    return process_inverted_frames(all_frames, center_angle)

def run_sector_animation():
    # Initialize controller
    controller = MainController(num_channels=54)
    
    # Setup all mirrors
    for channel in range(54):
        controller.add_table(f"mirror_{channel}", channel=channel)

    center_angle = 90
    
    try:
        # Create the sequence
        frames = create_sector_sequence(controller)
        print(f"\nTotal frames in sequence: {len(frames)}")
        
        # Play the animation continuously
        while True:
            print("\nStarting new animation cycle...")
            for i, frame in enumerate(frames):
                print(f"Playing frame {i+1}/{len(frames)}: {frame}")
                controller.play_frame_path([frame], steps=30, delay=0.02)
                # Small pause between movements
                time.sleep(0.5)
            
    except KeyboardInterrupt:
        print("\n[INFO] Ctrl+C detected, centering all mirrors.")
        # Center all mirrors
        center_frame = {f"mirror_{ch}": center_angle for ch in range(54)}
        controller.play_frame_path([center_frame], steps=10, delay=0.02)

def create_ripple_wave(controller, center_angle=90, move_amplitude=30, steps=30):
    """Creates a ripple wave effect from inner to outer rings"""
    # Define rings (channel ranges for each ring)
    inner_ring = list(range(0, 6))        # First 6 mirrors
    middle_ring = list(range(6, 24))      # Next 18 mirrors
    outer_ring = list(range(24, 54))      # Last 30 mirrors
    rings = [inner_ring, middle_ring, outer_ring]
    
    all_frames = []
    wave_offset = len(rings)  # How many steps to offset each ring for wave effect
    
    # Create frames for a complete wave cycle
    max_steps = len(rings) * wave_offset
    for step in range(max_steps + len(rings)):  # Extra steps to let the wave complete
        frame = {}
        
        # Calculate position for each ring
        for ring_idx, ring in enumerate(rings):
            # Offset each ring's movement to create wave
            ring_step = step - (ring_idx * wave_offset)
            
            if 0 <= ring_step < len(rings) * 2:  # Within active wave period
                # Calculate wave position (sine wave)
                wave_pos = math.sin(ring_step * math.pi / len(rings))
                
                # Apply to all mirrors in this ring without worrying about inversion
                for ch in ring:
                    angle = center_angle + (move_amplitude * wave_pos)
                    frame[f"mirror_{ch}"] = angle
            else:
                # Ring not yet started or finished wave
                for ch in ring:
                    frame[f"mirror_{ch}"] = center_angle
        
        all_frames.append(frame)
    
    # Process frames to handle inverted mirrors
    return process_inverted_frames(all_frames, center_angle)

def create_wave_sequence(controller, center_angle=90, move_amplitude=30, steps=30):
    """Creates a wave-like sequence moving through all sectors"""
    # Wave sequence: 2 -> 3 -> 4 -> 5 -> 6 -> 1
    sector_order = [2, 3, 4, 5, 6, 1]
    all_frames = []
    
    # Create wave frames for each sector
    for i, sector_num in enumerate(sector_order):
        # Current sector goes up
        frame = {}
        for ch in SECTORS[sector_num]:
            # Invert movement for inverted mirrors
            if ch in INVERTED_MIRRORS:
                frame[f"mirror_{ch}"] = center_angle + move_amplitude
            else:
                frame[f"mirror_{ch}"] = center_angle - move_amplitude
        # Previous sector (if any) returns to center
        if i > 0:
            prev_sector = sector_order[i-1]
            for ch in SECTORS[prev_sector]:
                frame[f"mirror_{ch}"] = center_angle
        all_frames.append(frame)
        
        # Current sector goes down
        frame = {}
        for ch in SECTORS[sector_num]:
            # Invert movement for inverted mirrors
            if ch in INVERTED_MIRRORS:
                frame[f"mirror_{ch}"] = center_angle - move_amplitude
            else:
                frame[f"mirror_{ch}"] = center_angle + move_amplitude
        all_frames.append(frame)
    
    # Final frame to return all to center
    final_frame = {}
    for ch in SECTORS[sector_order[-1]]:
        final_frame[f"mirror_{ch}"] = center_angle
    all_frames.append(final_frame)
    
    return all_frames

if __name__ == "__main__":
    run_sector_animation()

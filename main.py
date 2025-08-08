# main.py
import threading
import argparse
import json
import sys
from servo_controller import MainController
from movement_generator import MovementGenerator
import time
import signal

# Mapping from servo number to ring position (1-based indexing)
SERVO_TO_POSITION = {
    1: 1,   # inner1
    2: 2,   # inner2
    3: 3,   # inner3
    4: 4,   # inner4
    5: 5,   # inner5
    6: 6,   # inner6
    7: 7,   # middle1
    8: 8,   # middle2
    9: 9,   # middle3
    10: 10, # middle4
    11: 11, # middle5
    12: 12, # middle6
    13: 13, # middle7
    14: 14, # middle8
    15: 15, # middle9
    16: 16, # middle10
    17: 17, # middle11
    18: 18, # middle12
    19: 19, # middle13
    20: 20, # middle14
    21: 21, # middle15
    22: 22, # middle16
    23: 23, # middle17
    24: 24, # middle18
    25: 25, # outer1
    26: 26, # outer2
    27: 27, # outer3
    28: 28, # outer4
    29: 29, # outer5
    30: 30, # outer6
    31: 31, # outer7
    32: 32, # outer8
    33: 33, # outer9
    34: 34, # outer10
    35: 35, # outer11
    36: 36, # outer12
    37: 37, # outer13
    38: 38, # outer14
    39: 39, # outer15
    40: 40, # outer16
    41: 41, # outer17
    42: 42, # outer18
    43: 43, # outer19
    44: 44, # outer20
    45: 45, # outer21
    46: 46, # outer22
    47: 47, # outer23
    48: 48, # outer24
    49: 49, # outer25
    50: 50, # outer26
    51: 51, # outer27
    52: 52, # outer28
    53: 53, # outer29
    54: 54  # outer30
}

# Mapping from physical servo number (1-54) to logical channel (1-54)
CHANNEL_TO_SERVO = {
    1: 18,   2: 54,   3: 53,   4: 20,   5: 19,   6: 17,   7: 13,   8: 16,   9: 15,  10: 37,
    11: 44,  12: 40,  13: 41,  14: 42,  15: 43,  16: 22,  17: 28,  18: 25,  19: 24,  20: 26,  21: 27,
    22: 12,  23: 10,  24: 11,  25: 14,  26: 5,   27: 6,   28: 1,   29: 4,   30: 50,  31: 52,
    32: 49,  33: 47,  34: 38,  35: 39,  36: 46,  37: 48,  38: 45,  39: 51,  40: 36,  41: 32,
    42: 30,  43: 31,  44: 23,  45: 21,  46: 35,  47: 33,  48: 29,  49: 34,  50: 3,   51: 8,
    52: 7,   53: 2,   54: 9
}

# Reverse mapping from logical channel to servo number
SERVO_TO_CHANNEL = {v: k for k, v in CHANNEL_TO_SERVO.items()}

# Configuration for the three rings
INNER_RING_COUNT = 6
MIDDLE_RING_COUNT = 18
OUTER_RING_COUNT = 30

# List of servos that need inverted movement
INVERTED_SERVOS = [8, 11, 14, 17, 20, 23, 26, 28, 31, 33, 36, 38, 41, 43, 46, 48, 51, 53]

def setup_mirrors(controller):
    SPEED_MS = 30
    
    # Initialize ring lists
    inner_ring = []
    middle_ring = []
    outer_ring = []
    
    # Setup all rings using the channel mapping
    for logical_channel, servo_num in CHANNEL_TO_SERVO.items():
        # Get the mirror name based on the logical channel
        if logical_channel <= INNER_RING_COUNT:
            name = f"inner{logical_channel}"
            inner_ring.append(name)
        elif logical_channel <= INNER_RING_COUNT + MIDDLE_RING_COUNT:
            name = f"middle{logical_channel - INNER_RING_COUNT}"
            middle_ring.append(name)
        else:
            name = f"outer{logical_channel - (INNER_RING_COUNT + MIDDLE_RING_COUNT)}"
            outer_ring.append(name)
            
        # Check if this servo should be inverted
        inverted = logical_channel in INVERTED_SERVOS
            
        # Add the table with the mapped channel number (0-based)
        print(name, logical_channel, servo_num-1)

        controller.add_table(name, channel=servo_num-1, speed_ms=SPEED_MS, inverted=inverted)
    
    return inner_ring, middle_ring, outer_ring

def move_outer_ring(controller, angle):
    """Move all servos in the outer ring to a specific angle."""
    outer_servos = [f"outer{i}" for i in range(1, OUTER_RING_COUNT + 1)]
    controller.move_servos_to_angle(outer_servos, angle)

def move_middle_ring(controller, angle):
    """Move all servos in the middle ring to a specific angle."""
    middle_servos = [f"middle{i}" for i in range(1, MIDDLE_RING_COUNT + 1)]
    controller.move_servos_to_angle(middle_servos, angle)

def move_inner_ring(controller, angle):
    """Move all servos in the inner ring to a specific angle."""
    inner_servos = [f"inner{i}" for i in range(1, INNER_RING_COUNT + 1)]
    controller.move_servos_to_angle(inner_servos, angle)

def load_and_play_animation(file_path, controller, all_mirrors, step_size=1.0):
    """
    Load animation frames from a JSON file and play them.
    
    Args:
        file_path: Path to the JSON file containing animation frames
        controller: MainController instance to control the servos
        all_mirrors: List of all mirror names
        step_size: Size of each step in degrees (default: 1.0)
    """
    try:
        with open(file_path, 'r') as f:
            animation_data = json.load(f)
        
        print(f"Loaded animation data from {file_path}")
        print(f"Found {len(animation_data)} frames")
        
        # Convert string table names to actual mirror names if needed
        # The animation tool uses numbers as table names ("1", "2", etc.)
        # but our system uses names like "inner1", "middle1", etc.
        
        # Check if we need to convert table names
        first_frame = animation_data[0]
        if 'angles' in first_frame:
            table_keys = list(first_frame['angles'].keys())
            if table_keys and table_keys[0].isdigit():
                print("Converting numeric table names to mirror names...")
                # We need to convert numeric table names to mirror names
                for frame in animation_data:
                    if 'angles' in frame:
                        new_angles = {}
                        for table_num, angle in frame['angles'].items():
                            table_idx = int(table_num) - 1  # Convert to 0-based index
                            if 0 <= table_idx < len(all_mirrors):
                                new_angles[all_mirrors[table_idx]] = angle
                        frame['angles'] = new_angles
        
        # Convert animation frames to a path with the specified step size
        path = MovementGenerator.generate_path_from_animation_frames(animation_data, step_size)
        print(f"Generated path with {len(path)} frames")
        
        # Play the path
        print("Playing animation...")
        controller.play_frame_path(path)
        print("Animation playback complete")
        
        return True
    except FileNotFoundError:
        print(f"Error: File not found: {file_path}")
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON format in file: {file_path}")
    except Exception as e:
        print(f"Error: {str(e)}")
    
    return False

if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="SUNMIRROR controller")
    parser.add_argument("-f", "--file", help="Path to animation JSON file to play")
    parser.add_argument("-s", "--step-size", type=float, default=1.0,
                      help="Step size in degrees for animation interpolation (default: 1.0)")
    parser.add_argument("-l", "--loop", action="store_true", 
                      help="Run the animation file in a continuous loop")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--simulation", action="store_true", help="Run in simulation mode without hardware")
    
    args = parser.parse_args()
    
    debug = args.debug  # Set to True to enable debug prints
    simulation = args.simulation
    
    print("Starting mirror simulation...")
    # Initialize controller with enough channels for all servos (54 mirrors * 1 channel each)
    controller = MainController(simulation=simulation, debug=debug)
    print("Controller initialized, setting up mirrors...")
    
    # Setup all mirrors in their respective rings
    inner_ring, middle_ring, outer_ring = setup_mirrors(controller)
    
    # All mirror names in order
    all_mirrors = inner_ring + middle_ring + outer_ring
    
    center_angle = 90.0  # Ensure it's a single float value

    def stop_signal_handler():
        print("\n[INFO] Smoothly centering all mirrors...")
        try:
            controller.cleanup()
        except Exception as e:
            print(f"Error during cleanup: {e}")
        print("Goodbye!")
        exit(0)

        
    # Register the signal handlers
    signal.signal(signal.SIGINT, stop_signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, stop_signal_handler)  # kill command
    
    # If a file is provided, load and play it
    if args.file:
        # If loop flag is set, keep playing the animation in a loop
        if args.loop:
            print(f"Running animation file {args.file} in continuous loop mode. Press Ctrl+C to stop.")
            try:
                while True:
                    success = load_and_play_animation(args.file, controller, all_mirrors, args.step_size)
                    if not success:
                        print("Error playing animation, exiting loop.")
                        sys.exit(1)
            except KeyboardInterrupt:
                print("\nLoop interrupted by user. Centering all mirrors before exit...")
                # Center all mirrors before exiting
                controller.cleanup()
                sys.exit(0)
        else:
            # Play once and exit
            success = load_and_play_animation(args.file, controller, all_mirrors, args.step_size)
            if success:
                # Center all mirrors before exiting
                print("Centering all mirrors before exit...")
                controller.cleanup()
                sys.exit(0)
            else:
                sys.exit(1)
    
    try:
        print("\nAvailable commands:")
        print("  play - Play synchronized inout path")
        print("  playone - Play synchronized inout for one mirror only")
        print("  <table_number> <angle> - Move specific table to angle (e.g., '1 135')")
        print("  list - List all available tables")
        print("  servo <number> - Find channel for a servo number")
        print("  channel <number> - Find servo for a channel number")
        print("  quit - Exit the program")
        
        while True:
            cmd = input("\nEnter command: ").strip().lower()
            
            if cmd.startswith('servo '):
                try:
                    servo_num = int(cmd.split()[1])
                    if servo_num in SERVO_TO_POSITION:
                        position = SERVO_TO_POSITION[servo_num]
                        channel = CHANNEL_TO_SERVO[servo_num]
                        # Get the mirror name based on the position
                        if position <= INNER_RING_COUNT:
                            name = f"inner{position}"
                        elif position <= INNER_RING_COUNT + MIDDLE_RING_COUNT:
                            name = f"middle{position - INNER_RING_COUNT}"
                        else:
                            name = f"outer{position - (INNER_RING_COUNT + MIDDLE_RING_COUNT)}"
                        print(f"Servo {servo_num} maps to:")
                        print(f"  Mirror name: {name}")
                        print(f"  Channel number: {channel}")
                    else:
                        print(f"Error: Servo {servo_num} not found in mapping")
                except (IndexError, ValueError):
                    print("Error: Please provide a valid servo number (e.g., 'servo 1')")
            elif cmd.startswith('channel '):
                try:
                    channel = int(cmd.split()[1])
                    if channel in SERVO_TO_CHANNEL:
                        servo_num = SERVO_TO_CHANNEL[channel]
                        position = SERVO_TO_POSITION[servo_num]
                        # Get the mirror name based on the position
                        if position <= INNER_RING_COUNT:
                            name = f"inner{position}"
                        elif position <= INNER_RING_COUNT + MIDDLE_RING_COUNT:
                            name = f"middle{position - INNER_RING_COUNT}"
                        else:
                            name = f"outer{position - (INNER_RING_COUNT + MIDDLE_RING_COUNT)}"
                        print(f"Channel {channel} maps to:")
                        print(f"  Mirror name: {name}")
                        print(f"  Servo number: {servo_num}")
                    else:
                        print(f"Error: Channel {channel} not found in mapping")
                except (IndexError, ValueError):
                    print("Error: Please provide a valid channel number (e.g., 'channel 1')")
            elif cmd == 'quit':
                break
            elif cmd == 'list':
                print("\nAvailable tables:")
                for i, name in enumerate(all_mirrors, 1):
                    print(f"  {i}: {name}")
            elif cmd == 'play':
                print("Playing synchronized inout path...")
                # Generate and play a simple in-out movement for all mirrors
                sync_path = MovementGenerator.generate_sync_inout_path(
                    all_mirrors,
                    center=center_angle,
                    amplitude=45.0,  # Reduced amplitude for safety
                    step_size=1,
                    loops=1
                )
                #print(sync_path)
                controller.play_frame_path(sync_path)
            elif cmd == 'wave':
                print("Playing synchronized inout path...")
                # Generate and play a simple in-out movement for all mirrors
                sync_path = MovementGenerator.generate_wave_animation(
                    all_mirrors,
                    center=center_angle,
                    amplitude=45.0,  # Reduced amplitude for safety
                    step_size=2,
                    loops=4
                )
                #print(sync_path)
                controller.play_frame_path(sync_path)
            elif cmd == 'seqwave':
                print("Playing synchronized inout path...")
                # Generate and play a simple in-out movement for all mirrors
                sync_path = MovementGenerator.generate_sequential_wave(
                    inner_tables=inner_ring,
                    middle_tables=middle_ring,
                    outer_tables=outer_ring,
                    center=center_angle,
                    amplitude=45.0,
                    step_size=1,
                    wave_delay_ms=50,
                    loops=4
                )
                #print(sync_path)
                controller.play_frame_path(sync_path)
            elif cmd == 'wavecustom':
                print("Playing synchronized inout path for one...")
                # Generate and play a simple in-out movement for all mirrors
                sync_path = MovementGenerator.generate_wave_animation(
                    ["inner1", "inner2", "inner3", "inner4", "inner5", "inner6"],
                    center=center_angle,
                    wave_delay_ms=500,
                    amplitude=45.0,
                    step_size=1,
                    loops=10
                )
                #print(wave_path)
                controller.play_frame_path(sync_path)
            elif cmd == 'playcustom':
                print("Playing synchronized inout path for one...")
                # Generate and play a simple in-out movement for all mirrors
                sync_path = MovementGenerator.generate_sync_inout_path(
                    ["inner1", "inner2", "inner3", "inner4", "inner5", "inner6"],
                    center=center_angle,
                    amplitude=45.0,
                    step_size=1,
                    loops=10
                )
                #print(wave_path)
                controller.play_frame_path(sync_path)
            elif cmd == 'ringbyring':
                print("Moving all rings outward")
                # Generate and play synchronized movement for all mirrors
                sync_path = MovementGenerator.move_all_rings_to_angle(
                    inner_ring,
                    middle_ring,
                    outer_ring,
                    center_angle + 45.0,
                    center=center_angle,
                    step_size=1  # 1 degree per step for smooth movement
                )
                controller.play_frame_path(sync_path)

                time.sleep(5)

                sync_path = MovementGenerator.move_all_rings_to_angle(
                    inner_ring,
                    middle_ring,
                    outer_ring,
                    center_angle,
                    center=center_angle,
                    step_size=1  # 1 degree per step for smooth movement
                )
                controller.play_frame_path(sync_path)

                time.sleep(1)
                
                #sync_path = MovementGenerator.move_all_rings_to_angle(
                #    outer_ring,
                #    middle_ring,
                #    inner_ring,
                #    center_angle - 45.0,
                #    center=center_angle + 45.0,  # Start from previous position
                #    step_size=1  # 1 degree per step for smooth movement
                #)
                #controller.play_frame_path(sync_path)

                #time.sleep(1)

                #sync_path = MovementGenerator.move_all_rings_to_angle(
                #    inner_ring,
                #    middle_ring,
                #    outer_ring,
                #    center_angle,
                #    center=center_angle - 45.0,  # Start from previous position
                #    step_size=1  # 1 degree per step for smooth movement
                #)
                #controller.play_frame_path(sync_path)
            else:
                # Try to parse as table movement command
                try:
                    parts = cmd.split()
                    if len(parts) == 2:
                        table_num = int(parts[0])
                        angle = float(parts[1])
                        
                        if 0 <= table_num <= len(all_mirrors):
                            table_name = all_mirrors[table_num-1]
                            print(f"Moving {table_name} to {angle} degrees...")
                            controller.move_table(table_name, angle)
                        else:
                            print(f"Error: Table number must be between 0 and {len(all_mirrors)}")
                    else:
                        print("Error: Invalid command format. Use '<table_number> <angle>' or 'play' or 'list'")
                except ValueError:
                    print("Error: Invalid number format. Table number and angle must be numbers")
        
        # Proper cleanup
        print("\n[INFO] Ctrl+C detected, centering all mirrors.")
        # Center all mirrors
    except KeyboardInterrupt:
        print("\n[INFO] Ctrl+C detected, stopping...")
    finally:
        stop_signal_handler()

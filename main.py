# main.py
import threading
from servo_controller import MainController
from movement_generator import MovementGenerator

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
    11: 44,  12: 40,  13: 41,  14: 42,  15: 43,  17: 28,  18: 25,  19: 24,  20: 26,  21: 27,
    22: 12,  23: 10,  24: 11,  25: 14,  26: 5,   27: 6,   28: 1,   29: 4,   30: 50,  31: 52,
    32: 49,  33: 47,  34: 38,  35: 39,  36: 45,  37: 48,  38: 46,  39: 51,  40: 36,  41: 32,
    42: 30,  43: 31,  44: 23,  45: 21,  46: 35,  47: 22,  48: 29,  49: 34,  50: 3,   51: 8,
    52: 7,   53: 2,   54: 9
}

# Reverse mapping from logical channel to servo number
SERVO_TO_CHANNEL = {v: k for k, v in CHANNEL_TO_SERVO.items()}

# Configuration for the three rings
INNER_RING_COUNT = 6
MIDDLE_RING_COUNT = 18
OUTER_RING_COUNT = 30

def setup_mirrors(controller):
    SPEED_MS = 11
    
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
            
        # Add the table with the mapped channel number (0-based)
        print(name, logical_channel, servo_num-1)

        controller.add_table(name, channel=servo_num-1, speed_ms=SPEED_MS)
    
    return inner_ring, middle_ring, outer_ring

if __name__ == "__main__":
    debug = True  # Set to True to enable debug prints
    print("Starting mirror simulation...")
    # Initialize controller with enough channels for all servos (54 mirrors * 1 channel each)
    controller = MainController(simulation=False, debug=debug)
    print("Controller initialized, setting up mirrors...")
    
    # Setup all mirrors in their respective rings
    inner_ring, middle_ring, outer_ring = setup_mirrors(controller)
    
    # All mirror names in order
    all_mirrors = inner_ring + middle_ring + outer_ring
    
    center_angle = 90.0  # Ensure it's a single float value
    
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
            elif cmd == 'playone':
                print("Playing synchronized inout path for one...")
                # Generate and play a simple in-out movement for all mirrors
                sync_path = MovementGenerator.generate_sync_inout_path(
                    ["middle10"],
                    center=center_angle,
                    amplitude=45.0,  # Reduced amplitude for safety
                    step_size=1,
                    loops=1
                )
                #print(wave_path)
                controller.play_frame_path(sync_path)
            else:
                # Try to parse as table movement command
                try:
                    parts = cmd.split()
                    if len(parts) == 2:
                        table_num = int(parts[0])
                        angle = float(parts[1])
                        
                        if 1 <= table_num <= len(all_mirrors):
                            table_name = all_mirrors[table_num - 1]
                            print(f"Moving {table_name} to {angle} degrees...")
                            controller.move_table(table_name, angle)
                        else:
                            print(f"Error: Table number must be between 1 and {len(all_mirrors)}")
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
        # Center all mirrors
        print("\n[INFO] Smoothly centering all mirrors...")
        try:
            controller.cleanup()
        except Exception as e:
            print(f"Error during cleanup: {e}")
        print("Goodbye!")

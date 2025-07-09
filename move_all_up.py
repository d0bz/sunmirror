from servo_controller import MainController
import time

def move_all_up():
    # Initialize controller
    controller = MainController(num_channels=54)
    
    # Setup all mirrors
    for channel in range(54):
        controller.add_table(f"mirror_{channel}", channel=channel)

    # Configuration
    center_angle = 90
    up_angle = 135  # Moving up means increasing the angle
    steps = 30
    step_delay = 0.02
    
    try:
        # Create frame with all mirrors up
        up_frame = {f"mirror_{ch}": up_angle for ch in range(54)}
        
        # Move all mirrors up smoothly
        controller.play_frame_path([up_frame], steps=steps, delay=step_delay)
        
    except KeyboardInterrupt:
        print("\n[INFO] Ctrl+C detected, centering all mirrors.")
        # Center all mirrors
        center_frame = {f"mirror_{ch}": center_angle for ch in range(54)}
        controller.play_frame_path([center_frame], steps=10, delay=step_delay)

if __name__ == "__main__":
    move_all_up()

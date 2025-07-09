import pygame
import math
import time
from sector_mapping import SECTORS

# Initialize Pygame
pygame.init()

# Constants
WINDOW_SIZE = (800, 800)
CENTER = (WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] // 2)
INNER_RADIUS = 100
MIDDLE_RADIUS = 200
OUTER_RADIUS = 300

# Colors
BLACK = (0, 0, 0)
GRAY = (128, 128, 128)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
BLUE = (0, 0, 255)

class MirrorSimulator:
    def __init__(self):
        self.screen = pygame.display.set_mode(WINDOW_SIZE)
        pygame.display.set_caption("Mirror Array Simulator")
        self.clock = pygame.time.Clock()
        
        # Mirror states (channel: angle)
        self.mirror_states = {i: 90 for i in range(54)}
        
        # Mirror positions (channel: (x, y, radius))
        self.mirror_positions = self._calculate_mirror_positions()

    def _calculate_mirror_positions(self):
        positions = {}
        
        # Inner ring (6 mirrors)
        for i in range(6):
            angle = (i * 360 / 6 - 60) * math.pi / 180  # +30 to rotate for better alignment
            x = CENTER[0] + INNER_RADIUS * math.cos(angle)
            y = CENTER[1] + INNER_RADIUS * math.sin(angle)
            positions[i] = (x, y, 20)  # 20 is mirror size
        
        # Middle ring (18 mirrors)
        for i in range(18):
            angle = (i * 360 / 18 - 80) * math.pi / 180
            x = CENTER[0] + MIDDLE_RADIUS * math.cos(angle)
            y = CENTER[1] + MIDDLE_RADIUS * math.sin(angle)
            positions[i + 6] = (x, y, 20)
        
        # Outer ring (30 mirrors)
        for i in range(30):
            angle = (i * 360 / 30 - 85) * math.pi / 180
            x = CENTER[0] + OUTER_RADIUS * math.cos(angle)
            y = CENTER[1] + OUTER_RADIUS * math.sin(angle)
            positions[i + 24] = (x, y, 20)
        
        return positions

    def _draw_mirror(self, x, y, size, angle, sector=None):
        # Convert servo angle to visual angle (90° is horizontal)
        visual_angle = -(angle - 90) * math.pi / 180
        
        # Calculate triangle points
        p1 = (x - size * math.cos(visual_angle), y - size * math.sin(visual_angle))
        
        # Draw angle value
        font = pygame.font.Font(None, 24)  # None uses default font, 24 is size
        text = font.render(f"{int(angle)}°", True, WHITE)
        text_rect = text.get_rect(center=(x, y - size - 15))  # Position above mirror
        self.screen.blit(text, text_rect)
        p2 = (x + size * math.cos(visual_angle), y + size * math.sin(visual_angle))
        p3 = (x + size * math.sin(visual_angle), y - size * math.cos(visual_angle))
        
        # Draw mirror
        color = WHITE
        if sector is not None:
            # Color based on sector
            colors = [RED, (255, 128, 0), BLUE, (0, 255, 0), (255, 0, 255), (0, 255, 255)]
            color = colors[sector - 1]
            
        pygame.draw.polygon(self.screen, color, [p1, p2, p3])
        pygame.draw.polygon(self.screen, GRAY, [p1, p2, p3], 1)

    def update_mirror(self, channel, angle):
        self.mirror_states[channel] = angle

    def update_mirrors(self, angles_dict):
        for channel, angle in angles_dict.items():
            if isinstance(channel, str) and channel.startswith('mirror_'):
                channel = int(channel.split('_')[1])
            self.mirror_states[channel] = angle

    def draw(self):
        self.screen.fill(BLACK)
        
        # Draw circles for reference
        pygame.draw.circle(self.screen, GRAY, CENTER, INNER_RADIUS, 1)
        pygame.draw.circle(self.screen, GRAY, CENTER, MIDDLE_RADIUS, 1)
        pygame.draw.circle(self.screen, GRAY, CENTER, OUTER_RADIUS, 1)
        
        # Draw all mirrors
        for channel, (x, y, size) in self.mirror_positions.items():
            # Find which sector this mirror belongs to
            sector = None
            for sect_num, channels in SECTORS.items():
                if channel in channels:
                    sector = sect_num
                    break
            
            self._draw_mirror(x, y, size, self.mirror_states[channel], sector)
        
        pygame.display.flip()

    def run_animation(self, frame_sequence, steps=30, delay=0.02):
        running = True
        frame_index = 0
        step_counter = 0
        current_angles = self.mirror_states.copy()
        target_angles = None
        
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
            
            # Handle animation
            if frame_index < len(frame_sequence):
                if step_counter == 0:
                    # Start new frame
                    target_angles = {}
                    for channel_name, angle in frame_sequence[frame_index].items():
                        if channel_name.startswith('mirror_'):
                            channel = int(channel_name.split('_')[1])
                            target_angles[channel] = angle
                
                # Interpolate between current and target angles
                if target_angles:
                    ratio = step_counter / steps
                    for channel, target in target_angles.items():
                        start = current_angles[channel]
                        self.mirror_states[channel] = start + (target - start) * ratio
                
                step_counter += 1
                if step_counter == 1:  # Print only at the start of each frame
                    print(f"Playing frame {frame_index + 1}/{len(frame_sequence)}")
                
                time.sleep(delay)  # Add delay between each step
                
                if step_counter >= steps:
                    step_counter = 0
                    frame_index += 1
                    current_angles = self.mirror_states.copy()
                    time.sleep(0.5)  # Pause between movements
            
            self.draw()
            self.clock.tick(60)
        
        pygame.quit()

if __name__ == "__main__":
    from servo_controller import MainController
    from sector_animation import create_sector_sequence
    from sector_animation import create_ripple_wave

    import math
    
    # Create simulator
    simulator = MirrorSimulator()
    
    # Initialize controller
    controller = MainController(num_channels=54)
    
    # Setup all mirrors
    for channel in range(54):
        controller.add_table(f"mirror_{channel}", channel=channel)
    
    center_angle = 90
    
    try:
        # Create ripple wave animation sequence
        frames = create_ripple_wave(
            controller,
            center_angle=90,
            move_amplitude=25,  # Smaller amplitude for gentle wave
            steps=30
        )

        frames = create_sector_sequence(controller)
        
        print(f"Number of frames in sequence: {len(frames)}")
        # Run simulation continuously
        while True:
            print("\nStarting new ripple wave cycle...")
            simulator.run_animation(frames, steps=20, delay=0.01)
            time.sleep(0.1)  # Very short pause for continuous wave effect
        
    except KeyboardInterrupt:
        print("\n[INFO] Simulation stopped.")

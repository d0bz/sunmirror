import unittest
from movement_generator import MovementGenerator

class TestMovementGenerator(unittest.TestCase):
    def test_sync_inout_path(self):
        # Test setup
        table_names = ['test_servo']
        center = 90.0
        amplitude = 45.0
        steps = 20
        loops = 3  # Test multiple loops

        # Generate the path
        path = MovementGenerator.generate_sync_inout_path(
            table_names=table_names,
            center=center,
            amplitude=amplitude,
            steps=steps,
            loops=loops
        )

        # Test that we got a list of frames
        self.assertIsInstance(path, list)
        self.assertTrue(len(path) > 0)

        # Test that each frame has the correct format
        for frame in path:
            self.assertIsInstance(frame, dict)
            self.assertEqual(list(frame.keys()), table_names)
            angle = frame[table_names[0]]
            self.assertIsInstance(angle, float)

        # Print all angles for debugging
        print("\nAll angles:")
        angles = [frame[table_names[0]] for frame in path]
        for i, angle in enumerate(angles):
            print(f"{i:3d}: {angle:6.1f}")

        # Test movement constraints
        min_step = 2.4  # slightly less than STEP_SIZE
        max_step = 2.6  # slightly more than STEP_SIZE
        prev_angle = None
        prev_direction = None  # 1 for increasing, -1 for decreasing
        inner_pos = center - amplitude
        outer_pos = center + amplitude
        
        for frame in path:
            angle = frame[table_names[0]]
            
            # Test angle bounds
            self.assertGreaterEqual(angle, center - amplitude)
            self.assertLessEqual(angle, center + amplitude)

            if prev_angle is not None:
                # Test step size
                step_size = abs(angle - prev_angle)
                
                # Step size should be between min_step and max_step
                # except when at key positions (inner, outer, center)
                at_key_position = (
                    abs(prev_angle - inner_pos) < 0.1 or
                    abs(prev_angle - outer_pos) < 0.1 or
                    abs(prev_angle - center) < 0.1
                )
                
                if not at_key_position and step_size > 0.1:  # Ignore tiny steps
                    self.assertGreaterEqual(step_size, min_step,
                        f"Step size too small: {step_size} degrees from {prev_angle} to {angle}")
                    self.assertLessEqual(step_size, max_step,
                        f"Step size too large: {step_size} degrees from {prev_angle} to {angle}")
                
                # Test direction changes
                if step_size > 0.1:  # Only check significant movements
                    direction = 1 if angle > prev_angle else -1
                    if prev_direction is not None:
                        # Direction can only change at key positions
                        if direction != prev_direction and not at_key_position:
                            self.fail(f"Direction changed unexpectedly from {prev_direction} to {direction} at {prev_angle} -> {angle}")
                    prev_direction = direction
            
            prev_angle = angle

        # Test final position
        self.assertAlmostEqual(path[-1][table_names[0]], center, delta=max_step)

if __name__ == '__main__':
    unittest.main()

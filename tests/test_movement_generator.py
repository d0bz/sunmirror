import unittest
import sys
import os

# Add parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from movement_generator import MovementGenerator

class TestMovementGenerator(unittest.TestCase):
    def test_sequential_wave(self):
        # Test with 6 tables (2 inner, 2 middle, 2 outer)
        inner_tables = ['inner1']
        middle_tables = ['middle1']
        outer_tables = ['outer1']
        center = 90
        amplitude = 45
        step_size = 10  # Larger step size for easier testing
        wave_delay_ms = 50
        
        frames = MovementGenerator.generate_sequential_wave(
            inner_tables=inner_tables,
            middle_tables=middle_tables,
            outer_tables=outer_tables,
            center=center,
            amplitude=amplitude,
            step_size=step_size,
            wave_delay_ms=wave_delay_ms,
            loops=2
        )
        
        #print(frames)

        # Test that we got some frames
        self.assertTrue(len(frames) > 0)
        
        # Test that each frame contains all tables
        self.assertEqual(len(frames[0]), len(inner_tables+middle_tables+outer_tables))
        
        # Test that inner tables move first
        first_frame = frames[1]  # Skip initial frame
        
        # Inner tables should be moving (not at center)
        for table in inner_tables:
            self.assertNotEqual(first_frame[table], center)
            
        # Middle and outer tables should still be at center
        for table in middle_tables + outer_tables:
            self.assertEqual(first_frame[table], center)
            
        # Test final frame - all tables should return to center
        final_frame = frames[-1]
        for table in inner_tables+middle_tables+outer_tables:
            self.assertEqual(final_frame[table], center)
            
        # Test amplitude bounds
        for frame in frames:
            for angle in frame.values():
                self.assertLessEqual(angle, center + amplitude)
                self.assertGreaterEqual(angle, center - amplitude)

    def test_start_and_end_positions(self):
        # Test with same tables setup
        inner_tables = ['inner1', 'inner2', 'inner3']
        middle_tables = ['middle1', 'middle2', 'middle3']
        outer_tables = ['outer1', 'outer2', 'outer3']
        center = 90
        amplitude = 45
        step_size = 4
        wave_delay_ms = 50
        loops = 2

        frames = MovementGenerator.generate_sequential_wave(
            inner_tables=inner_tables,
            middle_tables=middle_tables,
            outer_tables=outer_tables,
            center=center,
            amplitude=amplitude,
            step_size=step_size,
            wave_delay_ms=wave_delay_ms,
            loops=loops
        )

        # Test first frame - all tables should start at center
        first_frame = frames[0]
        for table in inner_tables + middle_tables + outer_tables:
            self.assertEqual(
                first_frame[table], 
                center, 
                f"Table {table} not at center position in first frame. Expected {center}, got {first_frame[table]}"
            )

        # Test final frame - all tables should end at center
        final_frame = frames[-1]
        for table in inner_tables + middle_tables + outer_tables:
            self.assertEqual(
                final_frame[table], 
                center,
                f"Table {table} not at center position in final frame. Expected {center}, got {final_frame[table]}"
            )

    def test_wave_timing_and_direction(self):
        # Setup with minimal tables for clarity
        inner_tables = ['inner1']
        middle_tables = ['middle1']
        outer_tables = ['outer1']
        center = 90
        amplitude = 45
        step_size = 1  # Small step size for more precise testing
        wave_delay_ms = 50

        frames = MovementGenerator.generate_sequential_wave(
            inner_tables=inner_tables,
            middle_tables=middle_tables,
            outer_tables=outer_tables,
            center=center,
            amplitude=amplitude,
            step_size=step_size,
            wave_delay_ms=wave_delay_ms
        )

        def is_direction_change(prev_frame, curr_frame, next_frame, table):
            """Check if a table changes direction by comparing three consecutive frames"""
            if not all(t in f for f in [prev_frame, curr_frame, next_frame] for t in [table]):
                return False
            prev_diff = curr_frame[table] - prev_frame[table]
            next_diff = next_frame[table] - curr_frame[table]
            return (prev_diff > 0 and next_diff < 0) or (prev_diff < 0 and next_diff > 0)

        # Find frames where inner table changes direction
        for i in range(1, len(frames)-1):
            if is_direction_change(frames[i-1], frames[i], frames[i+1], 'inner1'):
                # When inner changes direction, check if middle starts moving in opposite direction
                inner_direction = frames[i+1]['inner1'] - frames[i]['inner1']
                
                # Look ahead a few frames to detect middle table movement
                for j in range(i, min(i + 10, len(frames)-1)):
                    middle_movement = frames[j+1]['middle1'] - frames[j]['middle1']
                    if middle_movement != 0:  # Middle table starts moving
                        self.assertNotEqual(
                            inner_direction * middle_movement,
                            abs(inner_direction * middle_movement),
                            f"Middle table should move in opposite direction to inner at frame {j}"
                        )
                        break

                # Similarly for outer table when middle changes direction
                for k in range(i, min(i + 20, len(frames)-2)):
                    if is_direction_change(frames[k-1], frames[k], frames[k+1], 'middle1'):
                        middle_direction = frames[k+1]['middle1'] - frames[k]['middle1']
                        
                        # Look ahead to detect outer table movement
                        for m in range(k, min(k + 10, len(frames)-1)):
                            outer_movement = frames[m+1]['outer1'] - frames[m]['outer1']
                            if outer_movement != 0:  # Outer table starts moving
                                self.assertNotEqual(
                                    middle_direction * outer_movement,
                                    abs(middle_direction * outer_movement),
                                    f"Outer table should move in opposite direction to middle at frame {m}"
                                )
                                break

    def test_move_all_rings_to_angle(self):
        # Test setup
        first_ring = ['first1', 'first2']
        second_ring = ['second1', 'second2']
        third_ring = ['third1', 'third2']
        center = 90
        target_angle = 135  # 45 degrees from center
        step_size = 5  # 5 degrees per step for testing

        frames = MovementGenerator.move_all_rings_to_angle(
            first_ring=first_ring,
            second_ring=second_ring,
            third_ring=third_ring,
            target_angle=target_angle,
            step_size=step_size,
            center=center
        )

        print(frames)

        # Test that we got the expected number of frames
        total_movement = abs(target_angle - center)
        expected_steps = int(total_movement / step_size)
        expected_frames = (expected_steps + 1) * 3  # +1 for final position, *3 for three rings
        self.assertEqual(len(frames), expected_frames, "Incorrect number of frames generated")

        # Test first sequence (first ring moving)
        first_sequence = frames[:expected_steps + 1]
        for frame in first_sequence:
            # Only first ring should be moving
            self.assertTrue(all(name in frame for name in first_ring), "First ring missing from frame")
            self.assertFalse(any(name in frame for name in second_ring), "Second ring present too early")
            self.assertFalse(any(name in frame for name in third_ring), "Third ring present too early")

        # Test second sequence (second ring moving)
        second_sequence = frames[expected_steps + 1:2*(expected_steps + 1)]
        for frame in second_sequence:
            # First ring should be at target, second ring moving
            self.assertTrue(all(name in frame for name in second_ring), "Second ring missing from frame")
            self.assertFalse(any(name in frame for name in third_ring), "Third ring present too early")

        # Test third sequence (third ring moving)
        third_sequence = frames[2*(expected_steps + 1):]
        for frame in third_sequence:
            # First and second rings at target, third ring moving
            self.assertTrue(all(name in frame for name in third_ring), "Third ring missing from frame")

        # Test angle bounds and step size
        for frame in frames:
            for angle in frame.values():
                self.assertGreaterEqual(angle, min(center, target_angle), "Angle below minimum")
                self.assertLessEqual(angle, max(center, target_angle), "Angle above maximum")

if __name__ == '__main__':
    unittest.main()

"""External preparation inputs remain legal and separate from policy control."""

import unittest

from mr3_learning.benchmark import probe_action


class PreparationProbeTests(unittest.TestCase):
    def test_outward_goals_do_not_reuse_crossing_stress_order(self):
        mask = [False] * 1000
        for action in (12, 345, 889):
            mask[action] = True
        candidates = [{"path_distances_m": [1., 1., 1.]} for _ in range(8)]
        for candidate, point in zip(candidates, (
                (-1., -1.4), (-1., 1.4), (1.45, 0.), (1., 0.),
                (1., .5), (-1., 0.), (0., 0.), (0., 0.))):
            candidate.update(x=point[0], y=point[1])
        for index in (3, 4, 5):
            candidates[index]["path_distances_m"] = [4., 4., 4.]
        snapshot = {"task_elapsed_sec": 0., "joint_action_mask": mask,
                    "candidates": candidates,
                    "robots": [{"x": 0., "y": -.45}, {"x": 0., "y": .45},
                               {"x": .45, "y": 0.}]}
        self.assertEqual(probe_action(snapshot), 345)
        self.assertEqual(probe_action(snapshot, outward_goals=True), 12)
        for index in (0, 1, 2):
            candidates[index]["path_distances_m"] = [100., 100., 100.]
        self.assertEqual(probe_action(snapshot, outward_goals=True), 12)
        # Commitment and cancellation inputs retain the original timing.
        snapshot["task_elapsed_sec"] = 4.
        self.assertEqual(probe_action(snapshot, outward_goals=True), 888)
        snapshot["task_elapsed_sec"] = 8.
        self.assertEqual(probe_action(snapshot, outward_goals=True), 889)


if __name__ == "__main__":
    unittest.main()

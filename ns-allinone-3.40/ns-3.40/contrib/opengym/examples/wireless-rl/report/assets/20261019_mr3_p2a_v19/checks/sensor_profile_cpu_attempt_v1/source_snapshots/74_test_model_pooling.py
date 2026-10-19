"""CPU mathematical equivalence of fixed bins; no GPU probe or optimizer."""

import unittest

import torch
from torch import nn

from mr3_learning.model import MR3ActorCritic


class FixedPoolingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous_threads = torch.get_num_threads()
        torch.set_num_threads(1)

    @classmethod
    def tearDownClass(cls):
        torch.set_num_threads(cls.previous_threads)

    def test_actual_convolution_and_pool_shapes(self):
        model = MR3ActorCritic().cpu()
        for encoder, side, feature_side, kernel in (
                (model.global_encoder, 128, 32, 8), (model.local_encoder, 64, 16, 4)):
            with self.subTest(input_side=side), torch.no_grad():
                features = encoder[:4](torch.zeros(1, 3, side, side, device="cpu"))
                self.assertEqual(tuple(features.shape), (1, 32, feature_side, feature_side))
                self.assertIsInstance(encoder[4], nn.AvgPool2d)
                self.assertEqual(encoder[4].kernel_size, kernel)
                self.assertEqual(tuple(encoder[4](features).shape), (1, 32, 4, 4))
        self.assertFalse(any(isinstance(layer, nn.AdaptiveAvgPool2d) for layer in model.modules()))

    def test_fixed_and_adaptive_outputs_and_input_gradients_are_equivalent(self):
        for side, kernel in ((32, 8), (16, 4)):
            with self.subTest(feature_side=side):
                source = torch.linspace(-5., 7., 2 * 3 * side * side,
                                        dtype=torch.float64, device="cpu")
                source = source.reshape(2, 3, side, side)
                fixed_input = source.clone().requires_grad_(True)
                adaptive_input = source.clone().requires_grad_(True)
                fixed = nn.AvgPool2d(kernel)(fixed_input)
                adaptive = nn.AdaptiveAvgPool2d((4, 4))(adaptive_input)
                torch.testing.assert_close(fixed, adaptive, rtol=0., atol=1e-12)
                upstream = torch.linspace(-2., 3., fixed.numel(), dtype=torch.float64,
                                          device="cpu").reshape_as(fixed)
                fixed.backward(upstream)
                adaptive.backward(upstream)
                torch.testing.assert_close(fixed_input.grad, adaptive_input.grad,
                                           rtol=0., atol=1e-12)


if __name__ == "__main__":
    unittest.main()

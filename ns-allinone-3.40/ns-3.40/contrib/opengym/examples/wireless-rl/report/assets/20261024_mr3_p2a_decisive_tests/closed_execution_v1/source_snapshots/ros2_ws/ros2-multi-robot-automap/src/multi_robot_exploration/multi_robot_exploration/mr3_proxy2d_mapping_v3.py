"""Conservative sensor-only observation-consistency candidate, disabled.

The closed cells touching a numerical endpoint are alternatives, not an
obstacle dilation or a sensor-noise confidence region. A grid-line endpoint
does not identify an obstacle normal. Ambiguous hits therefore supply no new
occupied evidence. This may leave grid-aligned walls unknown indefinitely.
"""

import numpy as np

from .mr3_proxy2d_mapping import SensorMapperV2, TIE_ULPS


MODEL = "range_ray_closed_cell_veto_v3"


class SensorMapperV3(SensorMapperV2):
    """Retain v2 validation, bounded scores and source-scan identity semantics.

    Current hit alternatives cannot remain free: after this scan's votes,
    negative evidence at those cells is reset to zero. This persists until
    actual new free evidence arrives; it is not a temporary output overlay.
    Prior positive evidence is retained, but an ambiguous hit adds none.
    """

    def __init__(self, shape, resolution, origin):
        super().__init__(shape, resolution, origin)
        self._pending_support = None

    def integrate(self, scan_id, sensor_pose, angles, ranges, range_min=.12, range_max=10.):
        try:
            accepted = super().integrate(scan_id, sensor_pose, angles, ranges,
                                         range_min=range_min, range_max=range_max)
            if accepted:
                flat = self._score.ravel()
                flat[self._pending_support] = np.maximum(flat[self._pending_support], 0)
            return accepted
        finally:
            # No scan history or persistent endpoint/support array is kept.
            self._pending_support = None

    def _votes(self, pose, angles, ranges, maximum):
        # Reuse unchanged v2 finite-lattice/workspace checks and integer ray
        # rasterization. Its forward-side hits are deliberately not reused.
        free, _ = super()._votes(pose, angles, ranges, maximum)
        heading = angles + pose[2]
        directions = np.stack((np.cos(heading), np.sin(heading)), axis=-1)
        origin = (pose[:2] - self.origin) / self.resolution
        endpoint = origin + directions * ranges[:, None] / self.resolution
        nearest = np.rint(endpoint)
        tolerance = TIE_ULPS * np.spacing(np.maximum(1., np.abs(endpoint)))
        ties = np.abs(endpoint - nearest) <= tolerance
        lower = np.where(ties, nearest - 1, np.floor(endpoint)).astype(np.int64)
        upper = np.where(ties, nearest, np.floor(endpoint)).astype(np.int64)
        measured_hit = ranges < maximum
        # Uniqueness is decided before map clipping. An out-of-map alternative
        # cannot turn an ambiguous observation into a unique occupied vote.
        unique = measured_hit & ~ties.any(axis=1)
        in_map = lambda cell: ((cell[..., 0] >= 0) & (cell[..., 0] < self.shape[1])
                               & (cell[..., 1] >= 0) & (cell[..., 1] < self.shape[0]))
        selected = lower[unique & in_map(lower)]
        hits = np.unique(selected[:, 1] * self.shape[1] + selected[:, 0])
        alternatives = np.stack((lower, upper,
            np.column_stack((lower[:, 0], upper[:, 1])),
            np.column_stack((upper[:, 0], lower[:, 1]))), axis=1)
        valid = measured_hit[:, None] & in_map(alternatives)
        cells = alternatives[valid]
        support = np.unique(cells[:, 1] * self.shape[1] + cells[:, 0])
        free = np.setdiff1d(free, support, assume_unique=True)
        self._pending_support = support
        return free, hits

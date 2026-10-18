"""Exact admitted-prefix oracle; no producer-selected reference is consulted."""
from bisect import bisect_left, insort


def expected_latest(self, kind, robot, clock):
    admitted = self.admitted[kind, robot]
    cache = self.__dict__.setdefault('_latest_admitted_index', {})
    state = cache.setdefault((kind, robot), [0, []])
    index = state[1]
    for offset in range(state[0], len(admitted)):
        item = admitted[offset]
        insort(index, (item['source_ns'], item['sequence'], -offset))
    state[0] = len(admitted)
    position = bisect_left(index, (clock + 1,)) - 1
    return admitted[-index[position][2]] if position >= 0 else None

"""Keep action Future state mutation in its owning node callback group."""
import queue


def initialize_action_callbacks(node):
    node.shutdown_requested = False
    node.action_done_callbacks = queue.SimpleQueue()
    node.action_done_guard = node.create_guard_condition(node.drain_action_done_callbacks)


def defer_action_done_callback(self, future, callback):
    """Future tasks bypass callback groups; enqueue state work back into ours."""
    def ready(completed):
        if self.shutdown_requested:
            return
        self.action_done_callbacks.put((callback, completed))
        try:
            self.action_done_guard.trigger()
        except Exception:
            if not self.shutdown_requested and self.context.ok():
                raise
    future.add_done_callback(ready)


def drain_action_done_callbacks(self):
    while not self.shutdown_requested:
        try:
            callback, completed = self.action_done_callbacks.get_nowait()
        except queue.Empty:
            return
        callback(completed)


"""Read-only native lifecycle queries for the external smoke harness."""
from lifecycle_msgs.msg import State
from lifecycle_msgs.srv import GetState


class LifecycleQueries:
    def __init__(self, node, names):
        self.clients = {name: node.create_client(GetState, name + '/get_state')
                        for name in names}
        self.pending = {}
        self.active = set()
        self.labels = {name: 'unavailable' for name in names}
        self.next_query = {}

    def poll(self, now):
        for name, (future, started) in list(self.pending.items()):
            if future.done():
                try:
                    state = future.result().current_state
                    self.labels[name] = state.label
                    if state.id == State.PRIMARY_STATE_ACTIVE and state.label == 'active':
                        self.active.add(name)
                except Exception:
                    self.labels[name] = 'query failed'
                del self.pending[name]
                self.next_query[name] = now + .5
            elif now - started >= 2.:
                self.clients[name].remove_pending_request(future)
                future.cancel()
                del self.pending[name]
                self.labels[name] = 'query timed out'
        for name, client in self.clients.items():
            if (name not in self.active and name not in self.pending
                    and now >= self.next_query.get(name, 0.) and client.service_is_ready()):
                self.pending[name] = client.call_async(GetState.Request()), now

    def missing(self):
        return [f'{name} ({self.labels[name]})' for name in self.clients if name not in self.active]

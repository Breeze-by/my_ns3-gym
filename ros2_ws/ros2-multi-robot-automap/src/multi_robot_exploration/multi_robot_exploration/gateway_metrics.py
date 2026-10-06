"""Application payload accounting and simulation-time metrics shared by live/replay."""

from collections import Counter, defaultdict
from bisect import bisect_left, bisect_right
import math
import statistics
from .fault_model import RELIABLE_TYPES


SCHEMA_VERSION = 1
PERCENTILE_MIN_SAMPLES = {"p50": 2, "p95": 20, "p99": 100}
WINDOW_COUNT_FIELDS = (
    "generated_messages", "generated_bytes", "explicit_generated_messages", "inferred_generated_messages",
    "carry_in_messages", "admitted_messages", "admitted_bytes", "admitted_attempts", "admitted_attempt_bytes",
    "attempted_messages", "attempted_bytes", "retry_attempts", "delivered_messages", "delivered_bytes",
    "accepted_messages", "accepted_bytes", "delivered_attempts", "delivered_attempts_bytes",
    "dropped_tx_attempts", "dropped_tx_attempts_bytes", "duplicate_copies", "duplicate_copy_bytes",
    "ttl_expired_attempts", "ttl_expired_bytes", "queue_overflow_attempts", "queue_overflow_bytes",
    "injected_loss_attempts", "injected_loss_bytes", "retry_exhausted_or_deadline_messages",
    "retry_exhausted_or_deadline_bytes", "stale_sequence_receipts", "receiver_expired_receipts",
    "cohort_delivered_messages", "cohort_accepted_messages",
)


def task_degradation_index(ideal, fault):
    """P3B.5 frozen scoring, available to installed P3C GUI and exports."""
    if not ideal or not fault or ideal.get("mission_mode") != "rally" or not ideal.get("success") or ideal.get("task_phase") != "COMPLETE":
        return None
    if fault.get("success") and fault.get("task_phase") == "COMPLETE":
        return 0.0
    if fault.get("partial_completion"):
        return 1.0 - fault["required_robot_count"] / ideal["robot_count"]
    return 1.0


def event_stamp(event):
    return float(event.get("time", event.get("event_time", event.get("observer_time", 0.0))))


def distribution(values):
    values = sorted(values)
    count = len(values)
    result = {"n": count, "mean": statistics.fmean(values) if values else None,
              "max": max(values) if values else None}
    for name, minimum in PERCENTILE_MIN_SAMPLES.items():
        q = int(name[1:]) / 100
        if count < minimum:
            result[name] = None
        else:
            index = (count - 1) * q
            low = math.floor(index)
            high = math.ceil(index)
            result[name] = values[low] + (values[high] - values[low]) * (index - low)
    return result


def freshness(updates, start, end, first_generated):
    """Exact source-age integrals; no reception is unknown age and not fresh."""
    start = max(start, first_generated)
    if end <= start:
        return {"observed_sec": 0.0, "no_data_sec": 0.0, "fresh_sec": 0.0,
                "stale_sec": 0.0, "monitored_sec": 0.0, "age_intervals": [],
                "first_no_data_time": None, "first_source_stale_time": None,
                "recovery_times_sec": [], "first_freshness_recovery_time": None, "unrecovered_stale_sec": 0.0}
    updates = sorted(updates)
    source, ttl, cursor = None, 0.0, start
    observed = fresh = missing = 0.0
    intervals = []
    first_no_data = first_stale = None
    states = []

    def state_interval(left, right, is_fresh):
        if right <= left:
            return
        if states and states[-1][2] == is_fresh and states[-1][1] == left:
            states[-1] = (states[-1][0], right, is_fresh)
        else:
            states.append((left, right, is_fresh))

    def integrate(right):
        nonlocal cursor, observed, fresh, missing, first_no_data, first_stale
        right = min(end, max(cursor, right))
        duration = right - cursor
        if source is None:
            missing += duration
            state_interval(cursor, right, False)
            if duration > 0 and first_no_data is None:
                first_no_data = cursor
        else:
            # Future source information is not usable before its source timestamp.
            known_start = max(cursor, source)
            missing += max(0.0, min(right, source) - cursor)
            state_interval(cursor, min(right, source), False)
            if right > known_start:
                observed += right - known_start
                intervals.append((known_start - source, right - source))
                fresh += max(0.0, min(right, source + ttl) - known_start) if ttl > 0 else right - known_start
                boundary = min(right, source + ttl) if ttl > 0 else right
                state_interval(known_start, boundary, True)
                state_interval(max(known_start, boundary), right, False)
                if ttl > 0 and right > source + ttl and first_stale is None:
                    first_stale = max(known_start, source + ttl)
        cursor = right

    for when, generated, limit in updates:
        if when > end:
            break
        if when > cursor:
            integrate(when)
        if source is None or generated >= source:
            source, ttl = generated, limit
    integrate(end)
    recovered = [(right, right-left) for left, right, is_fresh in states[:-1] if not is_fresh]
    return {"observed_sec": observed, "no_data_sec": missing, "fresh_sec": fresh,
            "stale_sec": end - start - fresh, "monitored_sec": end - start, "age_intervals": intervals,
            "first_no_data_time": first_no_data, "first_source_stale_time": first_stale,
            "recovery_times_sec": [duration for _, duration in recovered],
            "first_freshness_recovery_time": recovered[0][0] if recovered else None,
            "unrecovered_stale_sec": states[-1][1]-states[-1][0] if states and not states[-1][2] else 0.0}


def age_summary(parts):
    observed = sum(x["observed_sec"] for x in parts)
    monitored = sum(x["monitored_sec"] for x in parts)
    intervals = [pair for part in parts for pair in part["age_intervals"]]
    result = {name: sum(x[name] for x in parts) for name in
              ("observed_sec", "no_data_sec", "fresh_sec", "stale_sec", "monitored_sec")}
    result["fresh_ratio"] = result["fresh_sec"] / monitored if monitored else None
    for name in ("first_no_data_time", "first_source_stale_time", "first_freshness_recovery_time"):
        result[name] = min((x[name] for x in parts if x[name] is not None), default=None)
    recoveries = [value for part in parts for value in part["recovery_times_sec"]]
    result.update(recovery_count=len(recoveries), recovery_time_mean_sec=statistics.fmean(recoveries) if recoveries else None,
                  recovery_time_max_sec=max(recoveries, default=None),
                  unrecovered_stale_sec=sum(x["unrecovered_stale_sec"] for x in parts))
    result["mean"] = sum((b*b-a*a)/2 for a, b in intervals) / observed if observed else None
    result["max"] = max((b for _, b in intervals), default=None)
    result["p95"] = None
    if observed and intervals:
        low, high = 0.0, result["max"]
        for _ in range(32):
            mid = (low + high) / 2
            mass = sum(max(0.0, min(b, mid) - a) for a, b in intervals)
            if mass < 0.95 * observed:
                low = mid
            else:
                high = mid
        result["p95"] = (low + high) / 2
    return result


class LedgerMetrics:
    def __init__(self, context=None):
        self.context = dict(context or {})
        self.events = []
        self.messages = {}
        self.scope_ids = defaultdict(list)
        self.route_births = {}
        self.route_updates = defaultdict(list)
        self.order_cache = {}
        self.routes = defaultdict(list)
        self.timeline = []
        self.configurations = []
        self.queue_ticks = []
        self.errors = []
        self.first_events = {}
        self.last_time = 0.0

    def ingest(self, event):
        event = dict(event)
        when = event_stamp(event)
        if not math.isfinite(when):
            raise ValueError("ledger timestamps must be finite")
        self.last_time = max(self.last_time, when)
        self.events.append(event)
        kind = event.get("event", "")
        if kind == "metrics_tick" and "queues" in event:
            self.queue_ticks.append(event)
        if kind in ("gateway_start", "configuration_applied", "fault_epoch") and "configuration" in event:
            state = event["configuration"]
            self.configurations.append((when, state))
            if kind == "gateway_start":
                self.context.update({k: event[k] for k in
                    ("episode_id", "gazebo_seed", "fault_seed", "world", "mission_mode", "robot_count") if k in event})
        if kind == "fault_epoch":
            self.context.setdefault("episode_start_sim_time", when)
        reason = event.get("reason", "")
        if kind == "drop":
            self.first_events.setdefault("first_drop", event)
            if "expired" in reason:
                self.first_events.setdefault("first_ttl_expiry", event)
        if kind in ("navigation_deadline", "coordinator_stale_inputs", "coordinator_wait"):
            self.first_events.setdefault("first_" + kind, event)
        if kind in ("consumed", "target_reconfirmed", "navigation_deadline", "navigation_outcome",
                    "coordinator_wait", "coordinator_recovered", "configuration_applied", "configuration_rejected",
                    "task_phase", "robot_failure", "battery_transition", "collision"):
            self.timeline.append(event)
        identity = event.get("message_id")
        direction = event.get("direction")
        message_type = event.get("message_type")
        if not identity or not direction or not message_type:
            return
        key = (direction, message_type, event.get("sender", ""), event.get("recipient", ""))
        if identity not in self.messages:
            self.messages[identity] = {"key": key, "bytes": None, "events": [], "ttl": 0.0, "sorted": None}
            for scope in ((), key[:1], key[:2], key):
                self.scope_ids[scope].append(identity)
        message = self.messages[identity]
        if message["key"] != key:
            self.errors.append(f"route changed for {identity}")
        length = event.get("payload_length")
        if length is not None:
            if type(length) is not int or length < 0 or (message["bytes"] is not None and message["bytes"] != length):
                self.errors.append(f"payload length mismatch for {identity}")
            else:
                message["bytes"] = length
        message["ttl"] = float(event.get("ttl_sec", message["ttl"]))
        message["events"].append(event)
        message["sorted"] = None
        self.routes[key].append(event)
        if kind in ("generated", "enqueue"):
            self.route_births[key] = min(when, self.route_births.get(key, when))
        if kind == "accepted" and "source_time" in event:
            self.route_updates[key].append((when, float(event["source_time"]), identity))
        if kind == "delivered":
            self.order_cache.pop(key, None)

    def add_task_event(self, event):
        self.ingest(event)

    def _message_metrics(self, identities, start, end):
        counts = Counter()
        latencies = defaultdict(list)
        parts = []
        tx_keys, admitted_keys, resolved_keys = set(), set(), set()
        narrow = end - start <= 1.000001
        for identity in identities:
            message = self.messages[identity]
            if message["sorted"] is None:
                message["sorted"] = sorted(message["events"], key=event_stamp)
                message["times"] = [event_stamp(e) for e in message["sorted"]]
            right = bisect_right(message["times"], end)
            if narrow and bisect_left(message["times"], start) >= bisect_left(message["times"], end):
                continue
            records = message["sorted"][:right]
            if not records:
                continue
            size = message["bytes"] or 0
            explicit = [e for e in records if e["event"] == "generated"]
            enqueues = [e for e in records if e["event"] == "enqueue"]
            born = min((event_stamp(e) for e in explicit or enqueues), default=None)
            if born is None:
                continue
            if start <= born < end:
                counts["generated_messages"] += 1
                counts["generated_bytes"] += size
                counts["explicit_generated_messages" if explicit else "inferred_generated_messages"] += 1
            elif born < start:
                counts["carry_in_messages"] += 1
            first_admit = first_deliver = first_accept = None
            admitted = transmitted = delivered = accepted = False
            failed = False
            unresolved_tx = set()
            updates = []
            for event in records:
                when, kind = event_stamp(event), event["event"]
                selected = start <= when < end
                attempt_key = (identity, int(event.get("attempt", 1)))
                duplicate = bool(event.get("duplicate", False))
                if kind == "admitted":
                    admitted = True
                    first_admit = when if first_admit is None else first_admit
                    if selected:
                        admitted_keys.add(attempt_key)
                        counts["admitted_attempts"] += 1
                        counts["admitted_attempt_bytes"] += size
                if kind == "tx":
                    transmitted = True
                    unresolved_tx.add(attempt_key)
                    if selected:
                        tx_keys.add(attempt_key)
                        counts["attempted_messages"] += 1
                        counts["attempted_bytes"] += size
                        if event.get("attempt", 1) > 1:
                            counts["retry_attempts"] += 1
                        for name, left in (("queue_wait", "enqueue_time"), ("admit_to_tx", "admit_time")):
                            if left in event:
                                latencies[name].append(when - float(event[left]))
                if kind in ("delivered", "drop"):
                    if not duplicate and (kind == "delivered" or "tx_time" in event):
                        unresolved_tx.discard(attempt_key)
                        if selected:
                            resolved_keys.add(attempt_key)
                            name = "delivered_attempts" if kind == "delivered" else "dropped_tx_attempts"
                            counts[name] += 1
                            counts[name + "_bytes"] += size
                    if kind == "delivered":
                        delivered = True
                        first_deliver = when if first_deliver is None else first_deliver
                        if selected and not duplicate:
                            for name, left in (("tx_to_delivery", "tx_time"), ("source_to_delivery", "source_time")):
                                if left in event:
                                    latencies[name].append(when - float(event[left]))
                    if selected and duplicate:
                        counts["duplicate_copies"] += 1
                        counts["duplicate_copy_bytes"] += size
                    if kind == "drop" and selected:
                        reason = event.get("reason", "unknown")
                        category = ("ttl_expired" if "expired" in reason else
                                    "queue_overflow" if reason == "queue_overflow" else "injected_loss")
                        counts[category + "_attempts"] += 1
                        counts[category + "_bytes"] += size
                        if message["key"][1] not in RELIABLE_TYPES:
                            failed = True
                if kind == "failed":
                    failed = True
                    if selected:
                        counts["retry_exhausted_or_deadline_messages"] += 1
                        counts["retry_exhausted_or_deadline_bytes"] += size
                if kind == "stale_sequence" and selected:
                    counts["stale_sequence_receipts"] += 1
                if kind == "expired" and selected:
                    counts["receiver_expired_receipts"] += 1
                if kind == "accepted":
                    accepted = True
                    first_accept = when if first_accept is None else first_accept
                    if "source_time" in event:
                        updates.append((when, float(event["source_time"]), message["ttl"]))
                        if selected:
                            latencies["source_to_accept"].append(when - float(event["source_time"]))
            for name, timestamp in (("admitted", first_admit), ("delivered", first_deliver), ("accepted", first_accept)):
                if timestamp is not None and start <= timestamp < end:
                    counts[name + "_messages"] += 1
                    counts[name + "_bytes"] += size
            if start <= born < end:
                counts["cohort_delivered_messages"] += delivered
                counts["cohort_accepted_messages"] += accepted
            if narrow:
                continue
            # Conservation is over the entire retained trace, including cold start.
            counts["ledger_generated_messages"] += 1
            counts["ledger_generated_bytes"] += size
            counts["ledger_enqueued_messages"] += bool(enqueues)
            counts["ledger_enqueued_bytes"] += size * bool(enqueues)
            counts["ledger_admitted_messages"] += admitted
            counts["ledger_admitted_bytes"] += size * admitted
            counts["ledger_delivered_messages"] += delivered
            counts["ledger_delivered_bytes"] += size * delivered
            counts["ledger_generated_not_enqueued_messages"] += not enqueues
            counts["ledger_generated_not_enqueued_bytes"] += size * (not enqueues)
            counts["ledger_never_admitted_messages"] += bool(enqueues) and not admitted
            counts["ledger_never_admitted_bytes"] += size * (bool(enqueues) and not admitted)
            terminal = admitted and not delivered and failed and not unresolved_tx
            pending = admitted and not delivered and not terminal
            counts["ledger_terminal_without_delivery_messages"] += terminal
            counts["ledger_terminal_without_delivery_bytes"] += size * terminal
            counts["ledger_unresolved_messages"] += pending
            counts["ledger_unresolved_bytes"] += size * pending
            parts.append((message["key"], born, updates))
        return counts, latencies, parts, (admitted_keys, tx_keys, resolved_keys)

    def report(self, start, end, direction=None, message_type=None, sender=None, recipient=None):
        filters = (direction, message_type, sender, recipient)
        if filters in self.scope_ids:
            identities = self.scope_ids[filters]
        elif recipient is None and sender is None and message_type is not None:
            identities = self.scope_ids[filters[:2]]
        elif all(x is None for x in filters[1:]):
            identities = self.scope_ids[filters[:1]] if direction else self.scope_ids[()]
        else:
            identities = [identity for identity, message in self.messages.items() if all(
                value is None or value == actual for value, actual in zip(filters, message["key"]))]
        counts, latencies, histories, attempt_sets = self._message_metrics(identities, start, end)
        # AoI is per received stream, not per message. New source versions never roll back.
        keys = [key for key in self.routes if all(value is None or value == actual for value, actual in zip(filters, key))]
        aoi = age_summary([freshness([(t, s, self.messages[i]["ttl"]) for t, s, i in self.route_updates[key]],
                                    start, end, self.route_births.get(key, end)) for key in keys])
        generated = counts["generated_messages"]
        resolved = counts["delivered_attempts"] + counts["dropped_tx_attempts"]
        span = end - start
        snapshot = {
            "schema_version": SCHEMA_VERSION, **self.context, "start_sim_time": start, "sim_time": end,
            "elapsed_sim_time": end - float(self.context.get("episode_start_sim_time", start)),
            "direction": direction or "all", "message_type": message_type or "all",
            "sender": sender or "all", "recipient": recipient or "all", "counts": {**dict.fromkeys(WINDOW_COUNT_FIELDS, 0), **dict(counts)},
            "offered_bytes_per_sec": counts["generated_bytes"] / span if span else None,
            "goodput_bytes_per_sec": counts["accepted_bytes"] / span if span else None,
            "logical_pdr": counts["cohort_delivered_messages"] / generated if generated else None,
            "application_pdr": counts["cohort_accepted_messages"] / generated if generated else None,
            "attempt_pdr": counts["delivered_attempts"] / resolved if resolved else None,
            "attempt_loss_rate": counts["dropped_tx_attempts"] / resolved if resolved else None,
            "retry_rate": counts["retry_attempts"] / counts["attempted_messages"] if counts["attempted_messages"] else None,
            "delays": {key: distribution(latencies[key]) for key in
                       ("queue_wait", "admit_to_tx", "tx_to_delivery", "source_to_delivery", "source_to_accept")},
            "aoi": aoi, "configuration": self.configuration_at(end),
            "provisional": True, "ledger_record_count": len(self.events),
        }
        limits = {self.messages[i]["ttl"] for i in identities if self.messages[i]["ttl"] > 0}
        snapshot["freshness_ttl_sec"] = next(iter(limits)) if len(limits) == 1 else None
        ticks = [e for e in self.queue_ticks if event_stamp(e) <= end]
        queue = ticks[-1]["queues"] if ticks else {}
        snapshot["queues"] = {key: value for key, value in queue.items() if direction is None or key == direction}
        snapshot["queue_measurement"] = "transport_sample" if ticks else "unavailable_in_legacy_ledger"
        snapshot["first_events"] = self.first_events
        reordered = 0
        for key in keys:
            if key not in self.order_cache:
                delivered = sorted((e for e in self.routes[key] if e["event"] == "delivered" and not e.get("duplicate")), key=event_stamp)
                high, count, times, prefix = 0, 0, [], [0]
                for event in delivered:
                    sequence = int(event.get("sequence", 0))
                    count += sequence < high
                    high = max(sequence, high)
                    times.append(event_stamp(event))
                    prefix.append(count)
                self.order_cache[key] = (times, prefix)
            times, prefix = self.order_cache[key]
            reordered += prefix[bisect_left(times, end)] - prefix[bisect_left(times, start)]
        snapshot["reordered_receipts"] = reordered
        return snapshot

    def configuration_at(self, when):
        states = [state for time, state in self.configurations if time <= when]
        return states[-1] if states else self.context.get("configuration", {})

    def audit(self):
        """Reconcile bytes independently at logical-message and primary-attempt levels."""
        errors = list(self.errors)
        rows = []
        for key in sorted(self.routes):
            report = self.report(-1e30, self.last_time + 1e-6, *key)
            c = Counter(report["counts"])
            identities = [m for m in self.messages.values() if m["key"] == key]
            tx, outcomes, admitted = {}, {}, {}
            for message in identities:
                if not any(e["event"] in ("generated", "enqueue") for e in message["events"]):
                    errors.append("orphan ledger message")
                for event in message["events"]:
                    identity = (event["message_id"], int(event.get("attempt", 1)))
                    if event["event"] == "admitted":
                        admitted[identity] = message["bytes"] or 0
                    if event["event"] == "tx":
                        if identity in tx:
                            errors.append(f"duplicate tx attempt {identity}")
                        tx[identity] = message["bytes"] or 0
                    if not event.get("duplicate") and (event["event"] == "delivered" or
                        (event["event"] == "drop" and "tx_time" in event)):
                        if identity in outcomes:
                            errors.append(f"multiple primary outcomes {identity}")
                        outcomes[identity] = message["bytes"] or 0
            if tx.keys() != admitted.keys() or outcomes.keys() - tx.keys():
                errors.append(f"attempt stages do not reconcile: {key}")
            checks = []
            for unit in ("messages", "bytes"):
                checks.extend([
                    c["ledger_generated_"+unit] == c["ledger_enqueued_"+unit] + c["ledger_generated_not_enqueued_"+unit],
                    c["ledger_enqueued_"+unit] == c["ledger_admitted_"+unit] + c["ledger_never_admitted_"+unit],
                    c["ledger_admitted_"+unit] == c["ledger_delivered_"+unit] + c["ledger_terminal_without_delivery_"+unit] + c["ledger_unresolved_"+unit],
                ])
            if not all(checks):
                errors.append(f"logical bytes/messages do not reconcile: {key}")
            rows.append({"direction": key[0], "message_type": key[1], "sender": key[2], "recipient": key[3],
                         "counts": dict(c), "tx_attempts": len(tx), "tx_bytes": sum(tx.values()),
                         "settled_attempts": len(outcomes), "settled_bytes": sum(outcomes.values()),
                         "in_flight_attempts": len(tx.keys()-outcomes.keys()),
                         "in_flight_bytes": sum(tx[x] for x in tx.keys()-outcomes.keys())})
        return {"status": "PASS" if not errors else "FAIL", "errors": sorted(set(errors)), "streams": rows,
                "units": "serialized/compressed application payload bytes; ACK included; no MAC/PHY estimate"}

# pyright: reportMissingImports=false
import time

try:
    import frappe
except Exception:  # pragma: no cover - fallback for non-Frappe test runs
    frappe = None


class _StateStore:
    _LOCAL_STATE = {}

    def __init__(self, namespace):
        self.namespace = str(namespace or "cf")

    def _key(self, key):
        return f"{self.namespace}:{key}"

    def get(self, key, default=None):
        namespaced = self._key(key)
        if frappe:
            try:
                value = frappe.cache().get_value(namespaced)
                if value is not None:
                    return value
            except Exception:
                pass
        return self._LOCAL_STATE.get(namespaced, default)

    def set(self, key, value, ttl_seconds=0):
        namespaced = self._key(key)
        if frappe:
            try:
                kwargs = {}
                if ttl_seconds and int(ttl_seconds) > 0:
                    kwargs["expires_in_sec"] = int(ttl_seconds)
                frappe.cache().set_value(namespaced, value, **kwargs)
            except Exception:
                pass
        self._LOCAL_STATE[namespaced] = value


class CircuitBreakerManager:
    def __init__(self, config=None):
        config = config or {}
        self.enabled = bool(config.get("search_circuit_breaker_enabled", True))
        self.failure_threshold = max(1, int(config.get("search_circuit_breaker_failure_threshold", 3) or 3))
        self.recovery_seconds = max(5, int(config.get("search_circuit_breaker_recovery_seconds", 120) or 120))
        self.half_open_calls = max(1, int(config.get("search_circuit_breaker_half_open_calls", 1) or 1))
        namespace = str(config.get("search_circuit_breaker_namespace") or "cf:circuit").strip()
        self._store = _StateStore(namespace)

    def _state_key(self, provider):
        return f"provider:{str(provider or '').strip().lower()}"

    def _default_state(self):
        return {
            "status": "closed",
            "failures": 0,
            "opened_at": 0.0,
            "half_open_attempts": 0,
        }

    def get_state(self, provider):
        return dict(self._store.get(self._state_key(provider), self._default_state()) or self._default_state())

    def allow_request(self, provider):
        if not self.enabled:
            return True

        state = self.get_state(provider)
        now = time.time()
        status = state.get("status", "closed")

        if status == "open":
            opened_at = float(state.get("opened_at") or 0)
            if opened_at and now - opened_at >= self.recovery_seconds:
                state["status"] = "half_open"
                state["half_open_attempts"] = 0
                self._store.set(self._state_key(provider), state, ttl_seconds=max(self.recovery_seconds * 4, 300))
                return True
            return False

        if status == "half_open":
            attempts = int(state.get("half_open_attempts") or 0)
            if attempts >= self.half_open_calls:
                return False
            state["half_open_attempts"] = attempts + 1
            self._store.set(self._state_key(provider), state, ttl_seconds=max(self.recovery_seconds * 4, 300))
            return True

        return True

    def record_success(self, provider):
        if not self.enabled:
            return
        state = self.get_state(provider)
        state.update({"status": "closed", "failures": 0, "opened_at": 0.0, "half_open_attempts": 0})
        self._store.set(self._state_key(provider), state, ttl_seconds=max(self.recovery_seconds * 4, 300))

    def record_failure(self, provider):
        if not self.enabled:
            return
        state = self.get_state(provider)
        state["failures"] = int(state.get("failures") or 0) + 1
        if state["failures"] >= self.failure_threshold:
            state["status"] = "open"
            state["opened_at"] = time.time()
            state["half_open_attempts"] = 0
        self._store.set(self._state_key(provider), state, ttl_seconds=max(self.recovery_seconds * 4, 300))


class RateLimiter:
    """Token-bucket limiter with provider-level state."""

    def __init__(self, config=None):
        config = config or {}
        self.enabled = bool(config.get("search_rate_limiter_enabled", True))
        per_minute = max(1, int(config.get("search_rate_limit_per_provider_per_minute", 60) or 60))
        self.capacity = float(per_minute)
        self.refill_per_second = self.capacity / 60.0
        namespace = str(config.get("search_rate_limiter_namespace") or "cf:rate").strip()
        self._store = _StateStore(namespace)

    def _state_key(self, provider):
        return f"provider:{str(provider or '').strip().lower()}"

    def _default_state(self):
        now = time.time()
        return {
            "tokens": self.capacity,
            "updated_at": now,
        }

    def allow(self, provider, cost=1.0):
        if not self.enabled:
            return True

        cost_value = max(0.1, float(cost or 1.0))
        state = dict(self._store.get(self._state_key(provider), self._default_state()) or self._default_state())
        now = time.time()
        elapsed = max(0.0, now - float(state.get("updated_at") or now))
        replenished = min(self.capacity, float(state.get("tokens") or 0.0) + elapsed * self.refill_per_second)

        if replenished < cost_value:
            state["tokens"] = replenished
            state["updated_at"] = now
            self._store.set(self._state_key(provider), state, ttl_seconds=3600)
            return False

        state["tokens"] = replenished - cost_value
        state["updated_at"] = now
        self._store.set(self._state_key(provider), state, ttl_seconds=3600)
        return True

    def snapshot(self, provider):
        state = dict(self._store.get(self._state_key(provider), self._default_state()) or self._default_state())
        return {
            "tokens": round(float(state.get("tokens") or 0.0), 3),
            "capacity": round(self.capacity, 3),
            "enabled": self.enabled,
        }


class GracefulDegradation:
    def __init__(self, config=None):
        config = config or {}
        self.stale_cache_fallback_enabled = bool(config.get("search_stale_cache_fallback_enabled", True))

    def provider_unavailable_payload(self, provider, reason):
        return {
            "provider": str(provider or "").strip().lower(),
            "degraded": True,
            "reason": str(reason or "unavailable").strip().lower(),
        }


class HealthDashboard:
    def build_snapshot(self, providers, circuit_breaker, rate_limiter):
        entries = []
        for provider in sorted({str(item).strip().lower() for item in (providers or []) if str(item).strip()}):
            entries.append(
                {
                    "provider": provider,
                    "circuit": circuit_breaker.get_state(provider),
                    "rate_limiter": rate_limiter.snapshot(provider),
                }
            )
        return {"providers": entries, "generated_at": time.time()}

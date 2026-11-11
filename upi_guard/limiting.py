"""Atomic Redis sliding-window limiter; bounded in-process fallback for demos."""
import hashlib
import ipaddress
import threading
import time
import uuid
from collections import deque
from werkzeug.exceptions import ServiceUnavailable
from werkzeug.middleware.proxy_fix import ProxyFix


class TrustedProxy:
    def __init__(self, app, networks, hops):
        self.app = app
        self.networks = [ipaddress.ip_network(n.strip()) for n in networks if n.strip()]
        self.fixed = ProxyFix(app, x_for=hops, x_proto=hops, x_host=0, x_port=0, x_prefix=0)

    def __call__(self, environ, start_response):
        try:
            peer = ipaddress.ip_address(environ.get("REMOTE_ADDR", ""))
            trusted = any(peer in n for n in self.networks)
        except ValueError:
            trusted = False
        return (self.fixed if trusted else self.app)(environ, start_response)


class Limiter:
    LUA = """
    local t = redis.call('TIME')
    local now = tonumber(t[1])*1000 + math.floor(tonumber(t[2])/1000)
    redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now-ARGV[1])
    if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[2]) then return 0 end
    redis.call('ZADD', KEYS[1], now, ARGV[3])
    redis.call('PEXPIRE', KEYS[1], ARGV[1])
    return 1
    """

    def __init__(self, url=None):
        self.lock, self.buckets = threading.Lock(), {}
        self.redis = None
        if url:
            import redis
            self.redis = redis.Redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)

    def allowed(self, bucket, limit, seconds):
        key = "guard:rate:"+hashlib.sha256(bucket.encode()).hexdigest()
        if self.redis is not None:
            try:
                return bool(self.redis.eval(self.LUA, 1, key, seconds*1000, limit, uuid.uuid4().hex))
            except Exception as exc:
                raise ServiceUnavailable("Rate-limit service unavailable; retry later") from exc
        now = time.monotonic()
        with self.lock:
            if len(self.buckets) >= 10000:
                self.buckets = {k:v for k,v in self.buckets.items() if v[1] > now}
                if key not in self.buckets and len(self.buckets) >= 10000:
                    raise ServiceUnavailable("Rate-limit capacity reached")
            events, _ = self.buckets.setdefault(key, (deque(), now+seconds))
            while events and events[0] <= now-seconds: events.popleft()
            if len(events) >= limit: return False
            events.append(now)
            self.buckets[key] = (events, now+seconds)
            return True

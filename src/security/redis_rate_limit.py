"""Optional Redis-backed fixed-window rate limiter for multi-process API deployments."""
from __future__ import annotations
import time
class RedisRateLimiter:
    def __init__(self,url):
        try: import redis
        except ImportError as exc: raise RuntimeError("Install redis to use RedisRateLimiter") from exc
        self.client=redis.Redis.from_url(url,decode_responses=True)
    def allow(self,key,*,limit=10,window_seconds=60):
        bucket=int(time.time()//window_seconds); redis_key=f"smartgrid:rl:{key}:{bucket}"
        pipe=self.client.pipeline(); pipe.incr(redis_key); pipe.expire(redis_key,window_seconds+2)
        count,_=pipe.execute()
        return int(count)<=int(limit),max(0,int(window_seconds-(time.time()%window_seconds)))

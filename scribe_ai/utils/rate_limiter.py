#rate_limiter.py

import asyncio
import time

class RateLimiter:
    def __init__(self, max_rpm, period):
        self.max_calls=max_rpm
        self.period = period
        self.calls=[]
    
    async def wait(self):
        now = time.time()
        self.calls= [call for call in self.calls if now-call<self.period]
        if len(self.calls)>= self.max_calls:
            sleep_time=self.period-(now-self.calls[0])
        self.calls.append(time.time())
    async def __aenter__(self):
        await self.wait()
        return self
    async def __aexit__(self, exc_type, exc_value, exc_tb):
        pass
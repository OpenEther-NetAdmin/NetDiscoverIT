"""
Discovery Scheduler
Schedules periodic discovery runs
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)


class DiscoveryScheduler:
    """Schedules and runs periodic discoveries"""
    
    def __init__(self, config):
        self.config = config
        self.scan_interval = self._parse_interval(config.SCAN_INTERVAL)
        self._running = False
    
    def _parse_interval(self, interval: str) -> int:
        """Parse interval string to seconds"""
        interval = interval.lower().strip()
        
        if interval.endswith('h'):
            return int(interval[:-1]) * 3600
        elif interval.endswith('m'):
            return int(interval[:-1]) * 60
        elif interval.endswith('s'):
            return int(interval[:-1])
        else:
            # Default to hours
            return int(interval) * 3600
    
    async def run(self, discovery_callback: Callable[[], Awaitable[dict]]):
        """Run scheduler loop"""
        self._running = True
        logger.info(f"Scheduler started. Running discovery every {self.scan_interval}s")
        
        while self._running:
            try:
                # Run discovery
                result = await discovery_callback()
                
                logger.info(f"Scheduled discovery completed: {result}")
                
            except Exception as e:
                logger.error(f"Discovery error: {e}")
            
            # Wait for next interval
            await asyncio.sleep(self.scan_interval)
    
    def stop(self):
        """Stop the scheduler"""
        self._running = False
        logger.info("Scheduler stopped")
    
    async def run_at(self, callback: Callable[[], Awaitable[dict]], time: datetime):
        """Run callback at specific time"""
        now = datetime.utcnow()
        
        if time > now:
            wait_seconds = (time - now).total_seconds()
            logger.info(f"Waiting {wait_seconds}s until {time}")
            await asyncio.sleep(wait_seconds)
        
        return await callback()
    
    async def run_hourly(self, callback: Callable[[], Awaitable[dict]]):
        """Run callback every hour"""
        self._running = True
        
        while self._running:
            # Calculate next hour
            now = datetime.utcnow()
            next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            
            await self.run_at(callback, next_hour)
            
            # Then run every hour
            await asyncio.sleep(3600)
    
    async def run_daily(self, callback: Callable[[], Awaitable[dict]], hour: int = 2):
        """Run callback daily at specified hour (UTC)"""
        self._running = True
        
        while self._running:
            now = datetime.utcnow()
            
            # Calculate next run time
            if now.hour < hour:
                next_run = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            else:
                next_run = (now + timedelta(days=1)).replace(hour=hour, minute=0, second=0, microsecond=0)
            
            await self.run_at(callback, next_run)
            
            # Wait a bit to avoid tight loop
            await asyncio.sleep(60)

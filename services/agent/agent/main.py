"""
NetDiscoverIT Local Agent
Main entry point
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime

from fastapi import FastAPI
import uvicorn

from agent.collector import DeviceCollector
from agent.normalizer import ConfigNormalizer
from agent.sanitizer import ConfigSanitizer
from agent.vectorizer import DeviceVectorizer
from agent.uploader import VectorUploader
from agent.scheduler import DiscoveryScheduler
from agent.config import AgentConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create FastAPI app for agent"""
    app = FastAPI(title="NetDiscoverIT Local Agent")
    
    @app.get("/health")
    async def health():
        return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
    
    @app.get("/ready")
    async def ready():
        return {"status": "ready"}
    
    return app


class Agent:
    """Main agent orchestrator"""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.collector = DeviceCollector(config)
        self.normalizer = ConfigNormalizer(config)
        self.sanitizer = ConfigSanitizer()
        self.vectorizer = DeviceVectorizer(config)
        self.uploader = VectorUploader(config)
        self.scheduler = DiscoveryScheduler(config)
    
    async def run_discovery(self) -> dict:
        """Run a single discovery cycle"""
        logger.info("Starting discovery cycle")
        start_time = datetime.utcnow()
        
        # 1. Discover devices
        logger.info("Phase 1: Device discovery")
        devices = await self.collector.discover_devices()
        logger.info(f"Discovered {len(devices)} devices")
        
        # 2. Collect configs
        logger.info("Phase 2: Configuration collection")
        configs = {}
        for device in devices:
            try:
                config = await self.collector.get_config(device)
                configs[device['hostname']] = config
            except Exception as e:
                logger.error(f"Failed to get config for {device['hostname']}: {e}")
        
        # 3. Normalize to JSON
        logger.info("Phase 3: Configuration normalization")
        normalized = {}
        for hostname, config in configs.items():
            try:
                json_config = await self.normalizer.normalize(config)
                normalized[hostname] = json_config
            except Exception as e:
                logger.error(f"Failed to normalize config for {hostname}: {e}")
        
        # 4. Sanitize
        logger.info("Phase 4: PII sanitization")
        sanitized = {}
        for hostname, json_config in normalized.items():
            try:
                clean_config = self.sanitizer.sanitize(json_config)
                sanitized[hostname] = clean_config
            except Exception as e:
                logger.error(f"Failed to sanitize config for {hostname}: {e}")
        
        # 5. Generate vectors
        logger.info("Phase 5: Vector generation")
        vectors = []
        for hostname, clean_config in sanitized.items():
            try:
                device_vectors = await self.vectorizer.generate_vectors(clean_config)
                vectors.append({
                    'device_id': hostname,
                    'metadata': clean_config,
                    'vectors': device_vectors
                })
            except Exception as e:
                logger.error(f"Failed to generate vectors for {hostname}: {e}")
        
        # 6. Upload to cloud
        logger.info("Phase 6: Upload to cloud")
        if vectors:
            await self.uploader.upload_vectors(vectors)
        
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"Discovery complete in {elapsed:.2f}s")
        
        return {
            'devices_discovered': len(devices),
            'devices_processed': len(vectors),
            'elapsed_seconds': elapsed
        }


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="NetDiscoverIT Local Agent")
    parser.add_argument('--config', default='/app/config/agent.yaml', help='Config file path')
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    args = parser.parse_args()
    
    # Load config
    config = AgentConfig.from_file(args.config)
    logger.info(f"Starting NetDiscoverIT Agent v{config.VERSION}")
    
    agent = Agent(config)
    
    if args.once:
        # Run once
        result = await agent.run_discovery()
        logger.info(f"Discovery result: {result}")
    else:
        # Run scheduled
        logger.info(f"Starting scheduler with interval: {config.SCAN_INTERVAL}")
        await agent.scheduler.run(agent.run_discovery)


if __name__ == "__main__":
    asyncio.run(main())

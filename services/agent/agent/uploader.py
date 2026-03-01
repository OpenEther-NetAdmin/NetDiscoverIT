"""
Vector Uploader
Uploads vectors to cloud API
"""

import logging
from datetime import datetime
from typing import List, Dict

logger = logging.getLogger(__name__)


class VectorUploader:
    """Uploads device vectors to cloud API"""
    
    def __init__(self, config):
        self.config = config
        self.api_endpoint = config.API_ENDPOINT
        self.api_key = config.API_KEY
    
    async def upload_vectors(self, devices: List[Dict]) -> Dict:
        """Upload vector batch to cloud"""
        import httpx
        
        payload = {
            "batch_id": self._generate_batch_id(),
            "customer_id": self._get_customer_id(),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "devices": devices,
            "recommendations_requested": False
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        url = f"{self.api_endpoint}/api/v1/agent/vectors"
        
        logger.info(f"Uploading {len(devices)} devices to cloud")
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    logger.info(f"Upload successful: {response.json()}")
                    return response.json()
                else:
                    logger.error(f"Upload failed: {response.status_code} - {response.text}")
                    return {"error": f"HTTP {response.status_code}"}
                    
            except httpx.ConnectError as e:
                logger.error(f"Connection failed: {e}")
                return {"error": "connection_failed"}
            except Exception as e:
                logger.error(f"Upload error: {e}")
                return {"error": str(e)}
    
    async def upload_with_retry(self, devices: List[Dict], max_retries: int = 3) -> Dict:
        """Upload with retry logic"""
        import asyncio
        
        for attempt in range(max_retries):
            result = await self.upload_vectors(devices)
            
            if "error" not in result:
                return result
            
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(f"Retry {attempt + 1}/{max_retries} after {wait_time}s")
                await asyncio.sleep(wait_time)
        
        return {"error": "max_retries_exceeded"}
    
    async def fetch_recommendations(self, device_id: str) -> List[Dict]:
        """Fetch recommendations for a device"""
        import httpx
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }
        
        url = f"{self.api_endpoint}/api/v1/agent/recommendations?device_id={device_id}"
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=headers, timeout=30.0)
                
                if response.status_code == 200:
                    return response.json().get('recommendations', [])
                else:
                    logger.error(f"Recommendations fetch failed: {response.status_code}")
                    return []
                    
            except Exception as e:
                logger.error(f"Recommendations error: {e}")
                return []
    
    def _generate_batch_id(self) -> str:
        """Generate unique batch ID"""
        from uuid import uuid4
        return str(uuid4())
    
    def _get_customer_id(self) -> str:
        """Get customer ID from config"""
        # TODO: Implement proper customer ID management
        return "default-customer"

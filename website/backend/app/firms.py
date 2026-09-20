"""
NASA FIRMS API client.
"""
import requests
from typing import List, Dict, Optional
from datetime import datetime, date, timedelta
import logging

from .config import settings

logger = logging.getLogger(__name__)

# Disable URL logging to prevent key leakage
logging.getLogger("urllib3").setLevel(logging.WARNING)

class FIRMSClient:
    """NASA FIRMS API client with key redaction."""

    BASE_URL = "https://firms.modaps.eosdis.nasa.gov"

    def __init__(self):
        self.map_key = settings.NASA_FIRMS_MAP_KEY
        self.source = settings.FIRMS_SOURCE
        self.area = settings.FIRMS_AREA

    def _redact_url(self, url: str) -> str:
        """Redact MAP_KEY from URL for logging."""
        return url.replace(self.map_key, "***")

    def check_usage(self) -> Dict:
        """Check API key usage."""
        url = f"{self.BASE_URL}/mapserver/mapkey_status/?MAP_KEY={self.map_key}"
        logger.info(f"Checking usage: {self._redact_url(url)}")

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Usage check failed: {e}")
            return {"error": str(e)}

    def fetch_detections(
        self,
        day_range: int = 1,
        end_date: Optional[date] = None
    ) -> List[Dict]:
        """
        Fetch FIRMS detections for the specified date range.

        Args:
            day_range: Number of days to fetch (1-10 for area API)
            end_date: End date (defaults to today)

        Returns:
            List of detection dictionaries
        """
        if end_date is None:
            end_date = date.today() - timedelta(days=1)
        else:
            # FIRMS has ~1 day processing delay — never request today or future dates
            end_date = min(end_date, date.today() - timedelta(days=1))

        # FIRMS area API allows max 5 days per request regardless of source
        day_range = min(day_range, 5)

        # Build URL
        date_str = end_date.strftime("%Y-%m-%d")
        url = f"{self.BASE_URL}/api/area/csv/{self.map_key}/{self.source}/{self.area}/{day_range}/{date_str}"

        logger.info(f"Fetching: {self._redact_url(url)}")

        try:
            response = requests.get(url, timeout=60)
            response.raise_for_status()

            # Parse CSV
            lines = response.text.strip().split('\n')
            if len(lines) < 1:
                logger.warning("Empty response from FIRMS")
                return []

            header = lines[0].split(',')
            if len(lines) == 1:
                logger.info("No detections (header only)")
                return []

            # Check for error messages
            if "Invalid" in response.text or "not valid" in response.text:
                raise ValueError(f"FIRMS API error: {response.text[:200]}")

            # Parse rows
            detections = []
            for line in lines[1:]:
                values = line.split(',')
                if len(values) != len(header):
                    logger.warning(f"Skipping malformed row: {line}")
                    continue

                row = dict(zip(header, values))

                # Convert numeric fields
                try:
                    row['latitude'] = float(row['latitude'])
                    row['longitude'] = float(row['longitude'])
                    row['scan'] = float(row['scan'])
                    row['track'] = float(row['track'])
                    row['frp'] = float(row['frp'])
                    row['acq_time'] = int(row['acq_time'])

                    # Handle both column naming schemes
                    if 'brightness' in row:
                        row['brightness'] = float(row['brightness'])
                    elif 'bright_ti4' in row:
                        row['bright_ti4'] = float(row['bright_ti4'])

                    if 'bright_t31' in row:
                        row['bright_t31'] = float(row['bright_t31'])
                    elif 'bright_ti5' in row:
                        row['bright_ti5'] = float(row['bright_ti5'])

                    # Type field (may not exist in NRT)
                    if 'type' in row and row['type']:
                        row['type'] = int(row['type'])

                    detections.append(row)
                except (ValueError, KeyError) as e:
                    logger.warning(f"Skipping row with parse error: {e}")
                    continue

            logger.info(f"Fetched {len(detections)} detections")
            return detections

        except requests.RequestException as e:
            logger.error(f"FIRMS request failed: {e}")
            raise

    def fetch_date_range(
        self,
        start_date: date,
        end_date: date,
        max_days_per_request: int = 5  # FIRMS area API max is 5 days per request
    ) -> List[Dict]:
        """
        Fetch detections across a date range, chunking requests as needed.

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            max_days_per_request: Maximum days per API call (FIRMS limit is 10)

        Returns:
            List of all detections
        """
        all_detections = []
        current_end = end_date

        while current_end >= start_date:
            # Calculate days for this chunk
            days_available = (current_end - start_date).days + 1
            days_to_fetch = min(days_available, max_days_per_request)

            # Fetch chunk
            detections = self.fetch_detections(
                day_range=days_to_fetch,
                end_date=current_end
            )
            all_detections.extend(detections)

            # Walk end pointer back by the number of days just fetched
            current_end -= timedelta(days=days_to_fetch)

        logger.info(f"Total detections across range: {len(all_detections)}")
        return all_detections

# Global client instance
firms_client = FIRMSClient()

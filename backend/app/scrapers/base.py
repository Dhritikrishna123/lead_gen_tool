from abc import ABC, abstractmethod
from typing import List, Dict

class BaseScraper(ABC):
    """
    Abstract Base Class for all Lead Generation Scrapers.
    Enforces a consistent interface for executing searches.
    """
    
    @abstractmethod
    def scrape(self, intent: str, lead_count: int, job_id: int) -> List[Dict]:
        """
        Execute the scraper.
        
        Args:
            intent (str): The search keywords/prompt.
            lead_count (int): Maximum number of leads requested.
            job_id (int): The current job ID for logging/tracking.
            
        Returns:
            List[Dict]: A normalized list of lead dictionaries.
        """
        pass

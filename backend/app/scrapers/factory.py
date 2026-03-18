from app.scrapers.base import BaseScraper
from app.scrapers.upwork import UpworkScraper
from app.scrapers.freelancer import FreelancerScraper

class ScraperFactory:
    """
    Factory class to dynamically instantiate and return the correct scraper instance.
    """
    
    @staticmethod
    def get_scraper(source: str) -> BaseScraper:
        source_key = source.lower().strip()
        if source_key == "upwork":
            return UpworkScraper()
        elif source_key == "freelancer":
            return FreelancerScraper()
        else:
            raise ValueError(f"Unknown scraper source requested: {source_key}")

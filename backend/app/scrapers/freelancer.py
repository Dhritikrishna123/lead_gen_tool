import asyncio
import urllib.parse
from typing import List, Dict
import logging

from bs4 import BeautifulSoup
import zendriver as zd

logger = logging.getLogger(__name__)

# Base URL for freelancer job search
BASE_URL = "https://www.freelancer.com/jobs/"

class FreelancerScraper:
    """
    Scraper that navigates Freelancer.com using Zendriver and extracts job postings based on search intent.
    Currently hardcoded to run headless=False with a 10-second sleep for manual Cloudflare bypass locally.
    """

    async def _run_scraper(self, intent: str, lead_count: int) -> List[Dict]:
        params = {
            "keyword": intent, # Injecting the dynamic search intent
            "fixed": "true",
            "hourly": "true",
            "contest": "true",
            "local": "true",
            "featured": "true",
            "recruiter": "true",
            "fulltime": "true",
            "languages": "en,es,de,fr,pt",
            "status": "all"
        }

        query_string = urllib.parse.urlencode(params)
        url = f"{BASE_URL}?{query_string}"

        logger.info(f"Navigating to Freelancer: {url}")
        
        browser = await zd.start(headless=False)
        try:
            page = await browser.get(url)

            logger.info("Waiting 10 seconds for manual Cloudflare check bypass...")
            await asyncio.sleep(10)

            # Wait an extra moment to ensure the page is fully loaded
            await asyncio.sleep(3)

            logger.info("Extracting HTML...")
            html_content = await page.get_content()
            
            logger.info("Parsing with BeautifulSoup...")
            soup = BeautifulSoup(html_content, "html.parser")
            
            job_cards = soup.find_all("div", class_="JobSearchCard-item")
            logger.info(f"Found {len(job_cards)} job cards on Freelancer.")

            jobs_data = []
            
            for card in job_cards[:lead_count]:
                # Title & URL
                title_tag = card.find("a", class_="JobSearchCard-primary-heading-link")
                if not title_tag:
                    continue
                    
                title = title_tag.get_text(strip=True)
                url = "https://www.freelancer.com" + title_tag.get("href", "")
                
                # Description
                desc_tag = card.find("p", class_="JobSearchCard-primary-description")
                description = desc_tag.get_text(strip=True) if desc_tag else "N/A"
                
                # Skills
                skills_con = card.find("div", class_="JobSearchCard-primary-tags")
                skills = []
                if skills_con:
                    skill_tags = skills_con.find_all("a", class_="JobSearchCard-primary-tagsLink")
                    skills = [s.get_text(strip=True) for s in skill_tags]
                    
                # Time Left
                days_tag = card.find("span", class_="JobSearchCard-primary-heading-days")
                time_left = days_tag.get_text(strip=True) if days_tag else "N/A"
                
                # Price
                price_tag = card.find("div", class_="JobSearchCard-secondary-price")
                price = "N/A"
                if price_tag:
                    lines = [line.strip() for line in price_tag.stripped_strings]
                    if lines:
                        price = " ".join(lines)
                        
                # Bids
                bids_tag = card.find("div", class_="JobSearchCard-secondary-entry")
                bids = bids_tag.get_text(strip=True) if bids_tag else "N/A"
                
                jobs_data.append({
                    "title": title,
                    "url": url,
                    "price": price,
                    "bids": bids,
                    "time_left": time_left,
                    "description": description,
                    "skills": ", ".join(skills)
                })

            return jobs_data

        finally:
            await browser.stop()

    def scrape(self, intent: str, lead_count: int, job_id: int) -> List[Dict]:
        """Synchronous wrapper to be called securely from Celery."""
        return asyncio.run(self._run_scraper(intent, lead_count))

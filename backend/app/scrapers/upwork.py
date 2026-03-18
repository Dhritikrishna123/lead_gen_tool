import asyncio
import urllib.parse
from typing import List, Dict
import logging
import random
import traceback

from bs4 import BeautifulSoup
import zendriver as zd

from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://www.upwork.com/nx/search/jobs/"


class UpworkScraper(BaseScraper):
    """
    Scraper that navigates Upwork using Zendriver and extracts job postings based on search intent.
    Implements pagination and demo safety limits.
    """

    async def _run_scraper(self, intent: str, lead_count: int) -> List[Dict]:
        jobs_data = []
        max_pages = 10
        
        # Enforce safety cap of 500 leads max
        actual_lead_count = min(lead_count, 500)
        
        browser = await zd.start(headless=False)
        try:
            for page_num in range(1, max_pages + 1):
                params = {
                    "q": intent,
                    "sort": "relevance+desc",
                    "per_page": 50,
                    "page": page_num
                }

                query_string = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
                url = f"{BASE_URL}?{query_string}"

                logger.info(f"Navigating to Upwork Page {page_num}: {url}")
                page = await browser.get(url)

                if page_num == 1:
                    logger.info("Waiting 10 seconds for initial manual Cloudflare check bypass...")
                    await asyncio.sleep(10)
                else:
                    delay = random.uniform(3, 6)
                    logger.info(f"Page {page_num}: Sleeping for {delay:.2f}s to avoid bot detection...")
                    await asyncio.sleep(delay)

                logger.info("Extracting HTML...")
                html_content = await page.get_content()
                
                logger.info("Parsing with BeautifulSoup...")
                soup = BeautifulSoup(html_content, "html.parser")
                
                job_tiles = soup.find_all("article", class_=lambda x: x and "job-tile" in x)
                
                # Fallback if standard classes change
                if not job_tiles:
                    job_tiles = soup.find_all("section", {"data-test": "job-tile-list"})
                    if job_tiles:
                        job_tiles = job_tiles[0].find_all("article")
                        
                logger.info(f"Found {len(job_tiles)} job tiles on Page {page_num}.")
                
                if not job_tiles:
                    logger.info("No more job tiles found. Ending search.")
                    break
                
                for tile in job_tiles:
                    if len(jobs_data) >= actual_lead_count:
                        break
                        
                    try:
                        # Title
                        title_element = tile.find("h2", class_=lambda x: x and "job-tile-title" in x)
                        if not title_element:
                            title_element = tile.find("h2") # fallback
                        title = title_element.get_text(strip=True) if title_element else "N/A"
                        
                        # Link
                        link_element = title_element.find("a") if title_element else None
                        link = "https://www.upwork.com" + link_element["href"] if link_element and link_element.has_attr("href") else "N/A"
                        
                        # Details
                        job_type, experience_level, budget, duration, workload = "N/A", "N/A", "N/A", "N/A", "N/A"
                        
                        details_list = tile.find("ul", {"data-test": "JobInfo"})
                        if details_list:
                            type_li = details_list.find("li", {"data-test": "job-type-label"})
                            if type_li: job_type = " ".join(type_li.stripped_strings)
                            
                            exp_li = details_list.find("li", {"data-test": "experience-level"})
                            if exp_li: experience_level = " ".join(exp_li.stripped_strings)
                            
                            budget_li = details_list.find("li", {"data-test": ["is-fixed-price", "budget", "hourly-rate-label"]})
                            if budget_li: budget = " ".join(budget_li.stripped_strings)
                            
                            duration_li = details_list.find("li", {"data-test": "duration-label"})
                            if duration_li: duration = " ".join(duration_li.stripped_strings)
                            
                            workload_li = details_list.find("li", {"data-test": ["workload", "workload-label"]})
                            if workload_li: workload = " ".join(workload_li.stripped_strings)
                        
                        # Description
                        desc_container = tile.find("div", {"data-test": "UpCLineClamp JobDescription"})
                        if desc_container:
                            desc_text = " ".join(desc_container.stripped_strings)
                        else:
                            desc_text = "N/A"
                        
                        # Skills
                        skills_container = tile.find("div", {"data-test": "TokenClamp JobAttrs"})
                        skills = []
                        if skills_container:
                            skill_buttons = skills_container.find_all("button", {"data-test": "token"})
                            skills = [btn.get_text(strip=True) for btn in skill_buttons]
                            
                        jobs_data.append({
                            "title": title,
                            "url": link,
                            "job_type": job_type,
                            "experience_level": experience_level,
                            "budget": budget,
                            "duration": duration,
                            "workload": workload,
                            "description": desc_text,
                            "skills": ", ".join(skills)
                        })
                        
                    except Exception as e:
                        logger.warning(f"Failed to parse an Upwork job tile. Skipping. Error: {e}")
                        continue
                        
                if len(jobs_data) >= actual_lead_count:
                    logger.info(f"Reached cap of {actual_lead_count} leads.")
                    break

            return jobs_data

        except Exception as e:
            logger.error(f"Critical error during Upwork scraping: {e}")
            logger.debug(traceback.format_exc())
            return jobs_data
        finally:
            await browser.stop()

    def scrape(self, intent: str, lead_count: int, job_id: int) -> List[Dict]:
        """Synchronous wrapper to be called securely from Celery."""
        return asyncio.run(self._run_scraper(intent, lead_count))

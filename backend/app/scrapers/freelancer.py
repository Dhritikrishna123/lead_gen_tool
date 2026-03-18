import asyncio
from typing import List, Dict
import logging
import random
import traceback

from bs4 import BeautifulSoup
import zendriver as zd

from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://www.freelancer.com/jobs/"


class FreelancerScraper(BaseScraper):

    async def _set_angular_input(self, page, selector: str, value: str) -> bool:
        """
        Sets value on an Angular-bound input field and fires all required
        events so Angular's ngModel / reactive forms actually pick it up.
        """
        js = """
            (function(selector, value) {
                var el = document.querySelector(selector);
                if (!el) return false;

                el.focus();

                var nativeSetter = Object.getOwnPropertyDescriptor(
                    HTMLInputElement.prototype, 'value'
                ).set;
                nativeSetter.call(el, value);

                el.dispatchEvent(new Event('input',  { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));

                return true;
            })('%s', '%s');
        """ % (selector, value.replace("'", "\\'"))

        result = await page.evaluate(js)
        return bool(result)

    async def _run_scraper(self, intent: str, lead_count: int) -> List[Dict]:

        jobs_data: List[Dict] = []
        actual_lead_count = min(lead_count, 500)

        browser = await zd.start(headless=False)

        try:
            page = await browser.get(BASE_URL)
            await page
            await asyncio.sleep(3)

            logger.info("Waiting for search input...")
            search_box = await page.select("#keyword-input", timeout=15)
            if not search_box:
                logger.error("Search box not found!")
                return jobs_data

            await search_box.click()
            await asyncio.sleep(0.3)

            success = await self._set_angular_input(page, "#keyword-input", intent)
            if not success:
                logger.error("Failed to set input value via JS!")
                return jobs_data

            logger.info(f"Set search keyword: {intent}")
            await asyncio.sleep(0.5)

            actual_value = await page.evaluate(
                "document.querySelector('#keyword-input').value"
            )
            logger.info(f"Input field value confirmed: '{actual_value}'")

            if not actual_value or actual_value.strip() == "":
                logger.error("Input field is still empty after JS injection!")
                return jobs_data

            search_btn = await page.select("#search-submit", timeout=10)
            if not search_btn:
                logger.error("Search button not found!")
                return jobs_data

            await search_btn.click()
            logger.info("Search button clicked, waiting for results...")

            first_card = await page.select(".JobSearchCard-item", timeout=20)
            if not first_card:
                logger.error("No job cards appeared after search!")
                return jobs_data

            await asyncio.sleep(2)

            max_pages = (actual_lead_count // 20) + 2

            for page_num in range(1, max_pages + 1):

                logger.info(f"Scraping page {page_num}...")

                # Scroll to trigger lazy loading
                for _ in range(3):
                    await page.evaluate(
                        "window.scrollBy(0, document.body.scrollHeight)"
                    )
                    await asyncio.sleep(1)

                html = await page.get_content()
                soup = BeautifulSoup(html, "html.parser")

                job_cards = soup.find_all("div", class_="JobSearchCard-item")
                logger.info(f"Found {len(job_cards)} jobs on page {page_num}")

                if not job_cards:
                    logger.warning("No job cards found, stopping.")
                    break

                for card in job_cards:

                    if len(jobs_data) >= actual_lead_count:
                        break

                    try:
                        title_tag = card.find(
                            "a",
                            class_="JobSearchCard-primary-heading-link"
                        )
                        if not title_tag:
                            continue

                        title = title_tag.get_text(strip=True)
                        link_url = (
                            "https://www.freelancer.com"
                            + title_tag.get("href", "")
                        )

                        desc_tag = card.find(
                            "p",
                            class_="JobSearchCard-primary-description"
                        )
                        description = (
                            desc_tag.get_text(strip=True)
                            if desc_tag else "N/A"
                        )

                        skills_container = card.find(
                            "div",
                            class_="JobSearchCard-primary-tags"
                        )
                        skills = []
                        if skills_container:
                            skill_tags = skills_container.find_all(
                                "a",
                                class_="JobSearchCard-primary-tagsLink"
                            )
                            skills = [
                                s.get_text(strip=True) for s in skill_tags
                            ]

                        days_tag = card.find(
                            "span",
                            class_="JobSearchCard-primary-heading-days"
                        )
                        time_left = (
                            days_tag.get_text(strip=True)
                            if days_tag else "N/A"
                        )

                        price_tag = card.find(
                            "div",
                            class_="JobSearchCard-secondary-price"
                        )
                        price = "N/A"
                        if price_tag:
                            lines = [
                                line.strip()
                                for line in price_tag.stripped_strings
                            ]
                            if lines:
                                price = " ".join(lines)

                        bids_tag = card.find(
                            "div",
                            class_="JobSearchCard-secondary-entry"
                        )
                        bids = (
                            bids_tag.get_text(strip=True)
                            if bids_tag else "N/A"
                        )

                        jobs_data.append({
                            "title": title,
                            "url": link_url,
                            "price": price,
                            "bids": bids,
                            "time_left": time_left,
                            "description": description,
                            "skills": ", ".join(skills)
                        })

                    except Exception as e:
                        logger.warning(f"Failed parsing job card: {e}")
                        continue

                if len(jobs_data) >= actual_lead_count:
                    logger.info(f"Reached lead cap: {actual_lead_count}")
                    break

                # --- Pagination ---
                # Scroll to bottom so the footer/pagination is rendered
                await page.evaluate(
                    "window.scrollTo(0, document.body.scrollHeight)"
                )
                await asyncio.sleep(1)

                # The next button is identified by data-pagination-next-button attribute
                next_btn = await page.select(
                    "a[data-pagination-next-button]",
                    timeout=5
                )

                if not next_btn:
                    logger.info("No next button found — reached last page.")
                    break

                # Check if the next button is disabled (on last page it may have
                # no href or point to the same page)
                next_href = await page.evaluate(
                    "document.querySelector('a[data-pagination-next-button]')?.href"
                )
                current_url = page.url
                if not next_href or next_href == current_url:
                    logger.info("Next button href matches current page — last page reached.")
                    break

                logger.info(f"Clicking next page, navigating to: {next_href}")
                await next_btn.click()

                await asyncio.sleep(random.uniform(3, 5))

                # Wait for new job cards to load after pagination
                await page.select(".JobSearchCard-item", timeout=15)

            return jobs_data

        except Exception as e:
            logger.error(f"Critical scraping error: {e}")
            logger.debug(traceback.format_exc())
            return jobs_data

        finally:
            await browser.stop()

    def scrape(self, intent: str, lead_count: int, job_id: int) -> List[Dict]:
        """
        Runs the async scraper synchronously.
        Handles already-running event loops (FastAPI, Django async, etc).
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self._run_scraper(intent, lead_count)
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self._run_scraper(intent, lead_count)
                )
        except RuntimeError:
            return asyncio.run(self._run_scraper(intent, lead_count))
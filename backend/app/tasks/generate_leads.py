import logging
import traceback
from datetime import datetime, timezone
import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.tasks.celery_app import celery_app
from app.models import Job, Lead
from app.scrapers.factory import ScraperFactory

logger = logging.getLogger(__name__)

# Basic synchronous engine and session factory for the Celery worker
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@celery_app.task(bind=True, name="app.tasks.generate_leads")
def generate_leads_task(self, job_id: int, keywords: list = None, sources: list = None):
    """
    Celery task that manages the lifecycle of a lead generation job (QUEUED -> PROCESSING -> COMPLETED/FAILED).
    """
    db = SessionLocal()
    try:
        # 1. Fetch Job from DB
        job = db.get(Job, job_id)
        if not job:
            logger.error(f"Job {job_id} not found in database.")
            return

        # Idempotency Guard: Do not re-process terminated or already processed jobs 
        if job.status in ["completed", "failed", "cancelled"]:
            logger.warning(f"Job {job_id} is already in state '{job.status}'. Exiting to prevent duplicate execution.")
            return
            
        # 2. Transition job -> PROCESSING (0%)
        job.status = "processing"
        job.started_at = datetime.now(timezone.utc)
        job.progress = 0
        db.commit()

        # Cancellation Guard
        db.refresh(job)
        if job.status == "cancelled":
            logger.info(f"Job {job_id} was cancelled. Halting execution.")
            return

        # 3. Call Scrapers Sequentially
        try:
            intent = " ".join(keywords) if keywords else "software developer"
            
            allowed_sources = [s.lower() for s in sources] if sources else ["upwork", "freelancer"]
            if not allowed_sources:
                allowed_sources = ["upwork", "freelancer"]

            logger.info(f"Job {job_id} gathering {job.lead_count} total leads from sources: {allowed_sources} with intent: '{intent}'")

            # Pre-load existing URLs to avoid duplicate entries in PostgreSQL
            seen_urls = set(db.scalars(select(Lead.source_url).where(Lead.job_id == job.id)).all())

            # Progress Milestone 1: Initialization complete
            job.progress = 10
            db.commit()

            new_leads = []

            # Process Upwork
            if "upwork" in allowed_sources:
                job.progress = 25
                db.commit()
                
                # Base fair share, plus remainder if any
                upwork_quota = (job.lead_count // len(allowed_sources)) + (1 if job.lead_count % len(allowed_sources) > 0 else 0)
                logger.info(f"Job {job_id} starting Upwork scraping with target quota {upwork_quota}...")
                
                upwork_scraper = ScraperFactory.get_scraper("upwork")
                upwork_jobs_data = upwork_scraper.scrape(intent=intent, lead_count=upwork_quota, job_id=job.id)

                for jd in upwork_jobs_data:
                    if jd['url'] in seen_urls:
                        continue
                    seen_urls.add(jd['url'])
                    
                    description_block = (
                        f"Job Type: {jd['job_type']}\n"
                        f"Experience Level: {jd['experience_level']}\n"
                        f"Budget: {jd['budget']}\n"
                        f"Duration: {jd['duration']}\n"
                        f"Workload: {jd['workload']}\n"
                        f"Skills: {jd['skills']}\n"
                        f"---\n"
                        f"{jd['description']}"
                    )
                    new_leads.append(Lead(
                        job_id=job.id, name="Upwork User", company="Upwork",
                        title=jd["title"], source_url=jd["url"],
                        description=description_block, confidence=0.85
                    ))

            # Process Freelancer
            if "freelancer" in allowed_sources:
                job.progress = 50
                db.commit()
                
                # Assign the remaining balance of leads needed
                fl_quota = job.lead_count - len(new_leads)
                
                if fl_quota > 0:
                    logger.info(f"Job {job_id} starting Freelancer scraping for remaining {fl_quota} leads...")
                    freelancer_scraper = ScraperFactory.get_scraper("freelancer")
                    freelancer_jobs_data = freelancer_scraper.scrape(intent=intent, lead_count=fl_quota, job_id=job.id)

                for jd in freelancer_jobs_data:
                    if jd['url'] in seen_urls:
                        continue
                    seen_urls.add(jd['url'])
                    
                    description_block = (
                        f"Price: {jd['price']}\n"
                        f"Bids: {jd['bids']}\n"
                        f"Time Left: {jd['time_left']}\n"
                        f"Skills: {jd['skills']}\n"
                        f"---\n"
                        f"{jd['description']}"
                    )
                    new_leads.append(Lead(
                        job_id=job.id, name="Freelancer User", company="Freelancer",
                        title=jd["title"], source_url=jd["url"],
                        description=description_block, confidence=0.85
                    ))
                    
                    if len(new_leads) >= job.lead_count:
                        break
            
            # Progress Milestone 3: Injection Phase
            job.progress = 75
            db.commit()
            logger.info(f"Job {job_id} committing {len(new_leads)} total new leads to DB.")
            
            if new_leads:
                db.add_all(new_leads)
                
            db.commit()

            # Update to 100%
            job.progress = 100
            job.status = "completed"
            
        except Exception as e:
            # Catch all generic exceptions
            logger.error(f"Job {job_id} failed with error: {str(e)}")
            logger.debug(traceback.format_exc())
            job.status = "failed"
            job.error_message = str(e)

        # 4. Set completed_at and persist transitions
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

    except Exception as exc:
        logger.error(f"Critical error in task {self.request.id}: {exc}")
        db.rollback()
        raise exc
    finally:
        db.close()

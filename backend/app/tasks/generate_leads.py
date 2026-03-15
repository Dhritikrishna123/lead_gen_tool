import logging
import traceback
from datetime import datetime, timezone
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.tasks.celery_app import celery_app
from app.models.models import Job, Lead

logger = logging.getLogger(__name__)

# Basic synchronous engine and session factory for the Celery worker
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

from app.scrapers.upwork import UpworkScraper
from app.scrapers.freelancer import FreelancerScraper


@celery_app.task(bind=True, name="app.tasks.generate_leads")
def generate_leads_task(self, job_id: int):
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
            
        # 2. Transition job -> PROCESSING
        job.status = "processing"
        job.started_at = datetime.now(timezone.utc)
        job.progress = 0
        db.commit()

        # Cancellation Guard: Check if the job was cancelled just before processing began
        db.refresh(job)
        if job.status == "cancelled":
            logger.info(f"Job {job_id} was cancelled. Halting execution.")
            return

        # 3. Call Scrapers Sequentially
        try:
            # Allocate target quotas
            upwork_quota = max(1, job.lead_count // 2)
            freelancer_quota = job.lead_count - upwork_quota

            logger.info(f"Job {job_id} allocating {upwork_quota} to Upwork and {freelancer_quota} to Freelancer.")

            # Upwork
            upwork_scraper = UpworkScraper()
            upwork_jobs_data = upwork_scraper.scrape(intent=job.intent, lead_count=upwork_quota, job_id=job.id)

            # Freelancer
            freelancer_scraper = FreelancerScraper()
            freelancer_jobs_data = freelancer_scraper.scrape(intent=job.intent, lead_count=freelancer_quota, job_id=job.id)

            # Insert Upwork Leads
            for jd in upwork_jobs_data:
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
                db.add(Lead(
                    job_id=job.id, name="Upwork User", company="Upwork",
                    title=jd["title"], source_url=jd["url"],
                    description=description_block, confidence=0.85
                ))

            # Insert Freelancer Leads
            for jd in freelancer_jobs_data:
                description_block = (
                    f"Price: {jd['price']}\n"
                    f"Bids: {jd['bids']}\n"
                    f"Time Left: {jd['time_left']}\n"
                    f"Skills: {jd['skills']}\n"
                    f"---\n"
                    f"{jd['description']}"
                )
                db.add(Lead(
                    job_id=job.id, name="Freelancer User", company="Freelancer",
                    title=jd["title"], source_url=jd["url"],
                    description=description_block, confidence=0.85
                ))
            
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

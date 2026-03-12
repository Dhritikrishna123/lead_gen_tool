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

        # 3. Call Upwork Scraper
        try:
            scraper = UpworkScraper()
            jobs_data = scraper.scrape(intent=job.intent, lead_count=job.lead_count, job_id=job.id)

            for jd in jobs_data:
                # Combine dynamic payload facts into standard DB text wrapper
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
                
                new_lead = Lead(
                    job_id=job.id,
                    name="Upwork User",
                    email=None,
                    company="Upwork",
                    title=jd["title"],
                    source_url=jd["url"],
                    description=description_block,
                    confidence=0.85
                )
                db.add(new_lead)
            
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

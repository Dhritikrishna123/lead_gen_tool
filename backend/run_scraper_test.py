import sys
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import Job, Lead
from app.tasks.generate_leads import generate_leads_task

# Set up logging to console
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def test_scraper_integration():
    db = SessionLocal()
    try:
        # 2. Create a dummy test job
        new_job = Job(
            prompt="Find Java developers on freelancer or upwork",
            lead_count=300,
            status="pending"
        )
        db.add(new_job)
        db.commit()
        db.refresh(new_job)
        
        logger.info(f"Created test job '{new_job.id}' with prompt '{new_job.prompt}'")
        
        # 3. Trigger the Celery task synchronously
        logger.info("Starting generate_leads_task execution (Browser will open)...")
        generate_leads_task(job_id=new_job.id, keywords=["python", "developer"], sources=["upwork", "freelancer"])
        
        # 4. Verify results
        if new_job.error_message:
            logger.error(f"Job Error: {new_job.error_message}")
            
        leads = db.query(Lead).filter(Lead.job_id == new_job.id).all()
        logger.info(f"Found {len(leads)} leads in database for job {new_job.id}:")
        for lead in leads:
            logger.info(f"- [{lead.title}] {lead.source_url}")
            
    finally:
        db.close()

if __name__ == "__main__":
    test_scraper_integration()

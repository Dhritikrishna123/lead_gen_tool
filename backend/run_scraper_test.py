import sys
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.models import Job, Lead, User
from app.auth.security import get_password_hash
from app.tasks.generate_leads import generate_leads_task

# Set up logging to console
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def test_scraper_integration():
    db = SessionLocal()
    try:
        # 1. Grab any User or create a temporary isolated one
        user = db.query(User).first()
        if not user:
            user = User(id=99999, email="upwork_testing_isolation@example.com", hashed_password=get_password_hash("testpass"), is_active=True)
            db.add(user)
            db.commit()
            db.refresh(user)

        # 2. Create a dummy test job linked to the user
        new_job = Job(
            user_id=user.id,
            prompt="Find python developers on freelancer or upwork",
            lead_count=3,
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
        if job.error_message:
            logger.error(f"Job Error: {job.error_message}")
            
        leads = db.query(Lead).filter(Lead.job_id == job.id).all()
        logger.info(f"Found {len(leads)} leads in database for job {job.id}:")
        for lead in leads:
            logger.info(f"- [{lead.title}] {lead.source_url}")
            
    finally:
        db.close()

if __name__ == "__main__":
    test_scraper_integration()

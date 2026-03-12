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
        job = Job(user_id=user.id, intent="python developer", lead_count=3)
        db.add(job)
        db.commit()
        db.refresh(job)
        
        logger.info(f"Created test job '{job.id}' with intent '{job.intent}'")

        # 3. Run the Celery task logic synchronously to test integration
        logger.info("Starting generate_leads_task execution (Browser will open)...")
        generate_leads_task(job.id)
        
        # 4. Verify results
        db.refresh(job)
        logger.info(f"Job Status: {job.status}")
        logger.info(f"Job Progress: {job.progress}%")
        
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

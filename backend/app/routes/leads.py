from typing import List
import csv
import io

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.schemas.schemas import JobCreate, JobResponse, LeadResponse
from app.models import Job, Lead
from app.database import get_db
from app.tasks.generate_leads import generate_leads_task
from app.services.ai_engine import parse_prompt

router = APIRouter()


@router.post("/generate", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_leads(
    job_in: JobCreate,
    db: Session = Depends(get_db)
):
    """Queue a new lead generation job."""
    # Run the prompt through Gemini to extract logic targets
    parsed_data = await parse_prompt(job_in.prompt)
    keywords = parsed_data.get("keywords", [])
    sources = parsed_data.get("sources")

    new_job = Job(
        prompt=job_in.prompt,
        lead_count=job_in.lead_count,
        status="pending"
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)
    
    # Process scraping jobs asynchronously via Celery
    generate_leads_task.delay(new_job.id, keywords, sources)

    return new_job


from datetime import datetime, timezone

@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job_status(job_id: int, db: Session = Depends(get_db)):
    """Poll the status of a lead-generation job."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    
    return job


@router.get("/jobs/{job_id}/results", response_model=List[LeadResponse])
async def get_job_results(job_id: int, skip: int = 0, limit: int = 1000, db: Session = Depends(get_db)):
    """Retrieve the scraped leads for a completed job."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        
    if job.status != "completed":
        return []
        
    stmt = select(Lead).where(Lead.job_id == job_id).offset(skip).limit(limit)
    leads = db.execute(stmt).scalars().all()
    
    return leads


@router.get("/jobs/{job_id}/export")
async def export_job_results(job_id: int, db: Session = Depends(get_db)):
    """Export the scraped leads as a CSV file."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        
    stmt = select(Lead).where(Lead.job_id == job_id)
    leads = db.execute(stmt).scalars().all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Headers
    writer.writerow(["Lead Name", "Job Board", "Job Title", "Source URL", "Match Confidence", "Full Description"])
    
    for lead in leads:
        writer.writerow([
            lead.name,
            lead.company,
            lead.title,
            lead.source_url,
            lead.confidence,
            lead.description
        ])
        
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=leadgen_job_{job_id}.csv"}
    )




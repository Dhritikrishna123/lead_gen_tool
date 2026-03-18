import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import Job, Lead
from app.config import settings
from main import app

# For testing, we append `_test` to the database name so we don't accidentally
# drop all production tables when running `pytest`.
original_db = settings.DATABASE_URL.split("/")[-1]
TEST_SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL.replace(original_db, f"{original_db}_test")
engine = create_engine(TEST_SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(scope="module")
def setup_database():
    """
    Setup the isolated test database.
    """
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    # Populate dummy data
    db = TestingSessionLocal()
    
    # Create variables to share IDs back to the test suite
    test_state = {}
    
    try:
        dummy_job = Job(prompt="Find sales leads", lead_count=50, status="completed")
        db.add(dummy_job)
        db.commit()
        db.refresh(dummy_job)
        
        dummy_lead1 = Lead(job_id=dummy_job.id, name="Alice CEO", email="alice@test.com", confidence=0.95)
        dummy_lead2 = Lead(job_id=dummy_job.id, name="Bob CTO", email="bob@test.com", confidence=0.88)
        db.add_all([dummy_lead1, dummy_lead2])
        db.commit()
        
        test_state["job_id"] = dummy_job.id
    finally:
        db.close()
        
    yield test_state
    
    # Teardown
    Base.metadata.drop_all(bind=engine)


@patch("app.routes.leads.generate_leads_task.delay")
@patch("app.routes.leads.parse_prompt", new_callable=AsyncMock)
def test_generate_leads(mock_parse, mock_delay, setup_database):
    mock_parse.return_value = {"keywords": ["career", "ops"], "sources": []}
    mock_delay.return_value = None

    response = client.post(
        "/api/leads/generate",
        json={"prompt": "Find career ops", "lead_count": 50},
    )
    assert response.status_code == 202
    data = response.json()
    assert data["prompt"] == "Find career ops"
    assert data["lead_count"] == 50
    assert data["status"] == "pending"
    assert data["progress"] == 0
    assert "id" in data


def test_get_job_status_existing(setup_database):
    # Fetch the previously populated dummy completed job
    job_id = setup_database["job_id"]
    response = client.get(f"/api/leads/jobs/{job_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == job_id
    assert data["prompt"] == "Find sales leads"
    assert data["status"] == "completed"


def test_get_job_not_found(setup_database):
    response = client.get("/api/leads/jobs/99999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def test_get_job_results_populated(setup_database):
    # Fetch results for the pre-populated sales job
    job_id = setup_database["job_id"]
    response = client.get(f"/api/leads/jobs/{job_id}/results")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2
    
    names = [lead["name"] for lead in data]
    assert "Alice CEO" in names
    assert "Bob CTO" in names

@patch("app.routes.leads.generate_leads_task.delay")
@patch("app.routes.leads.parse_prompt", new_callable=AsyncMock)
def test_get_job_results_empty(mock_parse, mock_delay, setup_database):
    mock_parse.return_value = {"keywords": ["growth", "roles"], "sources": []}
    mock_delay.return_value = None

    # Create a new pending job 
    create_response = client.post(
        "/api/leads/generate",
        json={"prompt": "Find growth roles", "lead_count": 5},
    )
    job_id = create_response.json()["id"]

    # Now fetch results (should be empty since no leads are generated for a pending job)
    response = client.get(f"/api/leads/jobs/{job_id}/results")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0




"""API test fixtures. All require a reachable, migrated database."""

from __future__ import annotations

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests._env import db_reachable, provider_available

requires_db = pytest.mark.skipif(not db_reachable(), reason="DATABASE_URL not reachable")
requires_provider = pytest.mark.skipif(not provider_available(), reason="no LLM provider reachable")


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def tiny_pdf() -> bytes:
    """A two-page PDF with a handful of unambiguous, corroborating facts."""
    doc = pymupdf.open()
    p1 = doc.new_page(width=595, height=842)
    y = 60
    for line in [
        "Acme Logistics Limited - FY24 Results Summary",
        "",
        "Consolidated revenue for FY24 was INR 8,142 crore.",
        "Consolidated EBITDA for FY24 was INR 127 crore.",
        "The company operated 45 hubs across India as at March 31, 2024.",
        "Acme turned EBITDA profitable during FY24.",
    ]:
        p1.insert_text((54, y), line, fontsize=12)
        y += 22
    p2 = doc.new_page(width=595, height=842)
    y = 60
    for line in [
        "Acme Logistics Limited - FY24 Investor Presentation",
        "",
        "FY24 EBITDA was Rs. 1,266.41 million on a consolidated basis.",
        "Revenue from services in FY24 stood at Rs. 8,142 Cr.",
        "The network comprised over 40 hubs at the end of FY24.",
    ]:
        p2.insert_text((54, y), line, fontsize=12)
        y += 22
    return doc.tobytes()

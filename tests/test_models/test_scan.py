"""Tests for ScanLog and FilterResultDB models."""

from app.models.filter_result import FilterResultDB
from app.models.scan import ScanLog


def test_create_scan_log(db):
    scan = ScanLog(url="https://www.leboncoin.fr/ad/voitures/123", score=72)
    db.session.add(scan)
    db.session.commit()

    saved = ScanLog.query.first()
    assert saved.url.endswith("/123")
    assert saved.score == 72


def test_scan_filter_results(db):
    scan = ScanLog(url="https://www.leboncoin.fr/ad/voitures/456", score=85)
    db.session.add(scan)
    db.session.flush()

    fr = FilterResultDB(
        scan_id=scan.id,
        filter_id="L1",
        status="pass",
        score=1.0,
        message="Extraction OK",
    )
    db.session.add(fr)
    db.session.commit()

    assert len(scan.filter_results) == 1
    assert scan.filter_results[0].filter_id == "L1"
    assert scan.filter_results[0].status == "pass"

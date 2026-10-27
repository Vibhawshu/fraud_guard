from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from pathlib import Path
from typing import Optional
import json
import csv
import io

from backend.schemas import (
    PredictRequest, PredictResponse,
    HistoryItem, HistoryResponse, HistoryDetail, DeleteResponse,
)
from backend.predictor import predict
from backend.explainer import explain_prediction
from backend.database import init_db, get_db
from backend.models import AnalysisRecord

app = FastAPI(title="SMS & Email Fraud Detector")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent.parent


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/predict", response_model=PredictResponse)
async def predict_endpoint(request: PredictRequest, db: Session = Depends(get_db)):
    if len(request.text.strip()) < 3:
        raise HTTPException(status_code=400, detail="Text too short")

    # Allow optional metadata via attributes that may not be on the schema
    subject = getattr(request, "subject", None)
    sender = getattr(request, "sender", None)
    source = getattr(request, "source", "manual") or "manual"

    label, confidence, clean_text, model, vectorizer = predict(
        request.text, request.message_type
    )
    explanation = explain_prediction(clean_text, model, vectorizer)

    record = AnalysisRecord(
        message_type=request.message_type,
        source=source,
        subject=subject,
        sender=sender,
        original_text=request.text,
        label=label,
        confidence=confidence,
        explanation_json=json.dumps(explanation),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return PredictResponse(
        id=record.id,
        label=label,
        confidence=round(confidence, 4),
        explanation=explanation,
        raw_text=request.text,
        created_at=record.to_dict()["created_at"],
    )


@app.get("/history", response_model=HistoryResponse)
async def get_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    filter: str = Query("all", pattern="^(all|fraud|safe|sms|email|gmail)$"),
    db: Session = Depends(get_db),
):
    query = db.query(AnalysisRecord)

    if filter == "fraud":
        query = query.filter(AnalysisRecord.label.in_(["spam", "phishing"]))
    elif filter == "safe":
        query = query.filter(AnalysisRecord.label.in_(["ham", "legitimate"]))
    elif filter == "sms":
        query = query.filter(AnalysisRecord.message_type == "sms")
    elif filter == "email":
        query = query.filter(AnalysisRecord.message_type == "email")
    elif filter == "gmail":
        query = query.filter(AnalysisRecord.source == "gmail")

    total = query.count()
    rows = (
        query.order_by(desc(AnalysisRecord.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    total_all = db.query(AnalysisRecord).count()
    fraud_all = (
        db.query(AnalysisRecord)
        .filter(AnalysisRecord.label.in_(["spam", "phishing"]))
        .count()
    )
    last_record = (
        db.query(AnalysisRecord).order_by(desc(AnalysisRecord.created_at)).first()
    )

    stats = {
        "total": total_all,
        "fraud": fraud_all,
        "rate": round((fraud_all / total_all * 100), 1) if total_all > 0 else 0,
        "last_created": last_record.created_at.isoformat() + "Z" if last_record else None,
    }

    return HistoryResponse(
        items=[HistoryItem(**r.to_dict()) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        stats=stats,
    )


@app.get("/history/{record_id}", response_model=HistoryDetail)
async def get_history_detail(record_id: int, db: Session = Depends(get_db)):
    record = db.query(AnalysisRecord).filter(AnalysisRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return HistoryDetail(**record.to_dict())


@app.delete("/history/{record_id}", response_model=DeleteResponse)
async def delete_record(record_id: int, db: Session = Depends(get_db)):
    record = db.query(AnalysisRecord).filter(AnalysisRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    db.delete(record)
    db.commit()
    return DeleteResponse(deleted=1, message="Record deleted")


@app.delete("/history", response_model=DeleteResponse)
async def clear_history(db: Session = Depends(get_db)):
    count = db.query(AnalysisRecord).delete()
    db.commit()
    return DeleteResponse(deleted=count, message="All history cleared")


@app.get("/history/export")
async def export_history(db: Session = Depends(get_db)):
    rows = (
        db.query(AnalysisRecord)
        .order_by(desc(AnalysisRecord.created_at))
        .all()
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "id", "created_at", "message_type", "source", "subject", "sender",
        "label", "confidence", "original_text", "top_terms",
    ])
    for r in rows:
        top_terms = "; ".join(
            f"{t['token']} ({t['weight']:+.3f})"
            for t in json.loads(r.explanation_json)[:5]
        )
        writer.writerow([
            r.id,
            r.created_at.isoformat(),
            r.message_type,
            r.source or "manual",
            r.subject or "",
            r.sender or "",
            r.label,
            round(r.confidence, 4),
            r.original_text.replace("\n", " ")[:500],
            top_terms,
        ])

    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=fraud_history.csv"},
    )


app.mount("/", StaticFiles(directory=BASE_DIR / "frontend", html=True), name="frontend")
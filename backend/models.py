from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from database import Base


class Batch(Base):
    """One monthly salary upload."""
    __tablename__ = "batches"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String, nullable=False)        # e.g. "July 2026"
    filename = Column(String)
    status = Column(String, default="review")      # review | published
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    published_at = Column(DateTime, nullable=True)
    columns = Column(JSON)                          # ordered list of header names

    records = relationship(
        "EmployeeRecord", back_populates="batch", cascade="all, delete-orphan"
    )


class EmployeeRecord(Base):
    """One employee's row within a batch."""
    __tablename__ = "employee_records"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("batches.id"))
    emp_id = Column(String, index=True, nullable=False)
    name = Column(String)
    department = Column(String)
    designation = Column(String)
    net_payable = Column(String)
    data = Column(JSON)  # full row, in original column order: {header: value}

    batch = relationship("Batch", back_populates="records")
    review = relationship(
        "Review", back_populates="record", uselist=False, cascade="all, delete-orphan"
    )


class Review(Base):
    """Employee's confirmation / issue report for one record."""
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    record_id = Column(Integer, ForeignKey("employee_records.id"), unique=True)
    status = Column(String, default="pending")  # pending | ok | issue
    comment = Column(Text, default="")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    record = relationship("EmployeeRecord", back_populates="review")

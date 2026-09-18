"""Verify teacher readiness distribution of the seed (P1-09-03)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections import Counter

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.catalog import University
from app.models.teachers import Teacher
from app.services.teacher_readiness import compute_teacher_readiness

url = os.getenv("DATABASE_URL", settings.database_url)
with Session(create_engine(url)) as s:
    total = Counter()
    for uni in s.execute(select(University).order_by(University.name)).scalars():
        teachers = s.execute(
            select(Teacher).filter_by(university_id=uni.id)).scalars().all()
        dist = Counter()
        for t in teachers:
            r = compute_teacher_readiness(t.certificates, t.qualifications)
            dist[r.readiness.value] += 1
            total[r.readiness.value] += 1
        print(f"{uni.name[:28]:28s} n={len(teachers)} {dict(dist)}")
    print("TOTAL:", dict(total))

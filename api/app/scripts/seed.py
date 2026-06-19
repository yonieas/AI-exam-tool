"""Seed script: idempotent. Run after `alembic upgrade head`.

Creates Ms. Alvarez's demo data per docs/MOCK_DATA.md.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.models.class_ import Class, ClassEnrollment, ClassSubject
from app.models.exam import Exam, Question
from app.models.student import Student
from app.models.subject import Subject
from app.models.user import User


DEMO_EMAIL = "teacher@demo.local"
DEMO_NAME = "Ms. Alvarez"

SUBJECTS = [
    ("Physics", "PHYS"),
    ("Biology", "BIO"),
    ("Chemistry", "CHEM"),
    ("Mathematics", "MATH"),
]
CLASSES = [
    ("Grade 10-A", 10),
    ("Grade 11-B", 11),
]
STUDENTS_10A = [
    ("S001", "Aarav Singh", "aarav@demo.local"),
    ("S002", "Bea Costa", "bea@demo.local"),
    ("S003", "Cira Lopez", "cira@demo.local"),
    ("S004", "Daichi Ito", "daichi@demo.local"),
    ("S005", "Elena Popov", "elena@demo.local"),
    ("S006", "Finn O'Brien", "finn@demo.local"),
    ("S007", "Gita Rao", "gita@demo.local"),
    ("S008", "Hugo Martin", "hugo@demo.local"),
    ("S009", "Iris Nakata", "iris@demo.local"),
    ("S010", "Jamal Ahmed", "jamal@demo.local"),
    ("S011", "Kira Park", "kira@demo.local"),
    ("S012", "Leo Ferrari", "leo@demo.local"),
    ("S013", "Maya Devi", "maya@demo.local"),
    ("S014", "Niko Vargas", "niko@demo.local"),
    ("S015", "Omar Bashir", "omar@demo.local"),
]
STUDENTS_11B = [
    ("S101", "Pia Mendez", "pia@demo.local"),
    ("S102", "Quentin Lee", "quentin@demo.local"),
    ("S103", "Rina Suzuki", "rina@demo.local"),
    ("S104", "Sami Cohen", "sami@demo.local"),
    ("S105", "Tina Olsen", "tina@demo.local"),
    ("S106", "Uri Patel", "uri@demo.local"),
    ("S107", "Vera Hofmann", "vera@demo.local"),
    ("S108", "Wes Adekunle", "wes@demo.local"),
    ("S109", "Xena Volkov", "xena@demo.local"),
    ("S110", "Yara Saade", "yara@demo.local"),
    ("S111", "Zane Wei", "zane@demo.local"),
    ("S112", "Ana Becker", "ana@demo.local"),
    ("S113", "Boris Klein", "boris@demo.local"),
    ("S114", "Cleo Hart", "cleo@demo.local"),
    ("S115", "Dani Romero", "dani@demo.local"),
]


async def seed() -> None:
    async with SessionLocal() as session:  # type: AsyncSession
        # User
        user = (await session.execute(select(User).where(User.email == DEMO_EMAIL))).scalar_one_or_none()
        if not user:
            user = User(
                id=uuid.uuid4(),
                email=DEMO_EMAIL,
                full_name=DEMO_NAME,
                settings={"default_confidence_threshold": 0.7},
                last_login_at=datetime.utcnow(),
            )
            session.add(user)
            await session.flush()
        print(f"user: {user.id} ({user.email})")

        # Subjects
        subjects: dict[str, Subject] = {}
        for name, code in SUBJECTS:
            s = (await session.execute(
                select(Subject).where(Subject.owner_id == user.id, Subject.name == name)
            )).scalar_one_or_none()
            if not s:
                s = Subject(id=uuid.uuid4(), owner_id=user.id, name=name, code=code)
                session.add(s)
                await session.flush()
            subjects[name] = s
        print(f"subjects: {len(subjects)}")

        # Classes
        classes: list[Class] = []
        for cname, grade in CLASSES:
            c = (await session.execute(
                select(Class).where(Class.owner_id == user.id, Class.name == cname)
            )).scalar_one_or_none()
            if not c:
                c = Class(id=uuid.uuid4(), owner_id=user.id, name=cname, grade_level=grade)
                session.add(c)
                await session.flush()
            classes.append(c)
        print(f"classes: {len(classes)}")

        # ClassSubject: each class × all subjects
        for c in classes:
            for s in subjects.values():
                exists = (await session.execute(
                    select(ClassSubject).where(
                        ClassSubject.class_id == c.id, ClassSubject.subject_id == s.id
                    )
                )).scalar_one_or_none()
                if not exists:
                    session.add(ClassSubject(class_id=c.id, subject_id=s.id, owner_id=user.id))
        await session.flush()

        # Students
        all_students: list[Student] = []
        for code, name, email in STUDENTS_10A + STUDENTS_11B:
            s = (await session.execute(
                select(Student).where(Student.owner_id == user.id, Student.student_code == code)
            )).scalar_one_or_none()
            if not s:
                s = Student(
                    id=uuid.uuid4(), owner_id=user.id, name=name, student_code=code,
                    email=email, extra_columns={"homeroom": "10A" if code.startswith("S0") else "11B"},
                )
                session.add(s)
                await session.flush()
            all_students.append(s)
        print(f"students: {len(all_students)}")

        # Enrollments
        for i, s in enumerate(all_students):
            klass = classes[0] if i < 15 else classes[1]
            exists = (await session.execute(
                select(ClassEnrollment).where(
                    ClassEnrollment.class_id == klass.id, ClassEnrollment.student_id == s.id
                )
            )).scalar_one_or_none()
            if not exists:
                session.add(ClassEnrollment(
                    id=uuid.uuid4(), owner_id=user.id, class_id=klass.id, student_id=s.id,
                ))
        await session.commit()
        print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())

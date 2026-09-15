"""Quick verification for GET /fees/reports/today-collection using mongomock.

Runs the route handler directly (no server needed) with seeded payments:
  - 2 successful payments today  -> should be counted
  - 1 failed payment today       -> should be ignored
  - 1 successful payment yesterday -> should be ignored
  - 1 successful payment today on another branch -> counted only in all-branches scope
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mongoengine
import mongomock

mongoengine.connect(db="test_today_collection", mongo_client_class=mongomock.MongoClient)

from models.institution import School, AcademicYear, ClassRoom, Section
from models.student import Student
from models.fees import FeeInvoice, PaymentTransaction
from routes.fees import today_collection

# ---- Seed -----------------------------------------------------------------
school = School(name="Test School", code="TS1").save()
ay = AcademicYear(
    school=school, name="2026-2027",
    start_date=datetime(2026, 4, 1), end_date=datetime(2027, 3, 31),
    is_current=True,
).save()
classroom = ClassRoom(school=school, academic_year=ay, name="Class 1").save()
section = Section(school=school, academic_year=ay, classroom=classroom, name="A").save()


def make_student(adm, branch):
    return Student(
        admission_no=adm, student_id=f"SID-{adm}", first_name="Test", last_name=adm,
        gender="Male", school=school, academic_year=ay,
        classroom=classroom, section=section, branch_code=branch,
    ).save()


st_a = make_student("A1", "BR1")
st_b = make_student("B1", "BR2")

inv_a = FeeInvoice(
    school=school, student=st_a, academic_year=ay,
    invoice_no="INV-A-1", net_amount=1000, paid_amount=0, balance_amount=1000,
).save()
inv_b = FeeInvoice(
    school=school, student=st_b, academic_year=ay,
    invoice_no="INV-B-1", net_amount=2000, paid_amount=0, balance_amount=2000,
).save()

now = datetime.now()
today_10am = now.replace(hour=10, minute=0, second=0, microsecond=0)
yesterday = now - timedelta(days=1)

# 2 successful payments today (branch BR1)
PaymentTransaction(school=school, student=st_a, invoice=inv_a, transaction_no="T1",
                   payment_date=today_10am, amount=500, payment_mode="Cash", status="Success").save()
PaymentTransaction(school=school, student=st_a, invoice=inv_a, transaction_no="T2",
                   payment_date=now, amount=300, payment_mode="UPI", status="Success").save()
# failed payment today -> ignored
PaymentTransaction(school=school, student=st_a, invoice=inv_a, transaction_no="T3",
                   payment_date=now, amount=999, payment_mode="Cash", status="Failed").save()
# success yesterday -> ignored
PaymentTransaction(school=school, student=st_a, invoice=inv_a, transaction_no="T4",
                   payment_date=yesterday, amount=700, payment_mode="Cash", status="Success").save()
# success today but other branch (BR2)
PaymentTransaction(school=school, student=st_b, invoice=inv_b, transaction_no="T5",
                   payment_date=now, amount=1000, payment_mode="Online", status="Success").save()

fake_user = SimpleNamespace(is_superadmin=True, assigned_school=None,
                            assigned_branch_code=None, allowed_branch_codes=[])


async def run():
    all_scope = await today_collection(school_id=str(school.id), branch_code=None, current_user=fake_user)
    br1_scope = await today_collection(school_id=str(school.id), branch_code="BR1", current_user=fake_user)
    br2_scope = await today_collection(school_id=str(school.id), branch_code="BR2", current_user=fake_user)

    a, b1, b2 = all_scope["data"], br1_scope["data"], br2_scope["data"]
    print("ALL branches :", a)
    print("Branch BR1   :", b1)
    print("Branch BR2   :", b2)

    assert a["today_collected"] == 1800, f"ALL: expected 1800, got {a['today_collected']}"
    assert a["transaction_count"] == 3, f"ALL: expected 3 txns, got {a['transaction_count']}"
    assert a["date"] == now.date().isoformat(), f"ALL: wrong date {a['date']}"
    assert b1["today_collected"] == 800 and b1["transaction_count"] == 2, f"BR1 wrong: {b1}"
    assert b2["today_collected"] == 1000 and b2["transaction_count"] == 1, f"BR2 wrong: {b2}"
    print("\n✅ today_collection endpoint works correctly!")


asyncio.run(run())

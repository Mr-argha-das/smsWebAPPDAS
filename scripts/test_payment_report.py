"""Verify payment_history filters + totals used by the new Payment Report tab."""
import asyncio
import os
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mongoengine
import mongomock

mongoengine.connect(db="test_payment_report", mongo_client_class=mongomock.MongoClient)

from models.institution import School, AcademicYear, ClassRoom, Section
from models.student import Student
from models.fees import FeeInvoice, PaymentTransaction
from routes.fees import payment_history

school = School(name="R School", code="RS1").save()
ay = AcademicYear(school=school, name="2026-2027", start_date=datetime(2026, 4, 1),
                  end_date=datetime(2027, 3, 31), is_current=True).save()
classroom = ClassRoom(school=school, academic_year=ay, name="Class 1").save()
section = Section(school=school, academic_year=ay, classroom=classroom, name="A").save()
st = Student(admission_no="R1", student_id="SID-R1", first_name="Ram", last_name="K",
             gender="Male", school=school, academic_year=ay, classroom=classroom,
             section=section).save()
inv = FeeInvoice(school=school, student=st, academic_year=ay, invoice_no="INV-R-1",
                 net_amount=5000, paid_amount=0, balance_amount=5000).save()

now = datetime.now()
today_10 = now.replace(hour=10, minute=0, second=0, microsecond=0)
month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
in_month = month_start + timedelta(days=2, hours=5)
two_months_ago = (month_start - timedelta(days=45)).replace(hour=11)


def txn(no, when, amount, mode, status="Success"):
    PaymentTransaction(school=school, student=st, invoice=inv, transaction_no=no,
                       payment_date=when, amount=amount, payment_mode=mode,
                       status=status).save()


txn("P1", today_10, 1000, "Cash")           # today + this month
txn("P2", now, 500, "UPI")                  # today + this month
txn("P3", in_month, 2000, "Cash")           # this month (not today)
txn("P4", two_months_ago, 700, "Cheque")    # old
txn("P5", now, 999, "Cash", status="Failed")  # failed -> ignored everywhere

fake_user = SimpleNamespace(is_superadmin=True, assigned_school=None,
                            assigned_branch_code=None, allowed_branch_codes=[])


async def run():
    # 1) No filters: all successful payments
    r = await payment_history(school_id=str(school.id), per_page=100, page=1, current_user=fake_user)
    m = r["meta"]
    assert m["total"] == 4 and m["total_amount"] == 4200, m
    assert m["amount_by_mode"] == {"Cash": 3000.0, "UPI": 500.0, "Cheque": 700.0}, m["amount_by_mode"]
    print("no-filter totals        :", m["total"], m["total_amount"], m["amount_by_mode"], "✓")

    # 2) This month & today (two months old payment excluded from month)
    assert m["this_month_amount"] == 3500, m
    assert m["today_amount"] == 1500, m
    print("this-month / today      :", m["this_month_amount"], "/", m["today_amount"], "✓")

    # 3) Date range filter: only this month start -> today
    r2 = await payment_history(school_id=str(school.id), per_page=100, page=1,
                               start_date=month_start.date().isoformat(),
                               end_date=now.date().isoformat(),
                               current_user=fake_user)
    assert r2["meta"]["total"] == 3 and r2["meta"]["total_amount"] == 3500, r2["meta"]
    print("date-range filter       :", r2["meta"]["total"], r2["meta"]["total_amount"], "✓")

    # 4) Mode filter: Cash only
    r3 = await payment_history(school_id=str(school.id), per_page=100,
                               payment_mode="Cash", page=1, current_user=fake_user)
    assert r3["meta"]["total"] == 2 and r3["meta"]["total_amount"] == 3000, r3["meta"]
    assert r3["meta"]["amount_by_mode"] == {"Cash": 3000.0}, r3["meta"]
    print("mode filter (Cash)      :", r3["meta"]["total"], r3["meta"]["total_amount"], "✓")

    # 5) Date + mode combined
    r4 = await payment_history(school_id=str(school.id), per_page=100, page=1,
                               start_date=now.date().isoformat(),
                               end_date=now.date().isoformat(),
                               payment_mode="UPI", current_user=fake_user)
    assert r4["meta"]["total"] == 1 and r4["meta"]["total_amount"] == 500, r4["meta"]
    print("date + mode combined    :", r4["meta"]["total"], r4["meta"]["total_amount"], "✓")

    # 6) Pagination still works
    r5 = await payment_history(school_id=str(school.id), per_page=2, page=2, current_user=fake_user)
    assert r5["meta"]["total"] == 4 and len(r5["data"]) == 2 and r5["meta"]["total_pages"] == 2, r5["meta"]
    assert r5["meta"]["total_amount"] == 4200, "totals must ignore pagination"
    print("pagination + full totals:", r5["meta"]["total_pages"], "pages ✓")

    print("\n✅ payment_history filters + totals all correct!")


asyncio.run(run())

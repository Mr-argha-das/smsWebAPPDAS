"""Verify transport stats fix: stale assignments (deleted routes / inactive
students) must not inflate students_using_transport."""
import asyncio
import os
import sys
from datetime import datetime
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mongoengine
import mongomock

mongoengine.connect(db="test_transport_stats", mongo_client_class=mongomock.MongoClient)

from models.institution import School, AcademicYear, ClassRoom, Section
from models.student import Student
from models.transport import TransportRoute, StudentTransport
from routes.transport import transport_stats, delete_route

school = School(name="T School", code="TS2").save()
ay = AcademicYear(school=school, name="2026-2027", start_date=datetime(2026, 4, 1),
                  end_date=datetime(2027, 3, 31), is_current=True).save()
classroom = ClassRoom(school=school, academic_year=ay, name="Class 1").save()
section = Section(school=school, academic_year=ay, classroom=classroom, name="A").save()


def make_student(adm, active=True):
    st = Student(
        admission_no=adm, student_id=f"SID-{adm}", first_name="T", last_name=adm,
        gender="Male", school=school, academic_year=ay,
        classroom=classroom, section=section,
    )
    if not active:
        st.is_active = False
    return st.save()


route1 = TransportRoute(school=school, route_name="R1", route_code="R1").save()
route2 = TransportRoute(school=school, route_name="R2", route_code="R2").save()

st1 = make_student("S1")
st2 = make_student("S2")
st3 = make_student("S3", active=False)  # inactive student with stale assignment

StudentTransport(school=school, student=st1, route=route1).save()
StudentTransport(school=school, student=st2, route=route2).save()
StudentTransport(school=school, student=st3, route=route1).save()  # stale: student inactive

fake_user = SimpleNamespace(is_superadmin=True, assigned_school=None,
                            assigned_branch_code=None, allowed_branch_codes=[])


async def run():
    # Inactive student's assignment must not count -> expect 2, not 3
    r = await transport_stats(school_id=str(school.id), current_user=fake_user)
    assert r["data"]["students_using_transport"] == 2, r["data"]
    print("inactive student excluded     :", r["data"]["students_using_transport"], "✓")

    # Withdrawn/transferred student's assignment must not count either
    st1.update(admission_status="Withdrawn")
    r = await transport_stats(school_id=str(school.id), current_user=fake_user)
    assert r["data"]["students_using_transport"] == 1, r["data"]
    print("withdrawn student excluded    :", r["data"]["students_using_transport"], "✓")
    st1.update(admission_status="Active")
    r = await transport_stats(school_id=str(school.id), current_user=fake_user)
    assert r["data"]["students_using_transport"] == 2, r["data"]

    # Duplicate assignment row counts the student only once
    StudentTransport(school=school, student=st1, route=route1).save()
    r = await transport_stats(school_id=str(school.id), current_user=fake_user)
    assert r["data"]["students_using_transport"] == 2, r["data"]
    print("duplicate row counted once    :", r["data"]["students_using_transport"], "✓")

    # Per-route badge must show distinct active students only:
    # route1 has st1 (twice) + st3(inactive) -> badge must be 1
    from routes.transport import list_routes
    routes_res = await list_routes(school_id=str(school.id), branch_code=None, current_user=fake_user)
    badges = {row["route_name"]: row["student_count"] for row in routes_res["data"]}
    assert badges.get("R1") == 1, badges
    assert badges.get("R2") == 1, badges
    print("per-route badge correct       :", badges, "✓")

    # Delete route2 -> its assignment must be deactivated automatically
    await delete_route(route_id=str(route2.id), current_user=fake_user)
    r = await transport_stats(school_id=str(school.id), current_user=fake_user)
    assert r["data"]["students_using_transport"] == 1, r["data"]
    assert st2.reload().uses_transport is False
    print("route delete cleans assignment:", r["data"]["students_using_transport"], "✓")

    # Legacy stale data (assignment on already-inactive route) must not count:
    # simulate legacy record by direct insert bypassing the delete-cleanup.
    route3 = TransportRoute(school=school, route_name="R3", route_code="R3").save()
    st4 = make_student("S4")
    StudentTransport(school=school, student=st4, route=route3).save()
    route3.update(is_active=False)  # simulate old-style delete without cleanup
    r = await transport_stats(school_id=str(school.id), current_user=fake_user)
    assert r["data"]["students_using_transport"] == 1, r["data"]
    print("legacy stale route excluded   :", r["data"]["students_using_transport"], "✓")

    print("\n✅ Transport stats fix works correctly!")


asyncio.run(run())

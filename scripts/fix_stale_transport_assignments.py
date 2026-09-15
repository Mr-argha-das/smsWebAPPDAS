"""One-time cleanup: fix stale/duplicate student_transport assignments.

Stale records inflate per-route student badges and the Students stats card.
They appear when:
  1. a route was soft-deleted but its assignments stayed active
  2. a student was withdrawn/transferred/deleted but the assignment stayed active
  3. duplicate active assignment rows exist for the same student (keep latest)

Run from the repo root with the same Python env as the app:

    python scripts/fix_stale_transport_assignments.py            # dry-run (shows what would change)
    python scripts/fix_stale_transport_assignments.py --apply    # actually apply the fixes
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mongoengine
from config import settings

mongoengine.connect(db=settings.DB_NAME, host=settings.MONGODB_URL)

from models.institution import School
from models.student import Student
from models.transport import TransportRoute, StudentTransport

APPLY = "--apply" in sys.argv

print(f"Mode: {'APPLY (will write changes)' if APPLY else 'DRY-RUN (no changes)'}\n")

total_deactivated = 0
for school in School.objects:
    active_route_ids = {r.id for r in TransportRoute.objects(school=school, is_active=True).only("id")}
    active_student_ids = {
        s.id for s in Student.objects(school=school, is_active=True, admission_status="Active").only("id")
    }
    assignments = list(
        StudentTransport.objects(school=school, is_active=True).only("student", "route", "assigned_date")
    )
    if not assignments:
        continue

    to_disable = {}   # assignment id -> (assignment, reason)
    latest_by_student = {}
    for st in assignments:
        sid = st.student.id if st.student else None
        rid = st.route.id if st.route else None
        if not sid or sid not in active_student_ids:
            to_disable[st.id] = (st, "student withdrawn/inactive/deleted")
            continue
        if not rid or rid not in active_route_ids:
            to_disable[st.id] = (st, "route deleted/inactive")
            continue
        # duplicate detection among otherwise-valid assignments
        if sid not in latest_by_student or (st.assigned_date or 0) > (latest_by_student[sid].assigned_date or 0):
            latest_by_student[sid] = st

    valid_students_seen = set()
    for st in assignments:
        if st.id in to_disable or not st.student:
            continue
        sid = st.student.id
        if sid in valid_students_seen or latest_by_student.get(sid) is not st:
            to_disable[st.id] = (st, "duplicate assignment (keeping latest)")
        else:
            valid_students_seen.add(sid)

    if not to_disable:
        continue

    print(f"School: {school.name} ({school.id}) — {len(to_disable)} stale assignment(s)")
    for st, reason in to_disable.values():
        s_name = st.student.full_name if st.student else "(deleted student)"
        r_name = st.route.route_name if st.route else "(deleted route)"
        print(f"  - {st.id}: student={s_name}, route={r_name}  [{reason}]")

    if APPLY:
        for st, _ in to_disable.values():
            st.update(set__is_active=False)
            total_deactivated += 1
        # Sync student's uses_transport flag with reality
        for sid in active_student_ids:
            has_active = any(
                a.student and a.student.id == sid and a.id not in to_disable for a in assignments
            )
            if not has_active:
                Student.objects(id=sid).first().update(
                    uses_transport=False, transport_route=None, transport_route_name=None
                )

print()
if APPLY:
    print(f"✅ Done. Deactivated {total_deactivated} stale assignment(s).")
else:
    print("ℹ️  Dry-run complete. Re-run with --apply to deactivate these assignments.")

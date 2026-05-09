#!/usr/bin/env python3
"""Merge duplicate student records while keeping one canonical student."""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import connect_db, disconnect_db
from models.attendance import AttendanceSummary, StudentAttendance
from models.certificates import CertificateIssued
from models.examination import MarksEntry, Result
from models.fees import FeeInvoice, PaymentTransaction
from models.health import HealthRecord, MedicalVisit
from models.hostel import HostelAllocation, HostelFeeInvoice, HostelLeaveRequest
from models.library import LibraryMember
from models.parent_portal import ParentMessage, ParentPortalUser
from models.student import Student, TransferCertificate
from models.transport import StudentTransport


def norm_text(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def norm_digits(value: Optional[str]) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def norm_date(value: Optional[datetime]) -> str:
    return value.strftime("%Y-%m-%d") if value else ""


def full_name_key(student: Student) -> str:
    return norm_text(" ".join(part for part in [student.first_name, student.middle_name, student.last_name] if part))


def student_identity_key(student: Student) -> Optional[str]:
    school_id = str(student.school.id) if student.school else ""
    ay_id = str(student.academic_year.id) if student.academic_year else ""
    branch_code = norm_text(student.branch_code)
    parent = student.parent_info

    aadhar = norm_digits(student.aadhar_number)
    if aadhar:
        name = full_name_key(student)
        return f"aadhar:{school_id}:{aadhar}:{name}" if name else None

    srn = norm_text(student.srn_no)
    if srn:
        name = full_name_key(student)
        return f"srn:{school_id}:{srn}:{name}" if name else None

    name = full_name_key(student)
    father = norm_text(parent.father_name if parent else "")
    mother = norm_text(parent.mother_name if parent else "")
    dob = norm_date(student.date_of_birth)
    phone = norm_digits(student.phone or (parent.father_phone if parent else ""))

    signal_count = sum(1 for value in [father, mother, dob, phone] if value)
    if not name or signal_count < 2:
        return None

    return "|".join(["bio", school_id, ay_id, branch_code, name, father, mother, dob, phone])


def choose_keeper(students: list[Student]) -> Student:
    def score(student: Student) -> tuple[int, datetime]:
        filled = sum(
            1
            for value in [
                student.aadhar_number,
                student.srn_no,
                student.phone,
                student.email,
                student.current_address,
                student.permanent_address,
                student.parent_info.father_name if student.parent_info else None,
                student.parent_info.mother_name if student.parent_info else None,
            ]
            if value
        )
        return (filled, student.created_at or datetime.min)

    return sorted(students, key=score, reverse=True)[0]


def merge_missing_student_fields(keeper: Student, duplicate: Student) -> bool:
    changed = False
    simple_fields = [
        "middle_name",
        "date_of_birth",
        "gender",
        "religion",
        "caste",
        "nationality",
        "aadhar_number",
        "srn_no",
        "phone",
        "email",
        "current_address",
        "permanent_address",
        "photo",
        "remarks",
    ]
    for field in simple_fields:
        if not getattr(keeper, field, None) and getattr(duplicate, field, None):
            setattr(keeper, field, getattr(duplicate, field))
            changed = True

    if duplicate.parent_info:
        if not keeper.parent_info:
            keeper.parent_info = duplicate.parent_info
            changed = True
        else:
            for field in duplicate.parent_info._fields:
                if field == "id":
                    continue
                if not getattr(keeper.parent_info, field, None) and getattr(duplicate.parent_info, field, None):
                    setattr(keeper.parent_info, field, getattr(duplicate.parent_info, field))
                    changed = True

    sibling_ids = list(dict.fromkeys([*(keeper.sibling_student_ids or []), *(duplicate.sibling_student_ids or [])]))
    duplicate_id = str(duplicate.id)
    sibling_ids = [str(keeper.id) if sid == duplicate_id else sid for sid in sibling_ids]
    sibling_ids = [sid for sid in dict.fromkeys(sibling_ids) if sid != str(keeper.id)]
    if sibling_ids != (keeper.sibling_student_ids or []):
        keeper.sibling_student_ids = sibling_ids
        changed = True

    if changed:
        keeper.updated_at = datetime.utcnow()
    return changed


def replace_student_refs(keeper: Student, duplicate: Student, dry_run: bool) -> dict[str, int]:
    counts: dict[str, int] = {}
    direct_models = [
        FeeInvoice,
        PaymentTransaction,
        MarksEntry,
        Result,
        TransferCertificate,
        StudentTransport,
        AttendanceSummary,
        HostelAllocation,
        HostelFeeInvoice,
        HostelLeaveRequest,
        HealthRecord,
        MedicalVisit,
        LibraryMember,
        CertificateIssued,
        ParentMessage,
    ]

    for model in direct_models:
        queryset = model.objects(student=duplicate)
        count = queryset.count()
        counts[model.__name__] = count
        if count and not dry_run:
            queryset.update(student=keeper)

    duplicate_id = str(duplicate.id)
    keeper_id = str(keeper.id)

    parent_count = 0
    for parent in ParentPortalUser.objects(children__in=[duplicate]):
        new_children = []
        seen = set()
        for child in parent.children or []:
            child_id = str(child.id)
            if child_id == duplicate_id:
                child = keeper
                child_id = keeper_id
            if child_id not in seen:
                seen.add(child_id)
                new_children.append(child)
        parent_count += 1
        if not dry_run:
            parent.children = new_children
            parent.save()
    counts["ParentPortalUser.children"] = parent_count

    attendance_count = 0
    for attendance in StudentAttendance.objects(records__student=duplicate):
        seen_students = set()
        new_records = []
        changed = False
        for record in attendance.records or []:
            record_student_id = str(record.student.id) if record.student else ""
            if record_student_id == duplicate_id:
                record.student = keeper
                record.student_name = keeper.full_name
                record_student_id = keeper_id
                changed = True
            if record_student_id in seen_students:
                changed = True
                continue
            seen_students.add(record_student_id)
            new_records.append(record)
        attendance_count += 1
        if changed and not dry_run:
            attendance.records = new_records
            attendance.total_students = len(new_records)
            attendance.present_count = sum(1 for row in new_records if row.status == "Present")
            attendance.absent_count = sum(1 for row in new_records if row.status == "Absent")
            attendance.late_count = sum(1 for row in new_records if row.status == "Late")
            attendance.save()
    counts["StudentAttendance.records"] = attendance_count

    sibling_count = 0
    for student in Student.objects(sibling_student_ids=duplicate_id):
        updated_ids = [keeper_id if sid == duplicate_id else sid for sid in (student.sibling_student_ids or [])]
        updated_ids = list(dict.fromkeys(sid for sid in updated_ids if sid != str(student.id)))
        sibling_count += 1
        if not dry_run:
            student.sibling_student_ids = updated_ids
            student.save()
    counts["Student.sibling_student_ids"] = sibling_count

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge duplicate student records.")
    parser.add_argument("--dry-run", action="store_true", help="Only print what would change.")
    args = parser.parse_args()

    connect_db()
    try:
        groups: dict[str, list[Student]] = defaultdict(list)
        for student in Student.objects(is_active=True):
            key = student_identity_key(student)
            if key:
                groups[key].append(student)

        duplicate_groups = [students for students in groups.values() if len(students) > 1]
        summary = {
            "duplicate_groups": len(duplicate_groups),
            "duplicates_to_remove": sum(len(group) - 1 for group in duplicate_groups),
            "removed": 0,
            "references": defaultdict(int),
        }

        for group in duplicate_groups:
            keeper = choose_keeper(group)
            duplicates = [student for student in group if str(student.id) != str(keeper.id)]
            print(f"KEEP {keeper.admission_no} {keeper.full_name} ({keeper.id})")
            for duplicate in duplicates:
                print(f"  MERGE {duplicate.admission_no} {duplicate.full_name} ({duplicate.id})")
                if merge_missing_student_fields(keeper, duplicate) and not args.dry_run:
                    keeper.save()
                ref_counts = replace_student_refs(keeper, duplicate, args.dry_run)
                for name, count in ref_counts.items():
                    summary["references"][name] += count
                if not args.dry_run:
                    duplicate.delete()
                summary["removed"] += 1

        print("SUMMARY")
        print(f"duplicate_groups={summary['duplicate_groups']}")
        print(f"duplicates_to_remove={summary['duplicates_to_remove']}")
        print(f"removed={summary['removed'] if not args.dry_run else 0}")
        for name, count in sorted(summary["references"].items()):
            if count:
                print(f"{name}={count}")
    finally:
        disconnect_db()


if __name__ == "__main__":
    main()

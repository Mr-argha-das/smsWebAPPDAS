from __future__ import annotations

import csv
import io
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List


CLASS_MAP = {
    "NURSERY": "Nursery",
    "LKG": "LKG",
    "UKG": "UKG",
    "I": "1st",
    "II": "2nd",
    "III": "3rd",
    "IV": "4th",
    "V": "5th",
    "VI": "6th",
    "VII": "7th",
    "VIII": "8th",
    "IX": "9th",
    "X": "10th",
    "1ST": "1st",
    "2ND": "2nd",
    "3RD": "3rd",
    "4TH": "4th",
    "5TH": "5th",
    "6TH": "6th",
    "7TH": "7th",
    "8TH": "8th",
    "9TH": "9th",
    "10TH": "10th",
    "PASSOUT": "PASSOUT",
}

CLASS_PATTERN = re.compile(
    r"^(?P<class>PASSOUT|Nursery|LKG|UKG|10th|9th|8th|7th|6th|5th|4th|3rd|2nd|1st|X|IX|VIII|VII|VI|V|IV|III|II|I)\s*-\s*(?P<section>[A-Za-z])?\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
PASSOUT_PATTERN = re.compile(r"^PASSOUT\s+(?P<batch>\d{4}-\d{2})\s*-\s*(?P<section>[A-Za-z])\s+(?P<rest>.*)$", re.IGNORECASE)
ROW_START = re.compile(r"^\d+[.\s]+\d+\s+\d{2}-[A-Za-z]{3}-\d{4}\s+")


@dataclass
class ParsedStudentRow:
    admission_no: str = ""
    admission_date: str = ""
    class_name: str = ""
    section: str = ""
    name: str = ""
    father_name: str = ""
    mother_name: str = ""
    gender: str = ""
    dob: str = ""
    address: str = ""
    category: str = ""
    contact_no: str = ""
    aadhar_no: str = ""
    srn_no: str = ""
    remarks: str = ""
    source_raw: str = ""


def _run(cmd: List[str]) -> str:
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return result.stdout


def _swift_split_pdf_pages(pdf_path: str, out_dir: str) -> List[str]:
    script = Path(out_dir) / "split_pdf.swift"
    script.write_text(
        f"""
import Foundation
import PDFKit

let input = URL(fileURLWithPath: "{pdf_path}")
let outputDir = URL(fileURLWithPath: "{out_dir}", isDirectory: true)
guard let doc = PDFDocument(url: input) else {{
    fputs("Unable to open PDF\\n", stderr)
    exit(1)
}}

for index in 0..<doc.pageCount {{
    guard let page = doc.page(at: index) else {{ continue }}
    let pageDoc = PDFDocument()
    pageDoc.insert(page, at: 0)
    let url = outputDir.appendingPathComponent(String(format: "page_%03d.pdf", index + 1))
    pageDoc.write(to: url)
    print(url.path)
}}
""",
        encoding="utf-8",
    )
    stdout = _run(["swift", "-module-cache-path", "/tmp/swift-module-cache", str(script)])
    return [line.strip() for line in stdout.splitlines() if line.strip()]


def _swift_extract_pdf_text(pdf_path: str, out_dir: str) -> str:
    script = Path(out_dir) / "extract_text.swift"
    script.write_text(
        f"""
import Foundation
import PDFKit

let input = URL(fileURLWithPath: "{pdf_path}")
guard let doc = PDFDocument(url: input) else {{
    fputs("Unable to open PDF\\n", stderr)
    exit(1)
}}

for index in 0..<doc.pageCount {{
    guard let page = doc.page(at: index) else {{ continue }}
    print("=== PAGE \\(index + 1) ===")
    print(page.string ?? "")
}}
""",
        encoding="utf-8",
    )
    return _run(["swift", "-module-cache-path", "/tmp/swift-module-cache", str(script)])


def extract_pdf_text(pdf_path: str) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        return _swift_extract_pdf_text(pdf_path, tmpdir)


def _clean_text(value: str) -> str:
    text = re.sub(r"[—–]+", " ", value or "")
    text = text.replace("GENER AL", "GENERAL")
    text = text.replace("GEN ER", "GENERAL")
    text = text.replace("SNo Adm No Adm Date Class Name Father Name Mother Name Gen DOB Address Category Contact No Aadhar No SRN No", "")
    text = text.replace("SNo__AdmNo_ Adm Date Class Name Father Name Mother Name Gen DOB Address Category Contact No Aadhar No SRN No", "")
    text = text.replace("Adm Date", "")
    text = text.replace("Contact No", "")
    text = text.replace("Aadhar No", "")
    text = text.replace("SRN No", "")
    text = text.replace("Category", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _split_parent_names(pre_gender: str) -> tuple[str, str, str]:
    tokens = [token for token in re.split(r"\s+", pre_gender.strip()) if token]
    if not tokens:
        return "", "", ""
    if len(tokens) == 1:
        return tokens[0], "", ""
    if len(tokens) == 2:
        return tokens[0], tokens[1], ""
    if len(tokens) == 3:
        return tokens[0], tokens[1], tokens[2]
    if len(tokens) == 4:
        return " ".join(tokens[:2]), tokens[2], tokens[3]
    if len(tokens) == 5:
        return " ".join(tokens[:2]), " ".join(tokens[2:4]), tokens[4]
    return " ".join(tokens[:2]), " ".join(tokens[2:4]), " ".join(tokens[4:])


def _parse_row_block(block: str) -> ParsedStudentRow | None:
    compact = _clean_text(block)
    if not compact:
        return None
    start = re.match(r"^(?P<sno>\d+)\.?\s+(?P<adm_no>\d+)\s+(?P<adm_date>\d{2}-[A-Za-z]{3}-\d{4})\s+(?P<rest>.+)$", compact)
    if not start:
        return None

    rest = start.group("rest")
    passout_match = PASSOUT_PATTERN.match(rest)
    class_match = passout_match or CLASS_PATTERN.match(rest)
    if not class_match:
        return None

    class_raw = "PASSOUT" if passout_match else class_match.group("class")
    class_key = class_raw.upper()
    class_name = CLASS_MAP.get(class_key, class_raw)
    section = (class_match.groupdict().get("section") or "A").strip().upper()
    remainder = class_match.group("rest").strip()

    gd_match = re.search(r"\b(?P<gender>[MF])\s*=*\s*(?P<dob>\d{2}-[A-Za-z]{3}-\d{4})\b", remainder)
    pre_gender = remainder[:gd_match.start()].strip() if gd_match else remainder
    post_gender = remainder[gd_match.end():].strip() if gd_match else ""

    student_name, father_name, mother_name = _split_parent_names(pre_gender)
    normalized_post = post_gender.replace("GENER AL", "GENERAL").replace("GEN ER", "GENERAL")
    category_match = re.search(r"\b(GENERAL|GENER|OBC|SC|ST|EWS|BC)\b", normalized_post, flags=re.IGNORECASE)
    category = (category_match.group(1) if category_match else "").upper().replace("GENER", "GENERAL")
    if category_match:
        before_category = normalized_post[:category_match.start()].strip(" ,-")
        after_category = normalized_post[category_match.end():].strip(" ,-")
        after_category = re.sub(r"\b\d{4,12}\b", " ", after_category)
        after_category = re.sub(r"\bAL\b", " ", after_category).strip()
        address_part = re.sub(r"\s+", " ", f"{before_category} {after_category}").strip(" ,-")
    else:
        address_part = normalized_post
    numbers = re.findall(r"\b\d{4,12}\b", normalized_post)
    contact_no = next((num for num in numbers if len(num) == 10), "")
    aadhar_no = next((num for num in numbers if len(num) == 12), "")
    srn_no = ""
    if numbers:
        trailing = numbers[-1]
        if trailing not in {contact_no, aadhar_no} and len(trailing) <= 6:
            srn_no = trailing

    return ParsedStudentRow(
        admission_no=start.group("adm_no"),
        admission_date=start.group("adm_date"),
        class_name=class_name,
        section=section,
        name=student_name,
        father_name=father_name,
        mother_name=mother_name,
        gender={"M": "Male", "F": "Female"}.get((gd_match.group("gender") if gd_match else "").upper(), ""),
        dob=gd_match.group("dob") if gd_match else "",
        address=address_part,
        category=category,
        contact_no=contact_no,
        aadhar_no=aadhar_no,
        srn_no=srn_no,
        source_raw=compact,
    )


def parse_student_pdf_text(text: str) -> List[ParsedStudentRow]:
    rows: List[ParsedStudentRow] = []
    for page in re.split(r"=== PAGE \d+ ===", text):
        lines = [line.strip() for line in page.splitlines()]
        current: List[str] = []
        for line in lines:
            if not line or line.startswith("Page ") or line.startswith("Student List Detailed") or line.startswith("R.S MEMORIAL"):
                continue
            if ROW_START.match(line):
                if current:
                    parsed = _parse_row_block(" ".join(current))
                    if parsed:
                        rows.append(parsed)
                current = [line]
            elif current:
                current.append(line)
        if current:
            parsed = _parse_row_block(" ".join(current))
            if parsed:
                rows.append(parsed)
    return rows


def build_csv_from_rows(rows: List[ParsedStudentRow]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "Adm No",
        "Adm Date",
        "Class",
        "Section",
        "Name",
        "Father Name",
        "Mother Name",
        "Gen",
        "DOB",
        "Address",
        "Category",
        "Contact No",
        "Aadhar No",
        "SRN No",
        "Remarks",
        "Source Raw",
    ])
    for row in rows:
        writer.writerow([
            row.admission_no,
            row.admission_date,
            row.class_name,
            row.section,
            row.name,
            row.father_name,
            row.mother_name,
            row.gender,
            row.dob,
            row.address,
            row.category,
            row.contact_no,
            row.aadhar_no,
            row.srn_no,
            row.remarks,
            row.source_raw,
        ])
    return buffer.getvalue()


def convert_student_pdf_to_csv(pdf_path: str) -> tuple[str, int]:
    text = extract_pdf_text(pdf_path)
    rows = parse_student_pdf_text(text)
    return build_csv_from_rows(rows), len(rows)

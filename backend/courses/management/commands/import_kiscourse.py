import csv
from pathlib import Path
from urllib.parse import urlparse

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from courses.models import Course, University


def _parse_int(value):
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def _trim(value, limit):
    if value is None:
        return ""
    value = str(value).strip()
    return value[:limit]


def _guess_university_name(provider_id, course_url):
    hostname = ""
    if course_url:
        hostname = urlparse(course_url).hostname or ""
        hostname = hostname.lower().removeprefix("www.")

    if hostname:
        return f"{hostname} (UKPRN {provider_id})"[:255]
    return f"Provider UKPRN {provider_id}"[:255]


def _normalize_row(row):
    provider_id = _trim(row.get("UKPRN") or row.get("PUBUKPRN"), 128)
    title = _trim(row.get("TITLE") or row.get("TITLEW"), 255)
    if not provider_id or not title:
        return None

    course_url = _trim(row.get("CRSEURL") or row.get("CRSEURLW"), 500)
    course_external_id = _trim(row.get("KISCOURSEID") or row.get("KISAIMCODE") or row.get("UCASPROGID"), 128)
    study_mode = _trim(row.get("KISMODE"), 8)
    subject_area = _trim(row.get("HECOS"), 255)
    duration_years = _parse_int(row.get("NUMSTAGE"))

    return {
        "provider_id": provider_id,
        "title": title,
        "course_url": course_url,
        "course_external_id": course_external_id,
        "study_mode": study_mode,
        "subject_area": subject_area,
        "duration_years": duration_years,
    }


class Command(BaseCommand):
    help = "Import KISCOURSE.csv into University/Course tables."

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv",
            default="KISCOURSE.csv",
            help="Path to KISCOURSE CSV file. Default: KISCOURSE.csv at repo root.",
        )
        parser.add_argument("--limit", type=int, default=None, help="Optional row limit for testing.")
        parser.add_argument("--batch-size", type=int, default=2000, help="Bulk write batch size.")
        parser.add_argument("--country", default="UK", help="Country value for created universities.")
        parser.add_argument("--dry-run", action="store_true", help="Parse/plan only, do not write DB.")

    def handle(self, *args, **options):
        csv_path = Path(options["csv"]).expanduser()
        if not csv_path.is_absolute():
            csv_path = Path.cwd() / csv_path
        if not csv_path.exists() and csv_path.name == "KISCOURSE.csv":
            fallback = Path.cwd().parent / "KISCOURSE.csv"
            if fallback.exists():
                csv_path = fallback
        if not csv_path.exists():
            raise CommandError(f"CSV file not found: {csv_path}")

        limit = options["limit"]
        batch_size = options["batch_size"]
        country = _trim(options["country"], 64) or "UK"
        dry_run = options["dry_run"]

        normalized_rows = []
        providers = set()

        self.stdout.write(f"Reading {csv_path} ...")
        with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
            reader = csv.DictReader(fh)
            for idx, row in enumerate(reader, start=1):
                if limit and idx > limit:
                    break

                normalized = _normalize_row(row)
                if not normalized:
                    continue
                normalized_rows.append(normalized)
                providers.add(normalized["provider_id"])

        self.stdout.write(
            f"Parsed rows: {len(normalized_rows)} (providers: {len(providers)})."
        )
        if not normalized_rows:
            self.stdout.write(self.style.WARNING("No valid rows found."))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run complete. No database writes."))
            return

        with transaction.atomic():
            existing_unis = {
                uni.discover_uni_id: uni
                for uni in University.objects.filter(discover_uni_id__in=providers)
            }

            to_create_unis = []
            for provider_id in providers:
                if provider_id in existing_unis:
                    continue
                sample_row = next((r for r in normalized_rows if r["provider_id"] == provider_id), None)
                guessed_name = _guess_university_name(provider_id, (sample_row or {}).get("course_url", ""))
                to_create_unis.append(
                    University(name=guessed_name, discover_uni_id=provider_id, country=country)
                )

            if to_create_unis:
                University.objects.bulk_create(to_create_unis, batch_size=batch_size)
                existing_unis = {
                    uni.discover_uni_id: uni
                    for uni in University.objects.filter(discover_uni_id__in=providers)
                }

            university_ids = [u.id for u in existing_unis.values()]
            existing_courses = {
                (
                    c.university_id,
                    c.discover_uni_course_id,
                    c.study_mode,
                    c.title,
                ): c
                for c in Course.objects.filter(university_id__in=university_ids).only(
                    "id",
                    "university_id",
                    "discover_uni_course_id",
                    "study_mode",
                    "title",
                    "subject_area",
                    "duration_years",
                    "course_url",
                )
            }

            create_buffer = []
            update_buffer = []
            seen_keys = set()

            for row in normalized_rows:
                uni = existing_unis.get(row["provider_id"])
                if not uni:
                    continue

                key = (
                    uni.id,
                    row["course_external_id"],
                    row["study_mode"],
                    row["title"],
                )
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                existing = existing_courses.get(key)
                if not existing:
                    create_buffer.append(
                        Course(
                            university_id=uni.id,
                            title=row["title"],
                            discover_uni_course_id=row["course_external_id"],
                            subject_area=row["subject_area"],
                            duration_years=row["duration_years"],
                            study_mode=row["study_mode"],
                            course_url=row["course_url"],
                        )
                    )
                    continue

                changed = False
                if row["subject_area"] and existing.subject_area != row["subject_area"]:
                    existing.subject_area = row["subject_area"]
                    changed = True
                if row["duration_years"] and existing.duration_years != row["duration_years"]:
                    existing.duration_years = row["duration_years"]
                    changed = True
                if row["course_url"] and existing.course_url != row["course_url"]:
                    existing.course_url = row["course_url"]
                    changed = True

                if changed:
                    update_buffer.append(existing)

            if create_buffer:
                Course.objects.bulk_create(create_buffer, batch_size=batch_size)

            if update_buffer:
                Course.objects.bulk_update(
                    update_buffer,
                    fields=["subject_area", "duration_years", "course_url"],
                    batch_size=batch_size,
                )

        self.stdout.write(
            self.style.SUCCESS(
                "Import complete. "
                f"Universities created: {len(to_create_unis)} | "
                f"Courses created: {len(create_buffer)} | "
                f"Courses updated: {len(update_buffer)}"
            )
        )

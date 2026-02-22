#!/usr/bin/env python3
"""Bootstrap KISCOURSE data on a server.

Runs selected pipeline steps:
1) import KISCOURSE.csv into DB
2) map university names
3) scrape modules from course URLs
"""

import argparse
import os
import sys
from pathlib import Path


def _as_repo_default(csv_value):
    path = Path(csv_value).expanduser()
    if path.is_absolute():
        return str(path)

    cwd = Path.cwd()
    candidate = cwd / path
    if candidate.exists():
        return str(candidate)

    fallback = cwd.parent / path
    if fallback.exists():
        return str(fallback)

    return str(candidate)


def main():
    parser = argparse.ArgumentParser(description="Run KISCOURSE import/mapping/scraping pipeline")
    parser.add_argument("--settings", default="config.settings", help="Django settings module")

    parser.add_argument("--skip-import", action="store_true", help="Skip import_kiscourse step")
    parser.add_argument("--csv", default="KISCOURSE.csv", help="Path to CSV for import")
    parser.add_argument("--import-limit", type=int, default=None, help="Limit rows for import")
    parser.add_argument("--batch-size", type=int, default=2000, help="Batch size for import")

    parser.add_argument("--skip-map-unis", action="store_true", help="Skip university name mapping step")
    parser.add_argument("--mapping-csv", default="", help="Optional UKPRN->name mapping CSV")
    parser.add_argument("--institution-csv", default="", help="Discover Uni INSTITUTION.csv path")
    parser.add_argument(
        "--institution-name-column",
        default="",
        help="Optional explicit name column for INSTITUTION.csv (e.g. INSTNAME)",
    )
    parser.add_argument(
        "--map-limit",
        type=int,
        default=None,
        help="Max universities to map (default: all matching universities).",
    )
    parser.add_argument("--map-all", action="store_true", help="Map all universities, not only placeholders")

    parser.add_argument("--skip-scrape", action="store_true", help="Skip module scraping step")
    parser.add_argument("--scrape-limit", type=int, default=1000, help="Max courses to scrape")
    parser.add_argument("--provider-ukprn", default="", help="Only scrape courses for one provider")
    parser.add_argument("--overwrite", action="store_true", help="Re-scrape even if modules already stored")
    parser.add_argument("--sleep", type=float, default=0.2, help="Delay between scraping requests")

    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout for mapping/scraping")
    parser.add_argument("--insecure", action="store_true", help="Disable SSL verification for mapping/scraping")
    parser.add_argument("--dry-run", action="store_true", help="Dry run for all steps")

    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", args.settings)

    try:
        import django

        django.setup()
        from django.core.management import call_command
    except Exception as exc:
        print(f"Failed to initialize Django: {exc}", file=sys.stderr)
        return 1

    if not args.skip_import:
        print("[1/3] Importing KISCOURSE ...")
        call_command(
            "import_kiscourse",
            csv=_as_repo_default(args.csv),
            limit=args.import_limit,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
        )
    else:
        print("[1/3] Skipped import")

    if not args.skip_map_unis:
        print("[2/3] Mapping university names ...")
        call_command(
            "map_university_names",
            mapping_csv=args.mapping_csv,
            institution_csv=_as_repo_default(args.institution_csv) if args.institution_csv else "",
            institution_name_column=args.institution_name_column,
            kiscourse_csv=_as_repo_default(args.csv),
            limit=args.map_limit,
            timeout=args.timeout,
            insecure=args.insecure,
            all=args.map_all,
            dry_run=args.dry_run,
        )
    else:
        print("[2/3] Skipped university mapping")

    if not args.skip_scrape:
        print("[3/3] Scraping course modules ...")
        call_command(
            "scrape_course_modules",
            limit=args.scrape_limit,
            timeout=args.timeout,
            sleep=args.sleep,
            insecure=args.insecure,
            overwrite=args.overwrite,
            provider_ukprn=args.provider_ukprn,
            dry_run=args.dry_run,
        )
    else:
        print("[3/3] Skipped module scraping")

    print("Pipeline complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

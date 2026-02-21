import csv
import re
import ssl
from collections import Counter, defaultdict
from pathlib import Path
from urllib import error, request
from urllib.parse import urlparse

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from courses.models import Course, University

ORG_KEYWORDS = (
    "university",
    "college",
    "institute",
    "school",
    "academy",
)


def _clean(text):
    return re.sub(r"\s+", " ", (text or "")).strip()


def _download(url, timeout=15, insecure=False):
    req = request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        },
    )
    context = ssl._create_unverified_context() if insecure else None
    with request.urlopen(req, timeout=timeout, context=context) as response:
        body = response.read()

    for enc in ("utf-8", "latin-1"):
        try:
            return body.decode(enc)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8", errors="ignore")


def _parse_title(html):
    m = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return ""
    title = re.sub(r"<[^>]+>", " ", m.group(1))
    return _clean(title)


def _parse_og_site_name(html):
    m = re.search(
        r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        flags=re.IGNORECASE,
    )
    if not m:
        m = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:site_name["\']',
            html,
            flags=re.IGNORECASE,
        )
    return _clean(m.group(1)) if m else ""


def _extract_org_candidate(text):
    text = _clean(text)
    if not text:
        return ""

    parts = [p.strip() for p in re.split(r"\s+[|\-–:]\s+", text) if p.strip()]
    for part in parts:
        lowered = part.lower()
        if any(keyword in lowered for keyword in ORG_KEYWORDS):
            return part[:255]

    lowered = text.lower()
    if any(keyword in lowered for keyword in ORG_KEYWORDS):
        return text[:255]

    return ""


def _guess_from_domain(course_url):
    host = (urlparse(course_url).hostname or "").lower().removeprefix("www.")
    if not host:
        return ""

    first = host.split(".")[0]
    first = re.sub(r"[-_]+", " ", first)
    if len(first) < 3:
        return ""

    return " ".join(word.capitalize() for word in first.split())[:255]


def _load_mapping(mapping_csv):
    path = Path(mapping_csv).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        raise CommandError(f"Mapping CSV not found: {path}")

    mapping = {}
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        headers = [h.lower() for h in (reader.fieldnames or [])]

        ukprn_key = None
        name_key = None

        for candidate in ("ukprn", "provider_id", "discover_uni_id"):
            if candidate in headers:
                ukprn_key = reader.fieldnames[headers.index(candidate)]
                break

        for candidate in ("name", "provider_name", "university_name", "institution_name"):
            if candidate in headers:
                name_key = reader.fieldnames[headers.index(candidate)]
                break

        if not ukprn_key or not name_key:
            raise CommandError(
                "Mapping CSV must include UKPRN + name columns (e.g. ukprn,university_name)."
            )

        for row in reader:
            ukprn = _clean(row.get(ukprn_key))
            name = _clean(row.get(name_key))
            if not ukprn or not name:
                continue
            mapping[ukprn] = name[:255]

    return mapping


def _load_mapping_auto(csv_path, explicit_name_column=""):
    path = Path(csv_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        raise CommandError(f"CSV not found: {path}")

    mapping = {}
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        lowered_lookup = {name.lower(): name for name in fieldnames}

        ukprn_key = None
        for candidate in ("ukprn", "pubukprn", "provider_id", "discover_uni_id"):
            if candidate in lowered_lookup:
                ukprn_key = lowered_lookup[candidate]
                break

        if not ukprn_key:
            raise CommandError(
                f"Could not find UKPRN column in {path.name}. Expected one of: UKPRN, PUBUKPRN, provider_id."
            )

        name_key = None
        if explicit_name_column:
            for actual in fieldnames:
                if actual.lower() == explicit_name_column.lower():
                    name_key = actual
                    break
            if not name_key:
                raise CommandError(
                    f"Column '{explicit_name_column}' not found in {path.name}. Available: {', '.join(fieldnames)}"
                )
        else:
            preferred = (
                "institution_name",
                "providername",
                "provider_name",
                "instname",
                "name",
            )
            for candidate in preferred:
                if candidate in lowered_lookup:
                    name_key = lowered_lookup[candidate]
                    break

            if not name_key:
                for actual in fieldnames:
                    lowered = actual.lower()
                    if "name" in lowered and "url" not in lowered:
                        name_key = actual
                        break

        if not name_key:
            raise CommandError(
                f"Could not infer university-name column in {path.name}. "
                "Pass --institution-name-column explicitly."
            )

        for row in reader:
            ukprn = _clean(row.get(ukprn_key))
            name = _clean(row.get(name_key))
            if not ukprn or not name:
                continue
            mapping[ukprn] = name[:255]

    return mapping, ukprn_key, name_key, path


def _resolve_dataset_path(path_value):
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path
    cwd = Path.cwd()
    candidate = cwd / path
    if candidate.exists():
        return candidate
    fallback = cwd.parent / path
    if fallback.exists():
        return fallback
    return candidate


def _load_institution_mapping_weighted(institution_csv, explicit_name_column="", kiscourse_csv="KISCOURSE.csv"):
    institution_path = _resolve_dataset_path(institution_csv)
    if not institution_path.exists():
        raise CommandError(f"CSV not found: {institution_path}")

    # Parse INSTITUTION rows keyed by (PUBUKPRN, UKPRN)
    pair_to_name = {}
    with institution_path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        lowered_lookup = {name.lower(): name for name in fieldnames}

        pub_key = lowered_lookup.get("pubukprn")
        uk_key = lowered_lookup.get("ukprn")
        if not pub_key or not uk_key:
            raise CommandError("INSTITUTION.csv must include PUBUKPRN and UKPRN columns.")

        if explicit_name_column:
            name_key = next((x for x in fieldnames if x.lower() == explicit_name_column.lower()), None)
            if not name_key:
                raise CommandError(
                    f"Column '{explicit_name_column}' not found in {institution_path.name}. "
                    f"Available: {', '.join(fieldnames)}"
                )
        else:
            name_key = (
                lowered_lookup.get("legal_name")
                or lowered_lookup.get("institution_name")
                or lowered_lookup.get("providername")
                or lowered_lookup.get("provider_name")
                or lowered_lookup.get("instname")
                or lowered_lookup.get("name")
            )
            if not name_key:
                name_key = next(
                    (actual for actual in fieldnames if "name" in actual.lower() and "url" not in actual.lower()),
                    None,
                )
        if not name_key:
            raise CommandError(
                f"Could not infer university-name column in {institution_path.name}. "
                "Pass --institution-name-column explicitly."
            )

        for row in reader:
            pub = _clean(row.get(pub_key))
            uk = _clean(row.get(uk_key))
            name = _clean(row.get(name_key))
            if not pub or not uk or not name:
                continue
            pair_to_name[(pub, uk)] = name[:255]

    # Prefer canonical institution row where PUBUKPRN == UKPRN.
    # In this dataset release every UKPRN has a self-pair row and this avoids
    # franchise-heavy names overriding core provider names.
    self_pair_mapping = {}
    for (pub, uk), name in pair_to_name.items():
        if pub == uk:
            self_pair_mapping[uk] = name

    # Count KISCOURSE pair frequency to choose dominant institution name per UKPRN
    # as fallback for any UKPRN without self-pair rows.
    kiscourse_path = _resolve_dataset_path(kiscourse_csv)
    if not kiscourse_path.exists():
        # Fallback: no weighting possible; choose self-pair where possible, else first seen.
        mapping = dict(self_pair_mapping)
        for (_, uk), name in pair_to_name.items():
            mapping.setdefault(uk, name)
        return mapping, "UKPRN", f"{name_key} (self-pair preferred)", institution_path

    pair_counts = Counter()
    with kiscourse_path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            pub = _clean(row.get("PUBUKPRN"))
            uk = _clean(row.get("UKPRN"))
            if not pub or not uk:
                continue
            pair_counts[(pub, uk)] += 1

    by_ukprn_name_weight = defaultdict(Counter)
    for pair, weight in pair_counts.items():
        name = pair_to_name.get(pair)
        if not name:
            continue
        uk = pair[1]
        by_ukprn_name_weight[uk][name] += weight

    mapping = dict(self_pair_mapping)
    for uk, name_weights in by_ukprn_name_weight.items():
        if uk in mapping:
            continue
        # deterministic tie-break by name
        best = sorted(name_weights.items(), key=lambda x: (-x[1], x[0]))[0][0]
        mapping[uk] = best

    # Fill UKPRNs not present in KISCOURSE counts with first-seen value.
    for (_, uk), name in pair_to_name.items():
        mapping.setdefault(uk, name)

    return (
        mapping,
        "UKPRN",
        f"{name_key} (self-pair preferred; fallback weighted by PUBUKPRN+UKPRN in KISCOURSE)",
        institution_path,
    )


class Command(BaseCommand):
    help = "Map/clean University names using UKPRN mapping CSV and/or course page title heuristics."

    def add_arguments(self, parser):
        parser.add_argument(
            "--mapping-csv",
            default="",
            help="CSV with ukprn and university_name/provider_name columns.",
        )
        parser.add_argument(
            "--institution-csv",
            default="",
            help="Discover Uni INSTITUTION.csv path. Uses UKPRN/PUBUKPRN + inferred name column.",
        )
        parser.add_argument(
            "--institution-name-column",
            default="",
            help="Optional explicit name column in INSTITUTION.csv (e.g. INSTNAME).",
        )
        parser.add_argument(
            "--kiscourse-csv",
            default="KISCOURSE.csv",
            help="KISCOURSE CSV path used to weight INSTITUTION mapping by (PUBUKPRN, UKPRN).",
        )
        parser.add_argument("--limit", type=int, default=300, help="Max universities to process for heuristic mode.")
        parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout.")
        parser.add_argument("--insecure", action="store_true", help="Disable SSL verification for HTTP fetches.")
        parser.add_argument(
            "--all",
            action="store_true",
            help="Process all universities (default processes only placeholder/generic names).",
        )
        parser.add_argument("--dry-run", action="store_true", help="Show planned updates without writing.")

    def handle(self, *args, **options):
        mapping_csv = options["mapping_csv"].strip()
        institution_csv = options["institution_csv"].strip()
        institution_name_column = options["institution_name_column"].strip()
        kiscourse_csv = options["kiscourse_csv"].strip()
        limit = options["limit"]
        timeout = options["timeout"]
        insecure = options["insecure"]
        process_all = options["all"]
        dry_run = options["dry_run"]

        updated = 0
        skipped = 0
        failed = 0

        mapping = {}
        if institution_csv:
            institution_mapping, ukprn_key, name_key, resolved_path = _load_institution_mapping_weighted(
                institution_csv,
                explicit_name_column=institution_name_column,
                kiscourse_csv=kiscourse_csv or "KISCOURSE.csv",
            )
            mapping.update(institution_mapping)
            self.stdout.write(
                f"Loaded {len(institution_mapping)} mappings from {resolved_path} "
                f"(ukprn='{ukprn_key}', name='{name_key}')"
            )

        if mapping_csv:
            explicit_mapping = _load_mapping(mapping_csv)
            mapping.update(explicit_mapping)
            self.stdout.write(f"Loaded {len(explicit_mapping)} mappings from {mapping_csv}")

        base_qs = University.objects.all().order_by("id")
        if not process_all:
            base_qs = base_qs.filter(
                Q(name__icontains="ukprn")
                | Q(name__icontains=".ac.uk")
                | Q(name__icontains=".edu")
                | Q(name__icontains=".org")
            )

        processed = 0

        for university in base_qs.iterator(chunk_size=100):
            if processed >= limit:
                break
            processed += 1

            new_name = ""
            mapped = mapping.get(university.discover_uni_id, "")
            if mapped:
                new_name = mapped
            else:
                course_url = (
                    Course.objects.filter(university=university)
                    .exclude(course_url="")
                    .values_list("course_url", flat=True)
                    .first()
                )
                if not course_url:
                    skipped += 1
                    continue

                try:
                    html = _download(course_url, timeout=timeout, insecure=insecure)
                    og_name = _parse_og_site_name(html)
                    title_name = _parse_title(html)
                except (error.HTTPError, error.URLError, TimeoutError, ValueError) as exc:
                    failed += 1
                    self.stderr.write(f"[{university.id}] fetch failed: {exc}")
                    continue

                new_name = _extract_org_candidate(og_name) or _extract_org_candidate(title_name)
                if not new_name:
                    new_name = _guess_from_domain(course_url)

            if not new_name or new_name == university.name:
                skipped += 1
                continue

            self.stdout.write(f"[{university.id}] {university.name} -> {new_name}")
            if not dry_run:
                university.name = new_name[:255]
                university.save(update_fields=["name"])
            updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"University mapping complete. processed={processed} updated={updated} skipped={skipped} failed={failed} dry_run={dry_run}"
            )
        )

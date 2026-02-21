import re
import ssl
import time
from urllib import error, request

from django.core.management.base import BaseCommand
from django.utils import timezone

from courses.models import Course

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - handled at runtime
    BeautifulSoup = None


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

HEADING_KEYWORDS = (
    "module",
    "what you'll study",
    "what you will study",
    "course content",
    "course structure",
    "curriculum",
    "units",
)

NOISE_PATTERNS = (
    "apply",
    "entry requirement",
    "fees",
    "tuition",
    "open day",
    "scholarship",
    "accommodation",
    "privacy",
    "cookie",
    "contact",
)


def _clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def _looks_like_module_title(text):
    if not text:
        return False
    text = _clean(text)

    if len(text) < 4 or len(text) > 120:
        return False
    if text.lower().startswith("http"):
        return False

    lowered = text.lower()
    if any(pattern in lowered for pattern in NOISE_PATTERNS):
        return False

    words = text.split()
    if len(words) > 14:
        return False

    return any(char.isalpha() for char in text)


def _dedupe(values, limit=30):
    seen = set()
    output = []
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
        if len(output) >= limit:
            break
    return output


def _extract_modules_from_html(html):
    if BeautifulSoup is None:
        raise RuntimeError(
            "beautifulsoup4 is required for scraping. Install dependencies from backend/requirements.txt"
        )

    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "svg", "noscript"]):
        tag.decompose()

    modules = []
    headings = soup.find_all(["h1", "h2", "h3", "h4"])

    for heading in headings:
        heading_text = _clean(heading.get_text(" ", strip=True)).lower()
        if not any(keyword in heading_text for keyword in HEADING_KEYWORDS):
            continue

        sibling = heading
        scanned = 0
        while scanned < 250:
            sibling = sibling.find_next()
            if sibling is None:
                break
            scanned += 1

            if sibling.name in {"h1", "h2"} and sibling is not heading:
                break

            if sibling.name in {"li", "h3", "h4", "p"}:
                text = _clean(sibling.get_text(" ", strip=True))
                if _looks_like_module_title(text):
                    modules.append(text)

    if not modules:
        for li in soup.find_all("li"):
            text = _clean(li.get_text(" ", strip=True))
            if _looks_like_module_title(text):
                modules.append(text)

    return _dedupe(modules, limit=30)


def _download(url, timeout, insecure=False):
    req = request.Request(url, headers={"User-Agent": USER_AGENT})
    ssl_context = ssl._create_unverified_context() if insecure else None
    with request.urlopen(req, timeout=timeout, context=ssl_context) as response:
        payload = response.read()

    for encoding in ("utf-8", "latin-1"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="ignore")


class Command(BaseCommand):
    help = "Scrape likely module titles from each course URL and store in Course.scraped_modules."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100, help="Max number of courses to scrape.")
        parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout in seconds.")
        parser.add_argument("--sleep", type=float, default=0.3, help="Delay between requests.")
        parser.add_argument("--insecure", action="store_true", help="Disable SSL certificate verification.")
        parser.add_argument("--overwrite", action="store_true", help="Re-scrape courses that already have modules.")
        parser.add_argument(
            "--provider-ukprn",
            default="",
            help="Only scrape courses belonging to this provider UKPRN.",
        )
        parser.add_argument(
            "--course-id",
            action="append",
            type=int,
            default=[],
            help="Specific course id to scrape. Can be provided multiple times.",
        )
        parser.add_argument("--dry-run", action="store_true", help="Do not persist updates.")

    def handle(self, *args, **options):
        if BeautifulSoup is None:
            self.stderr.write(
                self.style.ERROR(
                    "Missing dependency: beautifulsoup4. Run `pip install -r backend/requirements.txt`."
                )
            )
            return

        limit = options["limit"]
        timeout = options["timeout"]
        sleep_seconds = options["sleep"]
        insecure = options["insecure"]
        overwrite = options["overwrite"]
        provider_ukprn = options["provider_ukprn"].strip()
        course_ids = options["course_id"]
        dry_run = options["dry_run"]

        queryset = Course.objects.select_related("university").exclude(course_url="").order_by("id")
        if provider_ukprn:
            queryset = queryset.filter(university__discover_uni_id=provider_ukprn)
        if course_ids:
            queryset = queryset.filter(id__in=course_ids)

        processed = 0
        updated = 0
        skipped = 0
        failed = 0

        for course in queryset.iterator(chunk_size=200):
            if processed >= limit:
                break
            processed += 1

            if not overwrite and course.scraped_modules:
                skipped += 1
                continue

            try:
                html = _download(course.course_url, timeout=timeout, insecure=insecure)
                modules = _extract_modules_from_html(html)
            except (RuntimeError, error.HTTPError, error.URLError, TimeoutError, ValueError) as exc:
                failed += 1
                self.stderr.write(f"[{course.id}] scrape failed: {exc}")
                continue

            if not modules:
                skipped += 1
                continue

            if not dry_run:
                course.scraped_modules = modules
                course.modules_last_scraped_at = timezone.now()
                course.save(update_fields=["scraped_modules", "modules_last_scraped_at"])

            updated += 1
            self.stdout.write(f"[{course.id}] {course.title} -> {len(modules)} modules")
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        summary = (
            f"Scrape complete. processed={processed} updated={updated} "
            f"skipped={skipped} failed={failed} dry_run={dry_run}"
        )
        self.stdout.write(self.style.SUCCESS(summary))

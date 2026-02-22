import json
import re
import ssl
from urllib import error, request
from urllib.parse import urljoin
from html import unescape

from django.conf import settings
from django.utils import timezone

from .models import Course, University

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - handled at runtime
    BeautifulSoup = None


SCRAPER_USER_AGENT = (
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
    "navigation link in category",
    "press escape key",
    "return to main menu",
    "register your interest",
    "chat to a student",
    "order a prospectus",
    "department of ",
    "faculty of ",
    "full time",
    "part time",
    "study abroad option",
    "with a year in industry",
    "modules, teaching and learning",
    "what you'll learn",
    "option modules may include",
    "core modules",
    "additional course costs",
    "for students entering",
    "included in the cost of your course",
    "free wifi via eduroam",
    "24/7 library and student it support",
    "skills workshops and resources",
    "library membership",
    "loan of high-end media equipment",
)

SINGLE_WORD_NOISE = {
    "students",
    "student",
    "staff",
    "alumni",
    "compulsory",
    "optional",
    "required",
    "core",
}

PROGRAMME_AWARD_RE = re.compile(r"\b(bsc|ba|beng|meng|msci|msc|ma|mres|mphil|phd|foundation)\b", re.IGNORECASE)
DURATION_RE = re.compile(r"\b(one|two|three|four|five|six|[1-9])\s+years?\b", re.IGNORECASE)
SECTION_HINT_RE = re.compile(
    r"(module|curriculum|course[-_ ]?content|course[-_ ]?structure|what[-_ ]?you[-_ ]?ll[-_ ]?study|units?)",
    re.IGNORECASE,
)

REDUX_DATA_ANCHOR = "window.REDUX_DATA = "
STARTUP_SCRIPT_RE = re.compile(
    r'<script[^>]+src=["\']([^"\']*startup[^"\']+\.js[^"\']*)["\']',
    re.IGNORECASE,
)
CONTENSIS_API_FULL_RE = re.compile(r'api:\s*"(https://api-[^"]+\.cloud\.contensis\.com)"')
CONTENSIS_PROJECT_RE = re.compile(r'projectId:\s*"([^"]+)"')
CONTENSIS_TOKEN_RE = re.compile(r'accessToken:\s*"([^"]+)"')
CONTENSIS_ALIAS_RE = re.compile(r'context\.ALIAS\s*=\s*"([^"]+)"')
MODULES_MODAL_URL_RE = re.compile(r'"modulesModalUrl":"([^"]+)"', re.IGNORECASE)
YEAR_ONLY_RE = re.compile(r"^year\s+[1-9][0-9]*$", re.IGNORECASE)
CREDITS_ONLY_RE = re.compile(r"^[0-9]{1,3}\s*credits?$", re.IGNORECASE)


def _clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


def _looks_like_module_title(text):
    if not text:
        return False
    text = _clean_text(text)

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

    if len(words) == 1 and lowered in SINGLE_WORD_NOISE:
        return False

    # Filter program title rows like "Artificial Intelligence BSc 3 years Full time".
    if PROGRAMME_AWARD_RE.search(text) and DURATION_RE.search(text):
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


def _is_high_confidence_module_title(text):
    if not _looks_like_module_title(text):
        return False

    lowered = _clean_text(text).lower()

    if YEAR_ONLY_RE.match(lowered):
        return False
    if lowered in {"placement year", "foundation year"}:
        return False
    if CREDITS_ONLY_RE.match(lowered):
        return False

    if any(token in lowered for token in ("you will", "you'll", "this module", "the following", "what you")):
        return False
    if lowered.startswith(("the ", "this ", "these ", "those ", "you ", "we ")):
        return False
    if lowered.endswith("."):
        return False
    if text and text[0].isalpha() and text[0].islower():
        return False

    # Long unpunctuated lines are often copied explanatory text, not titles.
    words = lowered.split()
    if len(words) >= 11 and all(mark not in lowered for mark in (",", "&", ":", "-", "/")):
        return False

    return True


def _normalize_module_candidates(values, strict=True, limit=30):
    normalized = []
    for value in values or []:
        if not isinstance(value, str):
            continue
        text = _clean_text(unescape(value))
        if not text:
            continue

        if strict:
            if not _is_high_confidence_module_title(text):
                continue
        else:
            if not _looks_like_module_title(text):
                continue
        normalized.append(text)
    return _dedupe(normalized, limit=limit)


def _normalize_user_modules(values, limit=60):
    modules = []
    for value in values or []:
        if not isinstance(value, str):
            continue
        text = _clean_text(value)
        if not text:
            continue
        lowered = text.lower()
        if YEAR_ONLY_RE.match(lowered) or CREDITS_ONLY_RE.match(lowered):
            continue
        if len(text) < 2 or len(text) > 160:
            continue
        modules.append(text)
    return _dedupe(modules, limit=limit)


def _default_modules_for_course(course_title="", subject_area=""):
    title = (course_title or "").lower()
    subject = (subject_area or "").lower()
    signal = f"{title} {subject}"

    if any(word in signal for word in ("artificial intelligence", "ai", "machine learning")):
        return [
            "Programming Foundations",
            "Discrete Mathematics",
            "Linear Algebra and Calculus",
            "Probability and Statistics",
            "Data Structures and Algorithms",
            "Machine Learning",
            "Deep Learning",
            "AI Ethics and Responsible AI",
        ]
    if any(word in signal for word in ("computer science", "software", "informatics")):
        return [
            "Programming Foundations",
            "Discrete Mathematics",
            "Data Structures and Algorithms",
            "Computer Systems",
            "Databases",
            "Software Engineering",
            "Networks and Security",
            "Final Year Project",
        ]
    if any(word in signal for word in ("data science", "analytics")):
        return [
            "Python for Data Analysis",
            "Linear Algebra and Calculus",
            "Probability and Statistics",
            "Data Management",
            "Machine Learning",
            "Data Visualization",
            "Experimental Design",
            "Capstone Project",
        ]
    if any(word in signal for word in ("business", "economics", "finance", "management")):
        return [
            "Business Fundamentals",
            "Microeconomics",
            "Macroeconomics",
            "Quantitative Methods",
            "Corporate Finance",
            "Strategic Management",
            "Applied Econometrics",
            "Final Year Project",
        ]
    if any(word in signal for word in ("biochemistry", "biology", "biomedical", "pharmacology", "chemistry")):
        return [
            "Cell Biology",
            "Molecular Biology",
            "Genetics and Gene Expression",
            "Biochemistry Laboratory Skills",
            "Metabolism and Enzymes",
            "Microbiology",
            "Research Methods",
            "Final Year Research Project",
        ]

    return [
        "Foundations",
        "Core Concepts",
        "Methods and Practice",
        "Intermediate Topics",
        "Advanced Topics",
        "Applied Project",
    ]


class CourseModuleScraperService:
    """Cache-first course module retrieval that scrapes a single course page when required."""

    def __init__(self, timeout=15, insecure=False, max_modules=30):
        self.timeout = timeout
        self.insecure = insecure
        self.max_modules = max_modules

    def get_or_scrape(self, course, refresh=False):
        if course.scraped_modules and not refresh:
            return list(course.scraped_modules), False

        if not course.course_url:
            raise ValueError("This course has no course_url for module scraping.")

        modules = []
        try:
            modules = self._scrape_url(course.course_url)
        except error.HTTPError as exc:
            if exc.code not in {403, 429, 503}:
                raise
        except error.URLError:
            pass

        # For blocked/temporary failures keep existing curated modules if available.
        if not modules and course.scraped_modules:
            return list(course.scraped_modules), False

        if not modules:
            modules = self._fallback_modules_from_course(course)
        course.scraped_modules = modules
        course.modules_last_scraped_at = timezone.now()
        course.save(update_fields=["scraped_modules", "modules_last_scraped_at"])
        return modules, True

    def _scrape_url(self, url):
        html = self._download(url)
        modules = self._extract_modules_from_html(html, page_url=url)
        return _dedupe(modules, limit=self.max_modules)

    def _download(self, url, headers=None):
        request_headers = {"User-Agent": SCRAPER_USER_AGENT}
        if headers:
            request_headers.update(headers)
        req = request.Request(url, headers=request_headers)
        context = ssl._create_unverified_context() if self.insecure else None
        with request.urlopen(req, timeout=self.timeout, context=context) as response:
            payload = response.read()

        for encoding in ("utf-8", "latin-1"):
            try:
                return payload.decode(encoding)
            except UnicodeDecodeError:
                continue
        return payload.decode("utf-8", errors="ignore")

    def _extract_modules_from_html(self, html, page_url=None):
        modules = self._extract_modules_from_contensis_entry_api(html, page_url=page_url)
        if modules:
            return modules
        modules = self._extract_modules_from_modal_endpoint(html, page_url=page_url)
        if modules:
            return modules

        if BeautifulSoup is None:
            raise RuntimeError(
                "Missing dependency: beautifulsoup4. Install with `pip install -r backend/requirements.txt`."
            )

        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "svg", "noscript"]):
            tag.decompose()

        modules = []
        headings = soup.find_all(["h1", "h2", "h3", "h4"])
        for heading in headings:
            heading_text = _clean_text(heading.get_text(" ", strip=True)).lower()
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
                    text = _clean_text(sibling.get_text(" ", strip=True))
                    if _looks_like_module_title(text):
                        modules.append(text)

        if not modules:
            modules = self._extract_from_hint_sections(soup)

        return modules

    def _extract_modules_from_modal_endpoint(self, html, page_url):
        if not page_url:
            return []

        matches = MODULES_MODAL_URL_RE.findall(html)
        if not matches:
            return []

        modules = []
        for raw_url in matches[:3]:
            modal_url = self._decode_embedded_url(raw_url)
            if not modal_url:
                continue
            full_url = urljoin(page_url, modal_url)
            try:
                modal_html = self._download(full_url)
            except Exception:
                continue
            modules.extend(self._extract_modules_from_modal_html(modal_html))
        return modules

    def _decode_embedded_url(self, raw_url):
        if not raw_url:
            return ""
        try:
            return json.loads(f"\"{raw_url}\"")
        except json.JSONDecodeError:
            return raw_url.replace("\\u0026", "&").replace("\\/", "/")

    def _extract_modules_from_modal_html(self, modal_html):
        modules = []
        if BeautifulSoup is None:
            for title in re.findall(r'class="title-type-5"[^>]*>([^<]+)</', modal_html, re.IGNORECASE):
                clean = _clean_text(unescape(title))
                if _looks_like_module_title(clean):
                    modules.append(clean)
            return modules

        soup = BeautifulSoup(modal_html, "html.parser")
        title_nodes = soup.select(".title-type-5")
        for node in title_nodes:
            text = _clean_text(node.get_text(" ", strip=True))
            if _looks_like_module_title(text):
                modules.append(text)
        return modules

    def _extract_modules_from_contensis_entry_api(self, html, page_url):
        redux_data = self._extract_redux_data(html)
        if not redux_data:
            return []

        entry_id = (
            redux_data.get("routing", {})
            .get("entry", {})
            .get("sys", {})
            .get("id")
        )
        if not entry_id:
            return []

        config = self._extract_contensis_config(html, page_url=page_url)
        if not config:
            return []

        entry_payload = self._fetch_contensis_entry(
            root_url=config["root_url"],
            project_id=config["project_id"],
            access_token=config["access_token"],
            entry_id=entry_id,
        )
        return self._extract_modules_from_contensis_payload(entry_payload)

    def _extract_redux_data(self, html):
        anchor_index = html.find(REDUX_DATA_ANCHOR)
        if anchor_index == -1:
            return {}

        object_start = html.find("{", anchor_index + len(REDUX_DATA_ANCHOR))
        if object_start == -1:
            return {}

        object_text = self._extract_balanced_js_object(html, object_start)
        if not object_text:
            return {}

        sanitized = re.sub(r":undefined(?=\s*[,}])", ":null", object_text)
        sanitized = re.sub(r":NaN(?=\s*[,}])", ":null", sanitized)
        sanitized = re.sub(r":Infinity(?=\s*[,}])", ":null", sanitized)

        try:
            return json.loads(sanitized)
        except json.JSONDecodeError:
            return {}

    def _extract_balanced_js_object(self, text, start_index):
        in_string = False
        quote = ""
        escaped = False
        depth = 0

        for index, char in enumerate(text[start_index:], start=start_index):
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    in_string = False
                continue

            if char in ('"', "'"):
                in_string = True
                quote = char
                continue

            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start_index : index + 1]

        return ""

    def _extract_contensis_config(self, html, page_url):
        if not page_url:
            return None

        startup_match = STARTUP_SCRIPT_RE.search(html)
        if not startup_match:
            return None

        startup_url = urljoin(page_url, startup_match.group(1))
        try:
            startup_js = self._download(startup_url)
        except Exception:
            return None

        project_match = CONTENSIS_PROJECT_RE.search(startup_js)
        token_match = CONTENSIS_TOKEN_RE.search(startup_js)
        if not token_match:
            token_match = re.search(r'context\.ACCESS_TOKEN\s*=\s*"([^"]+)"', startup_js)

        root_url = ""
        root_match = CONTENSIS_API_FULL_RE.search(startup_js)
        if root_match:
            root_url = root_match.group(1).strip()
        else:
            alias_match = CONTENSIS_ALIAS_RE.search(startup_js)
            if not alias_match:
                alias_match = re.search(r'var\s+alias\s*=\s*"([^"]+)"', startup_js)
            if alias_match:
                alias = alias_match.group(1).strip()
                root_url = f"https://api-{alias}.cloud.contensis.com"

        if not root_url or not project_match or not token_match:
            return None

        return {
            "root_url": root_url,
            "project_id": project_match.group(1).strip(),
            "access_token": token_match.group(1).strip(),
        }

    def _fetch_contensis_entry(self, root_url, project_id, access_token, entry_id):
        endpoint = (
            f"{root_url.rstrip('/')}/api/delivery/projects/{project_id}/entries/{entry_id}"
            "?versionStatus=latest"
        )
        try:
            payload = self._download(endpoint, headers={"accesstoken": access_token})
            return json.loads(payload)
        except Exception:
            return {}

    def _extract_modules_from_contensis_payload(self, payload):
        if not isinstance(payload, dict):
            return []

        modules = []
        for year in range(1, 8):
            modules.extend(self._extract_module_titles(payload.get(f"year{year}RequiredModules")))
            modules.extend(self._extract_module_titles(payload.get(f"year{year}OptionalModules")))
            modules.extend(self._extract_module_titles(payload.get(f"year{year}")))

            year_modules = payload.get(f"year{year}Modules")
            if isinstance(year_modules, dict):
                modules.extend(self._extract_module_titles(year_modules.get("requiredModules")))
                modules.extend(self._extract_module_titles(year_modules.get("optionalModules")))

        return [item for item in modules if _looks_like_module_title(item)]

    def _extract_module_titles(self, value):
        modules = []
        if isinstance(value, list):
            for item in value:
                modules.extend(self._extract_module_titles(item))
            return modules

        if isinstance(value, dict):
            title = value.get("entryTitle")
            if isinstance(title, str):
                modules.append(_clean_text(title))

            block_type = str(value.get("type", "")).strip().lower()
            if block_type == "modules":
                modules.extend(self._extract_module_titles(value.get("value")))

            for key in ("requiredModules", "optionalModules", "modules", "items"):
                if key in value:
                    modules.extend(self._extract_module_titles(value.get(key)))
            return modules

        if isinstance(value, str) and _looks_like_module_title(value):
            modules.append(_clean_text(value))

        return modules

    def _extract_from_hint_sections(self, soup):
        modules = []
        hints = []

        for tag in soup.find_all(["section", "article", "div"]):
            attrs_text = " ".join(
                filter(
                    None,
                    [
                        tag.get("id", ""),
                        " ".join(tag.get("class", [])),
                        tag.get("data-testid", ""),
                        tag.get("aria-label", ""),
                    ],
                )
            )
            if SECTION_HINT_RE.search(attrs_text or ""):
                hints.append(tag)

        for container in hints[:25]:
            for candidate in container.find_all(["li", "h3", "h4", "p"]):
                text = _clean_text(candidate.get_text(" ", strip=True))
                if _looks_like_module_title(text):
                    modules.append(text)

        return modules

    def _fallback_modules_from_course(self, course):
        return _default_modules_for_course(course.title, course.subject_area)


class CourseModuleDraftService:
    """Generates module drafts as year-grouped JSON via Gemini with deterministic backup."""

    PAGE_CONTEXT_KEYWORDS = (
        "module",
        "year",
        "compulsory",
        "required",
        "optional",
        "what you'll study",
        "teaching",
        "curriculum",
        "course structure",
    )

    def __init__(self, enable_ai=True):
        self.enable_ai = enable_ai
        self.api_key = getattr(settings, "GEMINI_API_KEY", "")
        self.model = getattr(
            settings,
            "GEMINI_MODULES_MODEL",
            getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash"),
        )

    @property
    def is_ai_configured(self):
        return bool(self.api_key)

    def build_draft(self, course, raw_modules=None, context_text=""):
        raw_candidates = _normalize_module_candidates(raw_modules or [], strict=False, limit=120)
        ai_seed_candidates = _normalize_module_candidates(raw_modules or [], strict=True, limit=60)
        grounding_context = self._build_context_blob(
            course=course,
            raw_modules=ai_seed_candidates,
            context_text=context_text,
        )
        source = "heuristic"
        notes = ""
        model_used = None
        gemini_confidence = None
        error_code = ""
        retry_after_seconds = None
        draft_modules = []
        draft_years = []

        if self.enable_ai and self.api_key:
            try:
                ai_payload, gemini_confidence = self._generate_with_gemini(
                    course=course,
                    grounding_context=grounding_context,
                )
                ai_years = self._normalize_years_payload(ai_payload.get("years", []))
                ai_years = self._filter_years_by_grounding_context(ai_years, grounding_context)
                if not ai_years:
                    raise RuntimeError("Gemini output was not grounded in source content for this course.")

                ai_modules = self._extract_modules_from_years(ai_years)
                draft_modules = _normalize_module_candidates(ai_modules, strict=True, limit=40)
                if not draft_modules:
                    raise RuntimeError("Gemini returned no valid module titles.")
                if len(draft_modules) < 3:
                    raise RuntimeError("Gemini found too few grounded modules for a reliable draft.")

                allowed = {m.casefold() for m in draft_modules}
                cleaned_years = []
                for item in ai_years:
                    required = [m for m in item["required"] if m.casefold() in allowed]
                    optional = [m for m in item["optional"] if m.casefold() in allowed]
                    if required or optional:
                        cleaned_years.append(
                            {
                                "year": item["year"],
                                "required": required,
                                "optional": optional,
                            }
                        )
                draft_years = cleaned_years
                if not draft_years:
                    raise RuntimeError("Gemini returned empty year buckets after normalization.")

                source = "gemini"
                model_used = self.model
            except Exception as strict_exc:  # broad by design: always produce a draft
                strict_reason = str(strict_exc)
                if self._is_quota_error(strict_reason):
                    error_code = "quota_exceeded"
                    retry_after_seconds = self._extract_retry_after_seconds(strict_reason)
                    notes = self._quota_error_note(retry_after_seconds)
                else:
                    try:
                        ai_payload, inferred_confidence = self._generate_inferred_with_gemini(
                            course=course,
                            raw_modules=raw_candidates,
                            context_text=context_text,
                        )
                        ai_years = self._normalize_years_payload(ai_payload.get("years", []))
                        ai_years = self._relabel_years_sequential(ai_years)
                        ai_modules = self._extract_modules_from_years(ai_years)
                        draft_modules = _normalize_module_candidates(ai_modules, strict=True, limit=40)
                        if len(draft_modules) < 3:
                            raise RuntimeError("Gemini inferred output is too small.")

                        allowed = {m.casefold() for m in draft_modules}
                        cleaned_years = []
                        for item in ai_years:
                            required = [m for m in item["required"] if m.casefold() in allowed]
                            optional = [m for m in item["optional"] if m.casefold() in allowed]
                            if required or optional:
                                cleaned_years.append(
                                    {
                                        "year": item["year"],
                                        "required": required,
                                        "optional": optional,
                                    }
                                )
                        draft_years = cleaned_years
                        if not draft_years:
                            raise RuntimeError("Gemini inferred output had empty year buckets after normalization.")

                        source = "gemini_inferred"
                        model_used = self.model
                        if inferred_confidence is not None:
                            gemini_confidence = min(float(inferred_confidence), 0.65)
                        notes = f"Inferred draft used because grounded extraction was insufficient: {strict_reason}"
                    except Exception as inferred_exc:
                        inferred_reason = str(inferred_exc)
                        if self._is_quota_error(inferred_reason):
                            error_code = "quota_exceeded"
                            retry_after_seconds = self._extract_retry_after_seconds(inferred_reason)
                            if retry_after_seconds is None:
                                retry_after_seconds = self._extract_retry_after_seconds(strict_reason)
                            notes = self._quota_error_note(retry_after_seconds)
                        else:
                            notes = (
                                "Gemini unavailable, heuristic draft used: "
                                f"{strict_reason}; inferred attempt failed: {inferred_reason}"
                            )

        if not draft_modules:
            draft_modules = self._heuristic_draft(course=course, raw_modules=raw_candidates, context_text=context_text)
            draft_years = self._build_years_from_modules(draft_modules)
            source = "heuristic"

        confidence = self._confidence_score(
            source=source,
            raw_modules=raw_candidates,
            draft_modules=draft_modules,
            draft_years=draft_years,
            gemini_confidence=gemini_confidence,
        )
        needs_confirmation = confidence < 0.8

        return {
            "modules": draft_modules,
            "years": draft_years,
            "source": source,
            "confidence": confidence,
            "needs_user_confirmation": needs_confirmation,
            "raw_modules": raw_candidates,
            "notes": notes,
            "model": model_used,
            "error_code": error_code,
            "retry_after_seconds": retry_after_seconds,
        }

    def normalize_user_modules(self, values):
        return _normalize_user_modules(values, limit=60)

    def _heuristic_draft(self, course, raw_modules=None, context_text=""):
        candidates = []
        candidates.extend(raw_modules or [])
        candidates.extend(self._extract_modules_from_context_text(context_text))

        strict_modules = _normalize_module_candidates(candidates, strict=True, limit=30)
        if len(strict_modules) >= 4:
            return strict_modules
        if len(strict_modules) >= 2:
            return strict_modules
        if strict_modules:
            defaults = _default_modules_for_course(course.title, course.subject_area)
            merged = list(strict_modules)
            seen = {item.casefold() for item in merged}
            for title in defaults:
                key = title.casefold()
                if key in seen:
                    continue
                merged.append(title)
                seen.add(key)
                if len(merged) >= 8:
                    break
            return merged

        return _default_modules_for_course(course.title, course.subject_area)[:10]

    def _extract_modules_from_context_text(self, context_text):
        if not context_text:
            return []

        modules = []
        for line in context_text.splitlines():
            cleaned = re.sub(r"^\s*[-*•\d\.\)\(]+\s*", "", line)
            cleaned = _clean_text(unescape(cleaned))
            if cleaned:
                modules.append(cleaned)
        return modules

    def _generate_with_gemini(self, course, grounding_context):
        prompt = self._build_prompt(course=course, grounding_context=grounding_context)
        return self._request_gemini_json(prompt)

    def _generate_inferred_with_gemini(self, course, raw_modules, context_text):
        prompt = self._build_inferred_prompt(
            course=course,
            raw_modules=raw_modules,
            context_text=context_text,
        )
        return self._request_gemini_json(prompt)

    def _request_gemini_json(self, prompt):
        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
            f"?key={self.api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": self._gemini_response_schema(),
                "temperature": 0,
            },
        }

        req = request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=25) as response:
                data = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Gemini HTTP {exc.code}: {body[:160]}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Gemini network error: {exc.reason}") from exc

        text = self._extract_text_from_gemini(data)
        parsed = self._extract_json(text)
        if not isinstance(parsed, dict):
            raise RuntimeError("Gemini output must be a JSON object.")
        confidence = self._extract_confidence(parsed)
        return parsed, confidence

    def _gemini_response_schema(self):
        return {
            "type": "OBJECT",
            "properties": {
                "years": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "year": {"type": "STRING"},
                            "required": {
                                "type": "ARRAY",
                                "items": {"type": "STRING"},
                            },
                            "optional": {
                                "type": "ARRAY",
                                "items": {"type": "STRING"},
                            },
                        },
                        "required": ["year", "required", "optional"],
                    },
                },
                "confidence": {"type": "NUMBER"},
                "notes": {"type": "STRING"},
            },
            "required": ["years", "confidence", "notes"],
        }

    def _build_prompt(self, course, grounding_context):
        return (
            "You are extracting official university course modules grouped by study year. "
            "Return strict JSON only and follow the schema exactly; no markdown and no prose. "
            "Required schema: "
            '{"years":[{"year":"Year 1","required":["..."],"optional":["..."]}],"confidence":0.0,"notes":""}. '
            "Rules: return real module titles only; never return headings such as Compulsory, Optional, Year 1, What you'll learn; "
            "never return full explanatory sentences; exclude credits-only lines; no duplicate modules across all years; "
            "keep module titles concise (2-12 words). "
            "Every module title must be copied exactly from the provided context (no paraphrasing). "
            "If context is insufficient, return years as [] and explain briefly in notes. Do not invent modules. "
            f"University: {course.university.name}. "
            f"Course: {course.title}. "
            f"Subject area: {course.subject_area or 'not provided'}. "
            f"Course URL: {course.course_url or 'not provided'}. "
            f"Context: {grounding_context or 'none'}."
        )

    def _build_inferred_prompt(self, course, raw_modules, context_text):
        context_blob = self._build_context_blob(course=course, raw_modules=raw_modules, context_text=context_text)
        return (
            "Generate a plausible year-by-year module list for a UK university course as strict JSON only. "
            "Do not output markdown. "
            "Required schema: "
            '{"years":[{"year":"Year 1","required":["..."],"optional":["..."]}],"confidence":0.0,"notes":""}. '
            "Rules: module titles only, no headings, no explanatory sentences, no credits-only lines, no duplicates. "
            "Aim for 3 or 4 academic years with 4-8 modules per year where possible. "
            "If the course likely includes optional modules, place them under optional. "
            f"University: {course.university.name}. "
            f"Course: {course.title}. "
            f"Subject area: {course.subject_area or 'not provided'}. "
            f"Course URL: {course.course_url or 'not provided'}. "
            f"Context: {context_blob or 'none'}."
        )

    def _build_context_blob(self, course, raw_modules, context_text):
        parts = []
        if raw_modules:
            parts.append("Scraped candidates:\n" + "\n".join(f"- {item}" for item in raw_modules[:60]))

        if context_text:
            cleaned_context = _clean_text(context_text)
            if cleaned_context:
                parts.append("User-provided context:\n" + cleaned_context[:5000])

        if course.course_url:
            try:
                page_html = self._download_text(course.course_url)
                page_lines = self._extract_page_context_lines(page_html)
                if page_lines:
                    parts.append("Course page lines:\n" + "\n".join(page_lines))
            except Exception:
                pass

        return "\n\n".join(parts)[:12000]

    def _filter_years_by_grounding_context(self, years, grounding_context):
        if not years:
            return []
        normalized_context = self._normalize_for_match(grounding_context)
        if not normalized_context:
            return []

        filtered = []
        for item in years:
            required = [m for m in item.get("required", []) if self._module_is_grounded(m, normalized_context)]
            optional = [m for m in item.get("optional", []) if self._module_is_grounded(m, normalized_context)]
            if required or optional:
                filtered.append(
                    {
                        "year": item["year"],
                        "required": required,
                        "optional": optional,
                    }
                )
        return filtered

    def _module_is_grounded(self, module_title, normalized_context):
        normalized_module = self._normalize_for_match(module_title)
        if not normalized_module:
            return False
        return normalized_module in normalized_context

    def _normalize_for_match(self, text):
        lowered = (text or "").casefold()
        lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
        return re.sub(r"\s+", " ", lowered).strip()

    def _is_quota_error(self, message):
        lowered = (message or "").lower()
        return "http 429" in lowered or "quota exceeded" in lowered or "resource_exhausted" in lowered

    def _extract_retry_after_seconds(self, message):
        lowered = (message or "").lower()
        match = re.search(r"retry in\s+([0-9]+(?:\.[0-9]+)?)s", lowered)
        if not match:
            return None
        try:
            return max(1, int(round(float(match.group(1)))))
        except (TypeError, ValueError):
            return None

    def _quota_error_note(self, retry_after_seconds):
        if retry_after_seconds is not None:
            return (
                "Gemini quota exceeded for this API key/project. "
                f"Retry in about {retry_after_seconds} seconds or disable AI for this request."
            )
        return "Gemini quota exceeded for this API key/project. Retry later or disable AI for this request."

    def _download_text(self, url):
        req = request.Request(url, headers={"User-Agent": SCRAPER_USER_AGENT})
        with request.urlopen(req, timeout=20) as response:
            payload = response.read()

        for encoding in ("utf-8", "latin-1"):
            try:
                return payload.decode(encoding)
            except UnicodeDecodeError:
                continue
        return payload.decode("utf-8", errors="ignore")

    def _extract_page_context_lines(self, html):
        if not html:
            return []

        if BeautifulSoup is not None:
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "svg", "noscript"]):
                tag.decompose()
            text = soup.get_text("\n")
        else:
            text = re.sub(r"<[^>]+>", "\n", html)

        all_lines = []
        for line in text.splitlines():
            cleaned = _clean_text(unescape(line))
            if not cleaned:
                continue
            if len(cleaned) < 3 or len(cleaned) > 220:
                continue
            all_lines.append(cleaned)

        keyword_lines = []
        for line in all_lines:
            lowered = line.lower()
            if any(keyword in lowered for keyword in self.PAGE_CONTEXT_KEYWORDS):
                keyword_lines.append(line)

        if len(keyword_lines) < 30:
            keyword_lines.extend(all_lines[:120])

        return _dedupe(keyword_lines, limit=220)

    def _extract_text_from_gemini(self, response):
        candidates = response.get("candidates", [])
        if not candidates:
            raise RuntimeError("Gemini returned no candidates")

        parts = candidates[0].get("content", {}).get("parts", [])
        text_chunks = [part.get("text", "") for part in parts if part.get("text")]
        if not text_chunks:
            raise RuntimeError("Gemini response did not include text content")
        return "\n".join(text_chunks)

    def _extract_json(self, text):
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.startswith("json"):
                stripped = stripped[4:].strip()

        if stripped.startswith("{"):
            return json.loads(stripped)

        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise RuntimeError("Gemini output did not contain JSON object")
        return json.loads(stripped[start : end + 1])

    def _extract_modules_from_ai_payload(self, payload):
        if isinstance(payload, dict):
            raw_modules = payload.get("modules", [])
        elif isinstance(payload, list):
            raw_modules = payload
        else:
            raw_modules = []

        titles = []
        if isinstance(raw_modules, list):
            for item in raw_modules:
                if isinstance(item, str):
                    titles.append(item)
                elif isinstance(item, dict):
                    title = item.get("title") or item.get("module") or item.get("name")
                    if isinstance(title, str):
                        titles.append(title)
        return titles

    def _normalize_years_payload(self, years):
        if not isinstance(years, list):
            return []

        normalized = []
        for index, item in enumerate(years):
            if not isinstance(item, dict):
                continue
            year_label = self._normalize_year_label(item.get("year"), index)
            required = _normalize_module_candidates(
                item.get("required") or item.get("compulsory") or item.get("core") or [],
                strict=True,
                limit=20,
            )
            optional = _normalize_module_candidates(
                item.get("optional") or item.get("elective") or [],
                strict=True,
                limit=20,
            )
            if not required and not optional:
                required = _normalize_module_candidates(item.get("modules") or [], strict=True, limit=20)

            if required or optional:
                normalized.append(
                    {
                        "year": year_label,
                        "required": required,
                        "optional": optional,
                    }
                )
        return self._sort_year_buckets(normalized)

    def _sort_year_buckets(self, years):
        def year_key(item):
            label = _clean_text(str(item.get("year", "")))
            lowered = label.lower()
            if lowered == "placement year":
                return (999, label)
            match = re.search(r"\byear\s*([1-9][0-9]*)\b", lowered)
            if match:
                return (int(match.group(1)), label)
            numeric = re.fullmatch(r"[1-9][0-9]*", label)
            if numeric:
                return (int(label), label)
            return (500, label)

        return sorted(years, key=year_key)

    def _relabel_years_sequential(self, years):
        if not years:
            return []
        relabeled = []
        counter = 1
        for item in years:
            label = _clean_text(str(item.get("year", "")))
            if label.lower() == "placement year":
                relabeled.append(item)
                continue
            relabeled.append(
                {
                    "year": f"Year {counter}",
                    "required": list(item.get("required", [])),
                    "optional": list(item.get("optional", [])),
                }
            )
            counter += 1
        return relabeled

    def _extract_modules_from_years(self, years):
        modules = []
        for item in years or []:
            if not isinstance(item, dict):
                continue
            modules.extend(item.get("required", []))
            modules.extend(item.get("optional", []))
        return modules

    def _normalize_year_label(self, label, index):
        text = _clean_text(str(label or ""))
        if not text:
            return f"Year {index + 1}"

        lowered = text.lower()
        if lowered in {"placement", "placement year"}:
            return "Placement Year"
        if YEAR_ONLY_RE.match(lowered):
            match = re.search(r"[1-9][0-9]*", lowered)
            if match:
                return f"Year {match.group(0)}"

        if re.fullmatch(r"[1-9][0-9]*", text):
            return f"Year {text}"

        year_number = re.search(r"\byear\s*([1-9][0-9]*)\b", lowered)
        if year_number:
            return f"Year {year_number.group(1)}"

        return text[:40]

    def _build_years_from_modules(self, modules):
        modules = _normalize_module_candidates(modules or [], strict=True, limit=30)
        if not modules:
            return []

        count = len(modules)
        if count <= 3:
            year_count = 1
        elif count <= 6:
            year_count = 2
        else:
            year_count = 3

        chunk_size = (count + year_count - 1) // year_count
        years = []
        for i in range(year_count):
            start = i * chunk_size
            end = min(count, start + chunk_size)
            if start >= end:
                continue
            years.append(
                {
                    "year": f"Year {i + 1}",
                    "required": modules[start:end],
                    "optional": [],
                }
            )
        return years

    def _extract_confidence(self, payload):
        if not isinstance(payload, dict):
            return None
        raw = payload.get("confidence")
        try:
            if raw is None:
                return None
            return max(0.0, min(1.0, float(raw)))
        except (TypeError, ValueError):
            return None

    def _confidence_score(self, source, raw_modules, draft_modules, draft_years, gemini_confidence=None):
        if not draft_modules:
            return 0.0

        score = 0.3
        if source == "gemini":
            score += 0.3
        elif source == "gemini_inferred":
            score += 0.22

        module_count = len(draft_modules)
        if module_count >= 8:
            score += 0.2
        elif module_count >= 5:
            score += 0.12
        elif module_count >= 3:
            score += 0.06

        year_count = len(draft_years or [])
        if year_count >= 3:
            score += 0.1
        elif year_count >= 2:
            score += 0.06

        raw_count = len(raw_modules or [])
        if raw_count:
            raw_set = {item.casefold() for item in raw_modules}
            overlap = sum(1 for item in draft_modules if item.casefold() in raw_set)
            score += 0.1 * min(1.0, overlap / raw_count)

        if gemini_confidence is not None:
            score = (score * 0.65) + (gemini_confidence * 0.35)

        return max(0.0, min(1.0, score))


class CourseModuleGraphService:
    """Builds module dependency adjacency matrices using Gemini (with deterministic fallback)."""

    def __init__(self, enable_ai=True, request_timeout=60):
        self.enable_ai = enable_ai
        self.request_timeout = max(10, min(int(request_timeout or 60), 120))
        self.api_key = getattr(settings, "GEMINI_API_KEY", "")
        self.model = getattr(
            settings,
            "GEMINI_MODULES_MODEL",
            getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash"),
        )

    @property
    def is_ai_configured(self):
        return bool(self.api_key)

    def build_graph(self, course, modules, threshold=0.55, max_outgoing=3):
        normalized_modules = _normalize_user_modules(modules or [], limit=60)
        if len(normalized_modules) < 2:
            raise ValueError("At least 2 modules are required to build a dependency graph.")

        if self.enable_ai and not self.api_key:
            raise RuntimeError("Gemini is not configured.")

        if self.enable_ai:
            raw_matrix = self._generate_with_gemini(course=course, modules=normalized_modules)
            source = "gemini"
        else:
            raw_matrix = [[0.0 for _ in normalized_modules] for _ in normalized_modules]
            source = "heuristic_empty"

        matrix = self._normalize_matrix(
            matrix=raw_matrix,
            module_count=len(normalized_modules),
            threshold=threshold,
            max_outgoing=max_outgoing,
        )
        return {
            "modules": normalized_modules,
            "adjacency_matrix": matrix,
            "source": source,
        }

    def _generate_with_gemini(self, course, modules):
        prompt = self._build_prompt(course=course, modules=modules)
        parsed, _ = self._request_gemini_json(prompt)
        matrix = parsed.get("adjacency_matrix")
        if not isinstance(matrix, list):
            raise RuntimeError("Gemini output missing adjacency_matrix.")
        return matrix

    def _request_gemini_json(self, prompt):
        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
            f"?key={self.api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": self._gemini_response_schema(),
                "temperature": 0.1,
            },
        }

        req = request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        last_error = None
        for attempt in range(2):
            timeout = self.request_timeout + (15 * attempt)
            try:
                with request.urlopen(req, timeout=timeout) as response:
                    data = json.loads(response.read().decode("utf-8"))
                break
            except error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="ignore")
                raise RuntimeError(f"Gemini HTTP {exc.code}: {body[:160]}") from exc
            except (error.URLError, TimeoutError) as exc:
                last_error = exc
                if attempt == 0:
                    continue
                reason = getattr(exc, "reason", exc)
                raise RuntimeError(f"Gemini network error: {reason}") from exc
        else:  # pragma: no cover
            raise RuntimeError(f"Gemini network error: {last_error}")

        text = self._extract_text_from_gemini(data)
        parsed = self._extract_json(text)
        if not isinstance(parsed, dict):
            raise RuntimeError("Gemini output must be a JSON object.")
        return parsed, None

    def _gemini_response_schema(self):
        return {
            "type": "OBJECT",
            "properties": {
                "adjacency_matrix": {
                    "type": "ARRAY",
                    "items": {
                        "type": "ARRAY",
                        "items": {"type": "NUMBER"},
                    },
                },
                "notes": {"type": "STRING"},
            },
            "required": ["adjacency_matrix", "notes"],
        }

    def _build_prompt(self, course, modules):
        lines = "\n".join(f"{idx + 1}. {title}" for idx, title in enumerate(modules))
        return (
            "You are building a directed dependency graph between university modules. "
            "Return strict JSON only with keys adjacency_matrix and notes.\n"
            "Rules:\n"
            "- adjacency_matrix must be N x N where N equals number of modules provided.\n"
            "- matrix[i][j] is a number in [0,1] representing how much module i supports/is prerequisite for module j.\n"
            "- diagonal must be 0.\n"
            "- Keep graph sparse: only meaningful links, not every module connected.\n"
            "- Use strong links only when skills transfer is realistic (e.g., algorithms -> robotics).\n"
            "- If unsure, use 0.\n"
            f"Course: {course.title}\n"
            f"Subject area: {course.subject_area or 'not provided'}\n"
            f"Modules:\n{lines}"
        )

    def _normalize_matrix(self, matrix, module_count, threshold=0.55, max_outgoing=3):
        clean = [[0.0 for _ in range(module_count)] for _ in range(module_count)]

        for i in range(module_count):
            row = matrix[i] if i < len(matrix) and isinstance(matrix[i], list) else []
            weighted_targets = []
            for j in range(module_count):
                if i == j:
                    continue
                raw = row[j] if j < len(row) else 0
                try:
                    value = float(raw)
                except (TypeError, ValueError):
                    value = 0.0
                value = max(0.0, min(1.0, value))
                if value >= threshold:
                    weighted_targets.append((j, value))

            weighted_targets.sort(key=lambda pair: pair[1], reverse=True)
            for target_index, value in weighted_targets[:max_outgoing]:
                clean[i][target_index] = round(value, 3)

        return clean

    def _extract_text_from_gemini(self, response):
        candidates = response.get("candidates", [])
        if not candidates:
            raise RuntimeError("Gemini returned no candidates")

        parts = candidates[0].get("content", {}).get("parts", [])
        text_chunks = [part.get("text", "") for part in parts if part.get("text")]
        if not text_chunks:
            raise RuntimeError("Gemini response did not include text content")
        return "\n".join(text_chunks)

    def _extract_json(self, text):
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.startswith("json"):
                stripped = stripped[4:].strip()

        if stripped.startswith("{"):
            return json.loads(stripped)

        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise RuntimeError("Gemini output did not contain JSON object")
        return json.loads(stripped[start : end + 1])


class DiscoverUniCatalogService:
    """Fetches and imports university/course catalog data from a Discover Uni compatible endpoint."""

    def __init__(self, base_url=None):
        self.base_url = base_url or getattr(settings, "DISCOVER_UNI_CATALOG_URL", "")

    def sync_from_url(self, url=None, limit=200):
        source_url = url or self.base_url
        if not source_url:
            raise ValueError("Discover Uni source URL is not configured.")

        req = request.Request(source_url, method="GET")
        try:
            with request.urlopen(req, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            raise RuntimeError(f"Discover Uni HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Discover Uni network error: {exc.reason}") from exc

        if isinstance(payload, dict):
            if isinstance(payload.get("results"), list):
                items = payload["results"]
            else:
                items = []
        elif isinstance(payload, list):
            items = payload
        else:
            items = []

        return self.sync_items(items, limit=limit)

    def sync_items(self, items, limit=200):
        imported = 0
        for item in items[:limit]:
            normalized = self._normalize_item(item)
            if not normalized:
                continue

            university, _ = University.objects.get_or_create(
                name=normalized["university_name"],
                defaults={
                    "discover_uni_id": normalized["university_external_id"],
                    "country": normalized["country"],
                },
            )

            updates = []
            if normalized["university_external_id"] and university.discover_uni_id != normalized["university_external_id"]:
                university.discover_uni_id = normalized["university_external_id"]
                updates.append("discover_uni_id")
            if normalized["country"] and university.country != normalized["country"]:
                university.country = normalized["country"]
                updates.append("country")
            if updates:
                university.save(update_fields=updates)

            course, _ = Course.objects.get_or_create(
                university=university,
                title=normalized["course_title"],
            )

            course_updates = []
            if normalized["course_external_id"] and course.discover_uni_course_id != normalized["course_external_id"]:
                course.discover_uni_course_id = normalized["course_external_id"]
                course_updates.append("discover_uni_course_id")
            if normalized["subject_area"] and course.subject_area != normalized["subject_area"]:
                course.subject_area = normalized["subject_area"]
                course_updates.append("subject_area")
            if normalized["duration_years"] and course.duration_years != normalized["duration_years"]:
                course.duration_years = normalized["duration_years"]
                course_updates.append("duration_years")
            if course_updates:
                course.save(update_fields=course_updates)

            imported += 1

        return imported

    def _normalize_item(self, item):
        if not isinstance(item, dict):
            return None

        university_name = (
            item.get("university_name")
            or item.get("provider_name")
            or item.get("institution_name")
            or ""
        )
        course_title = (
            item.get("course_title")
            or item.get("title")
            or item.get("course_name")
            or ""
        )

        university_name = str(university_name).strip()
        course_title = str(course_title).strip()

        if not university_name or not course_title:
            return None

        duration_years = item.get("duration_years")
        try:
            duration_years = int(duration_years) if duration_years is not None else None
        except (TypeError, ValueError):
            duration_years = None

        return {
            "university_name": university_name,
            "course_title": course_title,
            "university_external_id": str(
                item.get("university_id")
                or item.get("provider_id")
                or item.get("institution_id")
                or ""
            ).strip(),
            "course_external_id": str(
                item.get("course_id")
                or item.get("id")
                or ""
            ).strip(),
            "subject_area": str(item.get("subject_area") or item.get("subject") or "").strip(),
            "duration_years": duration_years,
            "country": str(item.get("country") or "UK").strip() or "UK",
        }

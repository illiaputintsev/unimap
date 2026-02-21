import json
from unittest.mock import patch
from urllib import error

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Course, University
from .services import (
    CourseModuleDraftService,
    CourseModuleScraperService,
    DiscoverUniCatalogService,
    _looks_like_module_title,
)

User = get_user_model()


class CourseCatalogAPITests(APITestCase):
    def setUp(self):
        self.uni = University.objects.create(name="Imperial College London")
        self.other_uni = University.objects.create(name="University of Manchester")

        Course.objects.create(university=self.uni, title="Computer Science BSc")
        Course.objects.create(university=self.uni, title="Mechanical Engineering BEng")
        Course.objects.create(university=self.other_uni, title="Computer Science with AI")
        self.user = User.objects.create_user(username="courseuser", password="course-pass-123")

    def test_university_search(self):
        response = self.client.get("/api/catalog/universities/?q=imperial")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_course_filter_by_university(self):
        response = self.client.get(f"/api/catalog/courses/?university_id={self.uni.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_discover_uni_service_sync_items(self):
        service = DiscoverUniCatalogService(base_url="https://example.test")
        imported = service.sync_items(
            [
                {
                    "provider_name": "University of Bristol",
                    "course_name": "Computer Science MEng",
                    "provider_id": "bristol-1",
                    "course_id": "cs-meng",
                    "subject": "Computer Science",
                    "duration_years": 4,
                }
            ],
            limit=10,
        )

        self.assertEqual(imported, 1)
        self.assertTrue(
            Course.objects.filter(
                university__name="University of Bristol",
                title="Computer Science MEng",
                discover_uni_course_id="cs-meng",
            ).exists()
        )

    def test_course_modules_endpoint_returns_cached_modules(self):
        course = Course.objects.create(
            university=self.uni,
            title="Cached Modules Course",
            course_url="https://example.com/course",
            scraped_modules=["Algorithms", "Databases"],
        )
        self.client.force_authenticate(self.user)

        response = self.client.post(
            f"/api/catalog/courses/{course.id}/modules/",
            {"use_ai": False},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["modules_count"], 2)
        self.assertFalse(response.data["scraped_now"])
        self.assertEqual(response.data["modules"], ["Algorithms", "Databases"])

    @patch(
        "courses.views.CourseModuleScraperService.get_or_scrape",
        return_value=(["Machine Learning", "Linear Algebra"], True),
    )
    def test_course_modules_endpoint_scrapes_when_missing(self, mocked_get_or_scrape):
        course = Course.objects.create(
            university=self.uni,
            title="To Scrape Course",
            course_url="https://example.com/course",
        )
        self.client.force_authenticate(self.user)

        response = self.client.post(
            f"/api/catalog/courses/{course.id}/modules/",
            {"refresh": True, "use_ai": False},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["scraped_now"])
        self.assertEqual(response.data["modules_count"], 2)
        self.assertEqual(response.data["modules"], ["Machine Learning", "Linear Algebra"])
        self.assertEqual(response.data["draft_source"], "heuristic")
        mocked_get_or_scrape.assert_called_once()

    @patch(
        "courses.views.CourseModuleScraperService.get_or_scrape",
        return_value=(["Year 1", "What you'll learn", "Microbiology"], True),
    )
    def test_course_modules_endpoint_flags_needs_confirmation(self, mocked_get_or_scrape):
        course = Course.objects.create(
            university=self.uni,
            title="Biochemistry",
            course_url="https://example.com/course",
        )
        self.client.force_authenticate(self.user)

        response = self.client.post(
            f"/api/catalog/courses/{course.id}/modules/",
            {"refresh": True, "use_ai": False},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["needs_user_confirmation"])
        self.assertIn("Microbiology", response.data["modules"])
        self.assertGreaterEqual(response.data["modules_count"], 1)
        mocked_get_or_scrape.assert_called_once()

    @patch(
        "courses.views.CourseModuleScraperService.get_or_scrape",
        return_value=(["Year 1", "Machine Learning", "Data Science"], True),
    )
    def test_course_modules_draft_endpoint_returns_curated_modules(self, mocked_get_or_scrape):
        course = Course.objects.create(
            university=self.uni,
            title="Artificial Intelligence",
            course_url="https://example.com/course",
        )
        self.client.force_authenticate(self.user)

        response = self.client.post(
            f"/api/catalog/courses/{course.id}/modules/draft/",
            {"refresh": True, "use_ai": False},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["draft_modules"], ["Machine Learning", "Data Science"])
        mocked_get_or_scrape.assert_called_once()

    def test_course_modules_confirm_endpoint_saves_user_modules(self):
        course = Course.objects.create(
            university=self.uni,
            title="Biochemistry",
            course_url="https://example.com/course",
        )
        self.client.force_authenticate(self.user)

        response = self.client.post(
            f"/api/catalog/courses/{course.id}/modules/confirm/",
            {"modules": ["Year 1", "Molecular Biology", "Biochemistry Lab Skills", "30 credits"]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["confirmed"])
        self.assertEqual(response.data["modules"], ["Molecular Biology", "Biochemistry Lab Skills"])

        course.refresh_from_db()
        self.assertEqual(course.scraped_modules, ["Molecular Biology", "Biochemistry Lab Skills"])

    @override_settings(GEMINI_API_KEY="")
    def test_course_modules_endpoint_returns_503_when_ai_not_configured(self):
        course = Course.objects.create(
            university=self.uni,
            title="Computer Science",
            course_url="https://example.com/course",
        )
        self.client.force_authenticate(self.user)

        response = self.client.post(
            f"/api/catalog/courses/{course.id}/modules/",
            {"use_ai": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn("Gemini is not configured", response.data["detail"])

    @override_settings(GEMINI_API_KEY="test-key", GEMINI_MODULES_MODEL="gemini-test")
    @patch("courses.views.CourseModuleScraperService.get_or_scrape", side_effect=RuntimeError("blocked"))
    @patch("courses.views.CourseModuleDraftService.build_draft")
    def test_course_modules_endpoint_ai_mode_returns_year_json(
        self,
        mocked_build_draft,
        mocked_get_or_scrape,
    ):
        course = Course.objects.create(
            university=self.uni,
            title="Computer Science",
            course_url="https://example.com/course",
        )
        self.client.force_authenticate(self.user)
        mocked_build_draft.return_value = {
            "modules": ["Programming Foundations", "Data Structures and Algorithms"],
            "years": [
                {
                    "year": "Year 1",
                    "required": ["Programming Foundations"],
                    "optional": [],
                },
                {
                    "year": "Year 2",
                    "required": ["Data Structures and Algorithms"],
                    "optional": [],
                },
            ],
            "source": "gemini",
            "confidence": 0.92,
            "needs_user_confirmation": False,
            "raw_modules": [],
            "notes": "",
            "model": "gemini-test",
        }

        response = self.client.post(
            f"/api/catalog/courses/{course.id}/modules/",
            {"use_ai": True, "refresh": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["draft_source"], "gemini")
        self.assertEqual(response.data["modules"], ["Programming Foundations", "Data Structures and Algorithms"])
        self.assertEqual(response.data["years"][0]["year"], "Year 1")
        self.assertEqual(response.data["years"][1]["year"], "Year 2")
        mocked_get_or_scrape.assert_called_once()
        mocked_build_draft.assert_called_once()

    @override_settings(GEMINI_API_KEY="test-key", GEMINI_MODULES_MODEL="gemini-test")
    @patch("courses.views.CourseModuleDraftService.build_draft")
    def test_course_modules_endpoint_accepts_gemini_inferred_source(self, mocked_build_draft):
        course = Course.objects.create(
            university=self.uni,
            title="Computer Science",
            course_url="https://example.com/course",
        )
        self.client.force_authenticate(self.user)
        mocked_build_draft.return_value = {
            "modules": ["Programming Foundations", "Data Structures and Algorithms", "Databases"],
            "years": [
                {
                    "year": "Year 1",
                    "required": ["Programming Foundations", "Data Structures and Algorithms"],
                    "optional": [],
                },
                {
                    "year": "Year 2",
                    "required": ["Databases"],
                    "optional": [],
                },
            ],
            "source": "gemini_inferred",
            "confidence": 0.58,
            "needs_user_confirmation": True,
            "raw_modules": [],
            "notes": "Inferred draft used because grounded extraction was insufficient.",
            "model": "gemini-test",
        }

        response = self.client.post(
            f"/api/catalog/courses/{course.id}/modules/",
            {"use_ai": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["draft_source"], "gemini_inferred")
        self.assertTrue(response.data["needs_user_confirmation"])

    @override_settings(GEMINI_API_KEY="test-key", GEMINI_MODULES_MODEL="gemini-test")
    @patch("courses.views.CourseModuleDraftService.build_draft")
    def test_course_modules_endpoint_returns_429_when_gemini_quota_exceeded(self, mocked_build_draft):
        course = Course.objects.create(
            university=self.uni,
            title="Computer Science",
            course_url="https://example.com/course",
        )
        self.client.force_authenticate(self.user)
        mocked_build_draft.return_value = {
            "modules": ["Programming Foundations", "Data Structures and Algorithms"],
            "years": [{"year": "Year 1", "required": ["Programming Foundations"], "optional": []}],
            "source": "heuristic",
            "confidence": 0.42,
            "needs_user_confirmation": True,
            "raw_modules": [],
            "notes": "Gemini quota exceeded for this API key/project. Retry in about 20 seconds.",
            "model": "gemini-test",
            "error_code": "quota_exceeded",
            "retry_after_seconds": 20,
        }

        response = self.client.post(
            f"/api/catalog/courses/{course.id}/modules/",
            {"use_ai": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn("quota exceeded", response.data["detail"].lower())
        self.assertEqual(response.data["retry_after_seconds"], 20)

    def test_course_modules_endpoint_persists_latest_draft_on_course(self):
        course = Course.objects.create(
            university=self.uni,
            title="Cached Modules Course",
            course_url="https://example.com/course",
            scraped_modules=["Algorithms", "Databases"],
        )
        self.client.force_authenticate(self.user)

        response = self.client.post(
            f"/api/catalog/courses/{course.id}/modules/",
            {"use_ai": False},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        course.refresh_from_db()
        self.assertEqual(course.ai_draft_modules, ["Algorithms", "Databases"])
        self.assertEqual(course.ai_draft_source, "heuristic")
        self.assertIsNotNone(course.ai_draft_generated_at)

    def test_module_title_filter_rejects_navigation_noise(self):
        self.assertFalse(
            _looks_like_module_title(
                "Study Navigation link in category Study. Press escape key to return to main menu"
            )
        )
        self.assertFalse(_looks_like_module_title("Register your interest"))
        self.assertFalse(_looks_like_module_title("Students"))

    def test_module_title_filter_rejects_program_titles(self):
        self.assertFalse(_looks_like_module_title("Artificial Intelligence BSc 3 years Full time"))
        self.assertFalse(_looks_like_module_title("Computer Science MSci 4 years Full time"))

    def test_module_title_filter_accepts_real_modules(self):
        self.assertTrue(_looks_like_module_title("Machine Learning"))
        self.assertTrue(_looks_like_module_title("Software Engineering"))


class CourseModuleScraperServiceTests(APITestCase):
    def test_contensis_entry_modules_are_extracted(self):
        service = CourseModuleScraperService()

        sample_html = """
        <html><head></head><body>
          <script>window.REDUX_DATA = {"routing":{"entry":{"sys":{"id":"course-abc"}}}};</script>
          <script src="/static/startup-1.0.45.js"></script>
        </body></html>
        """

        startup_js = """
        context.DELIVERY_API_CONFIG = Object({
          rootUrl: url().api,
          accessToken: "token-123",
          projectId: "website",
        });
        function url(){ return { api: "https://api-kcl.cloud.contensis.com" }; }
        """

        contensis_entry = {
            "year1RequiredModules": [
                {
                    "type": "modules",
                    "value": [
                        {"entryTitle": "Logic and Knowledge Representation (15 credits)"},
                        {"entryTitle": "Programming Practice and Applications (30 credits)"},
                    ],
                }
            ],
            "year2RequiredModules": [
                {
                    "type": "modules",
                    "value": [
                        {"entryTitle": "Machine Learning (30 credits)"},
                        {"entryTitle": "Data Science (15 credits)"},
                    ],
                }
            ],
            "year3OptionalModules": [
                {"type": "text", "value": "You are required to take 60 credits"},
                {
                    "type": "modules",
                    "value": [
                        {"entryTitle": "Human AI Interaction (15 credits)"},
                    ],
                },
            ],
        }

        with patch.object(
            service,
            "_download",
            side_effect=[sample_html, startup_js, json.dumps(contensis_entry)],
        ):
            modules = service._scrape_url("https://www.kcl.ac.uk/study/undergraduate/courses/artificial-intelligence-bsc")

        self.assertIn("Logic and Knowledge Representation (15 credits)", modules)
        self.assertIn("Programming Practice and Applications (30 credits)", modules)
        self.assertIn("Machine Learning (30 credits)", modules)
        self.assertIn("Data Science (15 credits)", modules)
        self.assertIn("Human AI Interaction (15 credits)", modules)
        self.assertNotIn("You are required to take 60 credits", modules)

    def test_modal_endpoint_modules_are_extracted(self):
        service = CourseModuleScraperService()

        page_html = """
        <html><body>
          <script>
            var model={"teachingAndLearning":{"modulesModalUrl":"\\/webapi\\/coursemodal\\/getteachingmodal?courseId=abc\\u0026instanceId=def"}};
          </script>
        </body></html>
        """
        modal_html = """
        <html><body>
          <span class="title-type-5">Modules, teaching and learning</span>
          <span class="title-type-5">What you'll learn</span>
          <span class="title-type-5">Introductory Microeconomics</span>
          <span class="title-type-5">Intermediate Macroeconomics</span>
          <span class="title-type-5">Option modules may include</span>
          <span class="title-type-5">Behavioural Economics</span>
        </body></html>
        """

        with patch.object(service, "_download", side_effect=[page_html, modal_html]):
            modules = service._scrape_url("https://www.leedsbeckett.ac.uk/courses/business-economics-ba/")

        self.assertEqual(
            modules,
            [
                "Introductory Microeconomics",
                "Intermediate Macroeconomics",
                "Behavioural Economics",
            ],
        )

    def test_get_or_scrape_handles_http_403_with_fallback(self):
        uni = University.objects.create(name="Kingston University")
        course = Course.objects.create(
            university=uni,
            title="Biochemistry",
            course_url="https://www.kingston.ac.uk/undergraduate/courses/biochemistry-bsc/",
        )
        service = CourseModuleScraperService()

        blocked = error.HTTPError(course.course_url, 403, "Forbidden", hdrs=None, fp=None)
        with patch.object(service, "_scrape_url", side_effect=blocked):
            modules, scraped_now = service.get_or_scrape(course, refresh=True)

        self.assertTrue(scraped_now)
        self.assertGreater(len(modules), 0)
        self.assertEqual(modules, list(course.scraped_modules))

    def test_get_or_scrape_keeps_cached_modules_when_blocked(self):
        uni = University.objects.create(name="Kingston University")
        course = Course.objects.create(
            university=uni,
            title="Biochemistry",
            course_url="https://www.kingston.ac.uk/undergraduate/courses/biochemistry-bsc/",
            scraped_modules=["Molecular Biology", "Biochemistry Laboratory Skills"],
        )
        service = CourseModuleScraperService()

        blocked = error.HTTPError(course.course_url, 403, "Forbidden", hdrs=None, fp=None)
        with patch.object(service, "_scrape_url", side_effect=blocked):
            modules, scraped_now = service.get_or_scrape(course, refresh=True)

        self.assertFalse(scraped_now)
        self.assertEqual(modules, ["Molecular Biology", "Biochemistry Laboratory Skills"])


class CourseModuleDraftServiceTests(APITestCase):
    def test_heuristic_draft_filters_noisy_lines(self):
        uni = University.objects.create(name="Any University")
        course = Course.objects.create(university=uni, title="Biochemistry")
        service = CourseModuleDraftService(enable_ai=False)

        draft = service.build_draft(
            course=course,
            raw_modules=[
                "Year 1",
                "What you'll learn",
                "30 credits",
                "Protein Structure and Function",
                "Genetics and Gene Expression",
            ],
        )
        self.assertEqual(
            draft["modules"],
            ["Protein Structure and Function", "Genetics and Gene Expression"],
        )
        self.assertEqual(draft["source"], "heuristic")

    @override_settings(GEMINI_API_KEY="test-key")
    def test_gemini_draft_normalizes_years_and_filters_heading_noise(self):
        uni = University.objects.create(name="Brunel University London")
        course = Course.objects.create(university=uni, title="Computer Science")
        service = CourseModuleDraftService(enable_ai=True)

        with patch.object(
            service,
            "_generate_with_gemini",
            return_value=(
                {
                    "years": [
                        {
                            "year": "Year 2",
                            "required": ["Data Structures and Algorithms", "Compulsory"],
                            "optional": [],
                        },
                        {
                            "year": "Year 1",
                            "required": ["Introductory Programming", "Optional"],
                            "optional": ["Discrete Mathematics"],
                        },
                    ],
                    "confidence": 0.9,
                    "notes": "",
                },
                0.9,
            ),
        ):
            draft = service.build_draft(
                course=course,
                raw_modules=[
                    "Introductory Programming",
                    "Discrete Mathematics",
                    "Data Structures and Algorithms",
                ],
            )

        self.assertEqual(draft["source"], "gemini")
        self.assertEqual(
            draft["modules"],
            [
                "Introductory Programming",
                "Discrete Mathematics",
                "Data Structures and Algorithms",
            ],
        )
        self.assertEqual([item["year"] for item in draft["years"]], ["Year 1", "Year 2"])

    @override_settings(GEMINI_API_KEY="test-key")
    def test_gemini_draft_rejects_ungrounded_titles(self):
        uni = University.objects.create(name="Brunel University London")
        course = Course.objects.create(university=uni, title="Computer Science")
        service = CourseModuleDraftService(enable_ai=True)

        with patch.object(
            service,
            "_generate_with_gemini",
            return_value=(
                {
                    "years": [
                        {
                            "year": "Year 1",
                            "required": ["Invented Module Title"],
                            "optional": [],
                        }
                    ],
                    "confidence": 0.8,
                    "notes": "",
                },
                0.8,
            ),
        ), patch.object(
            service,
            "_generate_inferred_with_gemini",
            return_value=(
                {
                    "years": [
                        {
                            "year": "Year 1",
                            "required": ["Programming Foundations", "Discrete Mathematics"],
                            "optional": [],
                        },
                        {
                            "year": "Year 2",
                            "required": ["Data Structures and Algorithms"],
                            "optional": [],
                        },
                    ],
                    "confidence": 0.6,
                    "notes": "",
                },
                0.6,
            ),
        ):
            draft = service.build_draft(course=course, raw_modules=["Introductory Programming"])

        self.assertEqual(draft["source"], "gemini_inferred")

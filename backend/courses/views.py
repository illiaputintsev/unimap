from django.utils import timezone
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404

from .models import Course, University
from .serializers import (
    CourseModulesConfirmRequestSerializer,
    CourseModulesDraftRequestSerializer,
    CourseSerializer,
    UniversitySerializer,
)
from .services import CourseModuleDraftService, CourseModuleScraperService, DiscoverUniCatalogService


def _save_latest_draft(course, draft):
    confidence = draft.get("confidence")
    if confidence is None:
        normalized_confidence = None
    else:
        try:
            normalized_confidence = float(confidence)
        except (TypeError, ValueError):
            normalized_confidence = None

    course.ai_draft_modules = list(draft.get("modules") or [])
    course.ai_draft_years = list(draft.get("years") or [])
    course.ai_draft_source = str(draft.get("source") or "")
    course.ai_draft_model = str(draft.get("model") or "")
    course.ai_draft_confidence = normalized_confidence
    course.ai_draft_notes = str(draft.get("notes") or "")
    course.ai_draft_generated_at = timezone.now()
    course.save(
        update_fields=[
            "ai_draft_modules",
            "ai_draft_years",
            "ai_draft_source",
            "ai_draft_model",
            "ai_draft_confidence",
            "ai_draft_notes",
            "ai_draft_generated_at",
        ]
    )


class UniversityListAPIView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = UniversitySerializer

    def get_queryset(self):
        queryset = University.objects.all()
        search = self.request.query_params.get("q")
        if search:
            queryset = queryset.filter(name__icontains=search.strip())
        return queryset


class CourseListAPIView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = CourseSerializer

    def get_queryset(self):
        queryset = Course.objects.select_related("university")
        university_id = self.request.query_params.get("university_id")
        search = self.request.query_params.get("q")

        if university_id:
            queryset = queryset.filter(university_id=university_id)
        if search:
            queryset = queryset.filter(title__icontains=search.strip())
        return queryset


class DiscoverUniSyncAPIView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        url = request.data.get("url")
        limit = request.data.get("limit", 200)

        try:
            limit = int(limit)
        except (TypeError, ValueError):
            return Response({"detail": "limit must be an integer."}, status=400)

        service = DiscoverUniCatalogService()
        try:
            imported = service.sync_from_url(url=url, limit=limit)
        except (ValueError, RuntimeError) as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"imported": imported})


class CourseModulesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, course_id):
        course = get_object_or_404(Course.objects.select_related("university"), id=course_id)

        serializer = CourseModulesDraftRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        refresh = validated["refresh"]
        insecure = validated["insecure"]
        timeout = validated["timeout"]
        context_text = validated.get("context_text", "")
        use_ai = validated.get("use_ai", True)

        modules = list(course.scraped_modules or [])
        scraped_now = False

        if use_ai:
            if refresh:
                scraper = CourseModuleScraperService(timeout=timeout, insecure=insecure)
                try:
                    modules, scraped_now = scraper.get_or_scrape(course, refresh=True)
                except Exception:
                    modules = list(course.scraped_modules or [])
                    scraped_now = False
        else:
            scraper = CourseModuleScraperService(timeout=timeout, insecure=insecure)
            try:
                modules, scraped_now = scraper.get_or_scrape(course, refresh=refresh)
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=400)
            except RuntimeError as exc:
                return Response({"detail": str(exc)}, status=503)
            except Exception as exc:
                return Response({"detail": f"Module scrape failed: {exc}"}, status=502)

        drafter = CourseModuleDraftService(enable_ai=use_ai)
        if use_ai and not drafter.is_ai_configured:
            return Response(
                {"detail": "Gemini is not configured. Set GEMINI_API_KEY in backend/.env and restart the server."},
                status=503,
            )
        draft = drafter.build_draft(
            course=course,
            raw_modules=modules,
            context_text=context_text,
        )
        _save_latest_draft(course, draft)
        if use_ai and draft["source"] not in {"gemini", "gemini_inferred"}:
            if draft.get("error_code") == "quota_exceeded":
                payload = {
                    "detail": draft["notes"] or "Gemini quota exceeded for this API key/project.",
                }
                if draft.get("retry_after_seconds") is not None:
                    payload["retry_after_seconds"] = draft["retry_after_seconds"]
                return Response(payload, status=429)
            return Response(
                {"detail": draft["notes"] or "Gemini module generation failed."},
                status=503,
            )
        curated_modules = draft["modules"] or modules

        return Response(
            {
                "course_id": course.id,
                "course_title": course.title,
                "university": course.university.name,
                "scraped_now": scraped_now,
                "modules_count": len(curated_modules),
                "modules": curated_modules,
                "raw_modules_count": len(draft["raw_modules"]),
                "raw_modules": draft["raw_modules"],
                "draft_source": draft["source"],
                "draft_model": draft["model"],
                "years": draft["years"],
                "draft_years": draft["years"],
                "confidence_percent": round(draft["confidence"] * 100, 1),
                "needs_user_confirmation": draft["needs_user_confirmation"],
                "draft_notes": draft["notes"],
                "modules_last_scraped_at": course.modules_last_scraped_at,
            }
        )


class CourseModulesDraftAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, course_id):
        course = get_object_or_404(Course.objects.select_related("university"), id=course_id)
        serializer = CourseModulesDraftRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        refresh = validated["refresh"]
        insecure = validated["insecure"]
        timeout = validated["timeout"]
        context_text = validated.get("context_text", "")
        use_ai = validated.get("use_ai", True)

        modules = list(course.scraped_modules or [])
        scraped_now = False
        if use_ai:
            if refresh:
                scraper = CourseModuleScraperService(timeout=timeout, insecure=insecure)
                try:
                    modules, scraped_now = scraper.get_or_scrape(course, refresh=True)
                except Exception:
                    modules = list(course.scraped_modules or [])
                    scraped_now = False
        else:
            if refresh or not modules:
                scraper = CourseModuleScraperService(timeout=timeout, insecure=insecure)
                try:
                    modules, scraped_now = scraper.get_or_scrape(course, refresh=refresh)
                except Exception:
                    modules = list(course.scraped_modules or [])

        drafter = CourseModuleDraftService(enable_ai=use_ai)
        if use_ai and not drafter.is_ai_configured:
            return Response(
                {"detail": "Gemini is not configured. Set GEMINI_API_KEY in backend/.env and restart the server."},
                status=503,
            )
        draft = drafter.build_draft(
            course=course,
            raw_modules=modules,
            context_text=context_text,
        )
        _save_latest_draft(course, draft)
        if use_ai and draft["source"] not in {"gemini", "gemini_inferred"}:
            if draft.get("error_code") == "quota_exceeded":
                payload = {
                    "detail": draft["notes"] or "Gemini quota exceeded for this API key/project.",
                }
                if draft.get("retry_after_seconds") is not None:
                    payload["retry_after_seconds"] = draft["retry_after_seconds"]
                return Response(payload, status=429)
            return Response(
                {"detail": draft["notes"] or "Gemini module generation failed."},
                status=503,
            )

        return Response(
            {
                "course_id": course.id,
                "course_title": course.title,
                "university": course.university.name,
                "scraped_now": scraped_now,
                "draft_modules_count": len(draft["modules"]),
                "draft_modules": draft["modules"],
                "modules_count": len(draft["modules"]),
                "modules": draft["modules"],
                "raw_modules_count": len(draft["raw_modules"]),
                "raw_modules": draft["raw_modules"],
                "draft_source": draft["source"],
                "draft_model": draft["model"],
                "years": draft["years"],
                "draft_years": draft["years"],
                "confidence_percent": round(draft["confidence"] * 100, 1),
                "needs_user_confirmation": draft["needs_user_confirmation"],
                "draft_notes": draft["notes"],
            }
        )


class CourseModulesConfirmAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, course_id):
        course = get_object_or_404(Course.objects.select_related("university"), id=course_id)
        serializer = CourseModulesConfirmRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        modules = serializer.validated_data["modules"]
        drafter = CourseModuleDraftService(enable_ai=False)
        normalized_modules = drafter.normalize_user_modules(modules)
        if not normalized_modules:
            return Response({"detail": "No valid module titles were provided."}, status=400)

        course.scraped_modules = normalized_modules
        course.modules_last_scraped_at = timezone.now()
        course.save(update_fields=["scraped_modules", "modules_last_scraped_at"])

        return Response(
            {
                "course_id": course.id,
                "course_title": course.title,
                "university": course.university.name,
                "confirmed": True,
                "modules_count": len(normalized_modules),
                "modules": normalized_modules,
                "modules_last_scraped_at": course.modules_last_scraped_at,
            }
        )

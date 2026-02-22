from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import ModuleLearningAIService


def _as_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class ModuleTopicsGenerateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        module_title = str(request.data.get("module_title") or "").strip()
        if not module_title:
            return Response({"detail": "module_title is required."}, status=status.HTTP_400_BAD_REQUEST)

        count = _as_int(request.data.get("count"), 10)
        roadmap_title = str(request.data.get("roadmap_title") or "").strip()
        existing_topics = request.data.get("existing_topics") or []
        note_excerpts = request.data.get("note_excerpts") or []

        service = ModuleLearningAIService()
        result = service.generate_topics(
            module_title=module_title,
            roadmap_title=roadmap_title,
            existing_topics=existing_topics,
            note_excerpts=note_excerpts,
            count=count,
        )
        return Response(
            {
                "module_title": module_title,
                "topics": result["topics"],
                "topics_count": len(result["topics"]),
                "source": result["source"],
                "model": result["model"],
                "note": result["note"],
            }
        )


class ModuleQuizGenerateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        module_title = str(request.data.get("module_title") or "").strip()
        if not module_title:
            return Response({"detail": "module_title is required."}, status=status.HTTP_400_BAD_REQUEST)

        question_count = _as_int(request.data.get("question_count"), 8)
        roadmap_title = str(request.data.get("roadmap_title") or "").strip()
        topics = request.data.get("topics") or []
        note_excerpts = request.data.get("note_excerpts") or []
        mistakes = request.data.get("mistakes") or []

        service = ModuleLearningAIService()
        result = service.generate_quiz(
            module_title=module_title,
            roadmap_title=roadmap_title,
            topics=topics,
            note_excerpts=note_excerpts,
            mistakes=mistakes,
            question_count=question_count,
        )
        return Response(
            {
                "module_title": module_title,
                "questions": result["questions"],
                "questions_count": len(result["questions"]),
                "source": result["source"],
                "model": result["model"],
                "note": result["note"],
            }
        )


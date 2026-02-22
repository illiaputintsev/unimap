from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from roadmaps.models import Roadmap

from .models import ModuleWorkspaceNote
from .services import ModuleLearningAIService


def _as_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _serialize_module_note(note, request=None):
    file_url = ""
    try:
        if note.file and hasattr(note.file, "url"):
            file_url = note.file.url
            if request is not None:
                file_url = request.build_absolute_uri(file_url)
    except Exception:
        file_url = ""

    return {
        "id": note.id,
        "roadmap_id": note.roadmap_id,
        "module_id": note.module_id,
        "module_title": note.module_title,
        "file_name": note.original_filename or (note.file.name.split("/")[-1] if note.file else ""),
        "file_url": file_url,
        "content_type": note.content_type,
        "file_size": note.file_size,
        "pages_parsed": note.pages_parsed,
        "char_count": note.char_count,
        "extracted_text_excerpt": note.extracted_text_excerpt,
        "created_at": note.created_at,
        "updated_at": note.updated_at,
    }


class ModuleNoteListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        module_id = str(request.query_params.get("module_id") or "").strip()
        if not module_id:
            return Response({"detail": "module_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        roadmap_id_raw = request.query_params.get("roadmap_id")
        notes = ModuleWorkspaceNote.objects.filter(user=request.user, module_id=module_id)
        if roadmap_id_raw not in (None, "", "null", "undefined"):
            try:
                roadmap_id = int(roadmap_id_raw)
            except (TypeError, ValueError):
                return Response({"detail": "roadmap_id must be an integer."}, status=status.HTTP_400_BAD_REQUEST)
            notes = notes.filter(roadmap_id=roadmap_id)
        else:
            notes = notes.filter(roadmap__isnull=True)

        return Response([_serialize_module_note(note, request) for note in notes])

    def post(self, request):
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return Response({"detail": "file is required."}, status=status.HTTP_400_BAD_REQUEST)

        module_id = str(request.data.get("module_id") or "").strip()
        if not module_id:
            return Response({"detail": "module_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        module_title = str(request.data.get("module_title") or "").strip()
        extracted_text_excerpt = str(request.data.get("extracted_text_excerpt") or "").strip()[:7000]
        pages_parsed = max(0, _as_int(request.data.get("pages_parsed"), 0))
        char_count = max(0, _as_int(request.data.get("char_count"), len(extracted_text_excerpt)))

        roadmap = None
        roadmap_id_raw = request.data.get("roadmap_id")
        if roadmap_id_raw not in (None, "", "null", "undefined"):
            try:
                roadmap_id = int(roadmap_id_raw)
            except (TypeError, ValueError):
                return Response({"detail": "roadmap_id must be an integer."}, status=status.HTTP_400_BAD_REQUEST)
            roadmap = get_object_or_404(Roadmap, id=roadmap_id, user=request.user)

        note = ModuleWorkspaceNote.objects.create(
            user=request.user,
            roadmap=roadmap,
            module_id=module_id,
            module_title=module_title,
            file=uploaded_file,
            original_filename=getattr(uploaded_file, "name", "") or "",
            content_type=str(getattr(uploaded_file, "content_type", "") or ""),
            file_size=int(getattr(uploaded_file, "size", 0) or 0),
            pages_parsed=pages_parsed,
            char_count=char_count,
            extracted_text_excerpt=extracted_text_excerpt,
        )

        return Response(_serialize_module_note(note, request), status=status.HTTP_201_CREATED)


class ModuleNoteDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, note_id):
        note = get_object_or_404(ModuleWorkspaceNote, id=note_id, user=request.user)
        try:
            if note.file:
                note.file.delete(save=False)
        except Exception:
            pass
        note.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


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
        quiz_mode = str(request.data.get("quiz_mode") or "practice").strip().lower()
        topics = request.data.get("topics") or []
        note_excerpts = request.data.get("note_excerpts") or []
        mistakes = request.data.get("mistakes") or []

        service = ModuleLearningAIService()
        result = service.generate_quiz(
            module_title=module_title,
            roadmap_title=roadmap_title,
            quiz_mode=quiz_mode,
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
                "quiz_mode": quiz_mode,
                "source": result["source"],
                "model": result["model"],
                "note": result["note"],
            }
        )

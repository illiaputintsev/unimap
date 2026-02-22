from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from roadmaps.models import Roadmap

from .models import ModuleWorkspaceNote, ModuleWorkspaceState
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


def _safe_text(value, max_len=5000):
    return str(value or "").strip()[:max_len]


def _normalize_topics_payload(topics):
    normalized = []
    for idx, topic in enumerate((topics or [])[:80]):
        if isinstance(topic, str):
            item = {
                "id": f"topic-{idx + 1}",
                "title": _safe_text(topic, 255),
                "why": "",
                "source": "custom",
                "createdAt": "",
            }
        elif isinstance(topic, dict):
            item = {
                "id": _safe_text(topic.get("id"), 128) or f"topic-{idx + 1}",
                "title": _safe_text(topic.get("title"), 255),
                "why": _safe_text(topic.get("why") or topic.get("why_it_matters") or topic.get("description"), 2000),
                "source": _safe_text(topic.get("source"), 64) or "custom",
                "createdAt": _safe_text(topic.get("createdAt"), 64),
            }
        else:
            continue
        if not item["title"]:
            continue
        normalized.append(item)
        if len(normalized) >= 40:
            break
    return normalized


def _normalize_attempts_payload(attempts):
    normalized = []
    for idx, attempt in enumerate((attempts or [])[-100:]):
        if not isinstance(attempt, dict):
            continue
        normalized.append(
            {
                "id": _safe_text(attempt.get("id"), 128) or f"attempt-{idx + 1}",
                "score": max(0, min(100, _as_int(attempt.get("score"), 0))),
                "totalQuestions": max(0, _as_int(attempt.get("totalQuestions"), 0)),
                "correctCount": max(0, _as_int(attempt.get("correctCount"), 0)),
                "source": _safe_text(attempt.get("source"), 64),
                "createdAt": _safe_text(attempt.get("createdAt"), 64),
                "focusedOnMistakes": bool(attempt.get("focusedOnMistakes")),
                "quizType": _safe_text(attempt.get("quizType"), 120),
                "quizMode": _safe_text(attempt.get("quizMode"), 32),
            }
        )
    return normalized[-50:]


def _normalize_mistake_bank_payload(mistakes):
    normalized = []
    for item in (mistakes or [])[:240]:
        if not isinstance(item, dict):
            continue
        key = _safe_text(item.get("key"), 500)
        question = _safe_text(item.get("question"), 2000)
        if not key and not question:
            continue
        topic = _safe_text(item.get("topic"), 255)
        normalized.append(
            {
                "key": key or f"{topic.lower()}|{question.lower()}",
                "topic": topic,
                "question": question,
                "correctAnswer": _safe_text(item.get("correctAnswer"), 1000),
                "lastUserAnswer": _safe_text(item.get("lastUserAnswer"), 1000),
                "explanation": _safe_text(item.get("explanation"), 2000),
                "count": max(1, _as_int(item.get("count"), 1)),
                "lastAt": _safe_text(item.get("lastAt"), 64),
            }
        )
        if len(normalized) >= 120:
            break
    return normalized


def _normalize_topic_stats_payload(topic_stats):
    if not isinstance(topic_stats, dict):
        return {}
    normalized = {}
    for key, value in list(topic_stats.items())[:400]:
        if not isinstance(value, dict):
            continue
        stat_key = _safe_text(key, 255).lower()
        if not stat_key:
            continue
        normalized[stat_key] = {
            "topicTitle": _safe_text(value.get("topicTitle"), 255),
            "attempts": max(0, _as_int(value.get("attempts"), 0)),
            "totalQuestions": max(0, _as_int(value.get("totalQuestions"), 0)),
            "correctQuestions": max(0, _as_int(value.get("correctQuestions"), 0)),
            "lastScore": max(0, min(100, _as_int(value.get("lastScore"), 0))),
            "updatedAt": _safe_text(value.get("updatedAt"), 64),
        }
    return normalized


def _normalize_activity_payload(activity):
    normalized = []
    for item in (activity or [])[:60]:
        if isinstance(item, str):
            message = _safe_text(item, 500)
            at = ""
        elif isinstance(item, dict):
            message = _safe_text(item.get("message"), 500)
            at = _safe_text(item.get("at"), 64)
        else:
            continue
        if not message:
            continue
        normalized.append({"message": message, "at": at})
        if len(normalized) >= 30:
            break
    return normalized


def _normalize_last_generated_payload(last_generated):
    if not isinstance(last_generated, dict):
        return {"topicsSource": "", "quizSource": "", "note": ""}
    return {
        "topicsSource": _safe_text(last_generated.get("topicsSource"), 80),
        "quizSource": _safe_text(last_generated.get("quizSource"), 80),
        "note": _safe_text(last_generated.get("note"), 3000),
    }


def _normalize_workspace_payload(workspace, *, module_id="", roadmap_id=None):
    workspace = workspace if isinstance(workspace, dict) else {}
    return {
        "version": max(1, _as_int(workspace.get("version"), 1)),
        "moduleId": _safe_text(workspace.get("moduleId") or module_id, 128),
        "roadmapId": str(roadmap_id) if roadmap_id is not None else None,
        "topics": _normalize_topics_payload(workspace.get("topics") or []),
        "attempts": _normalize_attempts_payload(workspace.get("attempts") or []),
        "mistakeBank": _normalize_mistake_bank_payload(workspace.get("mistakeBank") or []),
        "topicStats": _normalize_topic_stats_payload(workspace.get("topicStats") or {}),
        "activity": _normalize_activity_payload(workspace.get("activity") or []),
        "lastGenerated": _normalize_last_generated_payload(workspace.get("lastGenerated") or {}),
    }


def _serialize_module_workspace_state(workspace_state):
    return {
        "id": workspace_state.id,
        "roadmap_id": workspace_state.roadmap_id,
        "module_id": workspace_state.module_id,
        "module_title": workspace_state.module_title,
        "created_at": workspace_state.created_at,
        "updated_at": workspace_state.updated_at,
        "workspace": {
            "version": int(workspace_state.state_version or 1),
            "moduleId": workspace_state.module_id,
            "roadmapId": str(workspace_state.roadmap_id) if workspace_state.roadmap_id is not None else None,
            "topics": workspace_state.topics or [],
            "attempts": workspace_state.attempts or [],
            "mistakeBank": workspace_state.mistake_bank or [],
            "topicStats": workspace_state.topic_stats or {},
            "activity": workspace_state.activity or [],
            "lastGenerated": workspace_state.last_generated or {"topicsSource": "", "quizSource": "", "note": ""},
        },
    }


def _resolve_module_workspace_scope(request, source="query"):
    lookup = request.data if source == "data" else request.query_params

    module_id = str(lookup.get("module_id") or "").strip()
    if not module_id:
        return None, None, Response({"detail": "module_id is required."}, status=status.HTTP_400_BAD_REQUEST)

    roadmap = None
    roadmap_id_raw = lookup.get("roadmap_id")
    if roadmap_id_raw not in (None, "", "null", "undefined"):
        try:
            roadmap_id = int(roadmap_id_raw)
        except (TypeError, ValueError):
            return None, None, Response({"detail": "roadmap_id must be an integer."}, status=status.HTTP_400_BAD_REQUEST)
        roadmap = get_object_or_404(Roadmap, id=roadmap_id, user=request.user)

    return module_id, roadmap, None


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


class ModuleWorkspaceStateAPIView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    def get(self, request):
        module_id, roadmap, error_response = _resolve_module_workspace_scope(request, source="query")
        if error_response is not None:
            return error_response

        queryset = ModuleWorkspaceState.objects.filter(user=request.user, module_id=module_id)
        if roadmap is not None:
            queryset = queryset.filter(roadmap=roadmap)
        else:
            queryset = queryset.filter(roadmap__isnull=True)

        workspace_state = queryset.first()
        if workspace_state is None:
            return Response(
                {
                    "exists": False,
                    "module_id": module_id,
                    "roadmap_id": roadmap.id if roadmap else None,
                    "workspace": None,
                }
            )

        payload = _serialize_module_workspace_state(workspace_state)
        payload["exists"] = True
        return Response(payload)

    def put(self, request):
        module_id, roadmap, error_response = _resolve_module_workspace_scope(request, source="data")
        if error_response is not None:
            return error_response

        raw_workspace = request.data.get("workspace")
        if raw_workspace is None and isinstance(request.data, dict):
            raw_workspace = request.data

        workspace = _normalize_workspace_payload(
            raw_workspace,
            module_id=module_id,
            roadmap_id=(roadmap.id if roadmap else None),
        )
        module_title = _safe_text(request.data.get("module_title"), 255)
        if not module_title and isinstance(raw_workspace, dict):
            module_title = _safe_text(raw_workspace.get("moduleTitle"), 255)

        if roadmap is not None:
            workspace_state, created = ModuleWorkspaceState.objects.get_or_create(
                user=request.user,
                roadmap=roadmap,
                module_id=module_id,
                defaults={"module_title": module_title},
            )
        else:
            workspace_state = ModuleWorkspaceState.objects.filter(
                user=request.user,
                roadmap__isnull=True,
                module_id=module_id,
            ).first()
            created = False
            if workspace_state is None:
                workspace_state = ModuleWorkspaceState.objects.create(
                    user=request.user,
                    roadmap=None,
                    module_id=module_id,
                    module_title=module_title,
                )
                created = True

        workspace_state.module_title = module_title or workspace_state.module_title
        workspace_state.state_version = max(1, _as_int(workspace.get("version"), 1))
        workspace_state.topics = workspace.get("topics") or []
        workspace_state.attempts = workspace.get("attempts") or []
        workspace_state.mistake_bank = workspace.get("mistakeBank") or []
        workspace_state.topic_stats = workspace.get("topicStats") or {}
        workspace_state.activity = workspace.get("activity") or []
        workspace_state.last_generated = workspace.get("lastGenerated") or {}
        workspace_state.save(
            update_fields=[
                "module_title",
                "state_version",
                "topics",
                "attempts",
                "mistake_bank",
                "topic_stats",
                "activity",
                "last_generated",
                "updated_at",
            ]
        )

        payload = _serialize_module_workspace_state(workspace_state)
        payload["exists"] = True
        payload["created"] = created
        return Response(payload)


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

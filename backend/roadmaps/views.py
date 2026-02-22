from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from courses.models import Course

from .models import Edge, Node, Roadmap, TopicProgress
from .serializers import GenerateRoadmapRequestSerializer, TopicProgressUpdateSerializer
from .services import RoadmapGenerationService


def _clamp(value, minimum=0.0, maximum=1.0):
    return max(minimum, min(maximum, value))


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _build_progress_maps(roadmap, user):
    nodes = list(roadmap.nodes.all().order_by("order", "id"))
    progress_map = {
        progress.node_id: progress.mastery
        for progress in TopicProgress.objects.filter(user=user, node__roadmap=roadmap)
    }

    topics_by_module = {}
    for node in nodes:
        if node.type == "topic" and node.parent_module_id:
            topics_by_module.setdefault(node.parent_module_id, []).append(node)

    module_progress_map = {}
    for module in [node for node in nodes if node.type == "module"]:
        topics = topics_by_module.get(module.id, [])
        topic_mastery_values = [progress_map.get(topic.id, 0.0) for topic in topics]
        module_progress = (
            sum(topic_mastery_values) / len(topic_mastery_values) if topic_mastery_values else 0.0
        )
        module_progress_map[module.id] = module_progress

    return nodes, progress_map, topics_by_module, module_progress_map


def _serialize_roadmap_graph(roadmap, user):
    nodes, progress_map, topics_by_module, module_progress_map = _build_progress_maps(roadmap, user)
    edges = list(roadmap.edges.select_related("source", "target").all())

    if module_progress_map:
        overall_progress = sum(module_progress_map.values()) / len(module_progress_map)
    else:
        overall_progress = 0.0

    graph_nodes = []
    for node in nodes:
        payload = {
            "id": node.id,
            "type": node.type,
            "title": node.title,
            "description": node.description,
            "order": node.order,
            "parent_module_id": node.parent_module_id,
        }

        if node.type == "module":
            payload["progress_percent"] = round(module_progress_map.get(node.id, 0.0) * 100, 1)
            payload["topics_count"] = len(topics_by_module.get(node.id, []))
        else:
            payload["mastery_percent"] = round(progress_map.get(node.id, 0.0) * 100, 1)
            payload["impact_weight_percent"] = round(node.impact_weight * 100, 1)

        graph_nodes.append(payload)

    return {
        "roadmap_id": roadmap.id,
        "roadmap_title": roadmap.title,
        "overall_progress_percent": round(overall_progress * 100, 1),
        "nodes": graph_nodes,
        "edges": [
            {
                "id": edge.id,
                "source": edge.source_id,
                "target": edge.target_id,
                "edge_type": edge.edge_type,
                "influence_percent": round(edge.influence * 100, 1),
                "rationale": edge.rationale,
            }
            for edge in edges
        ],
    }


def _serialize_roadmap_graph_summary(roadmap, user):
    nodes, _, _, module_progress_map = _build_progress_maps(roadmap, user)
    module_count = sum(1 for node in nodes if node.type == "module")
    topic_count = sum(1 for node in nodes if node.type == "topic")
    edge_count = roadmap.edges.count()

    if module_progress_map:
        overall_progress = sum(module_progress_map.values()) / len(module_progress_map)
    else:
        overall_progress = 0.0

    return {
        "roadmap_id": roadmap.id,
        "modules_count": module_count,
        "topics_count": topic_count,
        "edges_count": edge_count,
        "overall_progress_percent": round(overall_progress * 100, 1),
    }


def _serialize_roadmap(roadmap, user):
    nodes, progress_map, topics_by_module, module_progress_map = _build_progress_maps(roadmap, user)
    edges = list(roadmap.edges.select_related("source", "target").all())

    module_payload = []

    for module in [node for node in nodes if node.type == "module"]:
        topics = topics_by_module.get(module.id, [])
        topic_payload = []

        for topic in topics:
            mastery = progress_map.get(topic.id, 0.0)
            topic_payload.append(
                {
                    "id": topic.id,
                    "title": topic.title,
                    "description": topic.description,
                    "order": topic.order,
                    "mastery_percent": round(mastery * 100, 1),
                    "impact_weight_percent": round(topic.impact_weight * 100, 1),
                }
            )

        module_progress = module_progress_map.get(module.id, 0.0)

        module_payload.append(
            {
                "id": module.id,
                "title": module.title,
                "description": module.description,
                "order": module.order,
                "progress_percent": round(module_progress * 100, 1),
                "topics": topic_payload,
            }
        )

    overall_progress = (
        sum(module_progress_map.values()) / len(module_progress_map) if module_progress_map else 0.0
    )

    course_payload = None
    if roadmap.course_id:
        course_payload = {
            "id": roadmap.course_id,
            "title": roadmap.course.title,
            "university": roadmap.course.university.name,
        }

    return {
        "id": roadmap.id,
        "title": roadmap.title,
        "created_at": roadmap.created_at,
        "updated_at": roadmap.updated_at,
        "generation_source": roadmap.generation_source,
        "generation_notes": roadmap.generation_notes,
        "manual_course_title": roadmap.manual_course_title,
        "course": course_payload,
        "overall_progress_percent": round(overall_progress * 100, 1),
        "modules": module_payload,
        "edges": [
            {
                "id": edge.id,
                "source": edge.source_id,
                "target": edge.target_id,
                "edge_type": edge.edge_type,
                "influence_percent": round(edge.influence * 100, 1),
                "rationale": edge.rationale,
            }
            for edge in edges
        ],
    }


class RoadmapGenerateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = GenerateRoadmapRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated = serializer.validated_data
        course = None
        course_title = validated.get("manual_course_title")

        if validated.get("course_id"):
            course = get_object_or_404(Course.objects.select_related("university"), id=validated["course_id"])
            course_title = course.title

        requested_module_names = validated.get("module_names", [])
        if not requested_module_names and course and course.scraped_modules:
            requested_module_names = [
                str(item).strip()
                for item in course.scraped_modules
                if isinstance(item, str) and str(item).strip()
            ][:10]

        generator = RoadmapGenerationService()
        graph, source, note = generator.generate(
            course_title=course_title,
            module_names=requested_module_names,
            career_goal=validated.get("career_goal", ""),
        )
        used_scraped_modules = bool(
            requested_module_names and not validated.get("module_names") and course
        )
        generation_notes = note
        if used_scraped_modules:
            addon = "Used modules scraped from course URL."
            generation_notes = f"{note} | {addon}" if note else addon

        roadmap_title = validated.get("title") or f"{course_title} Roadmap"
        module_definitions = graph.get("modules", [])

        with transaction.atomic():
            roadmap = Roadmap.objects.create(
                user=request.user,
                course=course,
                title=roadmap_title,
                manual_course_title="" if course else course_title,
                generation_source=source,
                generation_notes=generation_notes,
            )

            module_nodes = {}
            for module_index, module in enumerate(module_definitions):
                module_title = str(module.get("title", "")).strip() or f"Module {module_index + 1}"
                module_node = Node.objects.create(
                    roadmap=roadmap,
                    type="module",
                    title=module_title,
                    description=str(module.get("description", "")).strip(),
                    order=module_index,
                )
                module_nodes[module_title.lower()] = module_node

                for topic_index, topic in enumerate(module.get("topics", [])):
                    topic_title = str(topic.get("title", "")).strip() or f"{module_title} Topic {topic_index + 1}"
                    topic_node = Node.objects.create(
                        roadmap=roadmap,
                        type="topic",
                        title=topic_title,
                        description=str(topic.get("description", "")).strip(),
                        order=topic_index,
                        parent_module=module_node,
                        impact_weight=_clamp(_safe_float(topic.get("impact_weight", 0.0))),
                    )
                    Edge.objects.create(
                        roadmap=roadmap,
                        source=module_node,
                        target=topic_node,
                        edge_type="contains",
                        influence=1.0,
                        rationale="Module contains this topic.",
                    )

            for module in module_definitions:
                target_title = str(module.get("title", "")).strip().lower()
                target_node = module_nodes.get(target_title)
                if not target_node:
                    continue

                for dependency in module.get("depends_on", []):
                    source_title = str(dependency.get("module", "")).strip().lower()
                    source_node = module_nodes.get(source_title)
                    if not source_node or source_node.id == target_node.id:
                        continue

                    Edge.objects.get_or_create(
                        roadmap=roadmap,
                        source=source_node,
                        target=target_node,
                        edge_type="prerequisite",
                        defaults={
                            "influence": _clamp(_safe_float(dependency.get("influence", 0.0))),
                            "rationale": str(dependency.get("rationale", "")).strip(),
                        },
                    )

        return Response(_serialize_roadmap(roadmap, request.user), status=status.HTTP_201_CREATED)


class RoadmapListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        roadmaps = Roadmap.objects.filter(user=request.user).select_related("course", "course__university")
        payload = [_serialize_roadmap(roadmap, request.user) for roadmap in roadmaps]
        return Response(payload)


class RoadmapDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, roadmap_id):
        roadmap = get_object_or_404(
            Roadmap.objects.select_related("course", "course__university"),
            id=roadmap_id,
            user=request.user,
        )
        return Response(_serialize_roadmap(roadmap, request.user))


class RoadmapGraphAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, roadmap_id):
        roadmap = get_object_or_404(
            Roadmap.objects.select_related("course", "course__university"),
            id=roadmap_id,
            user=request.user,
        )
        return Response(_serialize_roadmap_graph(roadmap, request.user))


class RoadmapGraphSummaryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, roadmap_id):
        roadmap = get_object_or_404(
            Roadmap.objects.select_related("course", "course__university"),
            id=roadmap_id,
            user=request.user,
        )
        return Response(_serialize_roadmap_graph_summary(roadmap, request.user))


class TopicProgressUpdateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, topic_id):
        topic_node = get_object_or_404(
            Node.objects.select_related("roadmap"),
            id=topic_id,
            type="topic",
            roadmap__user=request.user,
        )

        serializer = TopicProgressUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        mastery_percent = serializer.validated_data["mastery_percent"]
        mastery = mastery_percent / 100.0

        TopicProgress.objects.update_or_create(
            user=request.user,
            node=topic_node,
            defaults={"mastery": mastery},
        )

        return Response(_serialize_roadmap(topic_node.roadmap, request.user))


class RoadmapGraphTopicProgressUpdateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, roadmap_id, topic_id):
        topic_node = get_object_or_404(
            Node.objects.select_related("roadmap"),
            id=topic_id,
            type="topic",
            roadmap_id=roadmap_id,
            roadmap__user=request.user,
        )

        serializer = TopicProgressUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        mastery_percent = serializer.validated_data["mastery_percent"]
        mastery = mastery_percent / 100.0

        TopicProgress.objects.update_or_create(
            user=request.user,
            node=topic_node,
            defaults={"mastery": mastery},
        )

        return Response(_serialize_roadmap_graph(topic_node.roadmap, request.user))

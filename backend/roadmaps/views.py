import math
from collections import deque

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


def _build_module_neighbors(module_nodes, edges):
    module_ids = {module.id for module in module_nodes}
    neighbors = {module_id: {} for module_id in module_ids}

    for edge in edges:
        source_id = edge.source_id
        target_id = edge.target_id

        if source_id not in module_ids or target_id not in module_ids:
            continue
        if source_id == target_id:
            continue

        influence = _safe_float(getattr(edge, "influence", 1.0), 1.0)
        weight = max(0.05, min(influence, 1.0))

        neighbors[source_id][target_id] = neighbors[source_id].get(target_id, 0.0) + weight
        neighbors[target_id][source_id] = neighbors[target_id].get(source_id, 0.0) + weight

    return neighbors


def _shortest_distances(seed_id, cluster_id_set, neighbors):
    distances = {seed_id: 0}
    queue = deque([seed_id])

    while queue:
        current = queue.popleft()
        current_distance = distances[current]
        for neighbor_id in neighbors.get(current, {}):
            if neighbor_id not in cluster_id_set:
                continue
            if neighbor_id in distances:
                continue
            distances[neighbor_id] = current_distance + 1
            queue.append(neighbor_id)

    return distances


def _split_cluster_by_connectivity(node_ids, neighbors, module_order_map, parts=2):
    if not isinstance(node_ids, list):
        return [node_ids]
    if len(node_ids) < max(4, parts * 2) or parts < 2:
        return [node_ids]

    cluster_id_set = set(node_ids)
    degree_map = {
        node_id: sum(1 for neighbor_id in neighbors.get(node_id, {}) if neighbor_id in cluster_id_set)
        for node_id in node_ids
    }

    def priority(node_id):
        return (
            -(degree_map.get(node_id, 0)),
            module_order_map.get(node_id, math.inf),
            node_id,
        )

    sorted_node_ids = sorted(node_ids, key=priority)
    seeds = [sorted_node_ids[0]]

    while len(seeds) < parts:
        seed_distance_maps = [
            _shortest_distances(seed_id, cluster_id_set, neighbors) for seed_id in seeds
        ]
        best_candidate = None
        best_distance = -1

        for candidate_id in node_ids:
            if candidate_id in seeds:
                continue

            min_distance = math.inf
            for distance_map in seed_distance_maps:
                min_distance = min(min_distance, distance_map.get(candidate_id, math.inf))

            if min_distance > best_distance:
                best_candidate = candidate_id
                best_distance = min_distance
            elif min_distance == best_distance and best_candidate is not None:
                if priority(candidate_id) < priority(best_candidate):
                    best_candidate = candidate_id

        if best_candidate is None or best_candidate in seeds:
            break
        seeds.append(best_candidate)

    if len(seeds) < 2:
        return [node_ids]

    seed_distances = {
        seed_id: _shortest_distances(seed_id, cluster_id_set, neighbors) for seed_id in seeds
    }
    assigned = {seed_id: [] for seed_id in seeds}
    load = {seed_id: 0 for seed_id in seeds}

    for node_id in sorted(node_ids, key=priority):
        best_seed = seeds[0]
        best_distance = math.inf
        best_load = load[best_seed]

        for seed_id in seeds:
            distance = seed_distances[seed_id].get(node_id, math.inf)
            seed_load = load[seed_id]
            if distance < best_distance:
                best_seed = seed_id
                best_distance = distance
                best_load = seed_load
            elif distance == best_distance and seed_load < best_load:
                best_seed = seed_id
                best_load = seed_load

        assigned[best_seed].append(node_id)
        load[best_seed] += 1

    groups = [group for group in assigned.values() if group]
    if len(groups) < 2:
        ordered = sorted(node_ids, key=lambda node_id: (module_order_map.get(node_id, math.inf), node_id))
        midpoint = max(1, len(ordered) // 2)
        groups = [ordered[:midpoint], ordered[midpoint:]]
        groups = [group for group in groups if group]

    for group in groups:
        group.sort(key=lambda node_id: (module_order_map.get(node_id, math.inf), node_id))

    return groups


def _enforce_cluster_count(clusters, neighbors, module_order_map, total_nodes):
    normalized_clusters = [list(cluster) for cluster in clusters if cluster]
    target_count = max(1, min(6, round(math.sqrt(max(total_nodes, 1) / 2.2))))

    while len(normalized_clusters) < target_count:
        split_index = -1
        split_size = 0
        for index, cluster in enumerate(normalized_clusters):
            if len(cluster) > split_size:
                split_index = index
                split_size = len(cluster)

        if split_index < 0 or split_size < 7:
            break

        split_result = _split_cluster_by_connectivity(
            normalized_clusters[split_index],
            neighbors,
            module_order_map,
            parts=2,
        )
        split_result = [group for group in split_result if group]
        if len(split_result) < 2:
            break

        smallest_group = min(len(group) for group in split_result)
        if smallest_group < 2:
            break

        normalized_clusters = (
            normalized_clusters[:split_index]
            + split_result
            + normalized_clusters[split_index + 1 :]
        )

    return normalized_clusters


def _build_cluster_metadata(nodes, edges):
    module_nodes = sorted(
        [node for node in nodes if node.type == "module"],
        key=lambda node: (node.order, node.id),
    )
    if not module_nodes:
        return {}, []

    module_by_id = {module.id: module for module in module_nodes}
    module_order_map = {
        module.id: (module.order if module.order is not None else math.inf)
        for module in module_nodes
    }
    neighbors = _build_module_neighbors(module_nodes, edges)

    labels = {module.id: module.id for module in module_nodes}
    ordered_ids = sorted(
        [module.id for module in module_nodes],
        key=lambda module_id: (
            -len(neighbors.get(module_id, {})),
            module_order_map.get(module_id, math.inf),
            module_id,
        ),
    )

    for _ in range(25):
        changed = False
        cluster_sizes = {}
        for label in labels.values():
            cluster_sizes[label] = cluster_sizes.get(label, 0) + 1

        for module_id in ordered_ids:
            module_neighbors = neighbors.get(module_id, {})
            if not module_neighbors:
                continue

            current_label = labels[module_id]
            label_scores = {current_label: 0.0}
            for neighbor_id, weight in module_neighbors.items():
                neighbor_label = labels[neighbor_id]
                label_scores[neighbor_label] = label_scores.get(neighbor_label, 0.0) + weight

            best_label = current_label
            best_score = -math.inf
            for label, score in label_scores.items():
                size = cluster_sizes.get(label, 1)
                adjusted_score = score / (size ** 0.35)
                if label == current_label:
                    adjusted_score += 0.08

                if adjusted_score > best_score:
                    best_label = label
                    best_score = adjusted_score
                elif adjusted_score == best_score and label < best_label:
                    best_label = label

            if best_label != current_label:
                labels[module_id] = best_label
                changed = True

        if not changed:
            break

    label_to_ids = {}
    for module_id, label in labels.items():
        label_to_ids.setdefault(label, []).append(module_id)

    singleton_ids = []
    for module_ids in label_to_ids.values():
        if len(module_ids) != 1:
            continue
        candidate_id = module_ids[0]
        if neighbors.get(candidate_id):
            singleton_ids.append(candidate_id)

    for module_id in singleton_ids:
        best_label = labels[module_id]
        best_weight = -math.inf
        for neighbor_id, weight in neighbors.get(module_id, {}).items():
            candidate_label = labels[neighbor_id]
            if candidate_label == labels[module_id]:
                continue
            if weight > best_weight:
                best_label = candidate_label
                best_weight = weight
        if best_label != labels[module_id]:
            labels[module_id] = best_label

    raw_clusters = {}
    for module_id, label in labels.items():
        raw_clusters.setdefault(label, []).append(module_id)

    isolated_ids = []
    mixed_clusters = []
    for module_ids in raw_clusters.values():
        is_isolated = all(not neighbors.get(module_id) for module_id in module_ids)
        if is_isolated:
            isolated_ids.extend(module_ids)
        else:
            mixed_clusters.append(module_ids)

    if isolated_ids:
        mixed_clusters.append(isolated_ids)

    rebalanced_clusters = _enforce_cluster_count(
        mixed_clusters,
        neighbors,
        module_order_map,
        total_nodes=len(module_nodes),
    )

    for cluster_ids in rebalanced_clusters:
        cluster_ids.sort(key=lambda module_id: (module_order_map.get(module_id, math.inf), module_id))

    rebalanced_clusters.sort(
        key=lambda cluster_ids: (
            -len(cluster_ids),
            sum(module_order_map.get(module_id, 0) for module_id in cluster_ids)
            / max(len(cluster_ids), 1),
        )
    )

    module_cluster_map = {}
    cluster_payload = []
    for index, cluster_ids in enumerate(rebalanced_clusters, start=1):
        cluster_id = f"cluster-{index}"
        cluster_label = f"Cluster {index}"
        module_titles = [module_by_id[module_id].title for module_id in cluster_ids if module_id in module_by_id]

        cluster_payload.append(
            {
                "id": cluster_id,
                "label": cluster_label,
                "index": index,
                "module_count": len(cluster_ids),
                "module_ids": cluster_ids,
                "module_titles": module_titles,
            }
        )

        for module_id in cluster_ids:
            module_cluster_map[module_id] = {
                "id": cluster_id,
                "label": cluster_label,
                "index": index,
            }

    return module_cluster_map, cluster_payload


def _module_relationship_label(edge_type, direction):
    if edge_type == "prerequisite":
        return "Unlocks" if direction == "outgoing" else "Depends on"
    if edge_type == "career":
        return "Supports" if direction == "outgoing" else "Supported by"
    if edge_type == "contains":
        return "Contains" if direction == "outgoing" else "Part of"
    return "Related to"


def _build_module_relationship_map(nodes, edges):
    module_nodes = [node for node in nodes if node.type == "module"]
    if not module_nodes:
        return {}

    module_by_id = {node.id: node for node in module_nodes}
    module_order_map = {
        node.id: (node.order if node.order is not None else math.inf)
        for node in module_nodes
    }
    relationship_map = {module.id: [] for module in module_nodes}

    for edge in edges:
        source_id = edge.source_id
        target_id = edge.target_id
        if source_id == target_id:
            continue
        if source_id not in module_by_id or target_id not in module_by_id:
            continue

        influence_percent = round(_safe_float(getattr(edge, "influence", 0.0), 0.0) * 100, 1)
        rationale = (edge.rationale or "").strip()

        for owner_id, other_id, direction in (
            (source_id, target_id, "outgoing"),
            (target_id, source_id, "incoming"),
        ):
            other_module = module_by_id[other_id]
            relationship_label = _module_relationship_label(edge.edge_type, direction)
            relationship_map[owner_id].append(
                {
                    "module_id": other_module.id,
                    "module_title": other_module.title,
                    "direction": direction,
                    "edge_type": edge.edge_type,
                    "relationship_label": relationship_label,
                    "influence_percent": influence_percent,
                    "rationale": rationale,
                    "reason": rationale or f"{relationship_label} {other_module.title.lower()}.",
                }
            )

    for module_id, related_items in relationship_map.items():
        deduped = {}
        for item in related_items:
            dedupe_key = (
                item["module_id"],
                item["direction"],
                item["edge_type"],
                (item["rationale"] or "").strip().lower(),
            )
            current = deduped.get(dedupe_key)
            if current is None or item["influence_percent"] > current["influence_percent"]:
                deduped[dedupe_key] = item

        relationship_map[module_id] = sorted(
            deduped.values(),
            key=lambda item: (
                0 if item["direction"] == "incoming" else 1,
                module_order_map.get(item["module_id"], math.inf),
                str(item["module_title"]).lower(),
                str(item["edge_type"]).lower(),
            ),
        )

    return relationship_map


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
    module_cluster_map, clusters_payload = _build_cluster_metadata(nodes, edges)
    module_relationship_map = _build_module_relationship_map(nodes, edges)

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
            payload["related_modules"] = module_relationship_map.get(node.id, [])
            cluster_meta = module_cluster_map.get(node.id)
        else:
            payload["mastery_percent"] = round(progress_map.get(node.id, 0.0) * 100, 1)
            payload["impact_weight_percent"] = round(node.impact_weight * 100, 1)
            cluster_meta = module_cluster_map.get(node.parent_module_id)

        if cluster_meta:
            payload["cluster_id"] = cluster_meta["id"]
            payload["cluster_label"] = cluster_meta["label"]
            payload["cluster_index"] = cluster_meta["index"]

        graph_nodes.append(payload)

    return {
        "roadmap_id": roadmap.id,
        "roadmap_title": roadmap.title,
        "overall_progress_percent": round(overall_progress * 100, 1),
        "clustering_method": "graph-connectivity-v1",
        "clusters": clusters_payload,
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
    edges = list(roadmap.edges.select_related("source", "target").all())
    _, clusters_payload = _build_cluster_metadata(nodes, edges)
    module_count = sum(1 for node in nodes if node.type == "module")
    topic_count = sum(1 for node in nodes if node.type == "topic")
    edge_count = len(edges)

    if module_progress_map:
        overall_progress = sum(module_progress_map.values()) / len(module_progress_map)
    else:
        overall_progress = 0.0

    return {
        "roadmap_id": roadmap.id,
        "modules_count": module_count,
        "topics_count": topic_count,
        "edges_count": edge_count,
        "clusters_count": len(clusters_payload),
        "overall_progress_percent": round(overall_progress * 100, 1),
    }


def _serialize_roadmap(roadmap, user):
    nodes, progress_map, topics_by_module, module_progress_map = _build_progress_maps(roadmap, user)
    edges = list(roadmap.edges.select_related("source", "target").all())
    module_cluster_map, clusters_payload = _build_cluster_metadata(nodes, edges)
    module_relationship_map = _build_module_relationship_map(nodes, edges)

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
        cluster_meta = module_cluster_map.get(module.id)

        module_payload.append(
            {
                "id": module.id,
                "title": module.title,
                "description": module.description,
                "order": module.order,
                "progress_percent": round(module_progress * 100, 1),
                "cluster_id": cluster_meta["id"] if cluster_meta else None,
                "cluster_label": cluster_meta["label"] if cluster_meta else None,
                "cluster_index": cluster_meta["index"] if cluster_meta else None,
                "related_modules": module_relationship_map.get(module.id, []),
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
        "clustering_method": "graph-connectivity-v1",
        "clusters": clusters_payload,
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

# Graph API (Frontend Handoff)

This file documents only graph-related endpoints.

## Base URL

`https://studentroadmap-api-m5hqauiyxa-nw.a.run.app`

## Auth

All graph endpoints require JWT access token:

`Authorization: Bearer <access_token>`

---

## 1) Course Modules Graph (Adjacency Matrix)

Builds dependency strength between module titles for one course.

`POST /api/catalog/courses/{course_id}/modules/graph/`

### Request body

All fields optional:

```json
{
  "modules": ["Programming Foundations", "Data Structures", "Machine Learning"],
  "threshold": 0.55,
  "max_outgoing": 3,
  "use_ai": true,
  "use_draft_fallback": true,
  "ai_timeout": 60
}
```

### Field notes

- `modules`: explicit module list from FE. If omitted, backend tries stored confirmed/draft modules for this course.
- `threshold`: minimum edge weight kept in final matrix (`0..1`).
- `max_outgoing`: max edges per source module after pruning.
- `use_ai`: if `true`, Gemini generates matrix.
- `use_draft_fallback`: when no confirmed modules exist, allows using draft modules.
- `ai_timeout`: Gemini request timeout (seconds).

### Success (`200`)

```json
{
  "course_id": 3422,
  "course_title": "Computer Science",
  "modules": ["Programming Foundations", "Data Structures", "Machine Learning"],
  "adjacency_matrix": [
    [0, 0.812, 0.301],
    [0, 0, 0.744],
    [0, 0, 0]
  ],
  "source": "gemini",
  "module_source": "stored_confirmed",
  "module_nodes": [
    {"id": 21, "title": "Programming Foundations"},
    {"id": 22, "title": "Data Structures"},
    {"id": 23, "title": "Machine Learning"}
  ]
}
```

### Possible errors

- `400`: not enough modules / validation issue.
- `503`: Gemini not configured / AI generation failure.

---

## 2) Roadmap Graph (Node/Edge)

Returns persisted roadmap graph for graph UI rendering.
Clusters are computed server-side from module dependency connectivity and returned as hints.

`GET /api/roadmaps/{roadmap_id}/graph/`

### Success (`200`)

```json
{
  "roadmap_id": 123,
  "roadmap_title": "Computer Science Roadmap",
  "overall_progress_percent": 34.2,
  "clustering_method": "graph-connectivity-v1",
  "clusters": [
    {
      "id": "cluster-1",
      "label": "Cluster 1",
      "index": 1,
      "module_count": 3,
      "module_ids": [1, 5, 8],
      "module_titles": ["Programming Foundations", "Data Structures", "Machine Learning"]
    }
  ],
  "nodes": [
    {
      "id": 1,
      "type": "module",
      "title": "Programming Foundations",
      "description": "",
      "order": 0,
      "parent_module_id": null,
      "progress_percent": 50.0,
      "topics_count": 3,
      "cluster_id": "cluster-1",
      "cluster_label": "Cluster 1",
      "cluster_index": 1
    },
    {
      "id": 2,
      "type": "topic",
      "title": "Control Flow",
      "description": "",
      "order": 0,
      "parent_module_id": 1,
      "mastery_percent": 70.0,
      "impact_weight_percent": 70.0,
      "cluster_id": "cluster-1",
      "cluster_label": "Cluster 1",
      "cluster_index": 1
    }
  ],
  "edges": [
    {
      "id": 55,
      "source": 1,
      "target": 2,
      "edge_type": "contains",
      "influence_percent": 100.0,
      "rationale": "Module contains this topic."
    }
  ]
}
```

---

## 3) Roadmap Graph Summary

Lightweight counts for dashboard/cards.

`GET /api/roadmaps/{roadmap_id}/graph/summary/`

### Success (`200`)

```json
{
  "roadmap_id": 123,
  "modules_count": 7,
  "topics_count": 21,
  "edges_count": 30,
  "clusters_count": 3,
  "overall_progress_percent": 34.2
}
```

---

## 4) Update Topic Progress (Graph Endpoint)

Updates mastery and returns refreshed graph payload.

`PATCH /api/roadmaps/{roadmap_id}/graph/topics/{topic_id}/progress/`

### Request body

```json
{
  "mastery_percent": 72.5
}
```

### Success (`200`)

Returns same shape as `GET /api/roadmaps/{roadmap_id}/graph/` with updated percentages.

---

## 5) Legacy Progress Endpoint (Still Active)

`PATCH /api/roadmaps/topics/{topic_id}/progress/`

Returns full roadmap detail payload (not graph-only payload).

---

## FE Integration Patterns

## A) Adjacency matrix view only

1. User selects course.
2. Generate/confirm modules.
3. Call `POST /api/catalog/courses/{course_id}/modules/graph/`.
4. Render matrix / convert matrix to edges in frontend.

## B) Full roadmap graph view

1. Generate roadmap via `POST /api/roadmaps/generate/`.
2. Fetch graph via `GET /api/roadmaps/{roadmap_id}/graph/`.
3. Update mastery via `PATCH /api/roadmaps/{roadmap_id}/graph/topics/{topic_id}/progress/`.
4. Re-render from response.

---

## Error Handling Recommendations

- `401`: refresh access token and retry once.
- `429`: Gemini quota issue (if returned by upstream generation flow).
- `503`: AI/service unavailable; show retry + manual fallback UI.

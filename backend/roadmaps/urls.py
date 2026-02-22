from django.urls import path

from .views import (
    RoadmapDetailAPIView,
    RoadmapGenerateAPIView,
    RoadmapGraphAPIView,
    RoadmapGraphSummaryAPIView,
    RoadmapGraphTopicProgressUpdateAPIView,
    RoadmapListAPIView,
    TopicProgressUpdateAPIView,
)

urlpatterns = [
    path("", RoadmapListAPIView.as_view(), name="roadmap-list"),
    path("generate/", RoadmapGenerateAPIView.as_view(), name="roadmap-generate"),
    path("<int:roadmap_id>/", RoadmapDetailAPIView.as_view(), name="roadmap-detail"),
    path("<int:roadmap_id>/graph/", RoadmapGraphAPIView.as_view(), name="roadmap-graph"),
    path("<int:roadmap_id>/graph/summary/", RoadmapGraphSummaryAPIView.as_view(), name="roadmap-graph-summary"),
    path(
        "<int:roadmap_id>/graph/topics/<int:topic_id>/progress/",
        RoadmapGraphTopicProgressUpdateAPIView.as_view(),
        name="roadmap-graph-topic-progress-update",
    ),
    path("topics/<int:topic_id>/progress/", TopicProgressUpdateAPIView.as_view(), name="topic-progress-update"),
]

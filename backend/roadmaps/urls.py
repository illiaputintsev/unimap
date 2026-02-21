from django.urls import path

from .views import (
    RoadmapDetailAPIView,
    RoadmapGenerateAPIView,
    RoadmapListAPIView,
    TopicProgressUpdateAPIView,
)

urlpatterns = [
    path("", RoadmapListAPIView.as_view(), name="roadmap-list"),
    path("generate/", RoadmapGenerateAPIView.as_view(), name="roadmap-generate"),
    path("<int:roadmap_id>/", RoadmapDetailAPIView.as_view(), name="roadmap-detail"),
    path("topics/<int:topic_id>/progress/", TopicProgressUpdateAPIView.as_view(), name="topic-progress-update"),
]

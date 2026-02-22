from django.urls import path

from .views import (
    ModuleNoteDetailAPIView,
    ModuleNoteListCreateAPIView,
    ModuleQuizGenerateAPIView,
    ModuleTopicsGenerateAPIView,
)


urlpatterns = [
    path("module-notes/", ModuleNoteListCreateAPIView.as_view(), name="module-notes-list-create"),
    path("module-notes/<int:note_id>/", ModuleNoteDetailAPIView.as_view(), name="module-note-detail"),
    path("module-topics/generate/", ModuleTopicsGenerateAPIView.as_view(), name="module-topics-generate"),
    path("module-quiz/generate/", ModuleQuizGenerateAPIView.as_view(), name="module-quiz-generate"),
]

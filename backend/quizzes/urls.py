from django.urls import path

from .views import ModuleQuizGenerateAPIView, ModuleTopicsGenerateAPIView


urlpatterns = [
    path("module-topics/generate/", ModuleTopicsGenerateAPIView.as_view(), name="module-topics-generate"),
    path("module-quiz/generate/", ModuleQuizGenerateAPIView.as_view(), name="module-quiz-generate"),
]


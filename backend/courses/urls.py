from django.urls import path

from .views import (
    CourseListAPIView,
    CourseModuleGraphAPIView,
    CourseModulesAPIView,
    CourseModulesConfirmAPIView,
    CourseModulesDraftAPIView,
    DiscoverUniSyncAPIView,
    UniversityListAPIView,
)

urlpatterns = [
    path("universities/", UniversityListAPIView.as_view(), name="university-list"),
    path("courses/", CourseListAPIView.as_view(), name="course-list"),
    path("courses/<int:course_id>/modules/", CourseModulesAPIView.as_view(), name="course-modules"),
    path("courses/<int:course_id>/modules", CourseModulesAPIView.as_view(), name="course-modules-no-slash"),
    path("courses/<int:course_id>/modules/draft/", CourseModulesDraftAPIView.as_view(), name="course-modules-draft"),
    path(
        "courses/<int:course_id>/modules/confirm/",
        CourseModulesConfirmAPIView.as_view(),
        name="course-modules-confirm",
    ),
    path(
        "courses/<int:course_id>/modules/graph/",
        CourseModuleGraphAPIView.as_view(),
        name="course-modules-graph",
    ),
    path("discover-uni/sync/", DiscoverUniSyncAPIView.as_view(), name="discover-uni-sync"),
]

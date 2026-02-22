from django.contrib import admin

from .models import Course, University


@admin.register(University)
class UniversityAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "discover_uni_id", "country")
    search_fields = ("name", "discover_uni_id")


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "university",
        "discover_uni_course_id",
        "study_mode",
        "subject_area",
        "duration_years",
        "modules_last_scraped_at",
        "ai_draft_source",
        "ai_draft_generated_at",
        "ai_draft_modules_count",
    )
    list_filter = ("university", "subject_area", "study_mode", "ai_draft_source")
    search_fields = ("title", "discover_uni_course_id", "university__name")
    readonly_fields = (
        "ai_draft_generated_at",
        "ai_draft_source",
        "ai_draft_model",
        "ai_draft_confidence",
        "ai_draft_notes",
        "ai_draft_modules",
        "ai_draft_years",
    )

    def ai_draft_modules_count(self, obj):
        return len(obj.ai_draft_modules or [])
    ai_draft_modules_count.short_description = "Draft modules"

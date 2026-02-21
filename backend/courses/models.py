from django.db import models


class University(models.Model):
    name = models.CharField(max_length=255)
    discover_uni_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    country = models.CharField(max_length=64, blank=True, default="UK")

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

class Course(models.Model):
    university = models.ForeignKey(University, on_delete=models.CASCADE, related_name="courses")
    title = models.CharField(max_length=255)
    discover_uni_course_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    subject_area = models.CharField(max_length=255, blank=True, default="")
    duration_years = models.PositiveSmallIntegerField(null=True, blank=True)
    study_mode = models.CharField(max_length=8, blank=True, default="", db_index=True)
    course_url = models.URLField(max_length=500, blank=True, default="")
    scraped_modules = models.JSONField(blank=True, default=list)
    modules_last_scraped_at = models.DateTimeField(null=True, blank=True)
    ai_draft_modules = models.JSONField(blank=True, default=list)
    ai_draft_years = models.JSONField(blank=True, default=list)
    ai_draft_source = models.CharField(max_length=32, blank=True, default="")
    ai_draft_model = models.CharField(max_length=128, blank=True, default="")
    ai_draft_confidence = models.FloatField(null=True, blank=True)
    ai_draft_notes = models.TextField(blank=True, default="")
    ai_draft_generated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("title",)

    def __str__(self):
        return f"{self.title} ({self.university})"

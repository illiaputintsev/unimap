from django.conf import settings
from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator

class Roadmap(models.Model):
    GENERATION_SOURCES = [
        ("gemini", "Gemini"),
        ("fallback", "Fallback"),
        ("manual", "Manual"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="roadmaps")
    course = models.ForeignKey("courses.Course", on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=255, default="My Roadmap")
    manual_course_title = models.CharField(max_length=255, blank=True, default="")
    generation_source = models.CharField(max_length=16, choices=GENERATION_SOURCES, default="fallback")
    generation_notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.title

class Node(models.Model):
    ROADMAP_NODE_TYPES = [("module", "Module"), ("topic", "Topic")]

    roadmap = models.ForeignKey(Roadmap, on_delete=models.CASCADE, related_name="nodes")
    type = models.CharField(max_length=16, choices=ROADMAP_NODE_TYPES)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    order = models.IntegerField(default=0)  # useful for UI layout hints
    parent_module = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="topics",
    )
    impact_weight = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )

    class Meta:
        ordering = ("order", "id")

    def __str__(self):
        return f"{self.type}: {self.title}"

class Edge(models.Model):
    EDGE_TYPES = [
        ("prerequisite", "Prerequisite"),
        ("contains", "Contains"),
        ("career", "Career"),
    ]

    roadmap = models.ForeignKey(Roadmap, on_delete=models.CASCADE, related_name="edges")
    source = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="out_edges")
    target = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="in_edges")
    edge_type = models.CharField(max_length=16, choices=EDGE_TYPES, default="prerequisite")
    influence = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )  # 0..1 (your “% affects future module” idea)
    rationale = models.CharField(max_length=255, blank=True, default="")

class TopicProgress(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    node = models.ForeignKey(Node, on_delete=models.CASCADE)  # should be a topic node
    mastery = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )  # 0..1
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "node")

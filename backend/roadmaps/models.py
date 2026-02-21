from django.conf import settings
from django.db import models

class Roadmap(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="roadmaps")
    course = models.ForeignKey("courses.Course", on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=255, default="My Roadmap")
    created_at = models.DateTimeField(auto_now_add=True)

class Node(models.Model):
    ROADMAP_NODE_TYPES = [("module", "Module"), ("topic", "Topic")]

    roadmap = models.ForeignKey(Roadmap, on_delete=models.CASCADE, related_name="nodes")
    type = models.CharField(max_length=16, choices=ROADMAP_NODE_TYPES)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    order = models.IntegerField(default=0)  # useful for UI layout hints

class Edge(models.Model):
    roadmap = models.ForeignKey(Roadmap, on_delete=models.CASCADE, related_name="edges")
    source = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="out_edges")
    target = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="in_edges")

    influence = models.FloatField(default=0.0)  # 0..1 (your “% affects future module” idea)
    rationale = models.CharField(max_length=255, blank=True, default="")

class TopicProgress(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    node = models.ForeignKey(Node, on_delete=models.CASCADE)  # should be a topic node
    mastery = models.FloatField(default=0.0)  # 0..1
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "node")
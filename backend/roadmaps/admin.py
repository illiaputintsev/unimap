from django.contrib import admin

from .models import Edge, Node, Roadmap, TopicProgress


@admin.register(Roadmap)
class RoadmapAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "user", "course", "generation_source", "created_at")
    search_fields = ("title", "user__username", "manual_course_title")
    list_filter = ("generation_source", "created_at")


@admin.register(Node)
class NodeAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "type", "roadmap", "parent_module", "order")
    list_filter = ("type",)
    search_fields = ("title", "roadmap__title")


@admin.register(Edge)
class EdgeAdmin(admin.ModelAdmin):
    list_display = ("id", "roadmap", "source", "target", "edge_type", "influence")
    list_filter = ("edge_type",)


@admin.register(TopicProgress)
class TopicProgressAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "node", "mastery", "updated_at")
    search_fields = ("user__username", "node__title")

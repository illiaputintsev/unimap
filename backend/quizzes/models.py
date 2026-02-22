import os

from django.conf import settings
from django.db import models


def _module_note_upload_to(instance, filename):
    base_name = os.path.basename(filename or "note.pdf")
    user_id = instance.user_id or "anon"
    roadmap_part = f"roadmap-{instance.roadmap_id}" if instance.roadmap_id else "roadmap-local"
    module_part = f"module-{instance.module_id or 'unknown'}"
    return f"module_notes/user-{user_id}/{roadmap_part}/{module_part}/{base_name}"


class ModuleWorkspaceNote(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="module_workspace_notes",
    )
    roadmap = models.ForeignKey(
        "roadmaps.Roadmap",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="module_workspace_notes",
    )
    module_id = models.CharField(max_length=128)
    module_title = models.CharField(max_length=255, blank=True, default="")
    file = models.FileField(upload_to=_module_note_upload_to)
    original_filename = models.CharField(max_length=255, blank=True, default="")
    content_type = models.CharField(max_length=127, blank=True, default="")
    file_size = models.BigIntegerField(default=0)
    pages_parsed = models.PositiveIntegerField(default=0)
    char_count = models.PositiveIntegerField(default=0)
    extracted_text_excerpt = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")

    def __str__(self):
        title = self.module_title or self.module_id or "module"
        return f"{title} · {self.original_filename or self.file.name}"


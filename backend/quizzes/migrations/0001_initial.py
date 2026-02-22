from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

import quizzes.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("roadmaps", "0002_roadmap_generation_and_progress_metadata"),
    ]

    operations = [
        migrations.CreateModel(
            name="ModuleWorkspaceNote",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("module_id", models.CharField(max_length=128)),
                ("module_title", models.CharField(blank=True, default="", max_length=255)),
                ("file", models.FileField(upload_to=quizzes.models._module_note_upload_to)),
                ("original_filename", models.CharField(blank=True, default="", max_length=255)),
                ("content_type", models.CharField(blank=True, default="", max_length=127)),
                ("file_size", models.BigIntegerField(default=0)),
                ("pages_parsed", models.PositiveIntegerField(default=0)),
                ("char_count", models.PositiveIntegerField(default=0)),
                ("extracted_text_excerpt", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "roadmap",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="module_workspace_notes",
                        to="roadmaps.roadmap",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="module_workspace_notes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("-created_at", "-id")},
        ),
    ]


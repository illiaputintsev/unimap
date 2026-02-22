from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("roadmaps", "0002_roadmap_generation_and_progress_metadata"),
        ("quizzes", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ModuleWorkspaceState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("module_id", models.CharField(max_length=128)),
                ("module_title", models.CharField(blank=True, default="", max_length=255)),
                ("state_version", models.PositiveIntegerField(default=1)),
                ("topics", models.JSONField(blank=True, default=list)),
                ("attempts", models.JSONField(blank=True, default=list)),
                ("mistake_bank", models.JSONField(blank=True, default=list)),
                ("topic_stats", models.JSONField(blank=True, default=dict)),
                ("activity", models.JSONField(blank=True, default=list)),
                ("last_generated", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "roadmap",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="module_workspace_states",
                        to="roadmaps.roadmap",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="module_workspace_states",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("-updated_at", "-id")},
        ),
        migrations.AddConstraint(
            model_name="moduleworkspacestate",
            constraint=models.UniqueConstraint(
                condition=models.Q(("roadmap__isnull", False)),
                fields=("user", "roadmap", "module_id"),
                name="uniq_module_workspace_state_user_roadmap_module",
            ),
        ),
        migrations.AddConstraint(
            model_name="moduleworkspacestate",
            constraint=models.UniqueConstraint(
                condition=models.Q(("roadmap__isnull", True)),
                fields=("user", "module_id"),
                name="uniq_module_workspace_state_user_local_module",
            ),
        ),
    ]

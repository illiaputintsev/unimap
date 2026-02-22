# Generated manually for roadmap generation and progress metadata
import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("roadmaps", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="roadmap",
            name="generation_notes",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="roadmap",
            name="generation_source",
            field=models.CharField(
                choices=[("gemini", "Gemini"), ("fallback", "Fallback"), ("manual", "Manual")],
                default="fallback",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="roadmap",
            name="manual_course_title",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="roadmap",
            name="updated_at",
            field=models.DateTimeField(default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="roadmap",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name="node",
            name="impact_weight",
            field=models.FloatField(
                default=0.0,
                validators=[
                    django.core.validators.MinValueValidator(0.0),
                    django.core.validators.MaxValueValidator(1.0),
                ],
            ),
        ),
        migrations.AddField(
            model_name="node",
            name="parent_module",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="topics",
                to="roadmaps.node",
            ),
        ),
        migrations.AddField(
            model_name="edge",
            name="edge_type",
            field=models.CharField(
                choices=[("prerequisite", "Prerequisite"), ("contains", "Contains"), ("career", "Career")],
                default="prerequisite",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="edge",
            name="influence",
            field=models.FloatField(
                default=0.0,
                validators=[
                    django.core.validators.MinValueValidator(0.0),
                    django.core.validators.MaxValueValidator(1.0),
                ],
            ),
        ),
        migrations.AlterField(
            model_name="topicprogress",
            name="mastery",
            field=models.FloatField(
                default=0.0,
                validators=[
                    django.core.validators.MinValueValidator(0.0),
                    django.core.validators.MaxValueValidator(1.0),
                ],
            ),
        ),
        migrations.AlterModelOptions(
            name="node",
            options={"ordering": ("order", "id")},
        ),
        migrations.AlterModelOptions(
            name="roadmap",
            options={"ordering": ("-created_at",)},
        ),
    ]

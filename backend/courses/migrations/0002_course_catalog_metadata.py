# Generated manually for course catalog metadata
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="university",
            name="country",
            field=models.CharField(blank=True, default="UK", max_length=64),
        ),
        migrations.AddField(
            model_name="university",
            name="discover_uni_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="course",
            name="discover_uni_course_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="course",
            name="duration_years",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="course",
            name="subject_area",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AlterModelOptions(
            name="course",
            options={"ordering": ("title",)},
        ),
        migrations.AlterModelOptions(
            name="university",
            options={"ordering": ("name",)},
        ),
    ]

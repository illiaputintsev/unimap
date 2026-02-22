from rest_framework import serializers

from .models import Course, University


class UniversitySerializer(serializers.ModelSerializer):
    class Meta:
        model = University
        fields = ("id", "name", "discover_uni_id", "country")


class CourseSerializer(serializers.ModelSerializer):
    university_name = serializers.CharField(source="university.name", read_only=True)

    class Meta:
        model = Course
        fields = (
            "id",
            "title",
            "university",
            "university_name",
            "discover_uni_course_id",
            "subject_area",
            "duration_years",
            "study_mode",
            "course_url",
        )


class CourseModulesDraftRequestSerializer(serializers.Serializer):
    refresh = serializers.BooleanField(required=False, default=False)
    insecure = serializers.BooleanField(required=False, default=False)
    timeout = serializers.IntegerField(required=False, min_value=3, max_value=60, default=15)
    context_text = serializers.CharField(required=False, allow_blank=True, max_length=12000)
    use_ai = serializers.BooleanField(required=False, default=True)


class CourseModulesConfirmRequestSerializer(serializers.Serializer):
    modules = serializers.ListField(
        child=serializers.CharField(max_length=255),
        allow_empty=False,
        max_length=60,
    )


class CourseModuleGraphRequestSerializer(serializers.Serializer):
    modules = serializers.ListField(
        child=serializers.CharField(max_length=255),
        required=False,
        allow_empty=False,
        max_length=60,
    )
    threshold = serializers.FloatField(required=False, min_value=0.0, max_value=1.0, default=0.55)
    max_outgoing = serializers.IntegerField(required=False, min_value=1, max_value=8, default=3)
    use_ai = serializers.BooleanField(required=False, default=True)
    use_draft_fallback = serializers.BooleanField(required=False, default=True)
    ai_timeout = serializers.IntegerField(required=False, min_value=10, max_value=120, default=60)

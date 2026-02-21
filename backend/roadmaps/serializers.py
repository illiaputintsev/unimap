from rest_framework import serializers


class GenerateRoadmapRequestSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255, required=False, allow_blank=True)
    course_id = serializers.IntegerField(required=False)
    manual_course_title = serializers.CharField(max_length=255, required=False, allow_blank=True)
    module_names = serializers.ListField(
        child=serializers.CharField(max_length=255),
        required=False,
        allow_empty=False,
    )
    career_goal = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate(self, attrs):
        course_id = attrs.get("course_id")
        manual_course_title = attrs.get("manual_course_title", "").strip()
        module_names = attrs.get("module_names", [])

        if not course_id and not manual_course_title:
            if module_names:
                manual_course_title = "Custom Course"
            else:
                raise serializers.ValidationError(
                    "Provide either course_id or manual_course_title to generate a roadmap."
                )

        attrs["manual_course_title"] = manual_course_title
        return attrs


class TopicProgressUpdateSerializer(serializers.Serializer):
    mastery_percent = serializers.FloatField(min_value=0.0, max_value=100.0)

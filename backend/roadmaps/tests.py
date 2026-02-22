from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from courses.models import Course, University


User = get_user_model()


@override_settings(GEMINI_API_KEY="")
class RoadmapAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="student1", password="strong-pass-123")
        self.client.force_authenticate(self.user)

        self.university = University.objects.create(name="Example University")
        self.course = Course.objects.create(
            university=self.university,
            title="Computer Science BSc",
        )

    def test_generate_roadmap_with_manual_course(self):
        payload = {
            "manual_course_title": "Computer Science",
            "module_names": ["Programming Foundations", "Mathematics for Computing", "Data Science"],
            "career_goal": "Data Scientist",
        }
        response = self.client.post("/api/roadmaps/generate/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["generation_source"], "fallback")
        self.assertEqual(len(response.data["modules"]), 3)

        first_module = response.data["modules"][0]
        self.assertGreaterEqual(len(first_module["topics"]), 1)
        self.assertIn("clusters", response.data)
        self.assertGreater(len(response.data["clusters"]), 0)
        self.assertIn("cluster_id", first_module)
        self.assertTrue(first_module["cluster_id"])

        edge_types = {edge["edge_type"] for edge in response.data["edges"]}
        self.assertIn("contains", edge_types)

    def test_generate_roadmap_from_course_id(self):
        payload = {"course_id": self.course.id}
        response = self.client.post("/api/roadmaps/generate/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["course"]["id"], self.course.id)

    def test_generate_roadmap_uses_scraped_modules_when_course_selected(self):
        self.course.scraped_modules = ["Module A", "Module B", "Module C"]
        self.course.save(update_fields=["scraped_modules"])

        response = self.client.post(
            "/api/roadmaps/generate/",
            {"course_id": self.course.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        returned_titles = [module["title"] for module in response.data["modules"]]
        self.assertEqual(returned_titles[:3], ["Module A", "Module B", "Module C"])
        self.assertIn("Used modules scraped from course URL.", response.data["generation_notes"])

    def test_generate_roadmap_with_only_module_names(self):
        response = self.client.post(
            "/api/roadmaps/generate/",
            {"module_names": ["Intro", "Advanced"]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["manual_course_title"], "Custom Course")

    def test_update_topic_progress_updates_module_and_overall_progress(self):
        generate_response = self.client.post(
            "/api/roadmaps/generate/",
            {"manual_course_title": "Computer Science"},
            format="json",
        )
        self.assertEqual(generate_response.status_code, status.HTTP_201_CREATED)

        topic_id = generate_response.data["modules"][0]["topics"][0]["id"]

        update_response = self.client.patch(
            f"/api/roadmaps/topics/{topic_id}/progress/",
            {"mastery_percent": 80},
            format="json",
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)

        updated_topic = update_response.data["modules"][0]["topics"][0]
        self.assertEqual(updated_topic["mastery_percent"], 80.0)
        self.assertGreater(update_response.data["modules"][0]["progress_percent"], 0)
        self.assertGreater(update_response.data["overall_progress_percent"], 0)

    def test_get_roadmap_graph_returns_nodes_and_edges(self):
        generate_response = self.client.post(
            "/api/roadmaps/generate/",
            {"manual_course_title": "Computer Science"},
            format="json",
        )
        self.assertEqual(generate_response.status_code, status.HTTP_201_CREATED)

        roadmap_id = generate_response.data["id"]
        response = self.client.get(f"/api/roadmaps/{roadmap_id}/graph/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["roadmap_id"], roadmap_id)
        self.assertIn("nodes", response.data)
        self.assertIn("edges", response.data)
        self.assertIn("clusters", response.data)
        self.assertGreater(len(response.data["clusters"]), 0)

        node_types = {node["type"] for node in response.data["nodes"]}
        self.assertIn("module", node_types)
        self.assertIn("topic", node_types)

        module_node = next(node for node in response.data["nodes"] if node["type"] == "module")
        self.assertIn("cluster_id", module_node)
        self.assertTrue(module_node["cluster_id"])
        self.assertIn("cluster_label", module_node)
        self.assertIn("cluster_index", module_node)

    def test_get_roadmap_graph_summary_returns_counts(self):
        generate_response = self.client.post(
            "/api/roadmaps/generate/",
            {"manual_course_title": "Computer Science"},
            format="json",
        )
        self.assertEqual(generate_response.status_code, status.HTTP_201_CREATED)
        roadmap_id = generate_response.data["id"]

        response = self.client.get(f"/api/roadmaps/{roadmap_id}/graph/summary/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["roadmap_id"], roadmap_id)
        self.assertGreater(response.data["modules_count"], 0)
        self.assertGreater(response.data["topics_count"], 0)
        self.assertGreater(response.data["edges_count"], 0)
        self.assertGreater(response.data["clusters_count"], 0)

    def test_graph_topic_progress_update_endpoint(self):
        generate_response = self.client.post(
            "/api/roadmaps/generate/",
            {"manual_course_title": "Computer Science"},
            format="json",
        )
        self.assertEqual(generate_response.status_code, status.HTTP_201_CREATED)
        roadmap_id = generate_response.data["id"]
        topic_id = generate_response.data["modules"][0]["topics"][0]["id"]

        response = self.client.patch(
            f"/api/roadmaps/{roadmap_id}/graph/topics/{topic_id}/progress/",
            {"mastery_percent": 55},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        topic_payload = next(node for node in response.data["nodes"] if node["id"] == topic_id)
        self.assertEqual(topic_payload["mastery_percent"], 55.0)

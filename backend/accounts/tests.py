from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase


User = get_user_model()


class RegisterAPITests(APITestCase):
    def test_register_user(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "username": "newstudent",
                "email": "student@example.com",
                "password": "secure-pass-123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(username="newstudent").exists())

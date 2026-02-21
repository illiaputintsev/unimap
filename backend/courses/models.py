from django.db import models

class University(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name

class Course(models.Model):
    university = models.ForeignKey(University, on_delete=models.CASCADE, related_name="courses")
    title = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.title} ({self.university})"
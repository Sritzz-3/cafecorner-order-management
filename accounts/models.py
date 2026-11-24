from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models


class Profile(models.Model):
    class Role(models.TextChoices):
        CUSTOMER = "CUSTOMER", "Customer"
        STAFF = "STAFF", "Staff"
        ADMIN = "ADMIN", "Admin"
        PRINTER = "PRINTER", "Printer"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.CUSTOMER)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        group_name = self.get_role_display()
        group, _ = Group.objects.get_or_create(name=group_name)
        self.user.groups.set([group])

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

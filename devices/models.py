from django.db import models
from vehicles.models import Vehicle

class Device(models.Model):
    name = models.CharField(max_length=100)
    token = models.CharField(max_length=64, unique=True)

    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    is_active = models.BooleanField(default=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
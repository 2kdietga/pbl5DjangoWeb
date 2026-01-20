from django.db import models
from categories.models import Category
from accounts.models import Account
from vehicles.models import Vehicle

class Violation(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    reporter = models.ForeignKey(Account, on_delete=models.CASCADE)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE)

    title = models.CharField(max_length=200)
    description = models.TextField()
    reported_at = models.DateTimeField(auto_now_add=True)
    image = models.ImageField(upload_to='violations/', null=True, blank=True)


    def __str__(self):
        return self.title

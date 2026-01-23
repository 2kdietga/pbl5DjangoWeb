from django.db import models
from categories.models import Category
from accounts.models import Account
from vehicles.models import Vehicle

class Violation(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    reporter = models.ForeignKey(Account, on_delete=models.CASCADE)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE)

    title = models.CharField(max_length=200, default ="Violation Report") 
    description = models.TextField()
    reported_at = models.DateTimeField(auto_now_add=True)
    image = models.ImageField(upload_to='violations/', null=True, blank=True)
    viewed = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Violation"
        verbose_name_plural = "Violations"
        ordering = ['-reported_at']

    def __str__(self):
        return self.reporter.get_full_name() + " - " + self.category.name

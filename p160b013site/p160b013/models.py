# C:\EP\p160b013site\p160b013\models.py
from django.db import models
import os
from django.conf import settings

class City(models.Model):
    name = models.CharField(max_length=100, unique=True)
    country = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    image_url = models.URLField(blank=True, null=True)

    def __str__(self):
        return self.name
    class Meta:
        verbose_name_plural = "Cities"

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name
    class Meta:
        verbose_name_plural = "Categories"

class Place(models.Model):
    wikidata_id = models.CharField(max_length=50, unique=True, blank=True, null=True)
    name = models.CharField(max_length=200)
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name='places')
    categories = models.ManyToManyField(Category, related_name='places', blank=True)
    description = models.TextField(blank=True)
    location_lat = models.FloatField(blank=True, null=True)
    location_lon = models.FloatField(blank=True, null=True)
    address = models.CharField(max_length=255, blank=True)
    image_url = models.URLField(blank=True, null=True)
    local_image_path = models.CharField(max_length=500, blank=True)
    page_rank_score = models.FloatField(default=0.0)

    @property
    def get_display_image_url(self):
        if self.local_image_path and os.path.exists(self.local_image_path) and settings.MEDIA_ROOT:
            try:
                relative_path = os.path.relpath(self.local_image_path, settings.MEDIA_ROOT)
                return f"{settings.MEDIA_URL}{relative_path.replace(os.sep, '/')}"
            except ValueError:
                 pass
        if self.image_url:
            return self.image_url
        return "https://via.placeholder.com/300x200?text=No+Image"

    def __str__(self):
        return f"{self.name}, {self.city.name}"

class DominantColor(models.Model):
    place = models.ForeignKey(Place, on_delete=models.CASCADE, related_name='dominant_colors')
    red = models.IntegerField()
    green = models.IntegerField()
    blue = models.IntegerField()
    rank = models.IntegerField() # Rank 1 to 5

    class Meta:
        unique_together = ('place', 'rank')
        ordering = ['place', 'rank']

    def __str__(self):
        return f"{self.place.name} - Color {self.rank} ({self.red},{self.green},{self.blue})"

    @property
    def hex_code(self):
        return f"#{self.red:02x}{self.green:02x}{self.blue:02x}"

# --- UPDATED SimilarityType Choices ---
class SimilarityType(models.TextChoices):
    STRUCT_SAME = 'STRUCT_SAME', 'Structural - Same City'
    IMG_SAME = 'IMG_SAME', 'Image - Same City' # Updated Label
    IMG_OTHER = 'IMG_OTHER', 'Image - Other Cities' # Updated Label
    IMG_COLOR = 'IMG_COLOR', 'Image (Color) - Any City' # Kept for potential future use or if processing relies on it
# --- END UPDATE ---

class SimilarPlace(models.Model):
    main_place = models.ForeignKey(Place, on_delete=models.CASCADE, related_name='similar_to')
    similar_place = models.ForeignKey(Place, on_delete=models.CASCADE, related_name='similar_from')
    similarity_score = models.FloatField()
    similarity_type = models.CharField(max_length=20, choices=SimilarityType.choices)

    class Meta:
        unique_together = ('main_place', 'similar_place', 'similarity_type')
        ordering = ['-similarity_score']

    def __str__(self):
        return f"{self.main_place.name} -> {self.similar_place.name} ({self.get_similarity_type_display()})"

class ImageFeature(models.Model):
    place = models.OneToOneField(Place, on_delete=models.CASCADE, primary_key=True, related_name='image_features')
    features = models.BinaryField()

    def __str__(self):
        return f"Features for {self.place.name}"
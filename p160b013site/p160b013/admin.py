# C:\EP\p160b013site\p160b013\admin.py
from django.contrib import admin
from .models import City, Category, Place, SimilarPlace, ImageFeature, DominantColor # Added DominantColor

admin.site.register(City)
admin.site.register(Category)
admin.site.register(Place)
admin.site.register(SimilarPlace)
admin.site.register(ImageFeature)
admin.site.register(DominantColor) # Register the new model
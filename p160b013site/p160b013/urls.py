# C:\EP\p160b013site\p160b013\urls.py
from django.urls import path
from . import views

app_name = 'p160b013' # Optional: for namespacing

urlpatterns = [
    path('', views.index, name='index'), # Home page - list cities
    path('city/<int:city_id>/', views.city_view, name='city_view'), # City page
    path('place/<int:place_id>/', views.place_detail, name='place_detail'), # POI page
]
# C:\EP\p160b013site\p160b013\views.py
from django.shortcuts import render, get_object_or_404
from .models import City, Place, SimilarPlace, SimilarityType, DominantColor
from django.core.paginator import Paginator
from django.db.models import F

def index(request):
    cities = City.objects.all().order_by('name')
    # Pass all cities to the context for the navbar
    return render(request, 'p160b013/index.html', {
        'cities': cities,
        'all_cities_nav': cities
        })

def city_view(request, city_id):
    city = get_object_or_404(City, pk=city_id)
    places_list = city.places.all()

    sort_by = request.GET.get('sort', 'name')
    if sort_by == 'score':
        places_list = places_list.order_by(F('page_rank_score').desc(nulls_last=True), 'name')
    else:
        places_list = places_list.order_by('name')

    paginator = Paginator(places_list, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    all_cities = City.objects.all().order_by('name') # For navigation

    return render(request, 'p160b013/city_view.html', {
        'city': city,
        'page_obj': page_obj,
        'sort_by': sort_by,
        'all_cities_nav': all_cities # For navbar
    })

def place_detail(request, place_id):
    # Prefetch related dominant colors and select related city
    place = get_object_or_404(
        Place.objects.select_related('city').prefetch_related('dominant_colors'),
        pk=place_id
    )

    sim_struct_same = SimilarPlace.objects.filter(
        main_place=place, similarity_type=SimilarityType.STRUCT_SAME
    ).select_related('similar_place__city')[:5]

    sim_img_same = SimilarPlace.objects.filter(
        main_place=place, similarity_type=SimilarityType.IMG_SAME
    ).select_related('similar_place__city')[:5]

    sim_img_other = SimilarPlace.objects.filter(
        main_place=place, similarity_type=SimilarityType.IMG_OTHER
    ).select_related('similar_place__city')[:5]

    # --- REMOVED Color Similarity Fetch ---
    # sim_img_color = SimilarPlace.objects.filter(
    #     main_place=place, similarity_type=SimilarityType.IMG_COLOR
    # ).select_related('similar_place__city')[:5]
    # --- END REMOVE ---

    all_cities = City.objects.all().order_by('name') # For navigation

    return render(request, 'p160b013/place_detail.html', {
        'place': place,
        'sim_struct_same': sim_struct_same,
        'sim_img_same': sim_img_same,
        'sim_img_other': sim_img_other,
        # 'sim_img_color': sim_img_color, # Removed from context
        'all_cities_nav': all_cities # For navbar
    })
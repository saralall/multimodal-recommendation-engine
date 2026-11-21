# C:\EP\data_load\load_to_db.py
import os
import sys
import django # Keep django import here
import csv
import re

def setup_django_env():
    """Sets up the Django environment to allow model access."""
    print("--- Running setup_django_env ---")
    try:
        # Calculate the absolute path to the Django project directory (p160b013site)
        # __file__ is the path to data_load/load_to_db.py
        # os.path.dirname(__file__) is data_load/
        # os.path.join(..., '..') goes up one level to EP/
        # os.path.join(..., '..', 'p160b013site') goes into EP/p160b013site/
        current_script_dir = os.path.dirname(os.path.abspath(__file__))
        project_path = os.path.abspath(os.path.join(current_script_dir, '..', 'p160b013site'))
        
        print(f"Calculated project_path: {project_path}")

        # Add the project path to sys.path if it's not already there
        if project_path not in sys.path:
            sys.path.insert(0, project_path) # Insert at the beginning
            print(f"Added {project_path} to sys.path")
        else:
            print(f"{project_path} is already in sys.path")

        # For good measure, also add the parent directory of the project_path (C:\EP)
        # This helps if Django settings or apps are structured in a way that expects this.
        # project_parent_dir = os.path.dirname(project_path)
        # if project_parent_dir not in sys.path:
        #     sys.path.insert(1, project_parent_dir) # Insert after project_path
        #     print(f"Added {project_parent_dir} to sys.path")

        print(f"Current sys.path: {sys.path}")

        # Set the DJANGO_SETTINGS_MODULE environment variable
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mysite.settings')
        print(f"DJANGO_SETTINGS_MODULE is set to: {os.environ['DJANGO_SETTINGS_MODULE']}")

        # Initialize Django
        print("Calling django.setup()...")
        django.setup()
        print("django.setup() completed successfully.")

    except Exception as e:
        print(f"!!! ERROR during django.setup(): {e} !!!")
        print("This often means DJANGO_SETTINGS_MODULE is incorrect, a required app is missing,")
        print("or there's an issue with your settings.py or installed apps.")
        sys.exit(1) # Exit if setup fails, as models cannot be imported

def load_data():
    """Loads data from CSV into the Django database."""
    print("--- Starting load_data ---")
    setup_django_env() # Ensure Django environment is set up
    
    # Model imports should now work if django.setup() was successful
    print("Attempting to import Django models...")
    from p160b013.models import City, Category, Place, ImageFeature, SimilarPlace
    print("Django models imported successfully.")

    CSV_FILE = os.path.join(os.path.dirname(__file__), '..', 'data_collection', 'collected_data', 'pois_merged_final.csv')

    if not os.path.exists(CSV_FILE):
        print(f"Error: MERGED CSV file not found at {CSV_FILE}")
        return

    print("Deleting old data (SimilarPlaces, ImageFeatures, Places, Categories, Cities)...")
    SimilarPlace.objects.all().delete()
    ImageFeature.objects.all().delete()
    Place.objects.all().delete()
    Category.objects.all().delete()
    City.objects.all().delete()
    print("Old data deleted.")

    print(f"Loading data from {CSV_FILE}...")

    city_cache = {}
    category_cache = {}
    places_to_process = []

    with open(CSV_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            try:
                city_name = row.get('city', 'Unknown City').strip()
                country_name = row.get('country', '').strip()

                if city_name not in city_cache:
                    city, _ = City.objects.get_or_create(
                        name=city_name,
                        defaults={'country': country_name}
                    )
                    city_cache[city_name] = city
                
                city_obj = city_cache[city_name]

                place = Place.objects.create(
                    wikidata_id=row.get('id', '').strip() or f"generated_id_{i}",
                    name=row.get('name', 'N/A').strip(),
                    city=city_obj,
                    description=row.get('description', '').strip(),
                    location_lat=float(row['lat']) if row.get('lat') and row.get('lat').strip() else None,
                    location_lon=float(row['lon']) if row.get('lon') and row.get('lon').strip() else None,
                    image_url=row.get('image_url', '').strip(),
                    local_image_path=row.get('local_image_path', '').strip(),
                )

                places_to_process.append({
                    'place_obj': place,
                    'categories_str': row.get('categories', '').strip()
                })

                if (i + 1) % 100 == 0: # Reduced frequency of printing
                     print(f"  Prepared {i+1} rows for place creation...")

            except ValueError as ve:
                print(f"  Skipping row due to ValueError: {row.get('name', 'N/A')}: {ve}")
            except Exception as e:
                print(f"  Error processing row for place creation: {row.get('name', 'N/A')}: {e}")

    print(f"Created {len(places_to_process)} Place objects.")
    print("Adding categories to places...")

    for idx, item in enumerate(places_to_process):
        place_obj = item['place_obj']
        cat_names_raw = item['categories_str'].split('|')
        categories_for_place = []

        for cat_name in cat_names_raw:
            cat_name_cleaned = re.sub(r"[\"']", "", cat_name).strip()
            if cat_name_cleaned:
                if cat_name_cleaned not in category_cache:
                    cat_obj, _ = Category.objects.get_or_create(name=cat_name_cleaned)
                    category_cache[cat_name_cleaned] = cat_obj
                
                categories_for_place.append(category_cache[cat_name_cleaned])

        if categories_for_place:
            try:
                place_obj.categories.set(categories_for_place)
            except Exception as e:
                print(f"Error setting categories for place {place_obj.name}: {e}")
        
        if (idx + 1) % 100 == 0:
            print(f"  Processed categories for {idx+1} places...")


    print("Categories linked to places.")
    print("Data loading finished.")

if __name__ == "__main__":
    # It's good practice to ensure sys.path manipulation happens right at the start
    # if the script is run directly, before even defining functions that might
    # implicitly try to load Django stuff if they were imported elsewhere.
    # However, for this script, setup_django_env() handles it before model import.
    load_data()
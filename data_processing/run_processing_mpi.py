# C:\EP\data_processing\run_processing_mpi.py
from mpi4py import MPI
import numpy as np
import os
import sys
import django
import pickle
from sklearn.metrics.pairwise import cosine_similarity
import networkx as nx
import time
# --- ADDED for Color Extraction & Similarity ---
import cv2 # Requires opencv-python
from sklearn.cluster import KMeans # Requires scikit-learn
# --- END ADD ---

# --- Setup Django Environment ---
def setup_django_env():
    project_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'p160b013site'))
    if project_path not in sys.path:
        sys.path.append(project_path)
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mysite.settings')
    try:
        django.setup()
    except Exception as e:
        print(f"Django setup failed: {e}")
        sys.exit(1)

# --- ADDED K-Means Color Extractor ---
def extract_dominant_colors(image_path, k=5):
    """Extracts k dominant colors using K-Means."""
    try:
        img = cv2.imread(image_path)
        if img is None:
            # print(f"  Rank {MPI.COMM_WORLD.Get_rank()}: Could not read image {os.path.basename(image_path)}")
            return None
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        pixels = img.reshape(-1, 3)
        # Reduce sample size for faster K-Means if image is large
        if pixels.shape[0] > 50000:
             pixels = pixels[np.random.choice(pixels.shape[0], 50000, replace=False)]

        kmeans = KMeans(n_clusters=k, n_init=5, random_state=42) # n_init=5 for speed
        kmeans.fit(pixels)
        counts = np.bincount(kmeans.labels_)
        sorted_idx = np.argsort(-counts)
        centroids = kmeans.cluster_centers_.astype(int)
        return centroids[sorted_idx] # Returns a (k, 3) array
    except Exception as e:
        # print(f"  Rank {MPI.COMM_WORLD.Get_rank()}: Error extracting colors from {os.path.basename(image_path)}: {e}")
        return None
# --- END ADD ---

# --- Image Feature Extraction (VGG16) ---
def process_image_features_worker(places_to_process):
    from tensorflow.keras.applications.vgg16 import VGG16, preprocess_input
    from tensorflow.keras.preprocessing import image as tf_image
    from tensorflow.keras.models import Model

    results_vgg = []
    results_color = []
    model = None
    rank = MPI.COMM_WORLD.Get_rank()

    try:
        base_model = VGG16(weights='imagenet', include_top=True)
        model = Model(inputs=base_model.input, outputs=base_model.get_layer('fc1').output)
    except Exception as e:
        print(f"Rank {rank}: FAILED to load VGG16 model: {e}. Cannot extract VGG16 features.")
        model = None # Ensure model is None if loading fails

    def extract_vgg_features(abs_img_path):
        if not model or not abs_img_path or not os.path.exists(abs_img_path):
            return None
        try:
            img = tf_image.load_img(abs_img_path, target_size=(224, 224))
            x = tf_image.img_to_array(img)
            x = np.expand_dims(x, axis=0)
            x = preprocess_input(x)
            features = model.predict(x, verbose=0).flatten()
            return features
        except Exception:
            return None

    for place_id, local_path, place_name in places_to_process:
        if not local_path or not os.path.exists(local_path):
            continue

        # VGG16 Features
        features_vgg = extract_vgg_features(local_path)
        if features_vgg is not None:
            results_vgg.append((place_id, pickle.dumps(features_vgg)))

        # Dominant Color Features
        colors = extract_dominant_colors(local_path)
        if colors is not None:
            # Flatten to a 15-dim vector and pickle
            color_vector = colors.flatten()
            results_color.append((place_id, pickle.dumps(color_vector), colors)) # Also send raw colors

    return results_vgg, results_color

# --- Structural Similarity ---
def calculate_structural_similarity_worker_mpi(place_data_chunk_struct, all_places_struct_dict):
    sim_results_struct = []
    for p1_id_s, p1_city_id_s, p1_cats_s_set in place_data_chunk_struct:
        if not p1_cats_s_set: continue
        for p2_id_s, (p2_city_id_s, p2_cats_s_set) in all_places_struct_dict.items():
            if p1_id_s == p2_id_s: continue
            if p1_city_id_s != p2_city_id_s: continue
            if not p2_cats_s_set: continue

            intersection = len(p1_cats_s_set.intersection(p2_cats_s_set))
            union = len(p1_cats_s_set.union(p2_cats_s_set))
            if union > 0:
                jaccard_sim = intersection / union
                if jaccard_sim > 0.01:
                    sim_results_struct.append((p1_id_s, p2_id_s, jaccard_sim))
    return sim_results_struct

# --- PageRank ---
def calculate_pagerank_mpi(graph_edges_for_pr):
    G_pr = nx.Graph()
    if not graph_edges_for_pr: return {}
    for main_id_pr, sim_id_pr, score_pr in graph_edges_for_pr:
        G_pr.add_edge(main_id_pr, sim_id_pr, weight=score_pr)
    if not G_pr.nodes: return {}
    try:
        pr_scores = nx.pagerank(G_pr, alpha=0.85, weight='weight', max_iter=500, tol=1.0e-6) # Adjusted params
        return pr_scores
    except Exception as e_pr:
        print(f"Rank {MPI.COMM_WORLD.Get_rank()}: PageRank calculation failed: {e_pr}")
        return {}

# --- Main MPI Logic ---
def main_mpi():
    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    size = comm.Get_size()

    data_for_features_bcast = None
    data_for_struct_sim_bcast = None
    place_id_to_city_id_map_bcast = None

    if rank == 0:
        print(f"--- MPI Processing Started with {size} processes ---")
        total_start_time = time.time()
        print("Rank 0: Setting up Django and loading initial data...")
        setup_django_env()
        from p160b013.models import Place, SimilarPlace, ImageFeature, SimilarityType, DominantColor

        all_places_from_db = list(Place.objects.select_related('city').prefetch_related('categories').all())

        data_for_features_bcast = [(p.id, p.local_image_path, p.name) for p in all_places_from_db if p.local_image_path and os.path.exists(p.local_image_path)]
        data_for_struct_sim_bcast = {p.id: (p.city_id, {cat.name for cat in p.categories.all()}) for p in all_places_from_db}
        place_id_to_city_id_map_bcast = {p.id: p.city_id for p in all_places_from_db}

        print(f"Rank 0: Loaded {len(all_places_from_db)} places. {len(data_for_features_bcast)} have valid local image paths.")
        print("Rank 0: Deleting old ImageFeatures, SimilarPlaces, and DominantColors...")
        ImageFeature.objects.all().delete()
        SimilarPlace.objects.all().delete()
        DominantColor.objects.all().delete() # Delete old colors
        Place.objects.all().update(page_rank_score=0.0)
        print("Rank 0: Old processed data deleted.")

    data_for_features_bcast = comm.bcast(data_for_features_bcast, root=0)
    data_for_struct_sim_bcast = comm.bcast(data_for_struct_sim_bcast, root=0)
    place_id_to_city_id_map_bcast = comm.bcast(place_id_to_city_id_map_bcast, root=0)
    comm.Barrier()

    if not data_for_features_bcast and rank == 0: print("Warning: No places with valid image paths for feature extraction.")
    if not data_for_struct_sim_bcast and rank == 0: print("Error: No places loaded for structural similarity. Exiting."); return

    # --- 1. Image Feature Extraction (VGG16 & Color) ---
    features_chunk = []
    if data_for_features_bcast:
        features_indices = np.array_split(np.arange(len(data_for_features_bcast)), size)[rank]
        features_chunk = [data_for_features_bcast[i] for i in features_indices]

    print(f"Rank {rank}: Processing {len(features_chunk)} images for VGG16 & Color features...")
    s_time = time.time()
    vgg_features_partial, color_features_partial = process_image_features_worker(features_chunk)
    e_time = time.time()
    print(f"Rank {rank}: Feature extraction took {e_time - s_time:.2f}s. Found {len(vgg_features_partial)} VGG / {len(color_features_partial)} Color.")

    gathered_vgg_features = comm.gather(vgg_features_partial, root=0)
    gathered_color_features = comm.gather(color_features_partial, root=0)
    comm.Barrier()

    # --- 2. Structural Similarity ---
    struct_sim_places_list = list(data_for_struct_sim_bcast.keys())
    struct_indices = np.array_split(np.arange(len(struct_sim_places_list)), size)[rank]
    struct_chunk_for_rank = [(pid, data_for_struct_sim_bcast[pid][0], data_for_struct_sim_bcast[pid][1]) for pid in [struct_sim_places_list[i] for i in struct_indices]]

    print(f"Rank {rank}: Calculating structural similarity for {len(struct_chunk_for_rank)} places...")
    s_time = time.time()
    struct_sim_partial = calculate_structural_similarity_worker_mpi(struct_chunk_for_rank, data_for_struct_sim_bcast)
    e_time = time.time()
    print(f"Rank {rank}: Structural similarity took {e_time - s_time:.2f}s. Found {len(struct_sim_partial)} pairs.")

    gathered_struct_sims = comm.gather(struct_sim_partial, root=0)
    comm.Barrier()

    # --- Rank 0: Consolidate, Calculate KNN, PageRank, Save ---
    if rank == 0:
        setup_django_env()
        from p160b013.models import Place, SimilarPlace, ImageFeature, SimilarityType, DominantColor

        print("\nRank 0: Consolidating and saving all results...")

        # --- Save VGG Image Features ---
        final_vgg_features_list = [item for sublist in gathered_vgg_features for item in sublist if item]
        if final_vgg_features_list:
            img_feat_objs = [ImageFeature(place_id=pid, features=feat_blob) for pid, feat_blob in final_vgg_features_list]
            ImageFeature.objects.bulk_create(img_feat_objs, batch_size=500)
            print(f"  Saved {len(img_feat_objs)} VGG16 features to DB.")
        else:
            print("  No VGG16 features to save.")

        # --- Save Dominant Colors ---
        final_color_list = [item for sublist in gathered_color_features for item in sublist if item]
        dominant_color_objs = []
        if final_color_list:
            for pid, _, colors_raw in final_color_list: # We need the raw (k,3) array
                for i, color_rgb in enumerate(colors_raw):
                    dominant_color_objs.append(DominantColor(
                        place_id=pid,
                        red=int(color_rgb[0]),
                        green=int(color_rgb[1]),
                        blue=int(color_rgb[2]),
                        rank=i + 1
                    ))
            DominantColor.objects.bulk_create(dominant_color_objs, batch_size=1000)
            print(f"  Saved {len(dominant_color_objs)} dominant colors to DB.")
        else:
            print("  No dominant colors to save.")


        all_sim_objects_to_save = []

        # --- Process VGG16 Similarities ---
        if len(final_vgg_features_list) > 1:
            vgg_place_ids = [item[0] for item in final_vgg_features_list]
            vgg_vectors = np.array([pickle.loads(item[1]) for item in final_vgg_features_list])
            print(f"  Calculating VGG16 cosine similarity for {len(vgg_place_ids)} vectors...")
            cosine_sim_matrix_vgg = cosine_similarity(vgg_vectors)

            for i in range(len(vgg_place_ids)):
                main_pid = vgg_place_ids[i]
                main_city_id = place_id_to_city_id_map_bcast.get(main_pid)
                if main_city_id is None: continue
                sorted_indices = np.argsort(-cosine_sim_matrix_vgg[i])
                count_sim = 0
                for k_idx in sorted_indices:
                    if count_sim >= 10: break
                    if k_idx == i: continue
                    sim_pid = vgg_place_ids[k_idx]
                    score = cosine_sim_matrix_vgg[i, k_idx]
                    if score > 0.65: # VGG threshold
                        sim_city_id = place_id_to_city_id_map_bcast.get(sim_pid)
                        if sim_city_id is None: continue
                        sim_type = SimilarityType.IMG_SAME if main_city_id == sim_city_id else SimilarityType.IMG_OTHER
                        all_sim_objects_to_save.append(SimilarPlace(
                            main_place_id=main_pid, similar_place_id=sim_pid,
                            similarity_score=score, similarity_type=sim_type
                        ))
                        count_sim += 1
            print(f"  Prepared {len(all_sim_objects_to_save)} VGG16 similarities.")
        else:
             print("  Not enough VGG features for similarity.")

        # --- Process Color Similarities ---
        if len(final_color_list) > 1:
            color_place_ids = [item[0] for item in final_color_list]
            color_vectors = np.array([pickle.loads(item[1]) for item in final_color_list])
            # Normalize color vectors (0-255) for cosine similarity
            color_vectors = color_vectors / 255.0
            print(f"  Calculating Color cosine similarity for {len(color_place_ids)} vectors...")
            cosine_sim_matrix_color = cosine_similarity(color_vectors)
            color_sim_count = 0

            for i in range(len(color_place_ids)):
                main_pid = color_place_ids[i]
                sorted_indices = np.argsort(-cosine_sim_matrix_color[i])
                count_sim = 0
                for k_idx in sorted_indices:
                    if count_sim >= 5: break # Top 5 color matches
                    if k_idx == i: continue
                    sim_pid = color_place_ids[k_idx]
                    score = cosine_sim_matrix_color[i, k_idx]
                    if score > 0.90: # Color threshold (needs to be high for RGB cosine)
                        all_sim_objects_to_save.append(SimilarPlace(
                            main_place_id=main_pid, similar_place_id=sim_pid,
                            similarity_score=score, similarity_type=SimilarityType.IMG_COLOR
                        ))
                        count_sim += 1
                        color_sim_count +=1

            print(f"  Prepared {color_sim_count} Color similarities.")
        else:
            print("  Not enough Color features for similarity.")


        # --- Consolidate Structural Similarities ---
        final_struct_sims = [item for sublist in gathered_struct_sims for item in sublist if item]
        unique_struct_pairs = {}
        for p1, p2, score in final_struct_sims:
            pair = tuple(sorted((p1, p2)))
            if pair not in unique_struct_pairs or score > unique_struct_pairs[pair]:
                 unique_struct_pairs[pair] = score

        struct_sim_count = 0
        for (p1, p2), score in unique_struct_pairs.items():
            all_sim_objects_to_save.append(SimilarPlace(
                main_place_id=p1, similar_place_id=p2,
                similarity_score=score, similarity_type=SimilarityType.STRUCT_SAME))
            all_sim_objects_to_save.append(SimilarPlace(
                main_place_id=p2, similar_place_id=p1,
                similarity_score=score, similarity_type=SimilarityType.STRUCT_SAME))
            struct_sim_count += 2
        print(f"  Prepared {struct_sim_count} structural similarities.")

        # --- Bulk save all similarities ---
        if all_sim_objects_to_save:
            SimilarPlace.objects.bulk_create(all_sim_objects_to_save, batch_size=500, ignore_conflicts=True)
            print(f"  Saved {len(all_sim_objects_to_save)} total similarity entries to DB.")
        else:
            print("  No similarity entries to save.")

        # --- Calculate & Save PageRank ---
        print("  Calculating PageRank using unique structural similarities...")
        pagerank_edges = [(p1, p2, score) for (p1,p2), score in unique_struct_pairs.items()]
        page_ranks = calculate_pagerank_mpi(pagerank_edges)

        if page_ranks:
            places_to_update_pr = []
            all_db_places_pr = Place.objects.in_bulk(list(page_ranks.keys())) # Fetch in bulk

            for place_id_pr, pr_score_val in page_ranks.items():
                place_obj = all_db_places_pr.get(place_id_pr)
                if place_obj:
                    place_obj.page_rank_score = pr_score_val
                    places_to_update_pr.append(place_obj)

            if places_to_update_pr:
                Place.objects.bulk_update(places_to_update_pr, ['page_rank_score'], batch_size=500)
                print(f"  Updated PageRank for {len(places_to_update_pr)} places.")
        else:
            print("  PageRank could not be calculated or no PR data.")

        total_end_time = time.time()
        print(f"--- MPI Processing Finished in {total_end_time - total_start_time:.2f} seconds ---")

if __name__ == "__main__":
    # NOTE: This script requires 'opencv-python' and 'scikit-learn'
    # pip install opencv-python scikit-learn
    # It also expects MPI and mpi4py to be installed.
    main_mpi()
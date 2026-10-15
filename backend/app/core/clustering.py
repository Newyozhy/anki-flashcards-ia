import math
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence


def normalize_vector(vec: Sequence[float]) -> List[float]:
    """L2-normalize a vector to unit length."""
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return list(vec)
    return [x / norm for x in vec]


def dot_product(v1: Sequence[float], v2: Sequence[float]) -> float:
    """Compute dot product between two vectors (cosine similarity if normalized)."""
    return sum(a * b for a, b in zip(v1, v2))


def determine_optimal_k(n_samples: int, min_k: int = 2, max_k: int = 6) -> int:
    """Determine a sensible cluster count based on deck size.
    
    Prevents both under-clustering (collapsing into a monolith) and over-clustering (orphan singletons).
    """
    if n_samples <= 0:
        return 1
    if n_samples < 6:
        return min(n_samples, 2)
    if n_samples < 15:
        return min(n_samples, 3)
    if n_samples < 40:
        return min(n_samples, 4)
    if n_samples < 140:
        return min(n_samples, 5)
    return min(n_samples, max_k)


@dataclass
class SphericalCluster:
    cluster_index: int
    note_ids: List[int]
    centroid: List[float]
    representative_note_ids: List[int]


@dataclass
class SphericalKMeansResult:
    k: int
    clusters: List[SphericalCluster]


def spherical_kmeans(
    items: List[Dict[str, Any]],
    k: Optional[int] = None,
    max_iter: int = 25,
    seed: int = 42,
) -> SphericalKMeansResult:
    """Perform spherical K-means (cosine distance) on embedded notes in pure Python.
    
    Args:
        items: List of dicts containing at least 'note_id' and 'vec' (List[float]).
        k: Optional cluster count. If None, chosen automatically via determine_optimal_k.
        max_iter: Maximum EM iterations.
        seed: Random seed for deterministic reproducibility.
    """
    if not items:
        return SphericalKMeansResult(k=0, clusters=[])

    n_samples = len(items)
    effective_k = k if (k is not None and k > 0) else determine_optimal_k(n_samples)
    effective_k = min(effective_k, n_samples)

    if effective_k <= 1:
        single_centroid = normalize_vector(items[0]["vec"])
        all_ids = [item["note_id"] for item in items]
        return SphericalKMeansResult(
            k=1,
            clusters=[
                SphericalCluster(
                    cluster_index=0,
                    note_ids=all_ids,
                    centroid=single_centroid,
                    representative_note_ids=all_ids[:5],
                )
            ],
        )

    # Normalize all vectors upfront
    normalized_items = [
        {"note_id": it["note_id"], "vec": normalize_vector(it["vec"])}
        for it in items
    ]
    dim = len(normalized_items[0]["vec"])

    rng = random.Random(seed)

    # 1. K-Means++ Initialization
    first_choice = rng.choice(normalized_items)["vec"]
    centroids: List[List[float]] = [list(first_choice)]

    for _ in range(1, effective_k):
        distances: List[float] = []
        for it in normalized_items:
            max_sim = max(dot_product(it["vec"], c) for c in centroids)
            # Cosine distance = 1 - sim
            dist = max(0.0, 1.0 - max_sim)
            distances.append(dist * dist)

        total_dist = sum(distances)
        if total_dist <= 1e-9:
            centroids.append(list(rng.choice(normalized_items)["vec"]))
        else:
            r_val = rng.random() * total_dist
            accum = 0.0
            chosen = normalized_items[-1]["vec"]
            for it, d in zip(normalized_items, distances):
                accum += d
                if accum >= r_val:
                    chosen = it["vec"]
                    break
            centroids.append(list(chosen))

    # 2. Expectation-Maximization Loop
    prev_assignments: List[int] = [-1] * n_samples

    for _ in range(max_iter):
        cluster_buckets: Dict[int, List[Dict[str, Any]]] = {i: [] for i in range(effective_k)}
        curr_assignments: List[int] = []

        # Assignment Step (E-step): Assign each item to the closest centroid by cosine similarity
        for it in normalized_items:
            best_idx = 0
            best_sim = -2.0
            for c_idx, c in enumerate(centroids):
                sim = dot_product(it["vec"], c)
                if sim > best_sim:
                    best_sim = sim
                    best_idx = c_idx
            cluster_buckets[best_idx].append(it)
            curr_assignments.append(best_idx)

        # Convergence check
        if curr_assignments == prev_assignments:
            break
        prev_assignments = curr_assignments

        # Update Step (M-step): Compute mean vector and re-project to unit sphere
        new_centroids: List[List[float]] = []
        for i in range(effective_k):
            members = cluster_buckets[i]
            if not members:
                # Retain previous centroid if empty
                new_centroids.append(centroids[i])
                continue

            accum_vec = [0.0] * dim
            for m in members:
                m_vec = m["vec"]
                for d in range(dim):
                    accum_vec[d] += m_vec[d]
            new_centroids.append(normalize_vector(accum_vec))
        centroids = new_centroids

    # 3. Post-clustering: Re-assign micro-clusters (< 4 members when total >= 30) to closest sibling
    if effective_k > 1 and n_samples >= 30:
        for c_idx in range(effective_k):
            if 0 < len(cluster_buckets[c_idx]) < 4:
                orphan_items = cluster_buckets[c_idx]
                cluster_buckets[c_idx] = []
                for it in orphan_items:
                    best_other = -1
                    best_sim = -2.0
                    for other_idx in range(effective_k):
                        if other_idx == c_idx or not cluster_buckets[other_idx]:
                            continue
                        sim = dot_product(it["vec"], centroids[other_idx])
                        if sim > best_sim:
                            best_sim = sim
                            best_other = other_idx
                    if best_other != -1:
                        cluster_buckets[best_other].append(it)

    # 4. Build Result with Representative Medoids
    result_clusters: List[SphericalCluster] = []
    cluster_counter = 0
    for c_idx in range(effective_k):
        members = cluster_buckets[c_idx]
        if not members:
            continue
        centroid = centroids[c_idx]

        # Sort members by cosine similarity to centroid descending
        sorted_members = sorted(
            members,
            key=lambda m: dot_product(m["vec"], centroid),
            reverse=True,
        )

        member_ids = [m["note_id"] for m in sorted_members]
        medoid_ids = member_ids[:5]

        result_clusters.append(
            SphericalCluster(
                cluster_index=cluster_counter,
                note_ids=member_ids,
                centroid=centroid,
                representative_note_ids=medoid_ids,
            )
        )
        cluster_counter += 1

    # Filter out empty clusters if any
    non_empty = [c for c in result_clusters if c.note_ids]
    return SphericalKMeansResult(k=len(non_empty), clusters=non_empty)

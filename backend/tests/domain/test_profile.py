from __future__ import annotations

import math

from app.domain.profile import assign_document, update_profile
from app.domain.types import DomainProfile


def unit(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


def test_first_document_forms_the_first_cluster() -> None:
    profile = DomainProfile()
    a = assign_document(profile, unit([1, 0, 0]))
    assert a.sub_cluster_id == "sc_1"
    assert a.is_new_cluster is True
    assert a.off_domain is False  # nothing to be off-domain from yet


def test_similar_document_joins_the_existing_cluster() -> None:
    profile = DomainProfile()
    a1 = assign_document(profile, unit([1, 0, 0]))
    profile = update_profile(profile, unit([1, 0, 0]), a1, "d1")

    a2 = assign_document(profile, unit([0.95, 0.31, 0]))
    assert a2.sub_cluster_id == "sc_1"
    assert a2.is_new_cluster is False
    assert a2.off_domain is False
    assert a2.similarity > 0.55


def test_off_topic_document_forms_a_new_cluster_and_is_flagged() -> None:
    profile = DomainProfile()
    a1 = assign_document(profile, unit([1, 0, 0]))
    profile = update_profile(profile, unit([1, 0, 0]), a1, "d1")

    a2 = assign_document(profile, unit([0, 0, 1]))
    assert a2.sub_cluster_id == "sc_2"
    assert a2.is_new_cluster is True
    assert a2.off_domain is True


def test_profile_is_updated_incrementally() -> None:
    profile = DomainProfile()
    embeddings = [unit([1, 0.1, 0]), unit([0.9, 0.2, 0]), unit([0.95, 0.05, 0.1])]

    for i, e in enumerate(embeddings):
        a = assign_document(profile, e)
        profile = update_profile(profile, e, a, f"d{i}", [f"Entity {i}", "Shared"])

    assert profile.document_count == 3
    assert len(profile.sub_clusters) == 1
    assert profile.sub_clusters[0].size == 3
    assert profile.sub_clusters[0].document_ids == ["d0", "d1", "d2"]
    # vocabulary accumulates and de-duplicates
    assert profile.vocabulary.count("Shared") == 1
    assert set(profile.vocabulary) == {"Entity 0", "Entity 1", "Entity 2", "Shared"}
    # centroid is a unit vector near the inputs
    assert math.isclose(
        math.sqrt(sum(x * x for x in profile.centroid_embedding)), 1.0, rel_tol=1e-6
    )


def test_cluster_centroid_moves_toward_new_members() -> None:
    profile = DomainProfile()
    a1 = assign_document(profile, unit([1, 0, 0]))
    profile = update_profile(profile, unit([1, 0, 0]), a1, "d1")
    before = list(profile.sub_clusters[0].centroid)

    a2 = assign_document(profile, unit([0.7, 0.7, 0]))
    profile = update_profile(profile, unit([0.7, 0.7, 0]), a2, "d2")
    after = profile.sub_clusters[0].centroid

    assert after[1] > before[1]  # centroid shifted toward the second document


def test_load_and_dump_round_trip() -> None:
    profile = DomainProfile()
    a = assign_document(profile, unit([1, 0, 0]))
    profile = update_profile(profile, unit([1, 0, 0]), a, "d1", ["Acme"])
    restored = DomainProfile.load(profile.dump())
    assert restored.document_count == 1
    assert restored.vocabulary == ["Acme"]
    assert restored.sub_clusters[0].id == "sc_1"

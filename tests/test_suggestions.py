"""GET /items/{id}/suggestions -- possible lost <-> found matches.

The test database is shared with every other test -- and with earlier runs of
this one -- so item text here is mostly random words. Items from different tests
then share too little to clear the similarity threshold against each other, and
each test sees only its own.
"""
import uuid

import pytest


def _tag():
    return " ".join(uuid.uuid4().hex[:8] for _ in range(3))


def _mk_item(client, headers, name, description, kind, occurred_on="2026-08-15", **extra):
    resp = client.post("/items", headers=headers, json={
        "name": name, "description": description, "kind": kind,
        "occurred_on": occurred_on, **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _suggest(client, item_id, **params):
    resp = client.get(f"/items/{item_id}/suggestions", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ref(client, headers, path, name):
    resp = client.post(path, headers=headers, json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _bottle(tag):
    return (f"Flask {tag}", f"Bottle {tag}.")


# --- ranking --------------------------------------------------------------

def test_boosts_rank_equally_similar_items(client, auth_headers):
    owner, finder = auth_headers(), auth_headers()
    tag = _tag()
    category = _ref(client, owner, "/categories", f"Bottles {tag}")
    location = _ref(client, owner, "/locations", f"Gym {tag}")
    name, desc = _bottle(tag)
    source = _mk_item(client, owner, name, desc, "lost", "2026-08-15",
                      category_id=category, location_id=location)

    # Same text for all four, so any difference in rank comes from the boosts.
    text = (f"Flask {tag} found", f"Bottle {tag}, found.")
    far = "2026-05-01"  # outside the +/-14 day window
    plain = _mk_item(client, finder, *text, "found", far)
    by_category = _mk_item(client, finder, *text, "found", far, category_id=category)
    by_location = _mk_item(client, finder, *text, "found", far, location_id=location)
    by_date = _mk_item(client, finder, *text, "found", "2026-08-20")

    results = _suggest(client, source["id"])["results"]
    ranked = [r["id"] for r in results]
    assert ranked[0] == by_category["id"]
    assert ranked[-1] == plain["id"]
    assert set(ranked) == {plain["id"], by_category["id"], by_location["id"], by_date["id"]}

    by_id = {r["id"]: r for r in results}
    base = by_id[plain["id"]]
    assert base["reasons"] == [] and base["score"] == base["similarity"]
    assert {r["similarity"] for r in results} == {base["similarity"]}
    assert by_id[by_category["id"]]["score"] == pytest.approx(base["score"] + 0.10, abs=1e-3)
    assert by_id[by_location["id"]]["score"] == pytest.approx(base["score"] + 0.05, abs=1e-3)
    assert by_id[by_date["id"]]["score"] == pytest.approx(base["score"] + 0.05, abs=1e-3)
    assert by_id[by_category["id"]]["reasons"] == ["same category"]
    assert by_id[by_location["id"]]["reasons"] == ["same location"]
    assert by_id[by_date["id"]]["reasons"] == ["within 14 days"]


def test_closer_text_ranks_higher(client, auth_headers):
    owner, finder = auth_headers(), auth_headers()
    tag = _tag()
    source = _mk_item(client, owner, *_bottle(tag), "lost")
    close = _mk_item(client, finder, *_bottle(tag), "found")
    two_words = " ".join(tag.split()[:2])  # one of the three words missing
    looser = _mk_item(client, finder, f"Flask {two_words}", f"Bottle {two_words}.", "found")

    results = {r["id"]: r for r in _suggest(client, source["id"])["results"]}
    assert results[close["id"]]["similarity"] > results[looser["id"]]["similarity"]
    ranked = list(results)
    assert ranked.index(close["id"]) < ranked.index(looser["id"])


# --- exclusions and threshold ----------------------------------------------

def test_only_open_items_of_the_opposite_kind_by_someone_else(client, auth_headers):
    owner, finder, other = auth_headers(), auth_headers(), auth_headers()
    tag = _tag()
    source = _mk_item(client, owner, *_bottle(tag), "lost")

    match = _mk_item(client, finder, *_bottle(tag), "found")
    same_kind = _mk_item(client, other, *_bottle(tag), "lost")
    own_post = _mk_item(client, owner, *_bottle(tag), "found")
    closed = _mk_item(client, finder, *_bottle(tag), "found")
    client.post(f"/items/{closed['id']}/status", headers=finder, json={"to_status": "closed"})

    ids = {r["id"] for r in _suggest(client, source["id"])["results"]}
    assert match["id"] in ids
    assert not ids & {same_kind["id"], own_post["id"], closed["id"], source["id"]}


def test_found_items_are_matched_against_lost_ones(client, auth_headers):
    owner, finder = auth_headers(), auth_headers()
    tag = _tag()
    lost = _mk_item(client, owner, *_bottle(tag), "lost")
    found = _mk_item(client, finder, *_bottle(tag), "found")

    results = _suggest(client, found["id"])["results"]
    assert lost["id"] in {r["id"] for r in results}
    assert all(r["kind"] == "lost" for r in results)


def test_weak_matches_are_dropped_even_with_every_boost(client, auth_headers):
    owner, finder = auth_headers(), auth_headers()
    tag = _tag()
    category = _ref(client, owner, "/categories", f"Misc {tag}")
    location = _ref(client, owner, "/locations", f"Quad {tag}")
    source = _mk_item(client, owner, *_bottle(tag), "lost",
                      category_id=category, location_id=location)
    # Same place, same category, same day -- but nothing like the flask.
    unrelated = _mk_item(client, finder, "Maroon leather wallet",
                         "Bifold, a few coins, no cards.", "found",
                         category_id=category, location_id=location)

    results = _suggest(client, source["id"])["results"]
    assert unrelated["id"] not in {r["id"] for r in results}
    assert all(r["similarity"] >= 0.25 for r in results)


def test_a_closed_item_gets_no_suggestions(client, auth_headers):
    owner, finder = auth_headers(), auth_headers()
    tag = _tag()
    source = _mk_item(client, owner, *_bottle(tag), "lost")
    _mk_item(client, finder, *_bottle(tag), "found")
    client.post(f"/items/{source['id']}/status", headers=owner, json={"to_status": "closed"})

    assert _suggest(client, source["id"])["results"] == []


# --- limits and response shape ---------------------------------------------

def test_at_most_five_suggestions(client, auth_headers):
    owner, finder = auth_headers(), auth_headers()
    tag = _tag()
    source = _mk_item(client, owner, *_bottle(tag), "lost")
    for _ in range(7):
        _mk_item(client, finder, *_bottle(tag), "found")

    assert len(_suggest(client, source["id"])["results"]) == 5
    assert len(_suggest(client, source["id"], limit=2)["results"]) == 2
    assert client.get(f"/items/{source['id']}/suggestions",
                      params={"limit": 6}).status_code == 422


def test_unknown_item_is_404(client):
    assert client.get("/items/99999999/suggestions").status_code == 404


def test_response_shape_matches_search_and_hides_contact(client, auth_headers):
    owner, finder = auth_headers(), auth_headers()
    tag = _tag()
    source = _mk_item(client, owner, *_bottle(tag), "lost")
    match = _mk_item(client, finder, *_bottle(tag), "found")

    # The owner holds an approved claim on the match: the one situation in which
    # the item page itself would disclose the finder's address to them.
    claim = client.post(f"/items/{match['id']}/claims", headers=owner,
                        json={"evidence": "the koala sticker"}).json()
    client.post(f"/claims/{claim['id']}/decision", headers=finder, json={"approve": True})
    assert client.get(f"/items/{match['id']}",
                      headers=owner).json()["reporter"]["contact_email"] is not None

    body = client.get(f"/items/{source['id']}/suggestions", headers=owner).json()
    assert body["item_id"] == source["id"]
    row = next(r for r in body["results"] if r["id"] == match["id"])

    search_row = client.get("/items", params={"q": match["name"]}).json()["results"][0]
    assert set(row) == set(search_row) | {"score", "similarity", "reasons"}
    assert row["reporter"] == search_row["reporter"]
    assert row["reporter"]["contact_email"] is None
    assert "email" not in row["reporter"]

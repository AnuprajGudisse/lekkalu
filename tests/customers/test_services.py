# Copyright (c) 2026 Lekkalu
import pytest
from sqlalchemy.exc import IntegrityError

from app.customers import services as customers
from app.customers.schemas import DuplicateCustomer
from tests.conftest import make_business


@pytest.fixture
def shop(session):
    return make_business(session)


@pytest.fixture
def lakshmi(session, shop):
    return customers.create(session, business_id=shop.id, name="Lakshmi", name_native="లక్ష్మి")


def test_normalize_drops_honorifics_case_and_punctuation():
    assert customers.normalize("Lakshmi garu") == customers.normalize("lakshmi")
    assert customers.normalize("  LAKSHMI,  Gaaru. ") == "lakshmi"
    assert customers.normalize("లక్ష్మి గారు") == "లక్ష్మి"


def test_normalize_folds_long_vowel_signs():
    assert customers.normalize("లక్ష్మీ") == "లక్ష్మి"


def test_exact_name_matches(session, shop, lakshmi):
    r = customers.find(session, business_id=shop.id, name="Lakshmi garu")
    assert (r.status, r.customer_id) == ("matched", lakshmi.id)


def test_native_name_matches_through_alias(session, shop, lakshmi):
    r = customers.find(session, business_id=shop.id, name=None, name_native="లక్ష్మీ")
    assert (r.status, r.customer_id) == ("matched", lakshmi.id)


def test_exact_native_match_wins_over_fuzzy_latin(session, shop, lakshmi):
    r = customers.find(session, business_id=shop.id, name="Laxmi", name_native="లక్ష్మి")
    assert (r.status, r.customer_id) == ("matched", lakshmi.id)


def test_fuzzy_name_is_ambiguous_never_matched(session, shop, lakshmi):
    r = customers.find(session, business_id=shop.id, name="Lakshmy")
    assert r.status == "ambiguous"
    assert r.candidate_ids == [lakshmi.id]


def test_exact_hits_on_two_customers_are_ambiguous(session, shop, lakshmi):
    padma = customers.create(session, business_id=shop.id, name="Padma")
    r = customers.find(session, business_id=shop.id, name="Padma", name_native="లక్ష్మి")
    assert r.status == "ambiguous"
    assert r.candidate_ids == sorted([lakshmi.id, padma.id])


def test_laxmi_asks_about_lakshmi(session, shop, lakshmi):
    r = customers.find(session, business_id=shop.id, name="Laxmi")
    assert (r.status, r.candidate_ids) == ("ambiguous", [lakshmi.id])


def test_unrelated_name_is_not_found(session, shop, lakshmi):
    assert customers.find(session, business_id=shop.id, name="Ravi").status == "not_found"


def test_duplicate_name_in_same_business_raises_domain_error(session, shop, lakshmi):
    with pytest.raises(DuplicateCustomer):
        customers.create(session, business_id=shop.id, name="lakshmi garu")
    other = make_business(session)
    assert customers.create(session, business_id=other.id, name="Lakshmi").id != lakshmi.id


def test_add_alias_stores_normalized_once(session, shop, lakshmi):
    customers.add_alias(session, customer_id=lakshmi.id, alias="Lachi Garu")
    customers.add_alias(session, customer_id=lakshmi.id, alias="lachi")
    assert lakshmi.aliases == ["లక్ష్మి", "lachi"]
    assert customers.find(session, business_id=shop.id, name="Lachi").customer_id == lakshmi.id


def test_other_integrity_errors_are_not_reported_as_duplicates(session):
    with pytest.raises(IntegrityError):
        customers.create(session, business_id=-1, name="Nobody")  # no such business

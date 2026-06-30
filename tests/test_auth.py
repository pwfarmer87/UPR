from upr.auth import (
    CAPABILITIES,
    User,
    authenticate,
    hash_password,
    make_user_record,
    verify_password,
)


def test_hash_is_salted_and_verifies():
    salt, h = hash_password("s3cret")
    assert verify_password("s3cret", salt, h)
    assert not verify_password("wrong", salt, h)
    # different salt -> different hash for same password
    salt2, h2 = hash_password("s3cret")
    assert salt != salt2 and h != h2


def test_roles_capabilities():
    viewer = User("v", "V", "viewer")
    analyst = User("a", "A", "analyst")
    admin = User("ad", "Ad", "admin")
    assert viewer.can("view") and not viewer.can("import")
    assert analyst.can("import") and analyst.can("scenario") and not analyst.can("admin")
    assert admin.can("admin")
    assert set(CAPABILITIES) == {"viewer", "analyst", "admin"}


def test_authenticate_against_user_store():
    record = make_user_record("pf", "Patrick", "admin", "hunter2")
    users = {"pf": User(**record)}
    assert authenticate("pf", "hunter2", users).role == "admin"
    assert authenticate("pf", "nope", users) is None
    assert authenticate("ghost", "hunter2", users) is None


def test_make_user_record_rejects_bad_role():
    try:
        make_user_record("x", "X", "superuser", "pw")
    except ValueError as e:
        assert "superuser" in str(e)
    else:
        raise AssertionError("expected ValueError")

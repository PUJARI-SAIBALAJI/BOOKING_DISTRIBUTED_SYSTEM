import pytest

from backend.models.user import User


def test_user_validation():

    data = {
        "name": "Santosh",
        "email": "SANTOSH@example.com",
        "password": "hashed_password",
        "role": "customer"
    }

    assert User.validate(data) is True


def test_user_invalid_role():

    data = {
        "name": "Santosh",
        "email": "santosh@example.com",
        "password": "hashed_password",
        "role": "superuser"
    }

    with pytest.raises(ValueError):

        User.validate(data)


def test_user_missing_email():

    data = {
        "name": "Santosh",
        "password": "hashed_password"
    }

    with pytest.raises(ValueError):

        User.validate(data)
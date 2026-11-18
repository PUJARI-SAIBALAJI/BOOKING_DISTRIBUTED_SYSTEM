import pytest
import bcrypt

from unittest.mock import patch

from bson import ObjectId

from backend.services.auth_service import (
    AuthService,
    AuthError
)


class FakeDatabase:
    pass


@pytest.fixture
def auth_service():

    return AuthService(FakeDatabase())


def test_valid_email(auth_service):

    assert auth_service.validate_email(
        "test@example.com"
    )


def test_invalid_email(auth_service):

    assert not auth_service.validate_email(
        "invalid-email"
    )


def test_password_hashing(auth_service):

    password = "Password123"

    hashed = auth_service.hash_password(password)

    assert hashed != password

    assert bcrypt.checkpw(
        password.encode(),
        hashed.encode()
    )


def test_password_verification(auth_service):

    password = "Password123"

    hashed = auth_service.hash_password(password)

    assert auth_service.verify_password(
        password,
        hashed
    )


def test_wrong_password(auth_service):

    hashed = auth_service.hash_password(
        "Password123"
    )

    assert not auth_service.verify_password(
        "WrongPassword",
        hashed
    )


def test_missing_registration_fields(auth_service):

    with pytest.raises(AuthError) as error:

        auth_service.register({})

    assert error.value.status_code == 400


def test_invalid_registration_email(auth_service):

    data = {
        "name": "Santosh",
        "email": "invalid-email",
        "password": "Password123"
    }

    with pytest.raises(AuthError):

        auth_service.register(data)


def test_short_password(auth_service):

    data = {
        "name": "Santosh",
        "email": "test@example.com",
        "password": "123"
    }

    with pytest.raises(AuthError):

        auth_service.register(data)


def test_public_registration_forces_customer_role(auth_service):

    data = {
        "name": "Santosh",
        "email": "test@example.com",
        "password": "Password123",
        "role": "admin"
    }

    with patch(
        "backend.services.auth_service.User.find_by_email",
        return_value=None
    ), patch(
        "backend.services.auth_service.User.create",
        return_value=ObjectId()
    ), patch(
        "backend.services.auth_service.User.find_by_id"
    ) as find_user, patch(
        "backend.services.auth_service.create_access_token",
        return_value="fake-token"
    ):

        find_user.return_value = {
            "_id": ObjectId(),
            "name": "Santosh",
            "email": "test@example.com",
            "role": "customer",
            "createdAt": None
        }

        result = auth_service.register(data)

        assert result["data"]["user"]["role"] == "customer"


def test_duplicate_email(auth_service):

    data = {
        "name": "Santosh",
        "email": "test@example.com",
        "password": "Password123"
    }

    with patch(
        "backend.services.auth_service.User.find_by_email",
        return_value={"email": "test@example.com"}
    ):

        with pytest.raises(AuthError) as error:

            auth_service.register(data)

        assert error.value.status_code == 409


def test_login_missing_fields(auth_service):

    with pytest.raises(AuthError) as error:

        auth_service.login({})

    assert error.value.status_code == 400


def test_login_invalid_credentials(auth_service):

    with patch(
        "backend.services.auth_service.User.find_by_email",
        return_value=None
    ):

        with pytest.raises(AuthError) as error:

            auth_service.login({
                "email": "test@example.com",
                "password": "Password123"
            })

        assert error.value.status_code == 401
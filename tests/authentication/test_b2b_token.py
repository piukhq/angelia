from unittest.mock import MagicMock, patch

import azure.core.exceptions
import jwt

from app.api.auth import ClientToken
from app.api.custom_error_handlers import TokenHTTPError
from app.api.helpers import vault
from app.api.helpers.vault import load_secrets_from_vault

from .helpers.keys import (
    private_key_eddsa,
    private_key_rsa,
    public_key_eddsa,
    public_key_rsa,
    wrong_public_key_eddsa,
    wrong_public_key_rsa,
)
from .helpers.token_helpers import create_b2b_token, validate_mock_request


class TestB2BAuth:
    channel: str
    external_id: str
    email: str
    secrets_dict: dict[str, str]
    supported_algorithms = ("RS512", "EdDSA")

    @classmethod
    def setup_class(cls) -> None:
        cls.channel = "com.test.channel"
        cls.external_id = "testme"
        cls.email = "customer1@test.com"
        cls.secrets_dict = {"key": public_key_rsa, "channel": cls.channel}

    def test_rsa_public_private_keys_are_valid(self) -> None:
        test_jwt = jwt.encode({"x": 1}, key=private_key_rsa, algorithm="RS512")
        test = jwt.decode(test_jwt, key=public_key_rsa, algorithms=list(self.supported_algorithms))
        assert test["x"] == 1

    def test_eddsa_public_private_keys_are_valid(self) -> None:
        test_jwt = jwt.encode({"x": 1}, key=private_key_eddsa, algorithm="EdDSA")
        test = jwt.decode(test_jwt, key=public_key_eddsa, algorithms=list(self.supported_algorithms))
        assert test["x"] == 1

    def test_load_secrets_from_vault_azure(self) -> None:
        with patch("app.api.helpers.vault.get_azure_client") as mock_get_client:
            key = '{"public_key": "blabla"}'

            def get_secret(_: str) -> MagicMock:
                _get_secret = MagicMock()
                _get_secret.value = key
                return _get_secret

            mock_get_client.return_value.get_secret.side_effect = get_secret
            loaded = load_secrets_from_vault(["test-1"], was_loaded=False, allow_reload=True)
            assert loaded
            assert vault._local_vault_store.get("test-1") == {"public_key": "blabla"}
            vault._local_vault_store = {}

    def test_load_secrets_from_vault_azure_fail(self) -> None:
        with patch("app.api.helpers.vault.get_azure_client") as mock_get_client:
            mock_get_client.return_value.get_secret.side_effect = azure.core.exceptions.ResourceNotFoundError

            loaded = load_secrets_from_vault(["test-1"], was_loaded=False, allow_reload=True)

            assert not loaded

    def test_auth_invalid_secret(self) -> None:
        with patch("app.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret:
            mock_get_secret.return_value = False
            try:
                auth_token = create_b2b_token(private_key_rsa, sub=self.external_id, kid="test-1", email=self.email)
                validate_mock_request(auth_token, ClientToken, media={"grant_type": "b2b", "scope": ["user"]})
                raise AssertionError("Did not detect the invalid key")
            except TokenHTTPError as e:
                assert e.error == "unauthorized_client"
                assert e.status == "400 Bad Request"
            except Exception as e:
                raise AssertionError(f"Exception in code or test {e}") from None

    def test_auth_invalid_key(self) -> None:
        for pub, priv, alg in (
            (wrong_public_key_rsa, private_key_rsa, "RS512"),
            (wrong_public_key_eddsa, private_key_eddsa, "EdDSA"),
        ):
            with patch("app.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret:
                secrets_dict = {"key": pub, "channel": self.channel}
                mock_get_secret.return_value = secrets_dict
                try:
                    auth_token = create_b2b_token(
                        priv, algorithm=alg, sub=self.external_id, kid="test-1", email=self.email
                    )
                    validate_mock_request(auth_token, ClientToken, media={"grant_type": "b2b", "scope": ["user"]})
                    raise AssertionError("Did not detect invalid key")
                except TokenHTTPError as e:
                    assert e.error == "unauthorized_client"
                    assert e.status == "400 Bad Request"
                except Exception as e:
                    raise AssertionError(f"Exception in code or test {e}") from None

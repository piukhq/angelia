import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import jwcrypto.common
import pytest
from falcon import testing
from jwcrypto import jwk

from app.api import app
from app.encryption import (
    JWE,
    ExpiredKey,
    InvalidKeyObj,
    JweClientError,
    JweException,
    JweServerError,
    MissingKey,
    _decrypt_payload,
    decrypt_payload,
)

TEST_RSA_PUBLIC_KEY = (
    "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAmlFEqgeo1Y17s"
    "igLgdIK\nHUcFh8Tsa7tsX3+uMSvIg+2XPJMi04o3fMd+P6s0rGuJ2qr0Xvlcl27r06/dFCwY\nAIqv3I9UeD"
    "GyDp++mZsVEJuaOt3/VMCBctZ9hol9Oo/KnkXP1bAAa1EqjlmzpTHi\nUZla2Z8HovRYXyGt5a+nDcp6b655S"
    "94xmXrADtaLW1NxYgrWEgc5mK7U0v69m3ER\nTJ8N3Hm1SGMYgVBfZxswG+mtHYTUpelXDAHUksY4yYfxw2+1"
    "9ASfKdpNy/k3Fzgj\n0qr/cq7RYHLyqfpL0ZQnLjlFnTOzG2pgrvnzoqDaPbt6n+eFSXPrtisFHmm1dyLc\nW"
    "wIDAQAB\n-----END PUBLIC KEY-----"
)

TEST_RSA_PRIVATE_KEY = (
    "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEAmlFEqgeo1Y17sigLgdIKHUcFh8Tsa7tsX3+u"
    "MSvIg+2XPJMi\n04o3fMd+P6s0rGuJ2qr0Xvlcl27r06/dFCwYAIqv3I9UeDGyDp++mZsVEJuaOt3/\nVMCBc"
    "tZ9hol9Oo/KnkXP1bAAa1EqjlmzpTHiUZla2Z8HovRYXyGt5a+nDcp6b655\nS94xmXrADtaLW1NxYgrWEgc5"
    "mK7U0v69m3ERTJ8N3Hm1SGMYgVBfZxswG+mtHYTU\npelXDAHUksY4yYfxw2+19ASfKdpNy/k3Fzgj0qr/cq7"
    "RYHLyqfpL0ZQnLjlFnTOz\nG2pgrvnzoqDaPbt6n+eFSXPrtisFHmm1dyLcWwIDAQABAoIBAAH48vP19qXnaR"
    "oe\nitMceSIrH11Kwzdl2XqKd2QGJI/BUI0+KR/AnwUJDhvT9IbnHp7UZzQLY3X/g0ac\n/vuk413VULRpJYB"
    "7QFBXRBoBWDoVb3ECAGksUr4qtfXCrjjGLRpry76BzRYdtlbb\njME9NDfyJy3mGfpLvbQnxF42hyWyGItTYr"
    "vCAESTTxqQPW8as2CZNqxc+qQix/wD\nqy9N4NnxXzwo/tbevcMx4asT9xIHVfNcngWRckD69bxRurIL/M/a+"
    "p6AIC0rHlrj\n2GftyhMXsfY2TWpRTGusBQOZbfipEGsjulJCaDRywTJPmDILYVMy98pSBlihoJCE\nn7VBXu"
    "UCgYEAxovs/O8Ho5bT8X22dHAzkt1/LQEWcYx2QwAAAlt8XAN15G00G/8b\nn64sojSdK7s2SmaAzsB3N0FjJ"
    "AuVCHLiTokywXT4f0LjWaE69dd3dprR+eP5tHcW\nEWbWBecNnpXLgZQ5nIItA/1grNLpWM770qUeIGgJGAi9"
    "IbSzF7NJlQUCgYEAxvjn\n2VV8y9EF1kmlx1sZ/7WjCh0zmLaXhUJ3ZgkxC6HbYvK1ff1TVg+T4ej3oWQspdU"
    "H\nErBdE/NsHYes1+R5rHGTK9vZSNU4BtH1jGZTAUSWOvgvgrX/WPUbCMI7CpbOesfE\n0FPBfeHa5VS/K+r7"
    "W8pM56IWprEeV+M0DcAvad8CgYEAgTTkF8ISDZKFAL3Xs7Sk\ny2mbbpUrnt9Sws1INECHEHYsDWhHpgSBXIw"
    "DfdeRhLkDXq2QG3xC2NGTjAyBgwsI\nXSWJwz20zVShEV4MOZprouKjzORgRuHMmax7kUHIqjA/TGdCiqhoVR"
    "VaCX4D3whr\n9qv/jAVIDbz6H+oxNjY1p2UCgYAYHwq0bUmwx8lGXi1Lyr6PImz+h+W+aLxbumAR\nLaIVf+z"
    "BxRy9hl14/HB4Ha8PkL5c6ENwP5M5HPSJa+5HSfp6LlaiJYfk7XxaT0/O\nUoVTjQYNZhMUbI3lMemyGSHhOc"
    "EUX217t/uoEB5iWPDIGTeZvB+woRTP5n8ANpoT\n5K2azwKBgC9d5dHa+6CRD/0gpb30/TzoQn5nMzkXPBj8d"
    "rzybz/Fu4wauc/HhTuY\nQ9go2jsZhpZgR+e37fzDzVxFeAA2F5mMbVHslpIh/qAvo+CWzCfausDCKRMSagC+"
    "\n1PpW5qJSKIkEBYQ1O+uh7rU6gL0LIXfxHHZiiFXB0P1UusSvHkew\n-----END RSA PRIVATE KEY-----"
)


@pytest.fixture()
def client():
    return testing.TestClient(app.create_app())


@pytest.fixture
def payload_data():
    return {"data": "to encrypt"}


@pytest.fixture
def encrypted_data(payload_data):
    jwe = JWE()
    data = jwe.encrypt(json.dumps(payload_data), public_key_pem=TEST_RSA_PUBLIC_KEY)
    return data


@pytest.fixture
def key_obj():
    expires_at = datetime.now() + timedelta(days=1)
    return {
        "public_key": TEST_RSA_PUBLIC_KEY,
        "private_key": TEST_RSA_PRIVATE_KEY,
        "expires_at": expires_at.timestamp(),
    }


SUPPORTED_KEY_MANAGEMENT_ALGS = [
    "RSA-OAEP",
    "RSA-OAEP-256",
]
SUPPORTED_CEK_ALGS = [
    "A128CBC-HS256",
    "A192CBC-HS384",
    "A256CBC-HS512",
    "A128GCM",
    "A192GCM",
    "A256GCM",
]
UNSUPPORTED_KEY_MANAGEMENT_ALGS = [
    "A128KW",
    "A192KW",
    "A256KW",
    "dir",
    "ECDH-ES",
    "ECDH-ES+A128KW",
    "ECDH-ES+A192KW",
    "ECDH-ES+A256KW",
    "A128GCMKW",
    "A192GCMKW",
    "A256GCMKW",
    "PBES2-HS256+A128KW",
    "PBES2-HS384+A192KW",
    "PBES2-HS512+A256KW",
]

# We support all CEK algs that is supported by the jwcrypto library
# UNSUPPORTED_CEK_ALGS = []


@pytest.mark.parametrize("alg", SUPPORTED_KEY_MANAGEMENT_ALGS)
@pytest.mark.parametrize("enc", SUPPORTED_CEK_ALGS)
def test_encrypt(alg, enc, payload_data):
    jwe = JWE()
    jwe.encrypt(json.dumps(payload_data), public_key_pem=TEST_RSA_PUBLIC_KEY, alg=alg, enc=enc)


@pytest.mark.parametrize("alg", UNSUPPORTED_KEY_MANAGEMENT_ALGS)
def test_encrypt_unsupported_algs(alg, payload_data):
    jwe = JWE()

    with pytest.raises(JweClientError):
        jwe.encrypt(json.dumps(payload_data), public_key_pem=TEST_RSA_PUBLIC_KEY, alg=alg)


@pytest.mark.parametrize("alg", SUPPORTED_CEK_ALGS)
def test_encrypt_invalid_algs(alg, payload_data):
    # Tests that supported CEK algs cannot be used for key management
    jwe = JWE()

    with pytest.raises(jwcrypto.common.InvalidJWAAlgorithm):
        jwe.encrypt(json.dumps(payload_data), public_key_pem=TEST_RSA_PUBLIC_KEY, alg=alg)


@pytest.mark.parametrize("enc", SUPPORTED_KEY_MANAGEMENT_ALGS)
def test_encrypt_invalid_encs(enc, payload_data):
    # Tests that supported key management algs cannot be used for CEK encryption
    jwe = JWE()

    with pytest.raises(jwcrypto.common.InvalidJWAAlgorithm):
        jwe.encrypt(json.dumps(payload_data), public_key_pem=TEST_RSA_PUBLIC_KEY, enc=enc)


@patch("app.encryption.JWE._get_keypair")
def test_decrypt(mock_get_keypair, encrypted_data, payload_data):
    jwe = JWE()
    mock_get_keypair.return_value = TEST_RSA_PRIVATE_KEY, None, 0

    jwe.deserialize(encrypted_data)
    payload = jwe.decrypt(kid="some-kid")

    assert mock_get_keypair.called
    assert json.loads(payload) == payload_data


@patch("app.encryption.JWE._get_keypair")
def test_decrypt_invalid_jwe(mock_get_keypair, encrypted_data, payload_data):
    jwe = JWE()
    mock_get_keypair.return_value = TEST_RSA_PRIVATE_KEY, None, 0

    jwe.deserialize(encrypted_data)
    jwe.token.objects["ciphertext"] = None

    with pytest.raises(JweClientError):
        jwe.decrypt(kid="some-kid")

    assert mock_get_keypair.called


def test_deserialize(encrypted_data):
    jwe = JWE()

    assert not jwe.token.objects
    jwe.deserialize(encrypted_data)
    assert jwe.token.objects

    for key in ("protected", "encrypted_key", "iv", "ciphertext", "tag"):
        assert key in jwe.token.objects
        assert jwe.token.objects[key]


def test_deserialize_invalid_jwe(payload_data):
    jwe = JWE()

    with pytest.raises(JweClientError):
        jwe.deserialize("badencryptedtoken")


@patch("app.encryption.vault.get_or_load_secret")
def test_get_keypair(mock_get_secret, key_obj):
    mock_get_secret.return_value = key_obj

    jwe = JWE()
    priv_key_pem, pub_key_pem, expires_at = jwe._get_keypair(kid="test-kid")

    assert mock_get_secret.called
    assert key_obj["private_key"] == priv_key_pem
    assert key_obj["public_key"] == pub_key_pem
    assert key_obj["expires_at"] == expires_at


@patch("app.encryption.vault.get_or_load_secret")
def test_missing_key_object_in_vault(mock_get_secret):
    mock_get_secret.return_value = {}

    jwe = JWE()
    with pytest.raises(MissingKey):
        jwe._get_keypair(kid="test-kid")

    assert mock_get_secret.called


@patch("app.encryption.vault.get_or_load_secret")
def test_invalid_key_object_in_vault(mock_get_secret, key_obj):
    jwe = JWE()
    required_keys = ["private_key", "expires_at"]

    for key in required_keys:
        test_key_obj = key_obj.copy()
        test_key_obj[f"invalid_{key}"] = test_key_obj.pop(key)
        mock_get_secret.return_value = test_key_obj

        with pytest.raises(InvalidKeyObj):
            jwe._get_keypair(kid="test-kid")

        assert mock_get_secret.called


@patch("app.encryption.vault.get_or_load_secret")
def test_expired_key(mock_get_secret, key_obj):
    jwe = JWE()

    expires_at = datetime.now() + timedelta(days=-2)
    key_obj["expires_at"] = expires_at.timestamp()
    mock_get_secret.return_value = key_obj

    with pytest.raises(ExpiredKey):
        jwe._get_keypair(kid="test-kid")

    assert mock_get_secret.called


@patch("app.encryption.vault.get_or_load_secret")
def test_get_keypair_without_pub_key_pem(mock_get_secret, key_obj):
    key_obj.pop("public_key")
    mock_get_secret.return_value = key_obj

    jwe = JWE()
    priv_key_pem, pub_key_pem, expires_at = jwe._get_keypair(kid="test-kid")

    assert mock_get_secret.called
    assert "public_key" not in key_obj
    assert pub_key_pem is None
    assert key_obj["private_key"] == priv_key_pem
    assert key_obj["expires_at"] == expires_at


@patch("app.encryption.JWE._get_keypair")
def test_get_private_key(mock_get_keypair):
    # Test get key when it's already been retrieved from the vault
    mock_get_keypair.return_value = TEST_RSA_PRIVATE_KEY, None, 0
    jwe = JWE()

    mock_key_val = "Not None value"
    jwe.private_key = mock_key_val
    jwe.get_private_key(kid="some-kid")

    assert not mock_get_keypair.called
    assert jwe.private_key == mock_key_val

    # Test get key from private key pem
    jwe = JWE()
    jwe.get_private_key(kid="some-kid")

    assert mock_get_keypair.called
    assert isinstance(jwe.private_key, jwk.JWK)

    # Test get key with invalid pem
    jwe = JWE()
    mock_get_keypair.return_value = "Invalid PEM", None, 0

    with pytest.raises(JweServerError):
        jwe.get_private_key(kid="some-kid")

    assert mock_get_keypair.called


@patch("app.encryption.JWE._get_keypair")
def test_get_public_key(mock_get_keypair):
    # Test get key when it's already been retrieved from the vault
    mock_get_keypair.return_value = TEST_RSA_PRIVATE_KEY, TEST_RSA_PUBLIC_KEY, 0
    jwe = JWE()

    mock_key_val = "Not None value"
    jwe.public_key = mock_key_val
    jwe.get_public_key(kid="some-kid")

    assert not mock_get_keypair.called
    assert jwe.public_key == mock_key_val

    # Test get key from public key pem
    mock_get_keypair.return_value = TEST_RSA_PRIVATE_KEY, TEST_RSA_PUBLIC_KEY, 0
    jwe = JWE()
    jwe.get_public_key(kid="some-kid")

    assert mock_get_keypair.called
    assert isinstance(jwe.public_key, jwk.JWK)

    # Test get key from private key
    mock_get_keypair.return_value = TEST_RSA_PRIVATE_KEY, None, 0
    jwe = JWE()
    jwe.private_key = jwe._get_key_from_pem(TEST_RSA_PRIVATE_KEY)
    jwe.get_public_key(kid="some-kid")

    assert mock_get_keypair.called
    assert isinstance(jwe.public_key, jwk.JWK)

    # Test get key from private key pem
    mock_get_keypair.return_value = TEST_RSA_PRIVATE_KEY, None, 0
    jwe = JWE()
    jwe.get_public_key(kid="some-kid")

    assert mock_get_keypair.called
    assert isinstance(jwe.public_key, jwk.JWK)

    # Test get key with invalid pem
    jwe = JWE()
    mock_get_keypair.return_value = "Invalid PEM", None, 0

    with pytest.raises(JweServerError):
        jwe.get_private_key(kid="some-kid")

    assert mock_get_keypair.called


# utility tests ###################################


@patch("app.encryption.JWE")
def test__decrypt_payload(mock_jwe, payload_data):
    mock_jwe.return_value.token.jose_header = {"kid": "some-kid"}
    mock_jwe.return_value.decrypt.return_value = json.dumps(payload_data)
    channel = "com.bink.test"

    decrypted_payload = _decrypt_payload(payload="some encrypted payload", channel=channel)

    assert mock_jwe.called
    assert mock_jwe.return_value.deserialize.called
    assert mock_jwe.return_value.decrypt.called
    assert mock_jwe.return_value.decrypt.call_args[1]["kid"] == "jwe-bink-test-ONXW2ZJNNNUWI"
    assert payload_data == decrypted_payload


@patch("app.encryption.api_logger")
@patch("app.encryption.JWE")
def test__decrypt_payload_logs_errors(mock_jwe, mock_logger, payload_data):
    """This is just to ensure we're logging any issues that arise during the decryption process"""

    # Error during deserialization
    mock_jwe.return_value.deserialize.side_effect = JweException
    channel = "com.bink.test"

    with pytest.raises(JweException):
        _decrypt_payload(payload="some encrypted payload", channel=channel)

    assert mock_jwe.called
    assert mock_jwe.return_value.deserialize.called
    assert not mock_jwe.return_value.decrypt.called
    assert mock_logger.debug.call_count == 1

    # Error when jose header is missing kid
    mock_jwe.return_value.deserialize.side_effect = None
    mock_jwe.return_value.token.jose_header = {"no-kid": "some-kid"}

    with pytest.raises(JweClientError):
        _decrypt_payload(payload="some encrypted payload", channel=channel)

    assert mock_logger.debug.call_count == 2

    # Error with decryption
    mock_jwe.return_value.token.jose_header = {"kid": "some-kid"}
    mock_jwe.return_value.decrypt.side_effect = JweException

    with pytest.raises(JweException):
        _decrypt_payload(payload="some encrypted payload", channel=channel)

    assert mock_logger.debug.call_count == 3


@patch("app.encryption._decrypt_payload")
def test_decrypt_payload_decorator(mock_decrypt, encrypted_data):
    mock_resource = MagicMock()
    mock_resource.on_post = MagicMock()

    mock_req = MagicMock()
    mock_resp = MagicMock()

    mock_req.media = encrypted_data
    mock_req.headers = {"ACCEPT": "application/json"}

    decrypt_payload(mock_resource.on_post)(mock_resource, mock_req, mock_resp)

    assert mock_resource.on_post.call_count == 1
    assert not mock_decrypt.called

    mock_req.headers = {"ACCEPT": "application/jose+json"}
    decrypt_payload(mock_resource.on_post)(mock_resource, mock_req, mock_resp)

    assert mock_resource.on_post.call_count == 2
    assert mock_decrypt.called

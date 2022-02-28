import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from jwcrypto import jwk

from app.encryption import JWE, InvalidKeyObj, ExpiredKey, MissingKey

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


@pytest.fixture(scope="function", autouse=True)
def payload_data():
    return {"data": "to encrypt"}


@pytest.fixture(scope="function")
def encrypted_data():
    jwe = JWE()
    data = jwe.encrypt(json.dumps(payload_data))
    return data


@pytest.fixture(scope="function")
def key_obj():
    expires_at = datetime.now() + timedelta(days=1)
    return {
        "public_key": TEST_RSA_PUBLIC_KEY,
        "private_key": TEST_RSA_PRIVATE_KEY,
        "expires_at": expires_at.timestamp(),
    }


def test_encrypt():
    pass


def test_decrypt():
    pass


def test_decrypt_invalid_jwe():
    pass


def test_deserialize():
    pass


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
    jwe.get_private_key(kid="")

    assert not mock_get_keypair.called
    assert jwe.private_key == mock_key_val

    # Test get key from private key pem
    jwe = JWE()
    jwe.get_private_key(kid="")

    assert mock_get_keypair.called
    assert isinstance(jwe.private_key, jwk.JWK)


@patch("app.encryption.JWE._get_keypair")
def test_get_public_key(mock_get_keypair):
    # Test get key when it's already been retrieved from the vault
    mock_get_keypair.return_value = TEST_RSA_PRIVATE_KEY, TEST_RSA_PUBLIC_KEY, 0
    jwe = JWE()

    mock_key_val = "Not None value"
    jwe.public_key = mock_key_val
    jwe.get_public_key(kid="")

    assert not mock_get_keypair.called
    assert jwe.public_key == mock_key_val

    # Test get key from public key pem
    mock_get_keypair.return_value = TEST_RSA_PRIVATE_KEY, TEST_RSA_PUBLIC_KEY, 0
    jwe = JWE()
    jwe.get_public_key(kid="")

    assert mock_get_keypair.called
    assert isinstance(jwe.public_key, jwk.JWK)

    # Test get key from private key
    mock_get_keypair.return_value = TEST_RSA_PRIVATE_KEY, None, 0
    jwe = JWE()
    jwe.private_key = jwe._get_key_from_pem(TEST_RSA_PRIVATE_KEY)
    jwe.get_public_key(kid="")

    assert mock_get_keypair.called
    assert isinstance(jwe.public_key, jwk.JWK)

    # Test get key from private key pem
    mock_get_keypair.return_value = TEST_RSA_PRIVATE_KEY, None, 0
    jwe = JWE()
    jwe.get_public_key(kid="")

    assert mock_get_keypair.called
    assert isinstance(jwe.public_key, jwk.JWK)


# utility tests ###################################


def test__decrypt_payload():
    pass


def test_decrypt_payload_decorator():
    pass

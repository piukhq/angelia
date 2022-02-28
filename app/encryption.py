import json
from base64 import b32decode, b32encode
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional

import falcon
from Crypto.PublicKey import RSA
from jwcrypto import jwe as crypto_jwe
from jwcrypto import jwk

from app.api.helpers import vault
from app.api.helpers.vault import save_secret_to_vault
from app.report import api_logger


# Padding stripping versions of base32
# as described for base64 in RFC 7515 Appendix C
def base32_encode(payload):
    if not isinstance(payload, bytes):
        payload = payload.encode("utf-8")
    encode = b32encode(payload)
    return encode.decode("utf-8").rstrip("=")


def base32_decode(payload):
    last_block_width = len(payload) % 8
    if last_block_width != 0:
        payload += (8 - last_block_width) * "="
    return b32decode(payload.encode("utf-8"))


def decrypt_payload(func):
    """
    todo: write this

    This can be used per resource function such as on_post, on_patch, on_put etc.
    """

    @wraps(func)
    def wrapper(self, req, resp):
        payload = req.media

        if req.headers.get("ACCEPT") != "application/jose+json" or not isinstance(payload, str):
            # If Accept value to denote encrypted payload is not found or the payload is not formatted as a JWE string
            # return early to avoid unnecessary processing.
            return func(self, req, resp)

        req.context.decrypted_media = _decrypt_payload(payload=payload, auth=req.context.auth_instance)
        return func(self, req, resp)

    return wrapper


def _decrypt_payload(payload, auth):
    jwe = JWE()
    channel = auth.auth_data["channel"]
    try:
        jwe.deserialize(payload)
        jwe_kid = jwe.token.jose_header["kid"]
    except JweClientError:
        api_logger.debug(f"Invalid JWE token - channel: {channel}")
        raise
    except KeyError:
        api_logger.debug(f"Invalid JWE token. JOSE header missing kid claim - channel: {channel}")
        raise JweClientError("JOSE header missing kid claim")

    azure_kid = f"jwe-{channel.removeprefix('com.').replace('.', '-')}-{base32_encode(jwe_kid)}"

    try:
        decrypted_payload = jwe.decrypt(kid=azure_kid)
        return json.loads(decrypted_payload)
    except JweClientError:
        api_logger.debug(
            f"Failed to decrypt payload for channel: {channel} - kid used: {azure_kid} - payload: {payload}"
        )


class JweException(Exception):
    pass


# Errors due to client mis-configuring JWE
# e.g missing claims, unsupported algorithms, using expired keys etc.
class JweClientError(JweException, falcon.HTTPBadRequest):
    def __init__(self, title=None, description=None, headers=None, **kwargs):
        super().__init__(
            title=title or "Invalid JWE",
            code="JWE_CLIENT_ERROR",
            description=description,
            headers=headers,
            **kwargs,
        )


class ExpiredKey(JweClientError):
    def __init__(self, title=None, **kwargs):
        super().__init__(
            title=title or "The key for the provided kid has expired. Please use a valid key to encrypt the CEK.",
            **kwargs,
        )


# Errors due to mis-configuring JWE from the server side e.g incorrect key storage
# Errors inheriting JweServerError do not need a title as it would be best to provide the default
# to the consumer so as not to expose the reason for internal server errors.
class JweServerError(JweException, falcon.HTTPInternalServerError):
    def __init__(self, title=None, description=None, headers=None, **kwargs):
        super().__init__(
            title=title or "Error occurred attempting to decrypt payload",
            code="JWE_SERVER_ERROR",
            description=description,
            headers=headers,
            **kwargs,
        )


class MissingKey(JweServerError):
    pass


class InvalidKeyObj(JweServerError):
    pass


class JWE:
    """todo: write this"""

    # Available algorithms
    # default_allowed_algs = [
    #     # Key Management Algorithms
    #     'RSA-OAEP', 'RSA-OAEP-256',
    #     'A128KW', 'A192KW', 'A256KW',
    #     'dir',
    #     'ECDH-ES', 'ECDH-ES+A128KW', 'ECDH-ES+A192KW', 'ECDH-ES+A256KW',
    #     'A128GCMKW', 'A192GCMKW', 'A256GCMKW',
    #     'PBES2-HS256+A128KW', 'PBES2-HS384+A192KW', 'PBES2-HS512+A256KW',
    #     # Content Encryption Algoritms
    #     'A128CBC-HS256', 'A192CBC-HS384', 'A256CBC-HS512',
    #     'A128GCM', 'A192GCM', 'A256GCM']

    allowed_algs = [
        # Key Management Algorithms
        "RSA-OAEP",
        "RSA-OAEP-256",
        # Content Encryption Algorithms
        "A128CBC-HS256",
        "A192CBC-HS384",
        "A256CBC-HS512",
        "A128GCM",
        "A192GCM",
        "A256GCM",
    ]

    def __init__(self):
        self.public_key: Optional[jwk.JWK] = None
        self.private_key: Optional[jwk.JWK] = None
        self.token: crypto_jwe.JWE = crypto_jwe.JWE(algs=self.allowed_algs)

    def get_public_key(self, kid: str) -> jwk.JWK:
        if self.public_key:
            return self.public_key

        priv_key_pem, pub_key_pem, _ = self._get_keypair(kid=kid)

        if pub_key_pem:
            self.public_key = self._get_key_from_pem(pub_key_pem)
        else:
            if not self.private_key:
                self.private_key = self._get_key_from_pem(priv_key_pem)
            pub_key = jwk.JWK()
            pub_key_json = self.private_key.export_public()
            self.public_key = pub_key.from_json(pub_key_json)

        return self.public_key

    def get_private_key(self, kid: str) -> jwk.JWK:
        if self.private_key:
            return self.private_key

        priv_key_pem, *_ = self._get_keypair(kid=kid)
        self.private_key = self._get_key_from_pem(priv_key_pem)
        return self.private_key

    @staticmethod
    def _get_keypair(kid: str) -> tuple[str, str, float]:
        key_obj = vault.get_or_load_secret(kid)
        time_now = datetime.now().timestamp()

        if not key_obj:
            api_logger.error(f"Could not locate JWE key secret in vault with name {kid}")
            raise MissingKey
        try:
            # Can be retrieved from private key JWK if this isn't present
            pub_key_pem = key_obj.get("public_key")
            priv_key_pem = key_obj["private_key"]
            expires_at = key_obj["expires_at"]
        except KeyError:
            api_logger.exception(f"Incorrectly formatted JWE key secret in vault with name {kid}")
            raise InvalidKeyObj

        if time_now > expires_at:
            # How should we handle expired keys? Return an error or process as usual but raise a sentry error?
            api_logger.warning(
                f"Decryption attempted with expired key - kid: {kid} "
                f"- expired at: {datetime.fromtimestamp(expires_at).isoformat()}"
            )
            raise ExpiredKey

        return priv_key_pem, pub_key_pem, expires_at

    @staticmethod
    def _get_key_from_pem(key_pem: str) -> jwk.JWK:
        key = jwk.JWK()
        key.import_from_pem(key_pem.encode())
        return key

    def deserialize(self, raw_jwe: str) -> None:
        try:
            self.token.deserialize(raw_jwe=raw_jwe)
        except crypto_jwe.InvalidJWEData:
            api_logger.debug(f"Invalid JWE token - token: {raw_jwe}")
            raise JweClientError("Could not deserialize payload. Invalid JWE data.")

    def encrypt(
        self,
        payload: str,
        alg: str = "RSA-OAEP-256",
        enc: str = "A256CBC-HS512",
        public_key_pem: str = None,
        kid: str = None,
        compact: bool = True,
    ) -> str:
        if not (self.private_key or public_key_pem or kid):
            raise JweClientError("No public key pem or kid provided")
        if alg not in self.allowed_algs:
            raise JweClientError(f"{alg} not supported")
        if enc not in self.allowed_algs:
            raise JweClientError(f"{enc} not supported")

        if public_key_pem:
            self.public_key = self._get_key_from_pem(public_key_pem)
        else:
            self.get_public_key(kid=kid)

        protected_header = {
            "alg": alg,
            "enc": enc,
            "typ": "JWE",
            "kid": self.public_key.thumbprint(),
        }
        jwe_token = crypto_jwe.JWE(payload.encode("utf-8"), recipient=self.public_key, protected=protected_header)
        return jwe_token.serialize(compact=compact)

    def decrypt(self, kid: str) -> str:
        self.get_private_key(kid=kid)
        try:
            self.token.decrypt(key=self.private_key)
        except (crypto_jwe.InvalidJWEData, crypto_jwe.InvalidJWEOperation) as e:
            api_logger.debug(f"Failed to decrypt payload - kid: {kid} - Exception: {e}")
            raise JweClientError("Failed to decrypt payload")
        return self.token.payload.decode("utf-8")


def gen_rsa_keypair(priv_path: str = "rsa", pub_path: str = "rsa.pub"):
    key = RSA.generate(2048)

    private_key = open(priv_path, "wb")
    private_key.write(key.export_key("PEM"))
    private_key.close()

    pub = key.public_key()
    pub_key = open(pub_path, "wb")
    pub_key.write(pub.export_key("PEM"))
    pub_key.close()


def gen_vault_key_obj(channel, pub, priv, days_to_expire=1, paths=True):
    pub_key = jwk.JWK()

    if paths:
        with open(pub, "r") as f:
            pub_key_pem = f.read()
            pub_key.import_from_pem(pub_key_pem)

        with open(priv, "r") as f:
            priv_key_pem = f.read()
    else:
        pub_key.import_from_pem(pub.encode())

    jwe_kid = pub_key.thumbprint()

    azure_kid = f"jwe-{channel.removeprefix('com.').replace('.', '-')}-{base32_encode(jwe_kid)}"
    expiry = datetime.now() + timedelta(days=days_to_expire)
    value = {"public_key": pub_key_pem, "private_key": priv_key_pem, "expires_at": expiry.timestamp()}

    api_logger.info(
        f"FOR TESTING PURPOSES OR LOCAL USE ONLY\nAzure secret name:\n{azure_kid}\n\nValue:\n{json.dumps(value)}\n\n"
    )


def encrypt(data, kid):
    jwe = JWE()
    return jwe.encrypt(data, alg="RSA-OAEP", kid=kid)


def test_encrypt():
    data = {
        "expiry_month": "12",
        "expiry_year": "24",
        "name_on_card": "Jeff Bloggs",
        "card_nickname": "My Mastercard",
        "issuer": "HSBC",
        "token": "H7FdKWKPOPhepzxS4MfUuvTDHxr",
        "last_four_digits": "9876",
        "first_six_digits": "444444",
        "fingerprint": "b5fe350d5135ab64a8f3c1097fadefd9effb",
        "provider": "MasterCard",
        "type": "debit",
        "country": "GB",
        "currency_code": "GBP",
    }
    kid = "jwe-barclays-bmb-GVTUQ6RZMFHFQYJNJN2EOWDLN5AUEUJRJU3TCV3GL44W243BGRREWLKCOZQWE2RSG5XVC"
    return encrypt(json.dumps(data), kid)


def test_save_vault_key(days_to_expire: int):
    expires_at = datetime.now() + timedelta(days=days_to_expire)
    key_obj = {
        "public_key": "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAmlFEqgeo1Y17sigLgdIK\nHUcFh8Tsa7tsX3+uMSvIg+2XPJMi04o3fMd+P6s0rGuJ2qr0Xvlcl27r06/dFCwY\nAIqv3I9UeDGyDp++mZsVEJuaOt3/VMCBctZ9hol9Oo/KnkXP1bAAa1EqjlmzpTHi\nUZla2Z8HovRYXyGt5a+nDcp6b655S94xmXrADtaLW1NxYgrWEgc5mK7U0v69m3ER\nTJ8N3Hm1SGMYgVBfZxswG+mtHYTUpelXDAHUksY4yYfxw2+19ASfKdpNy/k3Fzgj\n0qr/cq7RYHLyqfpL0ZQnLjlFnTOzG2pgrvnzoqDaPbt6n+eFSXPrtisFHmm1dyLc\nWwIDAQAB\n-----END PUBLIC KEY-----",
        "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEAmlFEqgeo1Y17sigLgdIKHUcFh8Tsa7tsX3+uMSvIg+2XPJMi\n04o3fMd+P6s0rGuJ2qr0Xvlcl27r06/dFCwYAIqv3I9UeDGyDp++mZsVEJuaOt3/\nVMCBctZ9hol9Oo/KnkXP1bAAa1EqjlmzpTHiUZla2Z8HovRYXyGt5a+nDcp6b655\nS94xmXrADtaLW1NxYgrWEgc5mK7U0v69m3ERTJ8N3Hm1SGMYgVBfZxswG+mtHYTU\npelXDAHUksY4yYfxw2+19ASfKdpNy/k3Fzgj0qr/cq7RYHLyqfpL0ZQnLjlFnTOz\nG2pgrvnzoqDaPbt6n+eFSXPrtisFHmm1dyLcWwIDAQABAoIBAAH48vP19qXnaRoe\nitMceSIrH11Kwzdl2XqKd2QGJI/BUI0+KR/AnwUJDhvT9IbnHp7UZzQLY3X/g0ac\n/vuk413VULRpJYB7QFBXRBoBWDoVb3ECAGksUr4qtfXCrjjGLRpry76BzRYdtlbb\njME9NDfyJy3mGfpLvbQnxF42hyWyGItTYrvCAESTTxqQPW8as2CZNqxc+qQix/wD\nqy9N4NnxXzwo/tbevcMx4asT9xIHVfNcngWRckD69bxRurIL/M/a+p6AIC0rHlrj\n2GftyhMXsfY2TWpRTGusBQOZbfipEGsjulJCaDRywTJPmDILYVMy98pSBlihoJCE\nn7VBXuUCgYEAxovs/O8Ho5bT8X22dHAzkt1/LQEWcYx2QwAAAlt8XAN15G00G/8b\nn64sojSdK7s2SmaAzsB3N0FjJAuVCHLiTokywXT4f0LjWaE69dd3dprR+eP5tHcW\nEWbWBecNnpXLgZQ5nIItA/1grNLpWM770qUeIGgJGAi9IbSzF7NJlQUCgYEAxvjn\n2VV8y9EF1kmlx1sZ/7WjCh0zmLaXhUJ3ZgkxC6HbYvK1ff1TVg+T4ej3oWQspdUH\nErBdE/NsHYes1+R5rHGTK9vZSNU4BtH1jGZTAUSWOvgvgrX/WPUbCMI7CpbOesfE\n0FPBfeHa5VS/K+r7W8pM56IWprEeV+M0DcAvad8CgYEAgTTkF8ISDZKFAL3Xs7Sk\ny2mbbpUrnt9Sws1INECHEHYsDWhHpgSBXIwDfdeRhLkDXq2QG3xC2NGTjAyBgwsI\nXSWJwz20zVShEV4MOZprouKjzORgRuHMmax7kUHIqjA/TGdCiqhoVRVaCX4D3whr\n9qv/jAVIDbz6H+oxNjY1p2UCgYAYHwq0bUmwx8lGXi1Lyr6PImz+h+W+aLxbumAR\nLaIVf+zBxRy9hl14/HB4Ha8PkL5c6ENwP5M5HPSJa+5HSfp6LlaiJYfk7XxaT0/O\nUoVTjQYNZhMUbI3lMemyGSHhOcEUX217t/uoEB5iWPDIGTeZvB+woRTP5n8ANpoT\n5K2azwKBgC9d5dHa+6CRD/0gpb30/TzoQn5nMzkXPBj8drzybz/Fu4wauc/HhTuY\nQ9go2jsZhpZgR+e37fzDzVxFeAA2F5mMbVHslpIh/qAvo+CWzCfausDCKRMSagC+\n1PpW5qJSKIkEBYQ1O+uh7rU6gL0LIXfxHHZiiFXB0P1UusSvHkew\n-----END RSA PRIVATE KEY-----",
        "expires_at": expires_at.timestamp(),
    }
    kid = "jwe-barclays-bmb-GVTUQ6RZMFHFQYJNJN2EOWDLN5AUEUJRJU3TCV3GL44W243BGRREWLKCOZQWE2RSG5XVC"

    save_secret_to_vault(kid, json.dumps(key_obj))

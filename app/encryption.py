import json
import os
from base64 import b32decode, b32encode
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional

import falcon
from Crypto.PublicKey import RSA
from jwcrypto import jwe as crypto_jwe
from jwcrypto import jwk

from app.api.helpers import vault
from app.api.metrics import encrypt_counter
from app.report import api_logger


class JweException(Exception):
    pass


# Errors due to client mis-configuring JWE
# e.g missing claims, unsupported algorithms, using expired keys etc.
class JweClientError(JweException, falcon.HTTPBadRequest):
    def __init__(self, title=None, description=None, headers=None, **kwargs):
        super().__init__(
            title=title or "Invalid JWE token",
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
    """
    This class is for handling JWE token encryption and decryption using the jwcrypto library and azure vault for
    key storage.

    Encryption/Decryption require RSA keys that are stored in the vault. These keys are stored in "key objects"
    containing the public key, private key, and the datetime of their expiry as a unix timestamp e.g:

    {
        "public_key": ...,
        "private_key": ...,
        "expires_at": 1234234234.3423
    }

    The secret name under which they are stored have a standard format, containing information about the channel which
    the keys relate, and the thumbprint of the public key in base32. Generation of the secret name and key objects
    can be done using the utility functions in this module.

    All errors raised are subclasses of falcon.HTTPError to handle API responses.
    """

    # Available algorithms
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
            api_logger.warning(
                f"Decryption attempted with expired key - kid: {kid} "
                f"- expired at: {datetime.fromtimestamp(expires_at).isoformat()}"
            )
            raise ExpiredKey

        return priv_key_pem, pub_key_pem, expires_at

    @staticmethod
    def _get_key_from_pem(key_pem: str) -> jwk.JWK:
        key = jwk.JWK()
        try:
            key.import_from_pem(key_pem.encode())
        except ValueError as e:
            api_logger.debug(e)
            raise JweServerError
        return key

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

    def deserialize(self, raw_jwe: str) -> None:
        try:
            self.token.deserialize(raw_jwe=raw_jwe)
        except crypto_jwe.InvalidJWEData:
            api_logger.debug(f"Invalid JWE token - token: {raw_jwe}")
            raise JweClientError("Could not deserialize payload. Invalid JWE data.")

    def decrypt(self, kid: str) -> str:
        self.get_private_key(kid=kid)
        try:
            self.token.decrypt(key=self.private_key)
        except (crypto_jwe.InvalidJWEData, crypto_jwe.InvalidJWEOperation) as e:
            api_logger.debug(f"Failed to decrypt payload - kid: {kid} - Exception: {e}")
            raise JweClientError("Failed to decrypt payload")
        return self.token.payload.decode("utf-8")

    def encrypt(
        self,
        payload: str,
        alg: str = "RSA-OAEP",
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


# Utilities ####################################################################################


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
    Decorator function that will attempt to decrypt a payload for an endpoint. For the decryption to be
    attempted, the ACCEPT header of the request must equal "application/jose+json" and the payload must
    be a string value. If not, we will assume the payload is unencrypted and process as normal.

    This can be used per resource function such as on_post, on_patch, on_put etc.
    """

    @wraps(func)
    def wrapper(self, req, resp, *args, **kwargs):
        payload = req.media

        if req.headers.get("ACCEPT", "").strip().lower() != "application/jose+json" or not isinstance(payload, str):
            # unencrypted metric
            encrypt_counter.labels(
                endpoint=f"angelia{req.path}", channel=req.context.auth_instance.auth_data["channel"], encryption=False
            ).inc()

            # If Accept value to denote encrypted payload is not found or the payload is not formatted as a JWE string
            # return early to avoid unnecessary processing.
            return func(self, req, resp, *args, **kwargs)

        req.context.decrypted_media = _decrypt_payload(
            payload=payload, channel=req.context.auth_instance.auth_data["channel"]
        )

        # encrypted metric
        encrypt_counter.labels(
            endpoint=f"angelia{req.path}", channel=req.context.auth_instance.auth_data["channel"], encryption=True
        ).inc()

        return func(self, req, resp, *args, **kwargs)

    return wrapper


def _decrypt_payload(payload: str, channel: str):
    jwe = JWE()
    try:
        jwe.deserialize(payload)
        jwe_kid = jwe.token.jose_header["kid"]
    except JweException:
        api_logger.debug(f"Invalid JWE token - channel: {channel} - payload: {payload}")
        raise
    except KeyError:
        api_logger.debug(
            f"Invalid JWE token. JOSE header missing kid claim - channel: {channel} "
            f"JOSE headers: {jwe.token.jose_header}"
        )
        raise JweClientError("JOSE header missing kid claim")

    azure_kid = f"jwe-{channel.removeprefix('com.').replace('.', '-')}-{base32_encode(jwe_kid)}"

    try:
        decrypted_payload = jwe.decrypt(kid=azure_kid)
        return json.loads(decrypted_payload)
    except JweException:
        api_logger.debug(
            f"Failed to decrypt payload for channel: {channel} - kid used: {azure_kid} - payload: {payload}"
        )
        raise


def gen_rsa_keypair(priv_path: str, pub_path: str):
    key = RSA.generate(2048)

    private_key = open(priv_path, "wb")
    private_key.write(key.export_key("PEM"))
    private_key.close()

    pub = key.public_key()
    pub_key = open(pub_path, "wb")
    pub_key.write(pub.export_key("PEM"))
    pub_key.close()


def gen_vault_key_obj(channel_slug, priv, pub, mins_to_expire=60 * 24, paths=True) -> tuple[str, dict]:
    pub_key = jwk.JWK()

    if paths:
        priv = os.path.abspath(priv)
        pub = os.path.abspath(pub)

        with open(pub, "rb") as f:
            pub_key_pem = f.read()
            pub_key.import_from_pem(pub_key_pem)
            pub_key_pem = pub_key_pem.decode()

        with open(priv, "rb") as f:
            priv_key_pem = f.read()
            priv_key_pem = priv_key_pem.decode()

    else:
        pub_key.import_from_pem(pub.encode())
        pub_key_pem = pub
        priv_key_pem = priv

    jwe_kid = pub_key.thumbprint()

    azure_kid = f"jwe-{channel_slug.removeprefix('com.').replace('.', '-')}-{base32_encode(jwe_kid)}"
    expiry = datetime.now() + timedelta(minutes=mins_to_expire)
    value = {"public_key": pub_key_pem, "private_key": priv_key_pem, "expires_at": expiry.timestamp()}

    print(
        "FOR TESTING PURPOSES OR LOCAL USE ONLY\nAzure secret name:"
        f"\n{azure_kid}\n\nValue:\n{json.dumps(value, indent=4)}\n\n"
    )
    return azure_kid, value


def manual_encrypt(data: dict, pub_key_path: str = None, kid: str = None):
    """
    A simplified, more user-friendly encryption function that allows providing a filepath to a public key.

    Can be used as a helper tool for manual testing with encryption.
    """
    if not (pub_key_path or kid):
        raise ValueError("pub_key_path or kid required")

    jwe = JWE()

    if pub_key_path:
        with open(pub_key_path, "r") as f:
            pub_key_pem = f.read()
        token = jwe.encrypt(json.dumps(data), public_key_pem=pub_key_pem)
    else:
        token = jwe.encrypt(json.dumps(data), kid=kid)

    return json.dumps(token)

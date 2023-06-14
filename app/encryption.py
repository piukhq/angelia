import json
import os
from base64 import b32decode, b32encode
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import falcon
from Crypto.PublicKey import RSA
from jwcrypto import jwe as crypto_jwe
from jwcrypto import jwk

from app.api.helpers import vault
from app.api.metrics import encrypt_counter
from app.report import api_logger

if TYPE_CHECKING:
    from typing import TypeVar

    from falcon import Request, Response

    ResType = TypeVar("ResType")


class JweException(Exception):
    pass


# Errors due to client mis-configuring JWE
# e.g missing claims, unsupported algorithms, using expired keys etc.
class JweClientError(JweException, falcon.HTTPBadRequest):
    def __init__(
        self, title: str | None = None, description: str | None = None, headers: dict | None = None, **kwargs: Any
    ) -> None:
        super().__init__(  # type: ignore
            title=title or "Invalid JWE token",
            code="JWE_CLIENT_ERROR",
            description=description,
            headers=headers,
            **kwargs,
        )


class ExpiredKey(JweClientError):
    def __init__(self, title: str | None = None, **kwargs: Any) -> None:
        super().__init__(
            title=title or "The key for the provided kid has expired. Please use a valid key to encrypt the CEK.",
            **kwargs,
        )


# Errors due to mis-configuring JWE from the server side e.g incorrect key storage
# Errors inheriting JweServerError do not need a title as it would be best to provide the default
# to the consumer so as not to expose the reason for internal server errors.
class JweServerError(JweException, falcon.HTTPInternalServerError):
    def __init__(
        self, title: str | None = None, description: str | None = None, headers: dict | None = None, **kwargs: Any
    ) -> None:
        super().__init__(  # type: ignore [call-arg]
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

    def __init__(self) -> None:
        self.public_key: jwk.JWK | None = None
        self.private_key: jwk.JWK | None = None
        self.token: crypto_jwe.JWE = crypto_jwe.JWE(algs=self.allowed_algs)

    @staticmethod
    def _get_keypair(kid: str) -> tuple[str, str | None, float]:
        key_obj: dict[str, str | float] = vault.get_or_load_secret(kid)
        time_now = datetime.now().timestamp()

        if not key_obj:
            api_logger.error(f"Could not locate JWE key secret in vault with name {kid}")
            raise MissingKey
        try:
            # Can be retrieved from private key JWK if this isn't present
            pub_key_pem = cast(str | None, key_obj.get("public_key"))
            priv_key_pem = cast(str, key_obj["private_key"])
            expires_at = cast(float, key_obj["expires_at"])
        except KeyError:
            api_logger.exception(f"Incorrectly formatted JWE key secret in vault with name {kid}")
            raise InvalidKeyObj from None

        if time_now > expires_at:
            api_logger.warning(
                f"Decryption attempted with expired key - kid: {kid} "
                f"- expired at: {datetime.fromtimestamp(expires_at, tz=UTC).isoformat()}"
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
            raise JweServerError from None
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

    def deserialize(self, raw_jwe: str | dict) -> None:
        try:
            self.token.deserialize(raw_jwe=raw_jwe)
        except crypto_jwe.InvalidJWEData:
            api_logger.debug(f"Invalid JWE token - token: {raw_jwe}")
            raise JweClientError("Could not deserialize payload. Invalid JWE data.") from None

    def decrypt(self, kid: str) -> str:
        self.get_private_key(kid=kid)
        try:
            self.token.decrypt(key=self.private_key)
        except (crypto_jwe.InvalidJWEData, crypto_jwe.InvalidJWEOperation) as e:
            api_logger.debug(f"Failed to decrypt payload - kid: {kid} - Exception: {e}")
            raise JweClientError("Failed to decrypt payload") from None
        return self.token.payload.decode("utf-8")

    def encrypt(  # noqa: PLR0913
        self,
        payload: str,
        alg: str = "RSA-OAEP",
        enc: str = "A256CBC-HS512",
        public_key_pem: str = None,  # type: ignore [assignment]
        kid: str = None,  # type: ignore [assignment]
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

        if not self.public_key:
            raise ValueError("public_key unexpectedly None")

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
def base32_encode(payload: bytes | str) -> str:
    if not isinstance(payload, bytes):
        payload = payload.encode("utf-8")
    encode = b32encode(payload)
    return encode.decode("utf-8").rstrip("=")


def base32_decode(payload: str) -> bytes:
    last_block_width = len(payload) % 8
    if last_block_width != 0:
        payload += (8 - last_block_width) * "="
    return b32decode(payload.encode("utf-8"))


def decrypt_payload(func: "Callable[..., ResType]") -> "Callable[..., ResType]":
    """
    Decorator function that will attempt to decrypt a payload for an endpoint. For the decryption to be
    attempted, the ACCEPT header of the request must equal "application/jose+json" and the payload must
    be a string value. If not, we will assume the payload is unencrypted and process as normal.

    This can be used per resource function such as on_post, on_patch, on_put etc.
    """

    @wraps(func)
    def wrapper(self: Any, req: "Request", resp: "Response", *args: Any, **kwargs: Any) -> "ResType":
        encryption = False
        payload = req.media

        if req.headers.get("ACCEPT", "").strip().lower() != "application/jose+json" or not isinstance(payload, str):
            endpoint = ""
            if kwargs:
                key = list(kwargs.keys())[0]
                endpoint = req.path.replace(str(kwargs[key]), f"{{{key}}}")

            # unencrypted metric
            encrypt_counter.labels(
                endpoint=endpoint or req.path,
                channel=req.context.auth_instance.auth_data["channel"],
                encryption=encryption,
            ).inc()

            # If Accept value to denote encrypted payload is not found or the payload is not formatted as a JWE string
            # return early to avoid unnecessary processing.
            return func(self, req, resp, *args, **kwargs)

        encryption = True
        req.context.decrypted_media = _decrypt_payload(
            payload=payload, channel=req.context.auth_instance.auth_data["channel"]
        )

        # encrypted metric
        encrypt_counter.labels(
            endpoint=req.path, channel=req.context.auth_instance.auth_data["channel"], encryption=encryption
        ).inc()

        return func(self, req, resp, *args, **kwargs)

    return wrapper


def _decrypt_payload(payload: str, channel: str) -> dict | list:
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
        raise JweClientError("JOSE header missing kid claim") from None

    azure_kid = f"jwe-{channel.removeprefix('com.').replace('.', '-')}-{base32_encode(jwe_kid)}"

    try:
        decrypted_payload = jwe.decrypt(kid=azure_kid)
        return json.loads(decrypted_payload)
    except JweException:
        api_logger.debug(
            f"Failed to decrypt payload for channel: {channel} - kid used: {azure_kid} - payload: {payload}"
        )
        raise


def gen_rsa_keypair(priv_path: str, pub_path: str) -> None:
    key = RSA.generate(2048)
    Path(priv_path).write_bytes(key.export_key("PEM"))

    pub = key.public_key()
    Path(pub_path).write_bytes(pub.export_key("PEM"))


def gen_vault_key_obj(
    channel_slug: str, priv: str, pub: str, mins_to_expire: int = 60 * 24, paths: bool = True
) -> tuple[str, dict]:
    pub_key = jwk.JWK()

    if paths:
        priv = os.path.abspath(priv)
        pub = os.path.abspath(pub)

        with open(pub, "rb") as f:
            pub_key_pem_raw = f.read()
            pub_key.import_from_pem(pub_key_pem_raw)
            pub_key_pem = pub_key_pem_raw.decode()

        with open(priv, "rb") as f:
            priv_key_pem = f.read().decode()

    else:
        pub_key.import_from_pem(pub.encode())
        pub_key_pem = pub
        priv_key_pem = priv

    jwe_kid = pub_key.thumbprint()

    azure_kid = f"jwe-{channel_slug.removeprefix('com.').replace('.', '-')}-{base32_encode(jwe_kid)}"
    expiry = datetime.now() + timedelta(minutes=mins_to_expire)
    value = {"public_key": pub_key_pem, "private_key": priv_key_pem, "expires_at": expiry.timestamp()}

    api_logger.info(
        "FOR TESTING PURPOSES OR LOCAL USE ONLY\nAzure secret name:"
        f"\n{azure_kid}\n\nValue:\n{json.dumps(value, indent=4)}\n\n"
    )
    return azure_kid, value


def manual_encrypt(data: dict, pub_key_path: str | None = None, kid: str | None = None) -> str:
    """
    A simplified, more user-friendly encryption function that allows providing a filepath to a public key.

    Can be used as a helper tool for manual testing with encryption.
    """

    if pub_key_path:
        pub_key_pem = Path(pub_key_path).read_text()

        token = JWE().encrypt(json.dumps(data), public_key_pem=pub_key_pem)
    elif kid:
        token = JWE().encrypt(json.dumps(data), kid=kid)
    else:
        raise ValueError("pub_key_path or kid required")

    return json.dumps(token)

import json
from base64 import b32decode, b32encode
from datetime import datetime, timedelta
from functools import wraps

import falcon
from Crypto.PublicKey import RSA
from jwcrypto import jwe as crypto_jwe
from jwcrypto import jwk

from app.api.helpers import vault
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

        auth = req.context.auth_instance
        req.context.decrypted_media = _decrypt_payload(payload=payload, auth=auth)
        return func(self, req, resp)

    return wrapper


def _decrypt_payload(payload, auth):
    jwe = JWE()
    channel = auth.auth_data["channel"]
    try:
        raise JWE.ExpiredKeyError
        jwe.deserialize(payload)
        jwe_kid = jwe.token.jose_header["kid"]
    except JWE.JweClientError:
        api_logger.debug(f"Invalid JWE token - channel: {channel}")
        raise
    except KeyError:
        api_logger.debug(f"Invalid JWE token. JOSE header missing kid claim - channel: {channel}")
        raise JWE.JweClientError("JOSE header missing kid claim")

    azure_kid = f"jwe-{channel.removeprefix('com.').replace('.', '-')}-{base32_encode(jwe_kid)}"

    try:
        decrypted_payload = jwe.decrypt(kid=azure_kid)
        return json.loads(decrypted_payload)
    except JWE.JweClientError:
        api_logger.debug(
            f"Failed to decrypt payload for channel: {channel} - kid used: {azure_kid} - payload: {payload}"
        )


class JWE:
    """todo: write this"""

    # Errors due to client mis-configuring JWE
    # e.g missing claims, unsupported algorithms, using expired keys etc.
    class JweClientError(falcon.HTTPBadRequest):

        def __init__(self, title=None, description=None, headers=None, **kwargs):
            super().__init__(
                title=title or "Invalid JWE",
                code="JWE_CLIENT_ERROR",
                description=description,
                headers=headers,
                **kwargs,
            )

    class ExpiredKeyError(JweClientError):
        def __init__(self, title=None, **kwargs):
            super().__init__(
                title=title or "The key for the provided kid has expired",
                **kwargs,
            )

    # Errors due to mis-configuring JWE from the server side e.g incorrect key storage
    # Errors inheriting JweServerError do not need a title as it would be best to provide the default
    # to the consumer so as not to expose the reason for internal server errors.
    class JweServerError(falcon.HTTPInternalServerError):
        def __init__(self, title=None, description=None, headers=None, **kwargs):
            super().__init__(
                title=title or "Error occurred attempting to decrypt payload",
                code="JWE_SERVER_ERROR",
                description=description,
                headers=headers,
                **kwargs,
            )

    class MissingKeyError(JweServerError):
        pass

    class InvalidKeyError(JweServerError):
        pass

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
        self.public_key = None
        self.private_key = None
        self.token = crypto_jwe.JWE(algs=self.allowed_algs)

    def _get_keypair(self, kid):
        key_obj = vault.get_or_load_secret(kid)
        time_now = datetime.now().timestamp()

        if not key_obj:
            api_logger.error(f"Could not locate JWE key secret in vault with name {kid}")
            raise self.MissingKeyError("Error decrypting payload")
        try:
            # Can be retrieved from private key JWK if this isn't present
            pub_key_pem = key_obj.get("public_key")
            priv_key_pem = key_obj["private_key"]
            expires_at = key_obj["expires_at"]
        except KeyError:
            api_logger.exception(f"Incorrectly formatted JWE key secret in vault with name {kid}")
            raise self.InvalidKeyError

        if time_now > expires_at:
            # How should we handle expired keys? Return an error or process as usual but raise a sentry error?
            api_logger.error(
                f"Decryption attempted with expired key - kid: {kid} "
                f"- expired at: {datetime.fromtimestamp(expires_at).isoformat()}"
            )
            raise self.ExpiredKeyError

        self.private_key = jwk.JWK()
        self.private_key.import_from_pem(priv_key_pem.encode())

        if pub_key_pem:
            self.public_key = jwk.JWK()
            self.public_key.import_from_pem(pub_key_pem.encode())
        else:
            self.public_key = self.private_key.export_public()

    def _get_key_from_pem(self, key_pem: str):
        key = jwk.JWK()
        key.import_from_pem(key_pem.encode())
        return key

    def deserialize(self, raw_jwe):
        try:
            self.token.deserialize(raw_jwe=raw_jwe)
        except crypto_jwe.InvalidJWEData:
            api_logger.debug(f"Invalid JWE token - token: {raw_jwe}")
            raise JWE.JweClientError("Could not deserialize payload. Invalid JWE data.")

    def encrypt(
        self,
        payload: str,
        alg: str = "RSA-OAEP-256",
        enc: str = "A256CBC-HS512",
        private_key_pem: str = None,
        kid: str = None,
        compact: bool = True,
    ) -> str:
        if not (private_key_pem or kid or self.private_key):
            raise self.JweServerError("No private key pem or kid provided")
        if alg not in self.allowed_algs:
            raise self.JweClientError(f"{alg} not supported")
        if enc not in self.allowed_algs:
            raise self.JweClientError(f"{enc} not supported")

        if private_key_pem:
            self.private_key = self._get_key_from_pem(private_key_pem)
        else:
            self._get_keypair(kid=kid)

        protected_header = {
            "alg": alg,
            "enc": enc,
            "typ": "JWE",
            "kid": self.public_key.thumbprint(),
        }
        jwe_token = crypto_jwe.JWE(payload.encode("utf-8"), recipient=self.public_key, protected=protected_header)
        return jwe_token.serialize(compact=compact)

    def decrypt(self, kid: str) -> str:
        self._get_keypair(kid=kid)
        try:
            self.token.decrypt(key=self.private_key)
        except crypto_jwe.InvalidJWEData:
            raise self.JweClientError("Failed to decrypt payload")
        return self.token.payload.decode("utf-8")


def gen_rsa_keypair(priv_path, pub_path):
    key = RSA.generate(2048)

    private_key = open(priv_path, "wb")
    private_key.write(key.export_key("PEM"))
    private_key.close()

    pub = key.public_key()
    pub_key = open(pub_path, "wb")
    pub_key.write(pub.export_key("PEM"))
    pub_key.close()


def gen_vault_key_obj(channel, pub, priv, days_to_expire):
    pub_key = jwk.JWK()
    pub_key.import_from_pem(pub.encode())
    jwe_kid = pub_key.thumbprint()

    azure_kid = f"jwe-{channel.removeprefix('com.').replace('.', '-')}-{base32_encode(jwe_kid)}"
    expiry = datetime.now() + timedelta(days=days_to_expire)
    value = {"public_key": pub, "private_key": priv, "expires_at": expiry.timestamp()}

    api_logger.info(
        f"FOR TESTING PURPOSES OR LOCAL USE ONLY\nAzure secret name:\n{azure_kid}\n\nValue:\n{json.dumps(value)}\n\n"
    )


def encrypt(data, kid):
    jwe = JWE()
    return jwe.encrypt(data, alg="RSA-OAEP-256", kid=kid)


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

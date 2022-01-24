import json
from base64 import b64encode, b64decode
from functools import wraps

import rustyjeff
from Crypto.Cipher import AES, PKCS1_OAEP
from Crypto.PublicKey import RSA
from Crypto.Random import get_random_bytes

from app.api.helpers.vault import dynamic_get_b2b_token_secret
from app.api.validators import _validate_req_schema, encrypted_payload_schema


def decrypt_payload(func):
    """
    Decorator function to decrypt payloads using RSA with OAEP padding to decrypt the key, and AES CCM
    to decrypt the payload using the decrypted key.
    The payload will only be decrypted if the channel requires it.
    if not, no further processing will be done and will return early.

    This can be used per resource function such as on_post, on_patch, on_put etc.
    """

    @wraps(func)
    def wrapper(self, req, resp):
        # check if decryption is required
        auth = req.context.auth_instance
        channel = auth.auth_data["channel"]

        # validate payload
        _validate_req_schema(encrypted_payload_schema, req, from_decrypt=True)

        # get payload, decrypt and format
        req.context.decrypted_media = _decrypt_payload(req.context.encrypted_media, auth)

        return func(self, req, resp)

    return wrapper


def _decrypt_payload(payload, auth):
    # todo: store keys as separate secrets in vault.
    #  Investigate storage key name i.e what prefix and how to get prefix from token.
    #  name = (prefix + pub key fingerprint)?
    secrets = dynamic_get_b2b_token_secret(auth.headers["kid"])

    cipher = RsaAesCipher({})
    decrypted_payload = json.loads(cipher.decrypt(payload))


    return decrypted_payload


def gen_rsa_keypair(priv_path, pub_path):
    key = RSA.generate(2048)

    private_key = open(priv_path, 'wb')
    private_key.write(key.export_key('PEM'))
    private_key.close()

    pub = key.public_key()
    pub_key = open(pub_path, 'wb')
    pub_key.write(pub.export_key('PEM'))
    pub_key.close()





def encrypt(data):
    key = get_random_bytes(16)

    # encrypt key with RSA and send in header
    b64key = b64encode(key)
    encrypted_key = rsa_encrypt(b64key)
    encrypted_b64key = b64encode(encrypted_key).decode("utf-8")

    header = json.dumps({"encrypted_key": encrypted_b64key}).encode('utf-8')

    cipher = AES.new(key, AES.MODE_CCM)
    cipher.update(header)
    ciphertext, tag = cipher.encrypt_and_digest(data.encode())

    json_k = ['iv', 'header', 'encrypted_value', 'tag']
    json_v = [b64encode(x).decode('utf-8') for x in (cipher.nonce, header, ciphertext, tag)]
    result = json.dumps(dict(zip(json_k, json_v)))
    return result


# Alt 1 - headers separated as different fields
# def encrypt(data):
#     key = get_random_bytes(16)
#
#     # encrypt key with RSA and send in header
#     b64key = b64encode(key)
#     encrypted_key = rsa_encrypt(b64key)
#     encrypted_b64key = b64encode(encrypted_key)
#     fingerprint = b"fingerprint"
#
#     cipher = AES.new(key, AES.MODE_CCM)
#     cipher.update(encrypted_b64key)
#     cipher.update(fingerprint)
#     ciphertext, tag = cipher.encrypt_and_digest(data.encode())
#
#     json_k = ['iv', 'encrypted_key', 'encrypted_value', 'tag', 'public_key_fingerprint']
#     json_v = [b64encode(x).decode('utf-8') for x in (cipher.nonce, encrypted_b64key, ciphertext, tag, fingerprint)]
#     result = json.dumps(dict(zip(json_k, json_v)))
#     return result


# Alt 2 - headers separated within headers field as json object.
# def encrypt(data):
#     key = get_random_bytes(16)
#
#     # encrypt key with RSA and send in header
#     b64key = b64encode(key)
#     encrypted_key = rsa_encrypt(b64key)
#     encrypted_b64key = b64encode(encrypted_key).decode("utf-8")
#
#     header = json.dumps({"encrypted_key": encrypted_b64key}).encode('utf-8')
#
#     cipher = AES.new(key, AES.MODE_CCM)
#     cipher.update(header)
#     ciphertext, tag = cipher.encrypt_and_digest(data.encode())
#
#     json_k = ['iv', 'encrypted_value', 'tag']
#     json_v = [b64encode(x).decode('utf-8') for x in (cipher.nonce, ciphertext, tag)]
#     json_dict = dict(zip(json_k, json_v))
#     json_dict["header"] = json.loads(header.decode())
#
#     result = json.dumps(json_dict)
#     return result


def decrypt(data: dict):
    try:
        json_k = ['iv', 'encrypted_key', 'encrypted_value', 'tag', 'public_key_fingerprint']
        jv = {k: b64decode(data[k]) for k in json_k}

        encrypted_key = jv['encrypted_key']

        # get key from cache?
        # if not cached, get from vault,
        # get current time and validate against timestamp in key structure
        # if invalid raise 5xx?
        # may want an RSA class here to handle these steps

        decrypted_b64key = rsa_decrypt(encrypted_key.decode("utf-8"))[0]
        decrypted_key = b64decode(decrypted_b64key)

        cipher = AES.new(decrypted_key, AES.MODE_CCM, nonce=jv['iv'])
        cipher.update(jv['encrypted_key'])
        cipher.update(jv['public_key_fingerprint'])
        plaintext = cipher.decrypt_and_verify(jv['encrypted_value'], jv['tag'])
        return plaintext.decode("utf-8")
    except (ValueError, KeyError):
        print("Incorrect decryption")
        raise


# def decrypt(data: dict):
#     try:
#         json_k = ['iv', 'header', 'encrypted_value', 'tag']
#         jv = {k: b64decode(data[k]) for k in json_k}
#
#         header = json.loads(jv['header'])
#         decrypted_b64key = rsa_decrypt(header["encrypted_key"])[0]
#         decrypted_key = b64decode(decrypted_b64key)
#
#         cipher = AES.new(decrypted_key, AES.MODE_CCM, nonce=jv['iv'])
#         cipher.update(jv['header'])
#         plaintext = cipher.decrypt_and_verify(jv['encrypted_value'], jv['tag'])
#         return plaintext.decode("utf-8")
#     except (ValueError, KeyError):
#         print("Incorrect decryption")
#         raise


def rsa_encrypt(data):
    key = RSA.importKey("-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAmlFEqgeo1Y17sigLgdIK\nHUcFh8Tsa7tsX3+uMSvIg+2XPJMi04o3fMd+P6s0rGuJ2qr0Xvlcl27r06/dFCwY\nAIqv3I9UeDGyDp++mZsVEJuaOt3/VMCBctZ9hol9Oo/KnkXP1bAAa1EqjlmzpTHi\nUZla2Z8HovRYXyGt5a+nDcp6b655S94xmXrADtaLW1NxYgrWEgc5mK7U0v69m3ER\nTJ8N3Hm1SGMYgVBfZxswG+mtHYTUpelXDAHUksY4yYfxw2+19ASfKdpNy/k3Fzgj\n0qr/cq7RYHLyqfpL0ZQnLjlFnTOzG2pgrvnzoqDaPbt6n+eFSXPrtisFHmm1dyLc\nWwIDAQAB\n-----END PUBLIC KEY-----")
    cipher = PKCS1_OAEP.new(key)
    ciphertext = cipher.encrypt(data)
    return ciphertext


def rsa_decrypt(data):
    priv_key = '-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEAmlFEqgeo1Y17sigLgdIKHUcFh8Tsa7tsX3+uMSvIg+2XPJMi\n04o3fMd+P6s0rGuJ2qr0Xvlcl27r06/dFCwYAIqv3I9UeDGyDp++mZsVEJuaOt3/\nVMCBctZ9hol9Oo/KnkXP1bAAa1EqjlmzpTHiUZla2Z8HovRYXyGt5a+nDcp6b655\nS94xmXrADtaLW1NxYgrWEgc5mK7U0v69m3ERTJ8N3Hm1SGMYgVBfZxswG+mtHYTU\npelXDAHUksY4yYfxw2+19ASfKdpNy/k3Fzgj0qr/cq7RYHLyqfpL0ZQnLjlFnTOz\nG2pgrvnzoqDaPbt6n+eFSXPrtisFHmm1dyLcWwIDAQABAoIBAAH48vP19qXnaRoe\nitMceSIrH11Kwzdl2XqKd2QGJI/BUI0+KR/AnwUJDhvT9IbnHp7UZzQLY3X/g0ac\n/vuk413VULRpJYB7QFBXRBoBWDoVb3ECAGksUr4qtfXCrjjGLRpry76BzRYdtlbb\njME9NDfyJy3mGfpLvbQnxF42hyWyGItTYrvCAESTTxqQPW8as2CZNqxc+qQix/wD\nqy9N4NnxXzwo/tbevcMx4asT9xIHVfNcngWRckD69bxRurIL/M/a+p6AIC0rHlrj\n2GftyhMXsfY2TWpRTGusBQOZbfipEGsjulJCaDRywTJPmDILYVMy98pSBlihoJCE\nn7VBXuUCgYEAxovs/O8Ho5bT8X22dHAzkt1/LQEWcYx2QwAAAlt8XAN15G00G/8b\nn64sojSdK7s2SmaAzsB3N0FjJAuVCHLiTokywXT4f0LjWaE69dd3dprR+eP5tHcW\nEWbWBecNnpXLgZQ5nIItA/1grNLpWM770qUeIGgJGAi9IbSzF7NJlQUCgYEAxvjn\n2VV8y9EF1kmlx1sZ/7WjCh0zmLaXhUJ3ZgkxC6HbYvK1ff1TVg+T4ej3oWQspdUH\nErBdE/NsHYes1+R5rHGTK9vZSNU4BtH1jGZTAUSWOvgvgrX/WPUbCMI7CpbOesfE\n0FPBfeHa5VS/K+r7W8pM56IWprEeV+M0DcAvad8CgYEAgTTkF8ISDZKFAL3Xs7Sk\ny2mbbpUrnt9Sws1INECHEHYsDWhHpgSBXIwDfdeRhLkDXq2QG3xC2NGTjAyBgwsI\nXSWJwz20zVShEV4MOZprouKjzORgRuHMmax7kUHIqjA/TGdCiqhoVRVaCX4D3whr\n9qv/jAVIDbz6H+oxNjY1p2UCgYAYHwq0bUmwx8lGXi1Lyr6PImz+h+W+aLxbumAR\nLaIVf+zBxRy9hl14/HB4Ha8PkL5c6ENwP5M5HPSJa+5HSfp6LlaiJYfk7XxaT0/O\nUoVTjQYNZhMUbI3lMemyGSHhOcEUX217t/uoEB5iWPDIGTeZvB+woRTP5n8ANpoT\n5K2azwKBgC9d5dHa+6CRD/0gpb30/TzoQn5nMzkXPBj8drzybz/Fu4wauc/HhTuY\nQ9go2jsZhpZgR+e37fzDzVxFeAA2F5mMbVHslpIh/qAvo+CWzCfausDCKRMSagC+\n1PpW5qJSKIkEBYQ1O+uh7rU6gL0LIXfxHHZiiFXB0P1UusSvHkew\n-----END RSA PRIVATE KEY-----'
    return rustyjeff.rsa_decrypt_base64(priv_key, [data])


class RsaAesCipher:
    iv: bytes
    encrypted_key: bytes
    encrypted_value: bytes
    tag: bytes
    public_key_fingerprint: bytes

    class DecryptionError(Exception):
        pass

    class ExpiredKey(DecryptionError):
        pass

    def __init__(self, rsa_keys: dict):
        """
        rsa_keys: dict of public key fingerprints to paired RSA private keys
        """
        self.rsa_keys = rsa_keys

    def _parse_payload(self, payload: dict):
        json_k = ['iv', 'encrypted_key', 'encrypted_value', 'tag', 'public_key_fingerprint']
        [setattr(self, k, b64decode(payload[k])) for k in json_k]

    def _get_priv_key(self):
        fingerprint = b64decode(self.public_key_fingerprint)
        # todo: get key and check timestamp validity


    def _rsa_decrypt(self, data: str):
        pkey = self._get_priv_key()
        priv_key = '-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEAmlFEqgeo1Y17sigLgdIKHUcFh8Tsa7tsX3+uMSvIg+2XPJMi\n04o3fMd+P6s0rGuJ2qr0Xvlcl27r06/dFCwYAIqv3I9UeDGyDp++mZsVEJuaOt3/\nVMCBctZ9hol9Oo/KnkXP1bAAa1EqjlmzpTHiUZla2Z8HovRYXyGt5a+nDcp6b655\nS94xmXrADtaLW1NxYgrWEgc5mK7U0v69m3ERTJ8N3Hm1SGMYgVBfZxswG+mtHYTU\npelXDAHUksY4yYfxw2+19ASfKdpNy/k3Fzgj0qr/cq7RYHLyqfpL0ZQnLjlFnTOz\nG2pgrvnzoqDaPbt6n+eFSXPrtisFHmm1dyLcWwIDAQABAoIBAAH48vP19qXnaRoe\nitMceSIrH11Kwzdl2XqKd2QGJI/BUI0+KR/AnwUJDhvT9IbnHp7UZzQLY3X/g0ac\n/vuk413VULRpJYB7QFBXRBoBWDoVb3ECAGksUr4qtfXCrjjGLRpry76BzRYdtlbb\njME9NDfyJy3mGfpLvbQnxF42hyWyGItTYrvCAESTTxqQPW8as2CZNqxc+qQix/wD\nqy9N4NnxXzwo/tbevcMx4asT9xIHVfNcngWRckD69bxRurIL/M/a+p6AIC0rHlrj\n2GftyhMXsfY2TWpRTGusBQOZbfipEGsjulJCaDRywTJPmDILYVMy98pSBlihoJCE\nn7VBXuUCgYEAxovs/O8Ho5bT8X22dHAzkt1/LQEWcYx2QwAAAlt8XAN15G00G/8b\nn64sojSdK7s2SmaAzsB3N0FjJAuVCHLiTokywXT4f0LjWaE69dd3dprR+eP5tHcW\nEWbWBecNnpXLgZQ5nIItA/1grNLpWM770qUeIGgJGAi9IbSzF7NJlQUCgYEAxvjn\n2VV8y9EF1kmlx1sZ/7WjCh0zmLaXhUJ3ZgkxC6HbYvK1ff1TVg+T4ej3oWQspdUH\nErBdE/NsHYes1+R5rHGTK9vZSNU4BtH1jGZTAUSWOvgvgrX/WPUbCMI7CpbOesfE\n0FPBfeHa5VS/K+r7W8pM56IWprEeV+M0DcAvad8CgYEAgTTkF8ISDZKFAL3Xs7Sk\ny2mbbpUrnt9Sws1INECHEHYsDWhHpgSBXIwDfdeRhLkDXq2QG3xC2NGTjAyBgwsI\nXSWJwz20zVShEV4MOZprouKjzORgRuHMmax7kUHIqjA/TGdCiqhoVRVaCX4D3whr\n9qv/jAVIDbz6H+oxNjY1p2UCgYAYHwq0bUmwx8lGXi1Lyr6PImz+h+W+aLxbumAR\nLaIVf+zBxRy9hl14/HB4Ha8PkL5c6ENwP5M5HPSJa+5HSfp6LlaiJYfk7XxaT0/O\nUoVTjQYNZhMUbI3lMemyGSHhOcEUX217t/uoEB5iWPDIGTeZvB+woRTP5n8ANpoT\n5K2azwKBgC9d5dHa+6CRD/0gpb30/TzoQn5nMzkXPBj8drzybz/Fu4wauc/HhTuY\nQ9go2jsZhpZgR+e37fzDzVxFeAA2F5mMbVHslpIh/qAvo+CWzCfausDCKRMSagC+\n1PpW5qJSKIkEBYQ1O+uh7rU6gL0LIXfxHHZiiFXB0P1UusSvHkew\n-----END RSA PRIVATE KEY-----'
        return rustyjeff.rsa_decrypt_base64(priv_key, [data])

    def encrypt(self, data: str) -> str:
        key = get_random_bytes(16)

        # encrypt key with RSA and send in header
        b64key = b64encode(key)
        encrypted_key = rsa_encrypt(b64key)
        encrypted_b64key = b64encode(encrypted_key).decode("utf-8")

        header = json.dumps({"encrypted_key": encrypted_b64key}).encode('utf-8')

        cipher = AES.new(key, AES.MODE_CCM)
        cipher.update(header)
        ciphertext, tag = cipher.encrypt_and_digest(data.encode())

        json_k = ['iv', 'header', 'encrypted_value', 'tag']
        json_v = [b64encode(x).decode('utf-8') for x in (cipher.nonce, header, ciphertext, tag)]
        result = json.dumps(dict(zip(json_k, json_v)))
        return result

    def decrypt(self, data: dict) -> str:
        try:
            self._parse_payload(data)

            # get key from cache?
            # if not cached, get from vault,
            # get current time and validate against timestamp in key structure
            # if invalid raise 5xx?
            # may want an RSA class here to handle these steps
            decrypted_b64key = rsa_decrypt(self.encrypted_key.decode("utf-8"))[0]
            decrypted_key = b64decode(decrypted_b64key)

            cipher = AES.new(decrypted_key, AES.MODE_CCM, nonce=self.iv)
            cipher.update(self.encrypted_key)
            cipher.update(self.public_key_fingerprint)
            plaintext = cipher.decrypt_and_verify(self.encrypted_value, self.tag)
            return plaintext.decode("utf-8")
        except (ValueError, KeyError):
            print("Incorrect decryption")
            raise



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
        "currency_code": "GBP"
    }
    return encrypt(json.dumps(data))

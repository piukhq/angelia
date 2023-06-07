import base64
import hashlib

from Crypto import Random
from Crypto.Cipher import AES

from app.api.helpers.vault import get_aes_key

# TODO : this should become its own library


class AESCipher:
    def __init__(self, aes_type: str) -> None:
        self.bs = 32
        _key = get_aes_key(aes_type).encode()
        self.key = hashlib.sha256(_key).digest()

    def encrypt(self, raw: str) -> bytes:
        if raw == "":  # noqa: PLC1901
            raise TypeError("Cannot encrypt nothing")

        padded_raw = self._pad(raw.encode("utf-8"))
        iv = Random.new().read(AES.block_size)
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        return base64.b64encode(iv + cipher.encrypt(padded_raw))

    def decrypt(self, enc: str | bytes) -> str:
        if enc == "":  # noqa: PLC1901
            raise TypeError("Cannot decrypt nothing")

        enc = base64.b64decode(enc)
        iv = enc[: AES.block_size]
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        return self._unpad(cipher.decrypt(enc[AES.block_size :])).decode("utf-8")

    def _pad(self, s: bytes) -> bytes:
        length = self.bs - (len(s) % self.bs)
        return s + bytes([length]) * length

    @staticmethod
    def _unpad(s: bytes) -> bytes:
        return s[: -ord(s[len(s) - 1 :])]

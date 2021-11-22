from app.api.helpers.vault import AESKeyNames
from app.lib.encryption import AESCipher
from tests.helpers.local_vault import set_vault_cache


def test_encrypt_decrypt_local():
    set_vault_cache(to_load=["aes-keys"])
    items = ["one", "rg1 1aa", "wefhe7¡€#∞§¶•ªº,.;'wewhf@€jhgd", "fgf", "s", "98989", "hhfhfhfhfrw5424w5r75t8797gy"]
    cipher = AESCipher(AESKeyNames.LOCAL_AES_KEY)
    for value_in_clear in items:
        enc_value = cipher.encrypt(value_in_clear).decode("utf-8")
        value_decrypted = cipher.decrypt(enc_value)
        assert value_decrypted == value_in_clear


def test_encrypt_decrypt_aes_key():
    set_vault_cache(to_load=["aes-keys"])
    items = ["one", "rg1 1aa", "wefhe7¡€#∞§¶•ªº,.;'wewhf@€jhgd", "fgf", "s", "98989", "hhfhfhfhfrw5424w5r75t8797gy"]
    cipher = AESCipher(AESKeyNames.AES_KEY)
    for value_in_clear in items:
        enc_value = cipher.encrypt(value_in_clear).decode("utf-8")
        value_decrypted = cipher.decrypt(enc_value)
        assert value_decrypted == value_in_clear

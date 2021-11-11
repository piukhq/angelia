from app.api.helpers.vault import AESKeyNames
from app.lib.encryption import AESCipher
from tests.helpers.local_vault import set_vault_cache


def test_encrypt_decrypt():
    set_vault_cache(to_load=["aes-keys"])
    items = ["one", "rg1 1aa", "wefhe7¡€#∞§¶•ªº,.;'wewhf@€jhgd", "fgf", "s", "98989", "hhfhfhfhfrw5424w5r75t8797gy"]
    cipher = AESCipher(AESKeyNames.LOCAL_AES_KEY)
    for value_in_clear in items:
        enc_value = cipher.encrypt(value_in_clear).decode("utf-8")
        value_decrypted = cipher.decrypt(enc_value)
        assert value_decrypted == value_in_clear


def test_stored_encryptions():
    set_vault_cache(to_load=["aes-keys"])
    cipher = AESCipher(AESKeyNames.LOCAL_AES_KEY)
    enc_items = {
        "one": "upg6XeEzndQKxD0PZDUm0KUOo+20MRUl98fvchB/qV7/iggz8fNc+bvUxMpfjuwg",
        "rg1 1aa": "iF0fLjSpKFHjrbi8+syv/3Eq+OzNRKJWVLHsiR8Iz1Qhm9cREcRmLJ+iuF601jBt",
        "wefhe7¡€#∞§¶•ªº,.;'wewhf@€jhgd": "GNCiFeqs455R/S9aI4lg5LmX70jnpGCUdkqM3mTt2doikrgEPSxnKL59nIzInU19TL4if"
        "DZfQ4VwT4TeBjGJiS6ddIZKs/VBzZxzZrfX5Rc=",
        "fgf": "rFTgJMyk6g1Rm3FlnGgusml7pu9McAmCAs82u4urohLAQ1ZkmffzzSsqLFdlKETl",
        "s": "cUsyTRqfGruZcRWY3rOPYr20wVR419282sGuewwWui009cHBohliTIMqYi44n5EC",
        "98989": "e/04jkckxrXMiYiGTei7Ilw6A67IVwYx97PLIq1X5PO8FBAFzmaUdsjmhd7BbtJ4",
        "hhfhfhfhfrw5424w5r75t8797gy": "pd3EPs7glw4E+EtaVZboZUcMMUQsiO/aJFELeeovRJw9KSdfHDf1Qbt2FDpEFqDe",
    }
    for clear_item, enc_item in enc_items.items():
        decrypted = cipher.decrypt(enc_item)
        assert decrypted == clear_item

from app.core.security import hash_password, verify_password

# сгенерирован passlib 1.7.4 (CryptContext bcrypt) до миграции на прямой bcrypt:
# существующие пользователи должны продолжать входить со старыми хэшами
PASSLIB_HASH = "$2b$12$QV/HeHJ3sAAI8iLeCWLhiukfuGquEqY6HPyg6maveVVQQo7DXTWLC"


def test_hash_and_verify_roundtrip():
    hashed = hash_password("password123")
    assert hashed.startswith("$2b$")
    assert verify_password("password123", hashed)
    assert not verify_password("wrong-password", hashed)


def test_legacy_passlib_hash_still_verifies():
    assert verify_password("password123", PASSLIB_HASH)
    assert not verify_password("wrong-password", PASSLIB_HASH)


def test_long_password_truncated_like_passlib():
    # passlib молча усекал до 72 байт; bcrypt>=5 бросал бы ValueError без явного среза
    long_password = "x" * 100
    hashed = hash_password(long_password)
    assert verify_password(long_password, hashed)
    # первые 72 байта совпадают — по семантике bcrypt это тот же пароль
    assert verify_password("x" * 72, hashed)


def test_garbage_hash_returns_false_not_500():
    assert not verify_password("password123", "not-a-bcrypt-hash")

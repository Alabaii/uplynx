"""Генерация пары VAPID-ключей для web push: python -m app.tools.vapid"""
from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid01, b64urlencode


def main() -> None:
    vapid = Vapid01()
    vapid.generate_keys()
    public_key = b64urlencode(
        vapid.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    )
    private_key = b64urlencode(vapid.private_key.private_numbers().private_value.to_bytes(32, "big"))
    print(f"VAPID_PUBLIC_KEY={public_key}")
    print(f"VAPID_PRIVATE_KEY={private_key}")


if __name__ == "__main__":
    main()

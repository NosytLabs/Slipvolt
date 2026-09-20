"""Small, auditable cryptographic helpers. No wallet private keys are stored."""
import base64
import hashlib
import hmac
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'

def decode_address(value: str) -> bytes:
    if not isinstance(value, str) or not 32 <= len(value) <= 44:
        raise ValueError('Invalid Solana address')
    n = 0
    for char in value:
        if char not in ALPHABET:
            raise ValueError('Invalid Solana address')
        n = n * 58 + ALPHABET.index(char)
    raw = (b'\0' * (len(value) - len(value.lstrip('1')))
           + (n.to_bytes((n.bit_length() + 7) // 8, 'big') if n else b''))
    if len(raw) != 32:
        raise ValueError('Solana addresses must decode to 32 bytes')
    return raw

def digest(value: str, pepper: str) -> str:
    return hmac.new(pepper.encode(), value.encode(), hashlib.sha256).hexdigest()

def verify_signature(wallet: str, message: str, signature: str) -> None:
    try:
        raw = base64.b64decode(signature, validate=True)
        if len(raw) != 64:
            raise ValueError('Invalid signature length')
        Ed25519PublicKey.from_public_bytes(decode_address(wallet)).verify(raw, message.encode())
    except Exception as exc:
        raise ValueError('Invalid wallet signature') from exc

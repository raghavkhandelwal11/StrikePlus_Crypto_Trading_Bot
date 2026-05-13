"""CLI: encrypt a raw private key for storage in WALLET_ENCRYPTED_KEY.

Usage:
  python backend/scripts/encrypt_key.py
  (prompts for the private key and password — does NOT take them on the command line
  to avoid leaving secrets in shell history.)
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

# Make the `app` package importable when running this script directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.security import encrypt_secret  # noqa: E402


def main() -> None:
    print("Encrypt wallet private key for storage in .env (WALLET_ENCRYPTED_KEY).")
    print("Both the private key and password are read from stdin, never echoed.\n")
    pk = getpass.getpass("Private key (0x...): ").strip()
    if not pk.startswith("0x"):
        pk = "0x" + pk
    pw = getpass.getpass("Encryption password: ")
    pw2 = getpass.getpass("Confirm password: ")
    if pw != pw2:
        sys.exit("passwords do not match")
    if not pw:
        sys.exit("password may not be empty")
    cipher = encrypt_secret(pk, pw)
    print("\nAdd these to your .env file:")
    print(f"WALLET_ENCRYPTED_KEY={cipher}")
    print("WALLET_ENCRYPTION_PASSWORD=  # the password you just chose")
    print("WALLET_ADDRESS=0x...        # the public address derived from the key")


if __name__ == "__main__":
    main()

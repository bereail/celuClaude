"""Utility: python scripts/hash_password.py <password>
Prints a bcrypt hash to paste into .env as APP_USER_PASSWORD_HASH.
"""

import sys

from passlib.context import CryptContext

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python scripts/hash_password.py <password>")
        sys.exit(1)
    ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    print(ctx.hash(sys.argv[1]))

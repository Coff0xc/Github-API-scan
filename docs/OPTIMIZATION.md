# About the old performance numbers

This page used to quote "3–5×", "100–430×", and a comparison table showing 0.24 seconds. Those numbers cannot be reproduced as one complete scan, and have been removed from the repository.

`benchmark.py` only times synthetic-row SQLite inserts. It does not search GitHub, and it does not call any model vendor.

Entry point, scope, and export behavior follow [README](../README.md) and [QUICKSTART.md](QUICKSTART.md).

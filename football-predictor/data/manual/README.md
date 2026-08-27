# Mutable operational evidence

This directory contains locally accumulated, time-sensitive evidence such as
official odds snapshots, external-market history, betting ledgers, prematch
intelligence, and shadow ledgers. Its generated CSV and image files are ignored
by Git because they change during scheduled runs and may contain personal or
licensed data.

Do not delete these files merely because Git ignores them. Preserve immutable
snapshots, timestamps, source metadata, and hashes in durable storage. Empty
field contracts intended for source control belong in `data/templates`.

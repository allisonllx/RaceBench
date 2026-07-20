# Distinguishes stale write outcomes

The user correctly predicted that a stale same-function rewrite is dangerous under `naive`, is usually caught as a possible conflict under `git_hash`, and is handled differently by prevention (`file_lock`) versus notification (`notify`). This means future lessons can use `stale read` and `lost update` as working concepts rather than reintroducing them from scratch.

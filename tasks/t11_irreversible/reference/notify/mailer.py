import release


def notify_customers():
    if not release.READY:
        raise RuntimeError("not ready")
    return f"notified:{release.RELEASE_VERSION}"

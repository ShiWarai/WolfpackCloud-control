"""Парсинг Kubernetes resource.Quantity (memory / CPU) без зависимости от k8s-клиента."""


def parse_k8s_memory_bytes(quantity: str | None) -> int:
    """Парсинг memory из Node/Pod resources (Ki, Mi, Gi, …) в байты."""
    s = (quantity or "").strip()
    if not s:
        return 0
    binary_suffixes = (
        ("Ki", 1024),
        ("Mi", 1024**2),
        ("Gi", 1024**3),
        ("Ti", 1024**4),
        ("Pi", 1024**5),
        ("Ei", 1024**6),
    )
    for suf, mult in binary_suffixes:
        if s.endswith(suf):
            return int(float(s[: -len(suf)].strip()) * mult)
    return int(float(s))


def parse_k8s_cpu_millicores(quantity: str | None) -> int:
    """CPU в millicores (100m → 100, 1 → 1000)."""
    s = (quantity or "").strip()
    if not s:
        return 0
    if s.endswith("m"):
        return int(float(s[:-1].strip()))
    return int(float(s) * 1000)

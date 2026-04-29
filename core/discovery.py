# This script identifies the architecture.
import platform
import os


def _canonical_arch(raw_arch: str) -> str:
    arch = (raw_arch or "").strip().lower()
    aliases = {
        "amd64": "x86_64",
        "arm64": "aarch64",
        "powerpc64le": "ppc64le",
        "ppc64el": "ppc64le",
        "ppc64": "ppc64le",
    }
    return aliases.get(arch, arch)


def get_arch_details():
    real_arch = _canonical_arch(platform.machine())
    is_mock = os.getenv("MOCK_S390X", "false").lower() == "true"

    if is_mock:
        return {"isa": "s390x", "type": "Mocked IBM Z", "is_enterprise": True}

    arch_map = {
        "x86_64": {"isa": "x86_64", "type": "Consumer Laptop", "is_enterprise": False},
        "aarch64": {"isa": "arm64", "type": "Raspberry Pi 5", "is_enterprise": False},
        "ppc64le": {
            "isa": "ppc64le",
            "type": "IBM Power10",
            "is_enterprise": True,
            "virtualization": "KVM-para",
            "threading_policy": "SMT1",
            "sockets": 8,
        },
        "s390x": {"isa": "s390x", "type": "IBM Z Mainframe", "is_enterprise": True},
    }

    return arch_map.get(real_arch, {"isa": real_arch, "type": "Unknown", "is_enterprise": False})

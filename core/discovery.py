#This script identifies the architecture.
import platform
import os

def get_arch_details():
    real_arch = platform.machine().lower()
    is_mock = os.getenv("MOCK_S390X", "false").lower() == "true"
    
    if is_mock:
        return {"isa": "s390x", "type": "Mocked IBM Z", "is_enterprise": True}
    
    arch_map = {
        "x86_64": {"isa": "x86_64", "type": "Consumer Laptop", "is_enterprise": False},
        "aarch64": {"isa": "arm64", "type": "Raspberry Pi 5", "is_enterprise": False},
        "ppc64le": {"isa": "ppc64le", "type": "IBM Power10", "is_enterprise": True},
        "s390x": {"isa": "s390x", "type": "IBM Z Mainframe", "is_enterprise": True}
    }
    
    return arch_map.get(real_arch, {"isa": real_arch, "type": "Unknown", "is_enterprise": False})
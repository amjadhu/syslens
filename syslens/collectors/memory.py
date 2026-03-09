import psutil


def _to_gb(b):
    return round(b / (1024 ** 3), 2)


def collect():
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()

    return {
        "ram": {
            "total_gb": _to_gb(vm.total),
            "available_gb": _to_gb(vm.available),
            "used_gb": _to_gb(vm.used),
            "percent": vm.percent,
        },
        "swap": {
            "total_gb": _to_gb(swap.total),
            "used_gb": _to_gb(swap.used),
            "free_gb": _to_gb(swap.free),
            "percent": swap.percent,
        },
    }

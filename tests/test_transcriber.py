from easytype.transcriber import resolve_compute_type


def test_compute_type_cpu():
    assert resolve_compute_type("cpu") == "int8"


def test_compute_type_cuda():
    assert resolve_compute_type("cuda") == "float16"


def test_compute_type_auto():
    assert resolve_compute_type("auto") == "default"

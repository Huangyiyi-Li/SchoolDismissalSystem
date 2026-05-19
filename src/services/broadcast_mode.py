TEST_MODE_WINDOW_SIGNATURE = "TestMode"


def get_effective_window_signature(window_signature, is_test_mode):
    if window_signature:
        return window_signature
    if is_test_mode:
        return TEST_MODE_WINDOW_SIGNATURE
    return None

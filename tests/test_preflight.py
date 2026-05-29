from easytype.preflight import Issue, detect_session, gather_issues, format_report


def test_detect_session_x11(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert detect_session() == "x11"


def test_detect_session_wayland(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    assert detect_session() == "wayland"


def test_all_ok_yields_no_failures():
    issues = gather_issues(
        groups=["input"], uinput_writable=True,
        binaries={"xdotool": True, "xclip": True, "notify-send": True}, tk_ok=True,
    )
    assert all(i.ok for i in issues)


def test_missing_input_group_reports_usermod_fix():
    issues = gather_issues(
        groups=["users"], uinput_writable=True,
        binaries={"xdotool": True, "xclip": True, "notify-send": True}, tk_ok=True,
    )
    group_issue = next(i for i in issues if i.name == "input group")
    assert not group_issue.ok
    assert "usermod -aG input" in group_issue.fix


def test_missing_uinput_reports_udev_rule():
    issues = gather_issues(
        groups=["input"], uinput_writable=False,
        binaries={"xdotool": True, "xclip": True, "notify-send": True}, tk_ok=True,
    )
    u = next(i for i in issues if i.name == "/dev/uinput access")
    assert not u.ok
    assert "uinput" in u.fix


def test_missing_binary_reported():
    issues = gather_issues(
        groups=["input"], uinput_writable=True,
        binaries={"xdotool": False, "xclip": True, "notify-send": True}, tk_ok=True,
    )
    x = next(i for i in issues if i.name == "xdotool")
    assert not x.ok
    assert "apt install" in x.fix


def test_format_report_marks_pass_and_fail():
    issues = [Issue("a", True, ""), Issue("b", False, "do this")]
    report = format_report(issues)
    assert "do this" in report
    assert "b" in report

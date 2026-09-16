from easytype.preflight import Issue, binaries_for, detect_session, gather_issues, format_report


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


def test_binaries_for_x11():
    assert binaries_for("x11") == ("xdotool", "xclip", "notify-send")


def test_binaries_for_wayland():
    assert binaries_for("wayland") == ("ydotool", "wl-copy", "wl-paste", "notify-send")


def test_binaries_for_unknown_session_falls_back_to_x11():
    assert binaries_for("unknown") == binaries_for("x11")


def test_wayland_issues_include_ydotoold_check():
    issues = gather_issues(
        groups=["input"], uinput_writable=True,
        binaries={"ydotool": True, "wl-copy": True, "wl-paste": True, "notify-send": True},
        tk_ok=True, session="wayland", ydotoold_running=False,
    )
    d = next(i for i in issues if i.name == "ydotoold running")
    assert not d.ok
    assert "systemctl --user enable --now ydotool" in d.fix


def test_x11_issues_have_no_ydotoold_check():
    issues = gather_issues(
        groups=["input"], uinput_writable=True,
        binaries={"xdotool": True, "xclip": True, "notify-send": True}, tk_ok=True,
    )
    assert not any(i.name == "ydotoold running" for i in issues)


def test_wayland_binary_fix_uses_correct_apt_packages():
    issues = gather_issues(
        groups=["input"], uinput_writable=True,
        binaries={"ydotool": False, "wl-copy": False, "wl-paste": False, "notify-send": False},
        tk_ok=True, session="wayland", ydotoold_running=True,
    )
    wl_copy = next(i for i in issues if i.name == "wl-copy")
    assert "wl-clipboard" in wl_copy.fix
    notify = next(i for i in issues if i.name == "notify-send")
    assert "libnotify-bin" in notify.fix


def test_format_report_marks_pass_and_fail():
    issues = [Issue("a", True, ""), Issue("b", False, "do this")]
    report = format_report(issues)
    assert "do this" in report
    assert "b" in report

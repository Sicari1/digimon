# -*- coding: utf-8 -*-
"""부화/진화/암흑진화/졸업 알림. 터미널 벨 + (WSL) Windows 토스트 best-effort.

- Windows 토스트: powershell.exe + 네이티브 WinRT(ToastNotificationManager). BurntToast 불필요.
  파이어앤포겟(Popen, 대기 안 함)이라 실패해도 게임 흐름을 막지 않는다.
- 터미널 벨(\\a)은 stderr 로 — 상태줄(stdout) 출력을 오염시키지 않는다.
"""
import sys, subprocess, shutil

NOTABLE = {"hatch", "evolve", "dark", "graduate", "candy_grant"}


def _summary(events):
    """가장 중요한 이벤트 하나로 (제목, 본문)."""
    order = {"candy_grant": 4, "graduate": 3, "dark": 2, "evolve": 1, "hatch": 0}
    ev = sorted((e for e in events if e.get("kind") in NOTABLE),
                key=lambda e: order.get(e["kind"], -1), reverse=True)
    if not ev:
        return None
    e = ev[0]
    k = e["kind"]
    name = e.get("name", "?")
    sh = "✨이로치 " if e.get("shiny") else ""
    if k == "hatch":
        return "DigiTokenBar — 부화!", f"🥚→🐣 {sh}{name} ({e.get('stage','')})"
    if k == "evolve":
        return "DigiTokenBar — 진화!", f"⚡ {name} ({e.get('stage','')})"
    if k == "dark":
        return "DigiTokenBar — 암흑진화!", f"🌑 {name} — 어둠에 물들었다"
    if k == "graduate":
        return "DigiTokenBar — 졸업!", f"🎓 {sh}{name} 도감 등록"
    if k == "candy_grant":
        return "DigiTokenBar — 한도 보상!", f"🍬 한도 100% 달성! 이상한 사탕 {e.get('count',1)}개 획득"
    return None


def _windows_toast(title, body):
    exe = shutil.which("powershell.exe")
    if not exe:
        return
    t = title.replace("'", "’")
    b = body.replace("'", "’")
    ps = (
        "$ErrorActionPreference='SilentlyContinue';"
        "[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]>$null;"
        "$x=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
        "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
        "$e=$x.GetElementsByTagName('text');"
        f"$e.Item(0).AppendChild($x.CreateTextNode('{t}'))>$null;"
        f"$e.Item(1).AppendChild($x.CreateTextNode('{b}'))>$null;"
        "$n=[Windows.UI.Notifications.ToastNotification]::new($x);"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('DigiTokenBar').Show($n);"
    )
    try:
        subprocess.Popen([exe, "-NoProfile", "-NonInteractive", "-Command", ps],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL)
    except Exception:
        pass


def notify(events):
    """이벤트가 있으면 벨 + 토스트. 없으면 무동작."""
    s = _summary(events or [])
    if not s:
        return
    title, body = s
    try:
        sys.stderr.write("\a")
        sys.stderr.flush()
    except Exception:
        pass
    _windows_toast(title, body)

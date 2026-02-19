from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
from pathlib import Path

MAPI_LOGON_UI = 0x00000001
MAPI_DIALOG = 0x00000008
MAPI_TO = 1
SUCCESS_SUCCESS = 0
MAPI_E_USER_ABORT = 1
MAPI_ERROR_NAMES = {
    2: "MAPI_E_FAILURE",
    3: "MAPI_E_LOGIN_FAILURE",
    4: "MAPI_E_DISK_FULL",
    5: "MAPI_E_INSUFFICIENT_MEMORY",
    6: "MAPI_E_ACCESS_DENIED",
    8: "MAPI_E_TOO_MANY_SESSIONS",
    9: "MAPI_E_TOO_MANY_FILES",
    10: "MAPI_E_TOO_MANY_RECIPIENTS",
    11: "MAPI_E_ATTACHMENT_NOT_FOUND",
    12: "MAPI_E_ATTACHMENT_OPEN_FAILURE",
    13: "MAPI_E_ATTACHMENT_WRITE_FAILURE",
    14: "MAPI_E_UNKNOWN_RECIPIENT",
    15: "MAPI_E_BAD_RECIPTYPE",
    16: "MAPI_E_NO_MESSAGES",
    17: "MAPI_E_INVALID_MESSAGE",
    18: "MAPI_E_TEXT_TOO_LARGE",
    19: "MAPI_E_INVALID_SESSION",
    20: "MAPI_E_TYPE_NOT_SUPPORTED",
    21: "MAPI_E_AMBIGUOUS_RECIPIENT",
    22: "MAPI_E_MESSAGE_IN_USE",
    23: "MAPI_E_NETWORK_FAILURE",
    24: "MAPI_E_INVALID_EDITFIELDS",
    25: "MAPI_E_INVALID_RECIPS",
    26: "MAPI_E_NOT_SUPPORTED",
}


class _MapiRecipDesc(ctypes.Structure):
    _fields_ = [
        ("ulReserved", ctypes.c_ulong),
        ("ulRecipClass", ctypes.c_ulong),
        ("lpszName", ctypes.c_char_p),
        ("lpszAddress", ctypes.c_char_p),
        ("ulEIDSize", ctypes.c_ulong),
        ("lpEntryID", ctypes.c_void_p),
    ]


class _MapiFileDesc(ctypes.Structure):
    _fields_ = [
        ("ulReserved", ctypes.c_ulong),
        ("flFlags", ctypes.c_ulong),
        ("nPosition", ctypes.c_ulong),
        ("lpszPathName", ctypes.c_char_p),
        ("lpszFileName", ctypes.c_char_p),
        ("lpFileType", ctypes.c_void_p),
    ]


class _MapiMessage(ctypes.Structure):
    _fields_ = [
        ("ulReserved", ctypes.c_ulong),
        ("lpszSubject", ctypes.c_char_p),
        ("lpszNoteText", ctypes.c_char_p),
        ("lpszMessageType", ctypes.c_char_p),
        ("lpszDateReceived", ctypes.c_char_p),
        ("lpszConversationID", ctypes.c_char_p),
        ("flFlags", ctypes.c_ulong),
        ("lpOriginator", ctypes.c_void_p),
        ("nRecipCount", ctypes.c_ulong),
        ("lpRecips", ctypes.POINTER(_MapiRecipDesc)),
        ("nFileCount", ctypes.c_ulong),
        ("lpFiles", ctypes.POINTER(_MapiFileDesc)),
    ]


def _to_mapi_bytes(value: str) -> bytes:
    return value.encode("mbcs", errors="replace")


def _send_via_simple_mapi(recipient: str, subject: str, attachment_path: Path) -> tuple[str, str]:
    try:
        mapi32 = ctypes.windll.LoadLibrary("MAPI32.DLL")
        send_mail = mapi32.MAPISendMail
    except (OSError, AttributeError) as exc:
        return "not_available", f"Simple MAPI niedostepne: {exc}"

    send_mail.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(_MapiMessage),
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]
    send_mail.restype = ctypes.c_ulong

    recipient_name = _to_mapi_bytes(recipient)
    recipient_address = _to_mapi_bytes(f"SMTP:{recipient}")
    subject_bytes = _to_mapi_bytes(subject)
    path_bytes = _to_mapi_bytes(str(attachment_path))
    filename_bytes = _to_mapi_bytes(attachment_path.name)

    recipient_desc = _MapiRecipDesc()
    recipient_desc.ulRecipClass = MAPI_TO
    recipient_desc.lpszName = recipient_name
    recipient_desc.lpszAddress = recipient_address

    file_desc = _MapiFileDesc()
    file_desc.nPosition = 0xFFFFFFFF
    file_desc.lpszPathName = path_bytes
    file_desc.lpszFileName = filename_bytes

    message = _MapiMessage()
    message.lpszSubject = subject_bytes
    message.nRecipCount = 1
    message.lpRecips = ctypes.pointer(recipient_desc)
    message.nFileCount = 1
    message.lpFiles = ctypes.pointer(file_desc)

    result = send_mail(
        None,
        None,
        ctypes.byref(message),
        MAPI_LOGON_UI | MAPI_DIALOG,
        0,
    )
    if result == SUCCESS_SUCCESS:
        return "success", "Otwarto domyslnego klienta poczty (Simple MAPI)."
    if result == MAPI_E_USER_ABORT:
        return "cancelled", "Wysylanie email anulowane przez uzytkownika."

    error_name = MAPI_ERROR_NAMES.get(int(result), "UNKNOWN_ERROR")
    return "error", f"Simple MAPI zwrocilo kod bledu {result} ({error_name})."


def _ps_single_quote(value: str) -> str:
    return value.replace("'", "''")


def _open_outlook_draft_with_attachment(
    recipient: str,
    subject: str,
    attachment_path: Path,
) -> tuple[bool, str]:
    script = "".join(
        [
            "$ErrorActionPreference='Stop';",
            "$outlook=New-Object -ComObject Outlook.Application;",
            "$mail=$outlook.CreateItem(0);",
            f"$mail.To='{_ps_single_quote(recipient)}';",
            f"$mail.Subject='{_ps_single_quote(subject)}';",
            f"$mail.Attachments.Add('{_ps_single_quote(str(attachment_path))}');",
            "$null=$mail.Display();",
        ]
    )
    command = [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        script,
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except OSError as exc:
        return False, f"Nie mozna uruchomic Outlook COM fallback: {exc}"

    if result.returncode == 0:
        return True, "Otwarto szkic wiadomosci przez Outlook COM (z zalacznikiem)."

    details = (result.stderr or result.stdout or "").strip()
    if details:
        return False, f"Outlook COM fallback nie powiodl sie: {details}"
    return False, "Outlook COM fallback nie powiodl sie."


def _find_outlook_executable() -> str | None:
    for command_name in ("outlook.exe", "outlook"):
        path = shutil.which(command_name)
        if path:
            return path

    common_paths = [
        Path(os.environ.get("ProgramFiles", "")) / "Microsoft Office" / "root" / "Office16" / "OUTLOOK.EXE",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft Office" / "root" / "Office16" / "OUTLOOK.EXE",
    ]
    for candidate in common_paths:
        if candidate.is_file():
            return str(candidate)
    return None


def _find_thunderbird_executable() -> str | None:
    for command_name in ("thunderbird.exe", "thunderbird"):
        path = shutil.which(command_name)
        if path:
            return path

    common_paths = [
        Path(os.environ.get("ProgramFiles", "")) / "Mozilla Thunderbird" / "thunderbird.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Mozilla Thunderbird" / "thunderbird.exe",
    ]
    for candidate in common_paths:
        if candidate.is_file():
            return str(candidate)
    return None


def _escape_thunderbird_compose(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _open_outlook_cli_with_attachment(
    recipient: str,
    subject: str,
    attachment_path: Path,
) -> tuple[bool, str]:
    outlook_exe = _find_outlook_executable()
    if not outlook_exe:
        return False, "Outlook CLI fallback niedostepny (nie znaleziono outlook.exe)."

    mail_target = recipient
    cleaned_subject = subject.strip()
    if cleaned_subject:
        mail_target = f"{recipient}&subject={cleaned_subject}"

    command = [
        outlook_exe,
        "/c",
        "ipm.note",
        "/m",
        mail_target,
        "/a",
        str(attachment_path),
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except OSError as exc:
        return False, f"Nie mozna uruchomic Outlook CLI fallback: {exc}"

    if result.returncode == 0:
        return True, "Otwarto szkic wiadomosci przez Outlook CLI (z zalacznikiem)."

    details = (result.stderr or result.stdout or "").strip()
    if details:
        return False, f"Outlook CLI fallback nie powiodl sie: {details}"
    return False, "Outlook CLI fallback nie powiodl sie."


def _send_via_thunderbird(
    recipient: str,
    subject: str,
    attachment_path: Path,
) -> tuple[bool, str]:
    thunderbird_exe = _find_thunderbird_executable()
    if not thunderbird_exe:
        return False, "Nie znaleziono Mozilla Thunderbird."

    attachment_uri = attachment_path.as_uri()
    compose_fields = [
        f"to='{_escape_thunderbird_compose(recipient)}'",
        f"subject='{_escape_thunderbird_compose(subject)}'",
        f"attachment='{_escape_thunderbird_compose(attachment_uri)}'",
    ]
    command = [
        thunderbird_exe,
        "-compose",
        ",".join(compose_fields),
    ]

    try:
        subprocess.Popen(command)
    except OSError as exc:
        return False, f"Nie mozna uruchomic Thunderbird: {exc}"
    return True, "Otwarto szkic wiadomosci przez Mozilla Thunderbird (z zalacznikiem)."


def _send_via_outlook(
    recipient: str,
    subject: str,
    attachment_path: Path,
) -> tuple[bool, str]:
    com_ok, com_info = _open_outlook_draft_with_attachment(
        recipient,
        subject,
        attachment_path,
    )
    if com_ok:
        return True, com_info

    cli_ok, cli_info = _open_outlook_cli_with_attachment(
        recipient,
        subject,
        attachment_path,
    )
    if cli_ok:
        return True, f"{com_info} Uzyto fallbacku Outlook CLI."

    return False, f"{com_info} {cli_info}"


def get_available_email_clients() -> list[tuple[str, str]]:
    options: list[tuple[str, str]] = [("Automatycznie (zalecane)", "auto")]

    if os.name != "nt":
        return options

    options.append(("Microsoft Outlook", "outlook"))

    if _find_thunderbird_executable() is not None:
        options.append(("Mozilla Thunderbird", "thunderbird"))

    options.append(("Domyslny klient Windows (MAPI)", "simple_mapi"))
    return options


def open_email_client(
    recipient: str,
    subject: str,
    transcription_path: str | Path,
    client: str = "auto",
) -> tuple[bool, str]:
    attachment_path = Path(transcription_path).expanduser().resolve()
    if not attachment_path.is_file():
        return False, f"Plik transkrypcji nie istnieje: {attachment_path}"

    selected_client = (client or "auto").strip().lower()
    if os.name != "nt":
        return (
            False,
            "Automatyczne dodanie zalacznika jest dostepne tylko na Windows.",
        )

    if selected_client == "simple_mapi":
        status, info = _send_via_simple_mapi(recipient, subject, attachment_path)
        if status == "success":
            return True, info
        return False, info

    if selected_client == "outlook":
        return _send_via_outlook(recipient, subject, attachment_path)

    if selected_client == "thunderbird":
        return _send_via_thunderbird(recipient, subject, attachment_path)

    if selected_client != "auto":
        return False, f"Nieznana opcja klienta email: {client!r}"

    thunderbird_ok, thunderbird_info = _send_via_thunderbird(
        recipient,
        subject,
        attachment_path,
    )
    if thunderbird_ok:
        return True, thunderbird_info

    status, info = _send_via_simple_mapi(recipient, subject, attachment_path)
    if status == "success":
        return True, info
    if status == "cancelled":
        return False, info

    outlook_ok, outlook_info = _send_via_outlook(recipient, subject, attachment_path)
    if outlook_ok:
        return True, f"{thunderbird_info} {info} {outlook_info}"

    return False, f"{thunderbird_info} {info} {outlook_info}"

"""เปิดเคสคู่ขนานในระบบแจ้งซ่อม itamtv (ASP.NET WebForms) + ดึงข้อมูลจาก Employee DB.

ทำงาน "เสริม" กับ ticket ใน dashboard — ล้มเหลวตรงไหนก็แค่ log + บันทึก comment
ห้ามทำให้ flow LINE พัง.

itamtv เก็บ state ฝั่ง server ผ่าน session — submit ตรงๆ ครั้งเดียวจะติด validation
("กรุณาระบุ ลักษณะงาน อาคาร และสถานที่") ต้องเลียนแบบผู้ใช้กรอกจริง 4 ขั้น
ด้วย cookie เดียวกัน + ส่งต่อ __VIEWSTATE จาก response ก่อนหน้า:
GET → postback เลือกผู้แจ้ง (ddlforemp) → postback เลือกประเภท (ddltype) → กด BtnSave
"""
import html
import logging
import re
import uuid

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.line_user import LineUser
from app.models.ticket import Ticket
from app.models.ticket_comment import TicketComment

logger = logging.getLogger(__name__)

# ticket.category → ddltype ของ itamtv
_TYPE_MAP = {"hardware": "2", "network": "3", "software": "1"}
# ddltype → label ของ subtype "อื่นๆ" ประจำประเภท (ใช้เมื่อไม่รู้ subtype เจาะจง)
_OTHER_SUBTYPE_LABEL = {"2": "อื่นๆ (Hardware)", "3": "อื่นๆ (Network)", "1": "อื่นๆ (Software)"}

_HIDDEN_FIELDS = ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION")


# ---------------------------------------------------------------------------
# Employee DB (Amarin Employee Database)
# ---------------------------------------------------------------------------

async def lookup_employee(full_name: str) -> dict | None:
    """หา record พนักงานจากชื่อ — คืน dict (มี emp_code/department/phone/id) หรือ None."""
    base = get_settings().EMPLOYEE_DB_URL
    if not base or not (full_name or "").strip():
        return None
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{base}/api/employees", params={"q": full_name.strip()})
        resp.raise_for_status()
        employees = resp.json().get("employees", [])
    return employees[0] if len(employees) == 1 else None


async def fetch_assets(employee_id: int) -> list[dict]:
    base = get_settings().EMPLOYEE_DB_URL
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{base}/api/employees/{employee_id}/assets")
        resp.raise_for_status()
        data = resp.json()
    return data if isinstance(data, list) else []


def asset_summary(assets: list[dict]) -> str:
    """สรุปเครื่องที่ผู้แจ้งถือครองเป็นข้อความให้ช่างเตรียมตัว."""
    lines = []
    for a in assets:
        parts = [a.get("asset_type") or "อุปกรณ์"]
        brand_model = " ".join(p for p in (a.get("brand"), a.get("model")) if p)
        if brand_model:
            parts.append(brand_model)
        if a.get("asset_no"):
            parts.append(f"asset: {a['asset_no']}")
        if a.get("serial_no"):
            parts.append(f"S/N: {a['serial_no']}")
        if a.get("is_rental"):
            parts.append("(เช่า)")
        lines.append("- " + " | ".join(parts))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# itamtv WebForms client
# ---------------------------------------------------------------------------

def _hidden(page: str) -> dict:
    out = {}
    for name in _HIDDEN_FIELDS:
        m = re.search(r'name="%s"[^>]*value="([^"]*)"' % name, page)
        out[name] = m.group(1) if m else ""
    return out


def _options(page: str, ddl: str) -> list[tuple[str, str]]:
    """คืน [(value, label), ...] ของ dropdown — label ถูก unescape แล้ว."""
    m = re.search(r'name="ctl00\$ContentPlaceHolder1\$%s"[^>]*>(.*?)</select>' % ddl, page, re.S)
    if not m:
        return []
    return [
        (html.unescape(v), html.unescape(t).strip())
        for v, t in re.findall(r'<option[^>]*value="([^"]*)"[^>]*>([^<]*)</option>', m.group(1))
    ]


def _pick_employee(page: str, emp_code: str | None, full_name: str) -> str | None:
    opts = _options(page, "ddlforemp")
    if emp_code and any(v == emp_code for v, _ in opts):
        return emp_code
    name = re.sub(r"\s+", " ", (full_name or "").strip())
    for v, t in opts:
        if re.sub(r"\s+", " ", t) == name:
            return v
    return None


def _pick_section(page: str, department: str | None) -> str | None:
    opts = _options(page, "ddlforsec")
    if department:
        want = re.sub(r"\s+", " ", department.strip()).lower()
        for v, t in opts:
            if re.sub(r"\s+", " ", t).lower() == want:
                return v
    return opts[0][0] if opts else None


def _pick_subtype(page: str, ddltype: str) -> str | None:
    opts = _options(page, "ddlsubtype")
    label = _OTHER_SUBTYPE_LABEL.get(ddltype)
    for v, t in opts:
        if label and t == label:
            return v
    for v, t in opts:
        if t == "อื่นๆ":
            return v
    return opts[0][0] if opts else None


def _multipart(fields: dict) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    body = b""
    for k, v in fields.items():
        body += (
            "--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
            % (boundary, k, v)
        ).encode()
    body += (
        "--%s\r\nContent-Disposition: form-data; "
        "name=\"ctl00$ContentPlaceHolder1$upload\"; filename=\"\"\r\n"
        "Content-Type: application/octet-stream\r\n\r\n\r\n" % boundary
    ).encode()
    body += ("--%s--\r\n" % boundary).encode()
    return body, "multipart/form-data; boundary=" + boundary


async def _submit_case(
    *, emp_code: str | None, full_name: str, department: str | None,
    category: str | None, location: str, note: str, phone: str = "",
) -> str:
    """เดิน 4 ขั้นเปิดเคสใน itamtv — คืนข้อความผลลัพธ์ (raise เมื่อพลาด)."""
    url = get_settings().ITAMTV_ADDJOB_URL
    if not url:
        raise RuntimeError("ITAMTV_ADDJOB_URL not configured")

    async with httpx.AsyncClient(timeout=30) as client:  # cookie jar เดียวทั้ง flow
        page = (await client.get(url)).text

        emp_value = _pick_employee(page, emp_code, full_name)
        if not emp_value:
            raise RuntimeError(f"ไม่พบผู้แจ้ง '{full_name}' ใน dropdown itamtv")
        ddltype = _TYPE_MAP.get(category or "", "4")
        base = {
            "ctl00_ToolkitScriptManager1_HiddenField": "",
            "__EVENTTARGET": "", "__EVENTARGUMENT": "",
            "ctl00$ContentPlaceHolder1$TxtTel": (phone or "-")[:20],
            "ctl00$ContentPlaceHolder1$TxtTel2": "",
            "ctl00$ContentPlaceHolder1$txtdate":
                re.search(r'name="[^"]*txtdate"[^>]*value="([^"]*)"', page).group(1),
            "ctl00$ContentPlaceHolder1$ddlforemp": emp_value,
            "ctl00$ContentPlaceHolder1$ddlforsec": _pick_section(page, department) or "",
            "ctl00$ContentPlaceHolder1$ddltype": ddltype,
            "ctl00$ContentPlaceHolder1$ddlsubtype": _pick_subtype(page, ddltype) or "",
            "ctl00$ContentPlaceHolder1$Txtobj": location[:250],
            "ctl00$ContentPlaceHolder1$Txtnote": note[:2000],
        }

        async def post(prev_page: str, extra: dict) -> str:
            fields = dict(base)
            fields.update(_hidden(prev_page))
            fields.update(extra)
            body, ctype = _multipart(fields)
            resp = await client.post(
                url, content=body, headers={"Content-Type": ctype, "Referer": url}
            )
            resp.raise_for_status()
            return resp.text

        page = await post(page, {"__EVENTTARGET": "ctl00$ContentPlaceHolder1$ddlforemp"})
        page = await post(page, {"__EVENTTARGET": "ctl00$ContentPlaceHolder1$ddltype"})
        page = await post(page, {"ctl00$ContentPlaceHolder1$BtnSave": "บันทึกข้อมูล"})

    alerts = re.findall(r"alert\('([^']*)'\)", page)
    if not any("เรียบร้อย" in a for a in alerts):
        raise RuntimeError(f"itamtv ไม่ยืนยันการบันทึก: {alerts or 'no alert'}")
    return alerts[0]


def _base_url() -> tuple[str, str]:
    """(โคน URL, token query) — ตัดชื่อไฟล์ AddJob.aspx ออกจาก ITAMTV_ADDJOB_URL."""
    url = get_settings().ITAMTV_ADDJOB_URL
    m = re.match(r"(.*/)[^/?]+\?(.*)$", url)
    return (m.group(1), m.group(2)) if m else (url, "")


async def find_job_no(ticket_no: str) -> str | None:
    """หาเลขเคส itamtv จากหน้ารายการงานค้าง โดยดูจาก marker [TK-...] ที่เราใส่ไว้ใน note."""
    root, token = _base_url()
    async with httpx.AsyncClient(timeout=15) as client:
        page = (await client.get(f"{root}fixremind.aspx?{token}")).text
    # แถวในตารางเรียง: <a ...>JOBNO</a> ... [TK-xxx] — หา job no ตัวที่อยู่ก่อน marker ของเรา
    best = None
    for m in re.finditer(r">\s*<b>([A-Z]{2}\d+)</b>", page):
        best_candidate = m.group(1)
        tail = page[m.end(): m.end() + 3000]
        if f"[{ticket_no}]" in tail:
            best = best_candidate
            break
    return best


async def cancel_case(job_no: str) -> str:
    """ยกเลิกเคสใน itamtv (BtnCancel — สิทธิ์ระดับผู้แจ้งทำได้แค่ 'ยกเลิกงาน').

    หมายเหตุ: การปิดแบบ 'ดำเนินการเรียบร้อย' เป็นสิทธิ์ฝั่งช่าง ต้องได้ URL/สิทธิ์
    ระบบฝั่งช่างมาก่อนถึงจะทำได้.
    """
    root, token = _base_url()
    url = f"{root}Addjob.aspx?{token}&mode=display&Id={job_no}"
    async with httpx.AsyncClient(timeout=30) as client:
        page = (await client.get(url)).text
        fields = {
            "ctl00_ToolkitScriptManager1_HiddenField": "",
            "__EVENTTARGET": "", "__EVENTARGUMENT": "",
            **_hidden(page),
            "ctl00$ContentPlaceHolder1$BtnCancel": "ยกเลิกงาน",
        }
        body, ctype = _multipart_no_upload(fields)
        resp = await client.post(url, content=body, headers={"Content-Type": ctype, "Referer": url})
        resp.raise_for_status()
    alerts = re.findall(r"alert\('([^']*)'\)", resp.text)
    if not any("เรียบร้อย" in a for a in alerts):
        raise RuntimeError(f"itamtv ไม่ยืนยันการยกเลิก {job_no}: {alerts or 'no alert'}")
    return alerts[0]


# ddlstatus ในหน้าช่าง: 0=รอจัดคิว, 1=กำลังดำเนินการ, 6=ดำเนินการเรียบร้อย
_STATUS_DONE = "6"
# ปุ่ม/ฟิลด์ที่ไม่ส่งกลับตอน save (image button, ปุ่มอื่น)
_SKIP_CONTROLS = {"ImgBtnDate", "BtnReset", "BtnCancel"}


def _form_controls_in_order(page: str) -> list[tuple[str, str, str]]:
    """ไล่ control ในฟอร์มตามลำดับ DOM → [(name, kind, value), ...].

    kind = text | select | textarea | file | checkbox | hidden.
    ต้องรักษา "ลำดับ" ให้ตรงหน้าเป๊ะ — itamtv ฝั่งช่างอ่าน field/ไฟล์แบบอิง index
    ส่งสลับลำดับ/ไฟล์ผิดตำแหน่ง server จะ error "Index was outside the bounds of the array".
    """
    controls: list[tuple[str, str, str]] = []
    pattern = re.compile(
        r'<input\b[^>]*?name="([^"]+)"[^>]*?>'
        r'|<select\b[^>]*?name="([^"]+)"[^>]*?>(.*?)</select>'
        r'|<textarea\b[^>]*?name="([^"]+)"[^>]*?>(.*?)</textarea>',
        re.S,
    )
    for m in pattern.finditer(page):
        if m.group(1) is not None:  # input
            tag = m.group(0)
            name = m.group(1)
            typ = (re.search(r'type="([^"]+)"', tag) or ["", "text"])[1]
            val = html.unescape((re.search(r'value="([^"]*)"', tag) or ["", ""])[1])
            controls.append((name, "file" if typ == "file" else typ, val))
        elif m.group(2) is not None:  # select
            sel = re.search(r'<option[^>]*selected[^>]*value="([^"]*)"', m.group(3))
            controls.append((m.group(2), "select", html.unescape(sel.group(1)) if sel else ""))
        else:  # textarea
            controls.append((m.group(4), "textarea", html.unescape(m.group(5))))
    return controls


def _current_status(page: str) -> str:
    m = re.search(
        r'ddlstatus"[^>]*>.*?<option[^>]*selected[^>]*value="([^"]*)"', page, re.S
    )
    return m.group(1) if m else ""


async def _save_status(client: httpx.AsyncClient, url: str, page: str, *,
                       status: str, people_code: str | None, note: str | None) -> str:
    """POST หน้า display หนึ่งครั้ง โดย override ddlstatus/ddlpeople/Txtnote2.

    ต้องส่ง field ตามลำดับ DOM เป๊ะ (server อ่านแบบอิง index) — คืน alert ที่ได้.
    """
    P = "ctl00$ContentPlaceHolder1$"
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    for name, kind, value in _form_controls_in_order(page):
        short = name.replace(P, "")
        if short in _SKIP_CONTROLS or kind == "checkbox":  # คง BtnSave, ตัด Reset/Cancel
            continue
        if short == "ddlstatus":
            value = status
        elif short == "ddlpeople" and people_code:
            value = people_code
        elif short == "Txtnote2" and note:
            value = note
        if kind == "file":
            parts.append(
                ('--%s\r\nContent-Disposition: form-data; name="%s"; filename=""\r\n'
                 'Content-Type: application/octet-stream\r\n\r\n\r\n' % (boundary, name)).encode()
            )
        else:
            parts.append(
                ('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n'
                 % (boundary, name, value)).encode()
            )
    parts.append(("--%s--\r\n" % boundary).encode())
    resp = await client.post(
        url, content=b"".join(parts),
        headers={"Content-Type": "multipart/form-data; boundary=" + boundary, "Referer": url},
    )
    resp.raise_for_status()
    alerts = re.findall(r"alert\('([^']*)'\)", resp.text)
    if not any("เรียบร้อย" in a for a in alerts):
        raise RuntimeError(f"itamtv save ล้มเหลว (status={status}): {alerts or 'no alert'}")
    return alerts[0]


async def complete_case(job_no: str, token: str, people_code: str | None = None,
                        note: str | None = None) -> str:
    """ปิดเคส = เซ็ต ddlstatus='ดำเนินการเรียบร้อย' (6) ในระบบ itamtv โดยใช้ token ช่าง.

    เคสสด (สถานะ 'รอจัดคิว'=0, ยังไม่มีผู้รับผิดชอบ) กระโดดเป็น 6 ตรงๆ ไม่ได้ (server
    error "index out of bounds") — ต้องผ่าน 'กำลังดำเนินการ'=1 + ระบุผู้รับผิดชอบก่อน
    แล้วค่อยเป็น 6. ฟังก์ชันนี้จัดการ 2 สเต็ปให้อัตโนมัติ.

    token: token ส่วนตัวของช่าง (ปลดล็อก ddlstatus/ddlpeople).
    people_code: emp code ของช่างผู้รับผิดชอบ (ddlpeople) — จำเป็นตอนเคสยังไม่ถูก assign.
    note: บันทึกการซ่อม (Txtnote2).
    """
    if not token:
        raise RuntimeError("ยังไม่มี itamtv token ของช่าง — ปิดเคสในระบบ itamtv อัตโนมัติไม่ได้")
    root, _ = _base_url()
    url = f"{root}Addjob.aspx?{token}&mode=display&Id={job_no}"
    async with httpx.AsyncClient(timeout=30) as client:
        page = (await client.get(url)).text
        if "ddlstatus" not in page.lower():
            raise RuntimeError("token นี้ไม่ใช่สิทธิ์ช่าง (ไม่มีช่องสถานะ) — ปิดเคสไม่ได้")
        if _current_status(page) == _STATUS_DONE:
            return "เคสนี้ปิด (ดำเนินการเรียบร้อย) อยู่แล้ว"
        # สเต็ป 1: ยังไม่ 'กำลังดำเนินการ' → assign + set 1 ก่อน (กัน error กระโดดสถานะ)
        if _current_status(page) != "1":
            await _save_status(client, url, page, status="1",
                               people_code=people_code, note=note)
            page = (await client.get(url)).text
        # สเต็ป 2: ปิดเป็น 'ดำเนินการเรียบร้อย'
        return await _save_status(client, url, page, status=_STATUS_DONE,
                                  people_code=people_code, note=note)


def _multipart_no_upload(fields: dict) -> tuple[bytes, str]:
    """multipart แบบไม่มี part ไฟล์ upload — หน้า display โพสต์ field เยอะเกินจะ 500."""
    boundary = uuid.uuid4().hex
    body = b""
    for k, v in fields.items():
        body += (
            "--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
            % (boundary, k, v)
        ).encode()
    body += ("--%s--\r\n" % boundary).encode()
    return body, "multipart/form-data; boundary=" + boundary


# ---------------------------------------------------------------------------
# entry point — เรียกหลังเปิด ticket ใน dashboard แล้ว
# ---------------------------------------------------------------------------

def _add_note(db: Session, ticket: Ticket, content: str) -> None:
    db.add(TicketComment(ticket_id=ticket.id, content=content, is_internal=True))
    db.commit()


async def mirror_ticket(db: Session, ticket: Ticket, lu: LineUser | None) -> None:
    """เปิดเคสคู่ขนานใน itamtv + แนบข้อมูลเครื่องผู้แจ้งเป็น internal comment.

    best-effort ทั้งฟังก์ชัน — error ใดๆ log + บันทึกไว้ใน comment แล้วจบ.
    """
    if not get_settings().ITAMTV_ENABLED:
        return
    full_name = (lu.display_name if lu else "") or ""

    emp = None
    try:
        emp = await lookup_employee(full_name)
    except Exception:  # noqa: BLE001
        logger.exception("employee lookup failed for %s", full_name)

    # ข้อมูลเครื่องที่ถือครอง → internal comment ให้ช่างเตรียมตัว
    if emp:
        try:
            assets = await fetch_assets(emp["id"])
            if assets:
                _add_note(
                    db, ticket,
                    "💻 เครื่องที่ผู้แจ้งถือครอง (จาก Employee DB):\n" + asset_summary(assets),
                )
        except Exception:  # noqa: BLE001
            logger.exception("fetch assets failed for %s", full_name)

    location = " ".join(
        p for p in ((lu.building if lu else None), (f"ชั้น {lu.floor}" if lu and lu.floor else None))
        if p
    ) or "-"
    note = f"[{ticket.ticket_no}] {ticket.title}\n{ticket.description or ''}"
    try:
        msg = await _submit_case(
            emp_code=(emp or {}).get("emp_code"),
            full_name=full_name,
            department=(emp or {}).get("department") or (lu.department if lu else None),
            category=ticket.category,
            location=location,
            note=note,
            phone=(emp or {}).get("phone") or "",
        )
        job_no = None
        try:
            job_no = await find_job_no(ticket.ticket_no)
        except Exception:  # noqa: BLE001
            logger.exception("find itamtv job no failed for %s", ticket.ticket_no)
        if job_no:
            ticket.itamtv_job_no = job_no  # เก็บไว้ใช้สั่งปิดเคสทีหลัง
            db.commit()
        tag = f" — เลขเคส {job_no}" if job_no else ""
        _add_note(db, ticket, f"🔁 เปิดเคสคู่ขนานใน itamtv แล้ว ({msg}){tag}")
    except Exception as exc:  # noqa: BLE001
        logger.exception("itamtv mirror failed for %s", ticket.ticket_no)
        _add_note(db, ticket, f"⚠️ เปิดเคสใน itamtv ไม่สำเร็จ: {exc} — รบกวนเปิดในระบบเองด้วยครับ")

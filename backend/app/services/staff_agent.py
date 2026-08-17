"""ผู้ช่วยสำหรับ IT staff — registry ของ "เครื่องมือ" ที่ผู้ช่วยเรียกได้.

เครื่องมือหนึ่งตัวอยู่ที่เดียวครบ 4 อย่าง (เดิมกระจายอยู่ 3 ไฟล์/3 จุด):
  schema  — JSON Schema ที่ส่งให้โมเดล (Ollama บังคับรูปแบบ args ให้)
  run     — ตัวรันจริง คืน dict (จะถูก dump เป็น JSON ป้อนกลับให้โมเดล)
  render  — จัดรูปผลลัพธ์เป็นข้อความตอบ staff แบบ deterministic (None = ให้โมเดลคุยต่อ)
  choices — ปุ่ม quick reply ท้ายผลลัพธ์ (ถ้ามี)

render สำคัญกว่าที่คิด: โมเดลเชื่อไม่ได้เวลาต้องอ่านผล tool มาเรียบเรียง (เคยได้พนักงาน 5 คน
แต่ตอบว่า "ไม่พบ") — งานของโมเดลคือ "เลือก tool + args" เท่านั้น ส่วนการรายงานข้อเท็จจริง
ให้โค้ดทำ จึงมั่วไม่ได้ 100%
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.line_user import LineUser
from app.models.ticket import Ticket
from app.models.ticket_comment import TicketComment
from app.models.user import User
from app.services import itamtv_service, line_service, ticket_service

logger = logging.getLogger(__name__)

_STR = {"type": "string"}
VALID_CATEGORIES = ("hardware", "software", "network", "account",
                    "service_request", "equipment_request", "other")
VALID_PRIORITIES = ("low", "medium", "high", "critical")
# คำที่โมเดลใช้แทน "คนที่กำลังคุยอยู่" เวลา staff บอกว่า "ผมดูแลเอง"
_SELF_WORDS = {"me", "myself", "self", "ผม", "ฉัน", "ตัวเอง", "ตัวผมเอง"}


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


@dataclass
class Ctx:
    """บริบทของการเรียกเครื่องมือหนึ่งครั้ง — ใครสั่ง บน DB session ไหน."""
    db: Session
    staff: User


@dataclass
class StaffTool:
    name: str
    description: str
    run: Callable[[Ctx, dict], Awaitable[dict]]
    properties: dict = field(default_factory=dict)
    required: list[str] = field(default_factory=list)
    render: Callable[[dict, dict], str | None] | None = None
    choices: Callable[[dict], dict | None] | None = None

    def schema(self) -> dict:
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": {"type": "object", "properties": self.properties,
                           "required": self.required},
        }}


# ---------------------------------------------------------------------------
# สถานะเคส — ใช้ร่วมกับปุ่ม postback ใน webhook ด้วย
# ---------------------------------------------------------------------------

async def apply_ticket_status(db: Session, ticket: Ticket, staff: User, target: str,
                              resolution: str | None = None) -> str:
    """เปลี่ยนสถานะ ticket ฝั่ง dashboard + sync itamtv ด้วยสิทธิ์ช่างคนที่สั่ง.

    target ∈ {in_progress, resolved}. คืนข้อความหมายเหตุผล itamtv (อาจว่าง).
    """
    ticket.status = target
    if ticket.assigned_to is None:
        ticket.assigned_to = staff.id
    if target == "resolved":
        ticket.resolved_at = datetime.now(timezone.utc)
    db.add(TicketComment(
        ticket_id=ticket.id, user_id=staff.id, is_internal=True,
        content=f"เปลี่ยนสถานะเป็น {ticket.status} ผ่าน LINE โดย {staff.display_name or staff.username}",
    ))
    if resolution:
        # ชี้แจงการแก้ไข — เก็บเป็น comment ที่ผู้แจ้งเห็นได้ (ไม่ใช่ internal)
        db.add(TicketComment(
            ticket_id=ticket.id, user_id=staff.id, is_internal=False,
            content=f"ชี้แจงการแก้ไข: {resolution}",
        ))
    db.commit()

    # ช่างรับงานเคสที่ผู้ใช้แจ้งมา → ถึงเวลาเปิดเคสใน itamtv ด้วย token ของช่างคนนี้
    if not ticket.itamtv_job_no:
        try:
            await itamtv_service.ensure_mirrored(db, ticket, staff)
        except Exception:  # noqa: BLE001
            logger.exception("ensure itamtv case failed for %s", ticket.ticket_no)
        db.refresh(ticket)
        if not ticket.itamtv_job_no:
            return "\n(⚠️ ยังเปิดเคสใน itamtv ไม่ได้ รบกวนทำในระบบเองด้วยครับ)"
    itamtv_target = itamtv_service.STATUS_TO_ITAMTV.get(target)
    if itamtv_target is None:
        return ""
    try:
        if not staff.itamtv_token:
            raise RuntimeError("บัญชีช่างยังไม่ได้ผูก itamtv token (ตั้งในหน้า Users)")
        msg = await itamtv_service.set_status(
            ticket.itamtv_job_no, token=staff.itamtv_token, target=itamtv_target,
            people_code=staff.itamtv_emp_code,
            # note = Txtnote2 "บันทึกการซ่อม" ฝั่ง itamtv → ใส่ชี้แจงการแก้ไขที่ staff บอกมา
            note=(resolution
                  or f"อัปเดตโดย {staff.display_name or staff.username} ผ่าน LINE"),
            level=ticket.itamtv_level,  # Level SLA ที่ AI ประเมินไว้ตอนเปิดเคส
        )
        return f"\nitamtv: {msg}"
    except Exception as exc:  # noqa: BLE001
        logger.warning("itamtv set_status failed for %s: %s", ticket.ticket_no, exc)
        db.add(TicketComment(
            ticket_id=ticket.id, user_id=staff.id, is_internal=True,
            content=f"⚠️ อัปเดตสถานะใน itamtv อัตโนมัติไม่ได้ ({exc}) — รบกวนทำในระบบเองด้วยครับ",
        ))
        db.commit()
        return "\n(⚠️ อัปเดตใน itamtv อัตโนมัติไม่ได้ รบกวนทำในระบบเองด้วยครับ)"


# ---------------------------------------------------------------------------
# search_tickets
# ---------------------------------------------------------------------------

async def _run_search_tickets(ctx: Ctx, args: dict) -> dict:
    assignee_id = ctx.staff.id if str(args.get("assignee", "")).lower() == "me" else None
    rows = ticket_service.search_tickets(
        ctx.db, status=args.get("status") or None,
        assignee_id=assignee_id, query=args.get("query") or None,
    )
    return {"tickets": rows}


def _render_search_tickets(data: dict, args: dict) -> str:
    tickets = data.get("tickets", [])
    if not tickets:
        return "ไม่พบเคสที่ตรงกับที่ค้นครับ"
    lines = ["เคสที่เจอครับ:"]
    for t in tickets:
        lines.append(
            f"- {t.get('ticket_no')} [{t.get('status_th')}] {t.get('title')}"
            f" — ผู้แจ้ง {t.get('reporter') or '-'}"
            + (f" · ดูแลโดย {t['assignee']}" if t.get("assignee") else "")
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# get_ticket
# ---------------------------------------------------------------------------

async def _run_get_ticket(ctx: Ctx, args: dict) -> dict:
    t = ticket_service.get_by_no(ctx.db, str(args.get("ticket_no", "")))
    if t is None:
        return {"error": "ไม่พบเคสนี้"}
    return ticket_service._ticket_dict(t)


def _render_get_ticket(data: dict, args: dict) -> str:
    if data.get("error"):
        return f"{data['error']}ครับ"
    return (
        f"{data.get('ticket_no')} [{data.get('status_th')}]\n"
        f"หัวข้อ: {data.get('title')}\n"
        f"ผู้แจ้ง: {data.get('reporter') or '-'} ({data.get('department') or '-'})\n"
        f"ผู้ดูแล: {data.get('assignee') or '-'} · ความเร่งด่วน {data.get('priority')}\n"
        f"{data.get('description') or ''}"
    )


# ---------------------------------------------------------------------------
# list_staff
# ---------------------------------------------------------------------------

async def _run_list_staff(ctx: Ctx, args: dict) -> dict:
    # ช่างที่มอบหมายงานได้ = staff ที่ยัง active และไม่ใช่หัวหน้างาน + งานที่ค้างอยู่ตอนนี้
    load = dict(
        ctx.db.query(Ticket.assigned_to, func.count(Ticket.id))
        .filter(Ticket.status.in_(["open", "in_progress"]))
        .group_by(Ticket.assigned_to)
        .all()
    )
    rows = (
        ctx.db.query(User)
        .filter(User.is_active.is_(True), User.role != "supervisor")
        .order_by(User.id)
        .all()
    )
    return {"staff": [
        {"name": u.display_name or u.username, "username": u.username,
         "open_tickets": load.get(u.id, 0), "itamtv_ready": bool(u.itamtv_token)}
        for u in rows
    ]}


def _render_list_staff(data: dict, args: dict) -> str:
    rows = data.get("staff", [])
    if not rows:
        return "ยังไม่มีช่างที่มอบหมายงานได้ในระบบครับ (ต้องเพิ่มผู้ใช้ในหน้า Users ก่อน)"
    lines = ["ช่างที่มอบหมายงานได้ตอนนี้ครับ:"]
    for i, s in enumerate(rows, 1):
        warn = "" if s.get("itamtv_ready") else " ⚠️ยังไม่ผูก itamtv"
        lines.append(f"{i}. {s['name']} — งานค้าง {s.get('open_tickets', 0)} เคส{warn}")
    lines.append("\nจะมอบหมายให้ใครครับ? กดปุ่มด้านล่างได้เลย")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# search_employees
# ---------------------------------------------------------------------------

async def _run_search_employees(ctx: Ctx, args: dict) -> dict:
    try:
        emps = await itamtv_service.search_employees(str(args.get("query", "")))
    except Exception as exc:  # noqa: BLE001
        logger.warning("search_employees failed: %s", exc)
        return {"error": "ต่อกับระบบพนักงานไม่ติด"}
    people = [
        {"id": e.get("id"), "name": e.get("name"), "nickname": e.get("nickname"),
         "emp_code": e.get("emp_code"), "department": e.get("department"),
         "position": e.get("position"), "bu": e.get("bu")}
        for e in emps
    ]
    return {"count": len(people), "employees": people}


def _render_search_employees(data: dict, args: dict) -> str:
    emps = data.get("employees", [])
    q = args.get("query", "")
    if not emps:
        return f"ค้นหา '{q}' ไม่พบพนักงานในระบบครับ ลองใช้ชื่อจริง/ชื่อเล่นอื่นดูได้ครับ"
    lines = [f"เจอพนักงานที่ตรงกับ '{q}' {len(emps)} คนครับ:"]
    for i, e in enumerate(emps, 1):
        nick = f" ({e['nickname']})" if e.get("nickname") else ""
        dept = e.get("department") or "-"
        ref = e.get("emp_code") or (f"id {e['id']}" if e.get("id") else "-")
        lines.append(f"{i}. {e.get('name')}{nick} — {dept} · {ref}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# list_assets
# ---------------------------------------------------------------------------

async def _run_list_assets(ctx: Ctx, args: dict) -> dict:
    emp = None
    try:
        if args.get("emp_code"):
            emp = await itamtv_service.lookup_employee_exact(emp_code=str(args["emp_code"]))
        elif args.get("name"):
            emp = await itamtv_service.lookup_employee(str(args["name"]))
    except Exception as exc:  # noqa: BLE001
        logger.warning("list_assets lookup failed: %s", exc)
        return {"error": "ต่อกับระบบพนักงานไม่ติด"}
    if not emp:
        return {"error": "หาพนักงานคนนี้ไม่เจอ"}
    try:
        assets = await itamtv_service.fetch_assets(emp["id"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch_assets failed: %s", exc)
        return {"error": "ดึงข้อมูลอุปกรณ์ไม่สำเร็จ"}
    return {"employee": emp.get("name"),
            "assets": itamtv_service.asset_summary(assets) or "ไม่มีอุปกรณ์ในระบบ"}


def _render_list_assets(data: dict, args: dict) -> str:
    if data.get("error"):
        return f"{data['error']}ครับ"
    return f"อุปกรณ์ที่ {data.get('employee')} ถือครอง:\n{data.get('assets')}"


# ---------------------------------------------------------------------------
# search_kb — คลังความรู้ (kb_chunks) + แบบฟอร์มที่ผูกไว้
# ---------------------------------------------------------------------------

async def _run_search_kb(ctx: Ctx, args: dict) -> dict:
    from app.services import rag_service

    query = str(args.get("query", "")).strip()
    if not query:
        return {"error": "ไม่ได้ระบุคำค้น"}
    try:
        context = await rag_service.retrieve_context(ctx.db, query)
    except Exception as exc:  # noqa: BLE001
        logger.warning("search_kb retrieve failed: %s", exc)
        return {"error": "ค้นคลังความรู้ไม่สำเร็จ"}
    form = None
    try:
        f = await rag_service.find_form(ctx.db, query)
        if f is not None:
            form = {"name": f.name, "slug": f.slug, "description": f.description}
    except Exception:  # noqa: BLE001
        logger.exception("search_kb find_form failed")
    return {"query": query, "context": context, "form": form}


def _render_search_kb(data: dict, args: dict) -> str | None:
    if data.get("error"):
        return f"{data['error']}ครับ"
    if not data.get("context") and not data.get("form"):
        return (f"ไม่เจอเรื่อง '{data.get('query')}' ในคลังความรู้ครับ "
                f"(เพิ่มได้ที่หน้า Knowledge Base ใน dashboard)")
    # มีเนื้อหา → ให้โมเดลเรียบเรียงตอบต่อ (สรุปจาก context ที่ได้จริง) แต่ถ้าเจอ "ฟอร์ม"
    # ให้โค้ดตอบเองเพราะต้องแปะลิงก์ที่ถูกต้อง ห้ามให้โมเดลแต่ง URL
    if data.get("form"):
        form = data["form"]
        link = line_service.form_link(form["slug"])
        desc = f"\n{form['description']}" if form.get("description") else ""
        head = f"แบบฟอร์มที่ตรงกับ '{data.get('query')}' ครับ: {form['name']}{desc}"
        return f"{head}\n{link}" if link else head
    return None


# ---------------------------------------------------------------------------
# set_status
# ---------------------------------------------------------------------------

async def _run_set_status(ctx: Ctx, args: dict) -> dict:
    target = str(args.get("status", "")).strip()
    if target not in ("in_progress", "resolved"):
        return {"error": "status ต้องเป็น in_progress หรือ resolved"}
    # schema กำหนดให้เป็น array อยู่แล้ว แต่รับสตริงเดี่ยว/คั่น comma ไว้ด้วยกันโมเดลหลุด
    raw_no = args.get("ticket_no")
    if isinstance(raw_no, (list, tuple)):
        numbers = [str(n).strip() for n in raw_no]
    else:
        numbers = [n.strip() for n in str(raw_no or "").replace(",", " ").split()]
    numbers = [n for n in numbers if n]
    if not numbers:
        return {"error": "ไม่ได้ระบุเลขเคส"}

    # ปิดเคสต้องมี "ชี้แจงการแก้ไข" (ช่องบังคับฝั่ง itamtv) — สั่งผ่าน LINE มักไม่มีติดมา
    # จึงหยุดถามก่อนหนึ่งจังหวะ ยกเว้น staff บอกเองว่าไม่ต้องระบุ
    resolution = str(args.get("resolution") or "").strip()
    if target == "resolved" and not resolution and not _as_bool(args.get("skip_resolution")):
        return {"need_resolution": True, "ticket_no": numbers}

    done, failed = [], []
    for no in numbers:
        t = ticket_service.get_by_no(ctx.db, no)
        if t is None:
            failed.append(no)
            continue
        note = await apply_ticket_status(ctx.db, t, ctx.staff, target, resolution or None)
        done.append({"ticket_no": t.ticket_no, "status": t.status, "itamtv": note.strip()})
    if not done:
        return {"error": "ไม่พบเคสนี้", "not_found": failed}
    return {"ok": True, "status": target, "tickets": done, "not_found": failed,
            "resolution": resolution or None}


SKIP_RESOLUTION_TEXT = "ปิดเลย ไม่ต้องชี้แจง"
WRITE_RESOLUTION_TEXT = "ขอใส่ชี้แจงการแก้ไข"


def _render_set_status(data: dict, args: dict) -> str | None:
    if data.get("need_resolution"):
        nos = ", ".join(data.get("ticket_no") or [])
        return (f"ก่อนปิด {nos} — จะใส่ “ชี้แจงการแก้ไข” ไหมครับ?\n"
                f"ถ้าจะใส่ พิมพ์ข้อความมาได้เลย หรือกด “{SKIP_RESOLUTION_TEXT}” "
                f"ถ้าไม่ต้องระบุครับ")
    if not data.get("ok"):
        return None  # error → ให้โมเดลอธิบาย/ถามต่อ
    th = ticket_service.STATUS_LABELS_TH.get(data.get("status"), data.get("status"))
    rows = data.get("tickets") or []
    missing = data.get("not_found") or []
    if len(rows) == 1:
        msg = (f"อัปเดตเคส {rows[0]['ticket_no']} เป็น “{th}” แล้วครับ ✅"
               f"{rows[0].get('itamtv') or ''}")
    else:
        lines = [f"อัปเดต {len(rows)} เคสเป็น “{th}” แล้วครับ ✅"]
        lines += [f"- {r['ticket_no']}{(' ' + r['itamtv']) if r.get('itamtv') else ''}"
                  for r in rows]
        msg = "\n".join(lines)
    if missing:
        msg += "\n⚠️ ไม่พบเคส: " + ", ".join(missing)
    if data.get("resolution"):
        msg += f"\nชี้แจงการแก้ไข: {data['resolution']}"
    return msg


# ---------------------------------------------------------------------------
# create_ticket — เปิดเคสแทนผู้แจ้งที่โทร/เดินมาหา staff
# ---------------------------------------------------------------------------

async def _run_create_ticket(ctx: Ctx, args: dict) -> dict:
    """ผู้แจ้งหาไม่เจอ/เจอหลายคน → คืน error ให้ AI ถามกลับ (ไม่เดา). best-effort mirror itamtv."""
    # helper ฝั่ง LINE อยู่ใน webhook (router) — import ตอนใช้เพื่อไม่ให้ import วน
    from app.api.webhook import (
        _find_staff_by_name, _notify_group_ticket, notify_staff_new_ticket,
    )

    db, staff = ctx.db, ctx.staff
    emp = None
    try:
        if args.get("reporter_emp_code"):
            emp = await itamtv_service.lookup_employee_exact(
                emp_code=str(args["reporter_emp_code"])
            )
            if emp is None:
                return {"error": f"หารหัสพนักงาน {args['reporter_emp_code']} ไม่เจอ ให้ถาม staff ยืนยัน"}
        elif args.get("reporter_name"):
            found = await itamtv_service.search_employees(str(args["reporter_name"]))
            if len(found) == 1:
                emp = found[0]
            elif len(found) == 0:
                return {"error": f"หาพนักงานชื่อ '{args['reporter_name']}' ไม่เจอ ให้ถาม staff ระบุใหม่"}
            else:
                return {
                    "error": "เจอพนักงานหลายคน ให้ถาม staff ว่าคนไหน",
                    "candidates": [
                        {"name": e.get("name"), "emp_code": e.get("emp_code"),
                         "department": e.get("department")} for e in found
                    ],
                }
    except Exception as exc:  # noqa: BLE001
        logger.warning("create_ticket reporter lookup failed: %s", exc)
        return {"error": "ต่อกับระบบพนักงานไม่ติด ลองใหม่อีกที"}

    reporter_name = (emp or {}).get("name") or str(args.get("reporter_name") or "").strip()
    if not reporter_name:
        return {"error": "ยังไม่รู้ว่าใครเป็นผู้แจ้ง ให้ถาม staff ก่อน"}

    category = args.get("category")
    if category not in VALID_CATEGORIES:
        category = "other"
    priority = args.get("priority")
    if priority not in VALID_PRIORITIES:
        priority = "medium"
    title = (str(args.get("title") or "").strip() or f"{reporter_name} แจ้งปัญหา")[:255]

    dept = (emp or {}).get("department") or "-"
    code = (emp or {}).get("emp_code") or "-"
    header = f"[เปิดโดยเจ้าหน้าที่ทางโทรศัพท์] ผู้แจ้ง: {reporter_name} ({dept}) รหัส {code}"
    description = header + "\n\n" + str(args.get("description") or "").strip()

    # หัวหน้างาน (role=supervisor) ไม่ได้ลงมือเอง → เปิดเคสแบบมอบหมาย: ยังไม่ in_progress
    # และยังไม่ส่งไป itamtv จนกว่าช่างจะกดรับงาน (เคสจะได้ขึ้นชื่อช่างคนที่ทำจริง)
    is_supervisor = staff.role == "supervisor"
    assignee: User | None = None
    assign_to = str(args.get("assign_to") or "").strip()
    # ช่างทั่วไปเปิดเคส = รับงานเองเสมอ → assign_to ไม่มีความหมาย ทิ้งไปเลย
    # (โมเดลชอบใส่ assign_to="me" ตามที่ staff พูดว่า "ผมดูแลเอง" แล้วไปตายตอนหาชื่อช่าง)
    if not is_supervisor:
        assign_to = ""
    elif assign_to.lower() in _SELF_WORDS:
        assignee = staff
        assign_to = ""
    if assign_to:
        assignee = _find_staff_by_name(db, assign_to)
        if assignee is None:
            return {"error": f"หาช่างชื่อ '{assign_to}' ในระบบไม่เจอ ให้ถาม staff ระบุใหม่"}
    if not is_supervisor:
        assignee = staff  # staff ทั่วไปเปิดเคสเอง = รับงานเองทันที

    ticket = ticket_service.create_ticket(
        db, title=title, description=description, category=category,
        ticket_type="L2", priority=priority,
        status="in_progress" if not is_supervisor else "open",
    )
    ticket.assigned_to = assignee.id if assignee else None
    ticket.reporter_name = reporter_name[:100]
    building = str(args.get("building") or "").strip()
    floor = str(args.get("floor") or "").strip()
    loc = "-".join(p for p in (building, f"ชั้น {floor}" if floor else "") if p)
    detail_parts = [p for p in (
        (emp or {}).get("department"), loc or None, (emp or {}).get("phone")
    ) if p]
    ticket.reporter_detail = (" · ".join(detail_parts) or None)
    if ticket.reporter_detail:
        ticket.reporter_detail = ticket.reporter_detail[:255]
    opened_by = staff.display_name or staff.username
    log = f"เปิดเคสแทนผู้แจ้งทางโทรศัพท์ โดย {opened_by}"
    if is_supervisor:
        who = (assignee.display_name or assignee.username) if assignee else "ทีมช่าง (ยังไม่ระบุ)"
        log += f" (หัวหน้างานมอบหมายให้ {who} — เคสจะเข้า itamtv เมื่อช่างกดรับงาน)"
    db.add(TicketComment(ticket_id=ticket.id, user_id=staff.id, is_internal=True, content=log))
    db.commit()
    db.refresh(ticket)

    # mirror itamtv ด้วยข้อมูลผู้แจ้ง (สร้าง LineUser ชั่วคราว ไม่ผูก DB — mirror อ่าน attr อย่างเดียว)
    lu = LineUser(
        line_user_id=f"phone-in:{ticket.ticket_no}",
        emp_name=reporter_name, emp_code=(emp or {}).get("emp_code"),
        emp_email=(emp or {}).get("email"), department=(emp or {}).get("department"),
        building=building or None, floor=floor or None,
    )
    if not is_supervisor:
        try:
            if staff.itamtv_token:
                # staff เปิดเคสเอง = รับงานเอง → บันทึกใน itamtv ด้วย token ของตัวเองทันที
                await itamtv_service.mirror_ticket(db, ticket, lu, token=staff.itamtv_token)
            else:
                db.add(TicketComment(
                    ticket_id=ticket.id, user_id=staff.id, is_internal=True,
                    content="⚠️ ยังไม่ได้เปิดเคสใน itamtv — บัญชีนี้ยังไม่ได้ผูก itamtv token",
                ))
                db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("mirror phone-in ticket %s failed", ticket.ticket_no)
    else:
        # หัวหน้างานมอบหมาย → ส่งการ์ดให้ช่างกดรับงาน (ระบุตัว = ส่งเฉพาะคนนั้น)
        try:
            await notify_staff_new_ticket(db, ticket, only_staff=assignee)
        except Exception:  # noqa: BLE001
            logger.exception("notify assignee for %s failed", ticket.ticket_no)
    try:
        await _notify_group_ticket(db, ticket)
    except Exception:  # noqa: BLE001
        logger.exception("group notify phone-in ticket %s failed", ticket.ticket_no)

    return {
        "ok": True, "ticket_no": ticket.ticket_no, "reporter": reporter_name,
        "status": ticket.status,
        "assigned_to": (assignee.display_name or assignee.username) if assignee else None,
        "note": ("มอบหมายแล้ว รอช่างกดรับงาน" if is_supervisor else None),
    }


def _render_create_ticket(data: dict, args: dict) -> str | None:
    if not data.get("ok"):
        # ผู้แจ้งกำกวม (เจอหลายคน) → ให้โมเดลถาม staff ต่อพร้อมรายชื่อ
        if data.get("candidates"):
            return None
        # error อื่นๆ → บอก staff ตรงๆ ห้ามปล่อยให้โมเดลเรียบเรียงเอง เพราะมันมักกลบ
        # ความล้มเหลวด้วยการตอบว่า "เปิดให้แล้ว" พร้อมเลขเคสที่แต่งขึ้น
        return f"เปิดเคสไม่สำเร็จครับ: {data.get('error') or 'ไม่ทราบสาเหตุ'}"
    return (
        f"เปิดเคส {data.get('ticket_no')} ให้แล้วครับ ✅\n"
        f"ผู้แจ้ง: {data.get('reporter')} · assign ให้ {data.get('assigned_to')}"
        f" · สถานะกำลังดำเนินการ 🔧"
    )


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------

TOOLS: dict[str, StaffTool] = {t.name: t for t in [
    StaffTool(
        name="search_tickets", description="ค้นหาเคสในระบบ",
        properties={
            "status": {"type": "string",
                       "enum": ["open", "pending_approval", "in_progress", "resolved", "closed"],
                       "description": "ไม่ใส่ = ทุกสถานะ"},
            "assignee": {**_STR, "description": "'me' = เฉพาะเคสที่ฉันดูแล"},
            "query": {**_STR, "description": "คำค้นในหัวข้อ/รายละเอียด/เลขเคส"},
        },
        run=_run_search_tickets, render=_render_search_tickets,
    ),
    StaffTool(
        name="get_ticket", description="ดูรายละเอียดเคสเดียว",
        properties={"ticket_no": {**_STR, "description": "เช่น TK-20260721-0001"}},
        required=["ticket_no"], run=_run_get_ticket, render=_render_get_ticket,
    ),
    StaffTool(
        name="list_staff",
        description="รายชื่อช่าง IT ที่มอบหมายงานได้ (ชื่อ + จำนวนงานค้าง) — ใช้ตอนหัวหน้างานถามว่ามีช่างคนไหนบ้าง",
        run=_run_list_staff, render=_render_list_staff,
        choices=lambda d: line_service.choice_quick_reply(
            [s["name"] for s in d.get("staff", [])]
        ),
    ),
    StaffTool(
        name="search_employees",
        description="ค้นพนักงานจากชื่อ/คำค้น คืนชื่อจริง/รหัส/แผนก ที่เจอทั้งหมด",
        properties={"query": _STR}, required=["query"],
        run=_run_search_employees, render=_render_search_employees,
        choices=lambda d: line_service.choice_quick_reply(
            [e.get("name", "") for e in d.get("employees", [])]
        ),
    ),
    StaffTool(
        name="search_kb",
        description="ค้นคลังความรู้/นโยบาย IT ของบริษัท และแบบฟอร์มขอใช้บริการ "
                    "(เช่น ขั้นตอนขอ WiFi/VPN, แบบฟอร์มต่างๆ) — ใช้ก่อนตอบคำถามเชิงนโยบาย/ขั้นตอนเสมอ",
        properties={"query": {**_STR, "description": "เรื่องที่จะค้น เช่น 'ขอใช้ WiFi', 'แบบฟอร์ม VPN'"}},
        required=["query"], run=_run_search_kb, render=_render_search_kb,
    ),
    StaffTool(
        name="list_assets",
        description="ดูอุปกรณ์ที่พนักงานคนหนึ่งถือครอง (ระบุ emp_code หรือ name อย่างใดอย่างหนึ่ง)",
        properties={"emp_code": _STR, "name": _STR},
        run=_run_list_assets, render=_render_list_assets,
    ),
    StaffTool(
        name="set_status",
        description="เปลี่ยนสถานะเคส ใส่ได้หลายเคสพร้อมกัน — sync เข้า itamtv ให้อัตโนมัติ",
        properties={
            "ticket_no": {"type": "array", "items": _STR,
                          "description": "เลขเคสทุกใบที่ต้องการเปลี่ยนสถานะ"},
            "status": {"type": "string", "enum": ["in_progress", "resolved"]},
            "resolution": {**_STR, "description": "ชี้แจงการแก้ไข (บันทึกการซ่อม) — ใส่ตอนปิดเคส "
                                                  "ถ้า staff บอกรายละเอียดการแก้มา"},
            "skip_resolution": {"type": "boolean",
                                "description": "true เมื่อ staff ยืนยันว่าไม่ต้องใส่ชี้แจงการแก้ไข"},
        },
        required=["ticket_no", "status"],
        run=_run_set_status, render=_render_set_status,
        choices=lambda d: (line_service.choice_quick_reply([SKIP_RESOLUTION_TEXT])
                           if d.get("need_resolution") else None),
    ),
    StaffTool(
        name="create_ticket",
        description="เปิดเคสแทนผู้ใช้ที่โทร/เดินมาแจ้ง staff เอง (ต้องได้ตัวผู้แจ้งที่ชัดเจนก่อน)",
        properties={
            "reporter_emp_code": {**_STR, "description": "รหัสพนักงานผู้แจ้ง (แม่นกว่า ใช้ก่อนถ้ามี)"},
            "reporter_name": {**_STR, "description": "ชื่อผู้แจ้ง ใช้เมื่อไม่รู้รหัส"},
            "title": _STR,
            "description": _STR,
            "category": {"type": "string", "enum": list(VALID_CATEGORIES)},
            "priority": {"type": "string", "enum": list(VALID_PRIORITIES)},
            "building": _STR,
            "floor": _STR,
            "assign_to": {**_STR, "description": "ชื่อ-นามสกุลของช่างคนอื่นที่จะมอบหมายให้ "
                                                 "(หัวหน้างานเท่านั้น) — ถ้าคนสั่งจะดูแลเคสเองไม่ต้องใส่"},
        },
        required=["title", "description", "category", "priority"],
        run=_run_create_ticket, render=_render_create_ticket,
    ),
]}


def schemas() -> list[dict]:
    """JSON Schema ของทุกเครื่องมือ — ส่งให้ Ollama ใน field tools."""
    return [t.schema() for t in TOOLS.values()]


async def run(ctx: Ctx, name: str, args: dict) -> dict:
    tool = TOOLS.get(name)
    if tool is None:
        return {"error": "ไม่รู้จักเครื่องมือนี้"}
    logger.info("staff tool run: %s(%s) by %s", name, args, ctx.staff.username)
    return await tool.run(ctx, args)


def render(name: str, data: dict, args: dict) -> str | None:
    """ข้อความตอบ staff จากผลลัพธ์จริง (None = ให้โมเดลคุยต่อเอง)."""
    tool = TOOLS.get(name)
    if tool is None or tool.render is None:
        return None
    return tool.render(data, args)


def choices(name: str, data: dict) -> dict | None:
    tool = TOOLS.get(name)
    if tool is None or tool.choices is None:
        return None
    return tool.choices(data)


_TICKET_NO_RE = re.compile(r"TK-\d{8}-\d{4}")


# คำที่แปลว่า "ลงมือทำให้แล้ว" — ต้องมีผลเครื่องมือรองรับเท่านั้น
_DONE_CLAIM_RE = re.compile(
    r"(ปิดเคส|ปิดให้|ปิดงาน|เปลี่ยนสถานะ|อัปเดตสถานะ|อัพเดทสถานะ|เปิดเคส|เปิดให้|"
    r"รับงาน|มอบหมาย)[^\n]{0,40}?(แล้ว|เรียบร้อย|เสร็จสิ้น)"
)
# ประโยคคำถาม/เสนอ ("ปิดเคสนี้เลยไหมครับ") ไม่ใช่การอ้างว่าทำแล้ว
_ASKING_RE = re.compile(r"(ไหม|มั้ย|หรือยัง|รึเปล่า|หรือเปล่า|ดีไหม|นะครับ\?|\?)")
# เครื่องมือที่ "เปลี่ยนของจริง" — อย่างอื่นเป็นแค่การดูข้อมูล
_ACTION_TOOLS = {"set_status", "create_ticket"}


def guard_unbacked_claim(reply: str, performed: set[str]) -> str | None:
    """บอทบอกว่า "ปิดเคสให้แล้ว/เปิดเคสให้แล้ว" ทั้งที่เทิร์นนี้ไม่ได้เรียกเครื่องมือที่ทำจริง
    → คืนข้อความแทนที่ (None = ปล่อยผ่าน).

    เคสจริงที่เจอ: staff สั่งปิดเคส บอทเรียกแค่ get_ticket (ดูเฉยๆ) แล้วตอบว่าปิดให้แล้ว
    สถานะในระบบไม่ขยับ — guard_fake_ticket_no จับไม่ได้เพราะเลขเคสนั้นมีจริงในบทสนทนา
    """
    if performed & _ACTION_TOOLS:
        return None  # ทำจริงไปแล้ว พูดได้
    for line in reply.splitlines():
        if _DONE_CLAIM_RE.search(line) and not _ASKING_RE.search(line):
            logger.warning("staff assistant claimed action without tool call: %r", line.strip())
            return ("ขอโทษครับ ผมยังไม่ได้ลงมือทำให้จริง 🙏 รบกวนบอกอีกทีว่าจะให้ทำอะไร"
                    "กับเคสไหนครับ เดี๋ยวผมจัดการแล้วรายงานผลจริงให้")
    return None


def guard_fake_ticket_no(reply: str, history: list[dict]) -> str:
    """กันโมเดล "แต่งเลขเคส" ตอนตอบเป็นข้อความ (เคยตอบว่าเปิดเคสให้แล้วทั้งที่ไม่ได้เรียก
    create_ticket — เลขที่แต่งมาดันไปชนเคสเก่าที่มีอยู่จริง ทำให้ staff เข้าใจผิด).

    เลขเคสที่พูดถึงได้ต้องเคยปรากฏใน transcript จริง (ผลเครื่องมือ หรือที่ staff พิมพ์เอง)
    ถ้าเจอเลขที่ไม่มีที่มา → ทิ้งคำตอบนี้ทั้งใบ บอก staff ตรงๆ ว่ายังไม่ได้ทำ
    """
    claimed = set(_TICKET_NO_RE.findall(reply))
    if not claimed:
        return reply
    known: set[str] = set()
    for msg in history:
        if msg.get("role") in ("tool", "user"):
            known.update(_TICKET_NO_RE.findall(msg.get("content") or ""))
    unknown = claimed - known
    if not unknown:
        return reply
    logger.warning("staff assistant fabricated ticket_no %s — reply dropped", unknown)
    return ("ขอโทษครับ ผมยังไม่ได้ดำเนินการให้จริง (เลขเคสที่ตอบไปเมื่อกี้ไม่ถูกต้อง) 🙏\n"
            "รบกวนสั่งอีกครั้งนะครับ เดี๋ยวผมทำแล้วแจ้งเลขเคสจริงให้")


__all__ = ["Ctx", "StaffTool", "TOOLS", "schemas", "run", "render", "choices",
           "guard_fake_ticket_no", "apply_ticket_status"]

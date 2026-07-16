import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import api, { apiError } from "../api";
import StatusBadge from "../components/StatusBadge";
import PriorityBadge from "../components/PriorityBadge";
import CommentBox from "../components/CommentBox";

const STATUS_OPTIONS = ["open", "in_progress", "resolved", "closed"];

function AttachmentPreview({ ticketId, attachment }) {
  const [url, setUrl] = useState(null);
  const isImage = attachment.mime_type?.startsWith("image/");

  useEffect(() => {
    if (!isImage) return;
    let objectUrl;
    api
      .get(`/tickets/${ticketId}/attachments/${attachment.id}/file`, {
        responseType: "blob",
      })
      .then(({ data }) => {
        objectUrl = URL.createObjectURL(data);
        setUrl(objectUrl);
      });
    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [ticketId, attachment.id, isImage]);

  if (!isImage) {
    return <li className="text-sm text-slate-400">{attachment.file_name}</li>;
  }

  return (
    <li className="list-none">
      {url ? (
        <a href={url} target="_blank" rel="noreferrer">
          <img
            src={url}
            alt={attachment.file_name}
            className="max-w-xs rounded-lg ring-1 ring-white/10 hover:ring-indigo-400/50 transition-all"
          />
        </a>
      ) : (
        <p className="text-sm text-slate-500">กำลังโหลดรูป...</p>
      )}
    </li>
  );
}

function EquipmentApproval({ ticketId, request, onChange, onDecide }) {
  const [itemName, setItemName] = useState(request?.item_name || "");
  const [quantity, setQuantity] = useState(request?.quantity || 1);
  const [saving, setSaving] = useState(false);

  if (!request) {
    // service_request ที่ไม่มีรายการอุปกรณ์ — อนุมัติ/ปฏิเสธได้เลย
    return <ApprovalButtons onDecide={onDecide} />;
  }

  const dirty =
    itemName !== request.item_name || Number(quantity) !== request.quantity;

  async function save() {
    setSaving(true);
    try {
      await api.patch(`/tickets/${ticketId}/equipment-request`, {
        item_name: itemName,
        quantity: Number(quantity),
      });
      await onChange();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mt-4 ring-1 ring-amber-400/30 bg-amber-400/5 rounded-xl p-4">
      <p className="font-medium text-amber-300 mb-2">คำขอเบิกอุปกรณ์ (ตรวจสอบก่อนอนุมัติ)</p>
      <div className="flex flex-wrap gap-3 items-end">
        <label className="text-sm">
          <span className="block text-slate-400 mb-1">รายการ</span>
          <input
            className="input-dark rounded-lg p-1.5 text-sm"
            value={itemName}
            onChange={(e) => setItemName(e.target.value)}
          />
        </label>
        <label className="text-sm">
          <span className="block text-slate-400 mb-1">จำนวน</span>
          <input
            type="number"
            min={1}
            className="input-dark rounded-lg p-1.5 text-sm w-24"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
          />
        </label>
        {dirty && (
          <button
            onClick={save}
            disabled={saving}
            className="text-sm ring-1 ring-amber-400/50 text-amber-300 rounded-lg px-3 py-1.5 hover:bg-amber-400/10 disabled:opacity-50 transition-colors"
          >
            บันทึกการแก้ไข
          </button>
        )}
      </div>
      <ApprovalButtons onDecide={onDecide} disabled={dirty} />
      {dirty && (
        <p className="text-xs text-amber-400 mt-1">* บันทึกการแก้ไขก่อนจึงจะอนุมัติได้</p>
      )}
    </div>
  );
}

function ApprovalButtons({ onDecide, disabled }) {
  return (
    <div className="flex gap-2 mt-3">
      <button
        onClick={() => onDecide("approve")}
        disabled={disabled}
        className="bg-gradient-to-br from-green-500 to-emerald-500 text-white px-4 py-1.5 rounded-lg text-sm font-medium shadow-[0_0_16px_rgba(74,222,128,0.3)] hover:shadow-[0_0_22px_rgba(74,222,128,0.5)] disabled:opacity-50 disabled:shadow-none transition-all"
      >
        อนุมัติ
      </button>
      <button
        onClick={() => onDecide("reject")}
        disabled={disabled}
        className="bg-gradient-to-br from-red-500 to-rose-500 text-white px-4 py-1.5 rounded-lg text-sm font-medium shadow-[0_0_16px_rgba(248,113,113,0.3)] hover:shadow-[0_0_22px_rgba(248,113,113,0.5)] disabled:opacity-50 disabled:shadow-none transition-all"
      >
        ปฏิเสธ
      </button>
    </div>
  );
}

export default function TicketDetail() {
  const { id } = useParams();
  const [ticket, setTicket] = useState(null);

  const load = useCallback(async () => {
    const { data } = await api.get(`/tickets/${id}`);
    setTicket(data);
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  async function updateStatus(status) {
    await api.patch(`/tickets/${id}`, { status });
    load();
  }

  async function addComment(content, isInternal) {
    await api.post(`/tickets/${id}/comments`, { content, is_internal: isInternal });
    load();
  }

  async function decide(action) {
    await api.post(`/tickets/${id}/${action}`);
    load();
  }

  async function notifyClose() {
    try {
      await api.post(`/tickets/${id}/notify-close`);
      alert("ส่งการ์ดปิดเคสไปหาช่างทาง LINE แล้วครับ");
    } catch (err) {
      alert(apiError(err, "ส่งไม่สำเร็จ"));
    }
  }

  if (!ticket) return <p className="text-slate-500">กำลังโหลด...</p>;

  return (
    <div className="max-w-3xl space-y-6 animate-fadein">
      <div className="glass rounded-xl p-6">
        <div className="flex items-center justify-between">
          <span className="font-mono text-sm text-slate-400">{ticket.ticket_no}</span>
          <div className="flex gap-2">
            <StatusBadge status={ticket.status} />
            <PriorityBadge priority={ticket.priority} />
          </div>
        </div>
        <h1 className="text-xl font-bold mt-2 text-glow">{ticket.title}</h1>
        <p className="text-slate-300 mt-2 whitespace-pre-wrap">{ticket.description}</p>
        <div className="text-sm text-slate-400 mt-4 grid grid-cols-2 gap-2">
          <span>ผู้แจ้ง: {ticket.line_user?.display_name || "-"}</span>
          <span>แผนก: {ticket.line_user?.department || "-"}</span>
          <span>หมวด: {ticket.category}</span>
          <span>ประเภท: {ticket.type}</span>
        </div>

        {ticket.ai_response && (
          <div className="mt-4 bg-teal-400/5 ring-1 ring-teal-400/30 rounded-xl p-3 text-sm">
            <p className="font-medium text-teal-300">AI ตอบครั้งแรก:</p>
            <p className="text-slate-300 mt-1">{ticket.ai_response}</p>
          </div>
        )}

        <div className="flex flex-wrap gap-2 mt-5">
          {STATUS_OPTIONS.map((s) => (
            <button
              key={s}
              onClick={() => updateStatus(s)}
              className="text-sm ring-1 ring-white/10 rounded-lg px-3 py-1 text-slate-300 hover:bg-white/5 hover:ring-indigo-400/40 hover:text-white transition-all"
            >
              → {s}
            </button>
          ))}
          {ticket.assigned_to && !["resolved", "closed"].includes(ticket.status) && (
            <button
              onClick={notifyClose}
              className="text-sm ring-1 ring-emerald-400/40 rounded-lg px-3 py-1 text-emerald-300 hover:bg-emerald-400/10 transition-all"
            >
              📲 แจ้งช่างให้ปิดเคส
            </button>
          )}
        </div>

        {ticket.status === "pending_approval" && (
          <EquipmentApproval
            ticketId={id}
            request={ticket.equipment_request}
            onChange={load}
            onDecide={decide}
          />
        )}
      </div>

      {ticket.attachments?.length > 0 && (
        <div className="glass rounded-xl p-6">
          <h2 className="font-semibold mb-2 text-slate-100">ไฟล์แนบ</h2>
          <ul className="flex flex-wrap gap-3">
            {ticket.attachments.map((a) => (
              <AttachmentPreview key={a.id} ticketId={id} attachment={a} />
            ))}
          </ul>
        </div>
      )}

      <div className="glass rounded-xl p-6 space-y-4">
        <h2 className="font-semibold text-slate-100">ความคิดเห็น / Activity</h2>
        <div className="space-y-3">
          {ticket.comments?.map((c) => (
            <div
              key={c.id}
              className={`text-sm p-3 rounded-lg ring-1 ${
                c.is_internal
                  ? "bg-amber-400/5 ring-amber-400/20"
                  : "bg-white/5 ring-white/10"
              }`}
            >
              <p className="whitespace-pre-wrap text-slate-200">{c.content}</p>
              <p className="text-xs text-slate-500 mt-1">
                {c.is_internal ? "ภายใน · " : ""}
                {new Date(c.created_at).toLocaleString("th-TH")}
              </p>
            </div>
          ))}
          {ticket.comments?.length === 0 && (
            <p className="text-slate-500 text-sm">ยังไม่มีความคิดเห็น</p>
          )}
        </div>
        <CommentBox onSubmit={addComment} />
      </div>
    </div>
  );
}

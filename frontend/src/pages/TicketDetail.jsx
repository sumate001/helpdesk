import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import api from "../api";
import StatusBadge from "../components/StatusBadge";
import PriorityBadge from "../components/PriorityBadge";
import CommentBox from "../components/CommentBox";

const STATUS_OPTIONS = ["open", "in_progress", "resolved", "closed"];

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
    <div className="mt-4 border border-amber-200 bg-amber-50 rounded-lg p-4">
      <p className="font-medium text-amber-800 mb-2">คำขอเบิกอุปกรณ์ (ตรวจสอบก่อนอนุมัติ)</p>
      <div className="flex flex-wrap gap-3 items-end">
        <label className="text-sm">
          <span className="block text-slate-500 mb-1">รายการ</span>
          <input
            className="border border-slate-300 rounded-md p-1.5 text-sm"
            value={itemName}
            onChange={(e) => setItemName(e.target.value)}
          />
        </label>
        <label className="text-sm">
          <span className="block text-slate-500 mb-1">จำนวน</span>
          <input
            type="number"
            min={1}
            className="border border-slate-300 rounded-md p-1.5 text-sm w-24"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
          />
        </label>
        {dirty && (
          <button
            onClick={save}
            disabled={saving}
            className="text-sm border border-amber-400 text-amber-700 rounded-md px-3 py-1.5 disabled:opacity-50"
          >
            บันทึกการแก้ไข
          </button>
        )}
      </div>
      <ApprovalButtons onDecide={onDecide} disabled={dirty} />
      {dirty && (
        <p className="text-xs text-amber-600 mt-1">* บันทึกการแก้ไขก่อนจึงจะอนุมัติได้</p>
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
        className="bg-green-600 text-white px-4 py-1.5 rounded-md text-sm disabled:opacity-50"
      >
        อนุมัติ
      </button>
      <button
        onClick={() => onDecide("reject")}
        disabled={disabled}
        className="bg-red-600 text-white px-4 py-1.5 rounded-md text-sm disabled:opacity-50"
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

  if (!ticket) return <p className="text-slate-400">กำลังโหลด...</p>;

  return (
    <div className="max-w-3xl space-y-6">
      <div className="bg-white rounded-lg shadow-sm p-6 border border-slate-200">
        <div className="flex items-center justify-between">
          <span className="font-mono text-sm text-slate-500">{ticket.ticket_no}</span>
          <div className="flex gap-2">
            <StatusBadge status={ticket.status} />
            <PriorityBadge priority={ticket.priority} />
          </div>
        </div>
        <h1 className="text-xl font-bold mt-2">{ticket.title}</h1>
        <p className="text-slate-600 mt-2 whitespace-pre-wrap">{ticket.description}</p>
        <div className="text-sm text-slate-500 mt-4 grid grid-cols-2 gap-2">
          <span>ผู้แจ้ง: {ticket.line_user?.display_name || "-"}</span>
          <span>แผนก: {ticket.line_user?.department || "-"}</span>
          <span>หมวด: {ticket.category}</span>
          <span>ประเภท: {ticket.type}</span>
        </div>

        {ticket.ai_response && (
          <div className="mt-4 bg-emerald-50 border border-emerald-200 rounded p-3 text-sm">
            <p className="font-medium text-emerald-700">AI ตอบครั้งแรก:</p>
            <p className="text-slate-700 mt-1">{ticket.ai_response}</p>
          </div>
        )}

        <div className="flex flex-wrap gap-2 mt-5">
          {STATUS_OPTIONS.map((s) => (
            <button
              key={s}
              onClick={() => updateStatus(s)}
              className="text-sm border border-slate-300 rounded-md px-3 py-1 hover:bg-slate-50"
            >
              → {s}
            </button>
          ))}
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
        <div className="bg-white rounded-lg shadow-sm p-6 border border-slate-200">
          <h2 className="font-semibold mb-2">ไฟล์แนบ</h2>
          <ul className="text-sm text-slate-600 list-disc pl-5">
            {ticket.attachments.map((a) => (
              <li key={a.id}>{a.file_name}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="bg-white rounded-lg shadow-sm p-6 border border-slate-200 space-y-4">
        <h2 className="font-semibold">ความคิดเห็น / Activity</h2>
        <div className="space-y-3">
          {ticket.comments?.map((c) => (
            <div
              key={c.id}
              className={`text-sm p-3 rounded ${
                c.is_internal ? "bg-amber-50" : "bg-slate-50"
              }`}
            >
              <p className="whitespace-pre-wrap">{c.content}</p>
              <p className="text-xs text-slate-400 mt-1">
                {c.is_internal ? "ภายใน · " : ""}
                {new Date(c.created_at).toLocaleString("th-TH")}
              </p>
            </div>
          ))}
          {ticket.comments?.length === 0 && (
            <p className="text-slate-400 text-sm">ยังไม่มีความคิดเห็น</p>
          )}
        </div>
        <CommentBox onSubmit={addComment} />
      </div>
    </div>
  );
}

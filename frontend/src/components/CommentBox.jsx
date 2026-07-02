import { useState } from "react";

export default function CommentBox({ onSubmit }) {
  const [content, setContent] = useState("");
  const [isInternal, setIsInternal] = useState(false);
  const [sending, setSending] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!content.trim()) return;
    setSending(true);
    try {
      await onSubmit(content, isInternal);
      setContent("");
    } finally {
      setSending(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2">
      <textarea
        className="input-dark w-full rounded-lg p-2 text-sm"
        rows={3}
        placeholder="เพิ่มความคิดเห็น..."
        value={content}
        onChange={(e) => setContent(e.target.value)}
      />
      <div className="flex items-center justify-between">
        <label className="flex items-center gap-2 text-sm text-slate-400">
          <input
            type="checkbox"
            checked={isInternal}
            onChange={(e) => setIsInternal(e.target.checked)}
          />
          เฉพาะ IT (ไม่ส่งหา user)
        </label>
        <button
          type="submit"
          disabled={sending}
          className="btn-primary px-4 py-1.5 rounded-lg text-sm font-medium"
        >
          ส่ง
        </button>
      </div>
    </form>
  );
}

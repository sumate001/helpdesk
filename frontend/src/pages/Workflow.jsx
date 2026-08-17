import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../api";

/* หน้าอธิบายการทำงานของระบบ — ให้ทีมใหม่/ผู้บริหารเห็นภาพรวมได้ใน 2 นาที
   ค่าที่เป็น "สวิตช์เปิดปิดได้" ดึงสดจาก /api/settings เพื่อให้แผนภาพตรงกับของจริงเสมอ
   (ไม่ใช่เอกสารที่ล้าสมัยตั้งแต่วันที่เขียน) — ถ้าไม่ใช่ admin จะดึงไม่ได้ ก็ซ่อนแถบนั้นไป */

const Chip = ({ tone = "slate", children }) => {
  const tones = {
    slate: "bg-white/5 text-slate-300 ring-white/10",
    indigo: "bg-indigo-400/10 text-indigo-300 ring-indigo-400/30",
    emerald: "bg-emerald-400/10 text-emerald-300 ring-emerald-400/30",
    amber: "bg-amber-400/10 text-amber-300 ring-amber-400/30",
    red: "bg-red-400/10 text-red-300 ring-red-400/30",
    sky: "bg-sky-400/10 text-sky-300 ring-sky-400/30",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full ring-1 whitespace-nowrap ${tones[tone]}`}>
      {children}
    </span>
  );
};

const Section = ({ title, subtitle, children }) => (
  <section className="space-y-3">
    <div>
      <h2 className="text-lg font-semibold text-slate-100">{title}</h2>
      {subtitle && <p className="text-sm text-slate-400 mt-0.5">{subtitle}</p>}
    </div>
    {children}
  </section>
);

/* ขั้นตอนแบบไทม์ไลน์ — เส้นต่อเนื่องด้านซ้าย อ่านไล่ลงได้ */
const Step = ({ n, title, children, tone = "indigo", last = false }) => {
  const dot = {
    indigo: "bg-indigo-400/20 text-indigo-300 ring-indigo-400/40",
    emerald: "bg-emerald-400/20 text-emerald-300 ring-emerald-400/40",
    amber: "bg-amber-400/20 text-amber-300 ring-amber-400/40",
    red: "bg-red-400/20 text-red-300 ring-red-400/40",
    sky: "bg-sky-400/20 text-sky-300 ring-sky-400/40",
  }[tone];
  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center shrink-0">
        <div
          className={`w-7 h-7 rounded-full ring-1 grid place-items-center text-xs font-bold ${dot}`}
        >
          {n}
        </div>
        {!last && <div className="w-px flex-1 bg-white/10 my-1" />}
      </div>
      <div className={`min-w-0 flex-1 ${last ? "" : "pb-4"}`}>
        <p className="font-medium text-slate-100 text-sm">{title}</p>
        <div className="text-sm text-slate-400 mt-1 space-y-1">{children}</div>
      </div>
    </div>
  );
};

/* กล่องขั้นตอนแนวนอน (ภาพรวม) — ล้นแล้วเลื่อนแนวนอนได้ ไม่ดันหน้าเว็บ */
const FlowRow = ({ items }) => (
  <div className="overflow-x-auto">
    <div className="flex items-stretch gap-2 min-w-max pb-1">
      {items.map((it, i) => (
        <div key={it.title} className="flex items-center gap-2">
          <div className="glass rounded-xl p-3 w-44">
            <p className="text-xl">{it.icon}</p>
            <p className="font-medium text-slate-100 text-sm mt-1">{it.title}</p>
            <p className="text-xs text-slate-400 mt-0.5">{it.desc}</p>
          </div>
          {i < items.length - 1 && <span className="text-slate-600 text-lg">→</span>}
        </div>
      ))}
    </div>
  </div>
);

const OVERVIEW = [
  { icon: "💬", title: "พนักงานทัก LINE", desc: "แชท 1-1 หรือในกลุ่ม / กรอกแบบฟอร์ม" },
  { icon: "🤖", title: "บอทคุยเก็บข้อมูล", desc: "ลองแก้เบื้องต้น + ถามสิ่งที่ขาด" },
  { icon: "🎫", title: "เปิดเคส", desc: "แจ้งทีม IT + ซิงก์เข้า itamtv" },
  { icon: "🔧", title: "ช่างรับงาน–ปิดงาน", desc: "กดจาก LINE หรือหน้า Dashboard" },
];

const STAFF_TOOLS = [
  { icon: "🔍", name: "ค้นหาเคส", desc: "ตามสถานะ/ผู้ดูแล/คำค้น" },
  { icon: "📄", name: "ดูรายละเอียดเคส", desc: "ผู้แจ้ง ผู้ดูแล ความเร่งด่วน" },
  { icon: "👥", name: "ค้นพนักงาน", desc: "ชื่อจริง รหัส แผนก" },
  { icon: "💻", name: "ดูอุปกรณ์ที่ถือครอง", desc: "จาก itamtv" },
  { icon: "🧑‍🔧", name: "รายชื่อช่าง", desc: "พร้อมจำนวนงานค้าง" },
  { icon: "📚", name: "ค้นคลังความรู้", desc: "นโยบาย + แบบฟอร์ม" },
  { icon: "✅", name: "เปลี่ยนสถานะเคส", desc: "รับงาน/ปิดงาน ทีละหลายใบได้" },
  { icon: "➕", name: "เปิดเคสแทนผู้แจ้ง", desc: "กรณีโทร/เดินมาแจ้ง" },
];

const JOBS = [
  { every: "ทุก 1 นาที", name: "ตามเรื่องที่ค้าง", desc: "ผู้ใช้เงียบกลางบทสนทนา → ถามซ้ำ แล้วเปิดเคสให้" },
  { every: "ทุก 1 นาที", name: "ตามงานช่าง", desc: "ถามความคืบหน้างานที่รับไว้ พร้อมปุ่มปิดเคส" },
  { every: "ทุก 1 นาที", name: "ตรวจ SLA", desc: "เกินเวลาตอบ/แก้ตามระดับความเร่งด่วน → ทำเครื่องหมายไว้" },
  { every: "ทุก 3 นาที", name: "ซิงก์ itamtv", desc: "ช่างปิดงานในระบบเดิม → สถานะที่นี่ตามให้อัตโนมัติ" },
];

export default function Workflow() {
  const [cfg, setCfg] = useState(null);

  useEffect(() => {
    // best-effort: staff ทั่วไปไม่มีสิทธิ์อ่าน settings → ไม่ต้องขึ้น error ให้รก
    api
      .get("/settings")
      .then(({ data }) => setCfg(data))
      .catch(() => setCfg(null));
  }, []);

  const onOff = (v) => (v ? { tone: "emerald", text: "เปิด" } : { tone: "slate", text: "ปิด" });

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-glow">การทำงานของระบบ</h1>
        <p className="text-sm text-slate-400 mt-1">
          ระบบรับแจ้งปัญหา IT ผ่าน LINE — บอทคุยเก็บข้อมูลและแก้เรื่องง่ายให้ก่อน
          เรื่องที่ต้องให้ช่างดูจึงเปิดเป็นเคส ส่วนคำขอใช้ทรัพยากรจะวิ่งผ่านการอนุมัติของหัวหน้า
        </p>
      </div>

      {cfg && (
        <div className="glass rounded-xl p-4">
          <p className="text-xs text-slate-500 mb-2">การตั้งค่าที่ใช้อยู่จริงตอนนี้</p>
          <div className="flex flex-wrap gap-2">
            <Chip tone="indigo">โมเดล: {cfg.OLLAMA_MODEL}</Chip>
            <Chip tone={onOff(cfg.TICKET_CONFIRM_REQUIRED).tone}>
              ยืนยันก่อนเปิดเคส: {onOff(cfg.TICKET_CONFIRM_REQUIRED).text}
            </Chip>
            <Chip tone={onOff(cfg.FOLLOWUP_ENABLED).tone}>
              ตามเรื่องอัตโนมัติ: {onOff(cfg.FOLLOWUP_ENABLED).text}
            </Chip>
            <Chip tone={onOff(cfg.ITAMTV_ENABLED).tone}>
              เชื่อม itamtv: {onOff(cfg.ITAMTV_ENABLED).text}
            </Chip>
            <Chip tone={onOff(cfg.EMPLOYEE_LOOKUP_ENABLED).tone}>
              ผูกข้อมูลพนักงาน: {onOff(cfg.EMPLOYEE_LOOKUP_ENABLED).text}
            </Chip>
          </div>
          <p className="text-xs text-slate-500 mt-2">
            แก้ได้ที่หน้า{" "}
            <Link to="/settings" className="text-indigo-300 hover:underline">
              ตั้งค่า
            </Link>{" "}
            — มีผลทันทีไม่ต้องรีสตาร์ต
          </p>
        </div>
      )}

      <Section title="ภาพรวม" subtitle="เส้นทางหลักของเรื่องหนึ่งเรื่อง ตั้งแต่พนักงานทักจนช่างปิดงาน">
        <FlowRow items={OVERVIEW} />
      </Section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Section
          title="1. แจ้งปัญหาผ่านแชท"
          subtitle="บอทไม่เปิดเคสจากข้อความเดียว แต่คุยเก็บข้อมูลก่อน"
        >
          <div className="glass rounded-xl p-4">
            <Step n="1" title="ผู้ใช้เล่าปัญหา">
              <p>
                แชท 1-1 รับทุกข้อความ · ในกลุ่มจะตอบเมื่อถูก @mention, ตอบกลับข้อความบอท
                หรือขึ้นต้นด้วยคำเรียก
              </p>
              <p>ส่งรูปหน้าจอ error ได้ — บอทอ่านรูปเป็นข้อมูลประกอบ</p>
            </Step>
            <Step n="2" title="ค้นคลังความรู้ก่อนตอบ">
              <p>
                ดึงนโยบาย/ขั้นตอนของบริษัทที่เกี่ยวข้องมาใช้ตอบ และดูว่าเรื่องนี้มี
                <Link to="/kb" className="text-indigo-300 hover:underline">
                  {" "}
                  แบบฟอร์ม{" "}
                </Link>
                รองรับไหม
              </p>
            </Step>
            <Step n="3" title="ลองแก้เบื้องต้น 1–2 ครั้ง">
              <p>แก้ได้ → บันทึกเป็นสถิติ ไม่รบกวนช่าง · แก้ไม่ได้ → เก็บข้อมูลเปิดเคสต่อ</p>
            </Step>
            <Step n="4" title="เก็บข้อมูลที่ยังขาด">
              <p>ชื่อ–ตึก–ชั้น เฉพาะที่ระบบยังไม่รู้ (ที่เคยบอกแล้วจะไม่ถามซ้ำ)</p>
            </Step>
            <Step n="5" title="ยืนยันแล้วเปิดเคส" tone="emerald">
              <p>สรุปให้ดูแล้วกดปุ่มยืนยัน → เปิดเคส แจ้งกลุ่ม IT พร้อมแนบรูปที่ส่งไว้</p>
              <p className="text-xs text-slate-500">
                ปิดขั้นยืนยันได้ที่หน้าตั้งค่า (ข้อมูลครบแล้วเปิดทันที)
              </p>
            </Step>
            <Step n="6" title="ถ้าผู้ใช้เงียบ" tone="amber" last>
              <p>เงียบ 10 นาที → บอทถามซ้ำ · เงียบต่อถึง 30 นาที → เปิดเคสให้อัตโนมัติ</p>
            </Step>
          </div>
        </Section>

        <Section
          title="2. คำขอที่ต้องอนุมัติ"
          subtitle="ขอใช้ทรัพยากร เช่น WiFi/VPN/เบิกอุปกรณ์"
        >
          <div className="glass rounded-xl p-4">
            <Step n="1" title="ผู้ขอกรอกแบบฟอร์ม">
              <p>บอทยื่นปุ่มฟอร์มให้เมื่อเรื่องตรงกับที่มีในคลังความรู้</p>
            </Step>
            <Step n="2" title="ระบบตัดสินว่าต้องอนุมัติไหม">
              <p>
                ดูจากกฎที่ตั้งไว้บนฟอร์ม ไม่ใช่การตีความของ AI — ระดับที่กำหนดไว้
                (เช่น ผู้จัดการขึ้นไป) ข้ามขั้นอนุมัติได้เลย
              </p>
            </Step>
            <Step n="3" title="หาผู้อนุมัติ" tone="sky">
              <p>
                ดูจาก
                <Link to="/approvals" className="text-indigo-300 hover:underline">
                  {" "}
                  ผังผู้อนุมัติ{" "}
                </Link>
                ตามแผนกของผู้ขอ · ยังไม่มีในผัง → บอทถามผู้ขอว่าหัวหน้าคือใคร
                แล้วเพิ่มเข้าผังให้เลย
              </p>
              <p className="text-xs text-slate-500">
                คนที่ถูกตั้งจะได้การ์ดแจ้ง พร้อมปุ่ม "ยอมรับ" บทบาทก่อนเสมอ
              </p>
            </Step>
            <Step n="4" title="หัวหน้ากดใน LINE">
              <p>
                การ์ดมีปุ่ม อนุมัติ ✅ / ไม่อนุมัติ ❌ — ระบบตรวจว่าคนกดคือผู้อนุมัติตัวจริง
                (ส่งต่อการ์ดให้คนอื่นกดแทนไม่ได้)
              </p>
            </Step>
            <Step n="5" title="ผลลัพธ์" tone="emerald" last>
              <p>
                <span className="text-emerald-300">อนุมัติ</span> → เคสเข้าคิวทีม IT ทันที ·{" "}
                <span className="text-red-300">ไม่อนุมัติ</span> → บอทถามเหตุผลแล้วแจ้งผู้ขอ
              </p>
              <p className="text-xs text-slate-500">
                หาผู้อนุมัติไม่ได้ / ยังไม่ผูก LINE → เด้งแจ้งกลุ่ม IT ให้ตามเอง ไม่ปล่อยค้างเงียบ
              </p>
            </Step>
          </div>
        </Section>
      </div>

      <Section
        title="3. ผู้ช่วยของเจ้าหน้าที่ IT"
        subtitle="เจ้าหน้าที่ที่ผูกบัญชีไว้ ทักบอทแล้วสั่งงานระบบได้จาก LINE โดยตรง"
      >
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {STAFF_TOOLS.map((t) => (
            <div key={t.name} className="glass rounded-xl p-3">
              <p className="text-lg">{t.icon}</p>
              <p className="text-sm font-medium text-slate-100 mt-1">{t.name}</p>
              <p className="text-xs text-slate-400 mt-0.5">{t.desc}</p>
            </div>
          ))}
        </div>
        <p className="text-xs text-slate-500">
          ผลลัพธ์ที่รายงานกลับมาถูกจัดรูปโดยระบบจากข้อมูลจริงเสมอ และการ "ลงมือทำ"
          ทุกอย่างต้องผ่านเครื่องมือเหล่านี้ — บอทอ้างว่าทำแล้วโดยไม่ได้ทำจริงไม่ได้
        </p>
      </Section>

      <Section title="4. งานที่ระบบทำเองเบื้องหลัง" subtitle="ไม่ต้องมีคนกด">
        <div className="glass rounded-xl divide-y divide-white/10">
          {JOBS.map((j) => (
            <div key={j.name} className="p-3 flex items-start gap-3">
              <Chip tone="sky">{j.every}</Chip>
              <div className="min-w-0">
                <p className="text-sm font-medium text-slate-100">{j.name}</p>
                <p className="text-xs text-slate-400 mt-0.5">{j.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </Section>

      <Section
        title="หลักการออกแบบ"
        subtitle="ทำไมระบบถึงเชื่อถือได้ ทั้งที่เบื้องหลังเป็น AI"
      >
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="glass rounded-xl p-4">
            <p className="text-sm font-medium text-slate-100">กฎอยู่ในโครงสร้าง ไม่ใช่คำสั่ง AI</p>
            <p className="text-xs text-slate-400 mt-1">
              เงื่อนไข เช่น "ต้องอนุมัติไหม / ใครอนุมัติ / สถานะไหนใช้ได้" เก็บเป็นข้อมูลที่โค้ด
              บังคับ AI จึงข้ามไม่ได้ ส่วนคลังความรู้มีไว้อธิบายให้คนอ่าน
            </p>
          </div>
          <div className="glass rounded-xl p-4">
            <p className="text-sm font-medium text-slate-100">ข้อมูลที่รายงานมาจากของจริง</p>
            <p className="text-xs text-slate-400 mt-1">
              ชื่อคน เลขเคส สถานะ อุปกรณ์ ต้องมาจากการอ่านฐานข้อมูลจริงเท่านั้น
              คำตอบที่อ้างเลขเคสหรืออ้างว่าทำสำเร็จโดยไม่มีหลักฐานจะถูกตัดทิ้ง
            </p>
          </div>
          <div className="glass rounded-xl p-4">
            <p className="text-sm font-medium text-slate-100">ไม่มีเรื่องค้างเงียบ</p>
            <p className="text-xs text-slate-400 mt-1">
              ผู้ใช้เงียบ ผู้อนุมัติไม่กด ส่งการ์ดไม่ได้ หรือระบบภายนอกล่ม — ทุกกรณีมีทางออกที่
              จบด้วยการแจ้งคนที่รับผิดชอบเสมอ
            </p>
          </div>
        </div>
      </Section>
    </div>
  );
}

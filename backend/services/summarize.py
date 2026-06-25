"""
Summarization Service (Anthropic Claude)
- สรุปการประชุมตามวาระ
- ระบุมติที่ประชุมและ action items
- จัดรูปแบบสำหรับรายงานทางการ ยสท.
"""
from typing import Optional
import anthropic

from config import get_settings, CLAUDE_MODEL

settings = get_settings()


SYSTEM_PROMPT = """คุณคือผู้ช่วยสรุปการประชุมของการยาสูบแห่งประเทศไทย (ยสท.)
มีความเชี่ยวชาญด้านการจัดทำรายงานการประชุมในรูปแบบทางราชการ

หน้าที่ของคุณ:
1. อ่าน transcript การประชุมและวาระที่กำหนดให้
2. สรุปสาระสำคัญแต่ละวาระอย่างกระชับและครบถ้วน
3. ระบุมติที่ประชุมอย่างชัดเจน
4. ระบุ action items พร้อมผู้รับผิดชอบและกำหนดเวลา (ถ้าปรากฏในการประชุม)

รูปแบบการตอบ: ใช้ภาษาไทยทางการ เหมาะสำหรับรายงานราชการ"""


def summarize_meeting(
    transcript_text: str,
    agenda_items: list[str],
    meeting_date: Optional[str] = None,
    meeting_title: Optional[str] = None,
    anthropic_api_key: Optional[str] = None,
) -> dict:
    """
    สรุปการประชุมด้วย Claude
    คืนค่า: {summary_by_agenda, action_items, full_summary}
    """
    api_key = anthropic_api_key or settings.anthropic_api_key
    client = anthropic.Anthropic(api_key=api_key)

    agenda_text = "\n".join(
        f"วาระที่ {i+1}: {item}" for i, item in enumerate(agenda_items)
    )

    header = ""
    if meeting_title:
        header += f"การประชุม: {meeting_title}\n"
    if meeting_date:
        header += f"วันที่: {meeting_date}\n"

    user_prompt = f"""{header}
วาระการประชุม:
{agenda_text}

transcript การประชุม:
{transcript_text}

กรุณาสรุปการประชุมตามรูปแบบต่อไปนี้:

สำหรับแต่ละวาระ ให้ระบุ:
## วาระที่ [N]: [ชื่อวาระ]

**สาระสำคัญ:**
[สรุปประเด็นสำคัญที่หารือ]

**มติที่ประชุม:**
[ระบุมติ หรือ "ที่ประชุมรับทราบ" ถ้าไม่มีมติ]

**ผู้รับผิดชอบ / กำหนดการ:**
[ระบุ action items ถ้ามี หรือ "-" ถ้าไม่มี]

---

และสรุปท้ายสุด:
## สรุป action items ทั้งหมด
[รายการ action items ทั้งหมด พร้อมผู้รับผิดชอบ]"""

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=3000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    full_summary = response.content[0].text

    # แยก action items ออกมา
    action_items = _extract_action_items(full_summary)

    # แยกสรุปตามวาระ
    summary_by_agenda = _parse_agenda_summaries(full_summary, agenda_items)

    return {
        "full_summary": full_summary,
        "summary_by_agenda": summary_by_agenda,
        "action_items": action_items,
    }


def _extract_action_items(summary_text: str) -> list[dict]:
    """ดึง action items จาก summary"""
    items = []
    in_action_section = False

    for line in summary_text.split("\n"):
        if "action items" in line.lower() or "สรุป action" in line:
            in_action_section = True
            continue
        if in_action_section and line.startswith("##"):
            break
        if in_action_section and line.strip().startswith(("-", "•", "*", "1", "2", "3")):
            cleaned = line.strip().lstrip("-•*0123456789. ")
            if cleaned:
                items.append({"text": cleaned, "done": False})

    return items


def _parse_agenda_summaries(summary_text: str, agenda_items: list[str]) -> list[dict]:
    """แยกสรุปของแต่ละวาระออกมาเป็น list"""
    result = []
    sections = summary_text.split("## วาระที่")

    for i, item in enumerate(agenda_items):
        section_text = ""
        for sec in sections:
            if sec.strip().startswith(str(i + 1)):
                section_text = "## วาระที่" + sec
                break

        result.append({
            "agenda_number": i + 1,
            "agenda_title": item,
            "summary": section_text.strip() or f"(ไม่พบข้อมูลวาระที่ {i+1} ใน transcript)",
        })

    return result

# Tech Radar (อัปเดตอัตโนมัติ)

แดชบอร์ดสำหรับ dev ที่อยากรู้ว่าตอนนี้เทรนไหนร้อน โมเดลไหนน่าใช้ และมีอะไรเปลี่ยนจากรอบก่อน — ดึงข้อมูลอัตโนมัติแล้ว deploy บน GitHub Pages

## ได้อะไรบ้าง

- **เทรนปี** — สรุปธีมที่กำลังสนใจ + คำแนะนำ น่าใช้ / น่าจับตา / ระวัง
- **AI Models** — เทียบ Artificial Analysis + LMArena + ราคา/ความเร็ว
- **ข้อมูลสด** — OpenRouter, HN, GitHub (รวมแยกภาษา), Hugging Face, npm, CISA KEV, EPSS
- **diff จากรอบก่อน** + ประวัติรายวันใน `history/`
- แก้รายการเฝ้าดูได้ที่ `watchlist.yml`

หน้าเว็บ: `https://<user>.github.io/tech-radar/`

## วิธีเร็ว (คำสั่งเดียว)

1. ติดตั้ง [GitHub CLI](https://cli.github.com)
2. สมัคร [Artificial Analysis](https://artificialanalysis.ai/) แล้วสร้าง API key (ถ้ามี)
3. รัน `./setup.sh tech-radar`

สคริปต์จะสร้าง repo สาธารณะ, ใส่ secret, เปิด Pages, แล้วรัน workflow ครั้งแรก

## วิธีทำเอง

1. สร้าง repo สาธารณะ แล้วอัปโหลดไฟล์ทั้งหมด (รวม `.github`)
2. Settings → Secrets → Actions → `AA_API_KEY`
3. Settings → Pages → Source = GitHub Actions
4. Actions → update-radar → Run workflow

## รันท้องถิ่น

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export AA_API_KEY=...   # ถ้ามี
export GITHUB_TOKEN=... # ถ้ามี (เพิ่มโควต้า GitHub API)
python update_radar.py
python -m http.server 8080
# เปิด http://localhost:8080
```

## หมายเหตุ

- รันทุก 3 ชั่วโมง (เวลาจริงอาจเลื่อนได้ตามคิว Actions)
- DB-Engines / Stack Overflow Survey ไม่มี API จึงไม่อัปเดตเอง
- ต้องแสดงที่มา Artificial Analysis ตามเงื่อนไข — อย่าใส่ API key ในโค้ดฝั่งเบราว์เซอร์
- คำแนะนำในแท็บเทรนปีมาจากสัญญาณบนบอร์ด ไม่ใช่คำรับประกันคุณภาพผลิตภัณฑ์

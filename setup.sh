#!/usr/bin/env bash
# สร้าง repo, ตั้งค่า secret, เปิด GitHub Pages และสั่งรันครั้งแรก
# ใช้: ./setup.sh [ชื่อ-repo]   (Windows: รันใน Git Bash)
set -e
REPO="${1:-tech-radar}"
cd "$(dirname "$0")"
if ! command -v gh >/dev/null; then echo "ติดตั้ง GitHub CLI ก่อน: https://cli.github.com"; exit 1; fi
gh auth status >/dev/null 2>&1 || gh auth login
git init -q -b main 2>/dev/null || true
git add -A
git commit -qm "init tech radar" 2>/dev/null || true
if gh repo view "$REPO" >/dev/null 2>&1; then
  echo "repo $REPO มีอยู่แล้ว — จะ push ขึ้น origin"
  git remote remove origin 2>/dev/null || true
  gh repo view "$REPO" --json url -q .url | xargs -I{} git remote add origin {}
  git push -u origin HEAD:main
else
  gh repo create "$REPO" --public --source=. --push
fi
OWNER="$(gh api user -q .login)"
if [ -z "$AA_API_KEY" ]; then read -rsp "Artificial Analysis API key (กด Enter ข้ามได้): " AA_API_KEY; echo; fi
if [ -n "$AA_API_KEY" ]; then gh secret set AA_API_KEY --body "$AA_API_KEY"; fi
gh api -X POST "repos/$OWNER/$REPO/pages" -f build_type=workflow >/dev/null 2>&1 \
  || gh api -X PUT "repos/$OWNER/$REPO/pages" -f build_type=workflow >/dev/null 2>&1 \
  || echo "ตั้ง Pages เองที่ Settings > Pages > Source = GitHub Actions"
gh workflow run update-radar.yml >/dev/null 2>&1 || true
echo "เสร็จแล้ว รอประมาณ 2-5 นาที แล้วเปิด https://$OWNER.github.io/$REPO/"
echo "ดูสถานะรัน: https://github.com/$OWNER/$REPO/actions"

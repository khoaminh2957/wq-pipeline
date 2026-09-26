# Handoff — frame-library work (for a new session; conversation history does not transfer)

Written 2026-09-26 from the local VS Code session 822757b8. Read CLAUDE.md (RULE 0/1/2) first, then this, then
docs/frames/00_decisions.md.

## The goal (Khoa, /goal 2026-09-24, verbatim)

"tôi có 1 hypothesis: nếu dựng sẵn các câu trúc (nhiều khung rồi thay các field phù hợp thì tỉ lệ cải thiện alpha sẽ
tăng lên bao nhiêu), bước 1: tìm các bộ khung (gồm nhiều hàm + field kèm sẵn để set điều kiện) có kết quả sau khi sim
alpha cao hơn các khung khác, tạo 100 khung trước, bước 2 thử với nhiều field và đo kết quả performance trên IS trên
các khung đó có chứng minh được là khung đó có thật sự bền hay ko hay chỉ ăn may, bước 3: lưu các khung đó với trong
thư viện khung (tạo hẵn 1 thư viện khung được hệ thống hoá tuỳ vào đặc tính và chức năng), cứ thể tạo thật nhiều khung
và lọc rồi đưa vào thư viện khung, sau này từ các field phù hợp trong thư viện field mà lắp vào thư viện khung để tạo
alpha, bạn hãy kiểm chứng nhiều vòng với hypothesis của tôi"

## Where things stand

| step | state | files |
|---|---|---|
| Phase A (history, no quota) | done: 66,058 alphas -> 33,007 frames; split-half reliability r = 0.64 within USA/d1 forge era (near-synonym fields only); 100 candidate frames (43 mined, 57 novel) | 10_, 11_, 12_ |
| Round 1 (4 arms, same day) | done: no pre-registered gain; LOW_SHARPE a 0.6 % vs incumbent 1.3 %; settings and the option/short-sale datasets confound | 13a, 20_ |
| Round 2 (fresh fields, all frames) | done: B1 (LS rank correlation) NOT met, p 0.10; on y08 rankings replicate (rho 0.83; 0.76 inside option/short-sale frames); top quintile kept ~88 % of its lead | 13, 21_ |
| Submitted-alpha frames (245 ACTIVE -> 233 frames) screen | done: 830 scored, y08 0.84 % with other-dataset fields (F12) | 13c, 22_ |
| Round 4 | SCHEDULED on the VPS: systemd timer `frames-r4` 2026-09-26 11:05 +07 (replication of 74 frames + same-dataset arm, 480 sims); needs an auth tap | 13d |
| Frames loop (replaces the incumbent, F5) | BUILT, NOT SIGNED, NOT DEPLOYED: all six modules have open SERIOUS items | 30_loop_build_audit.md |
| Incumbent forge loop | STOPPED and DISABLED on the VPS since 2026-09-24 21:48 (F5) | — |

Across R1B, R2, R3S, R3SB (3,530 sims): 0 alphas cleared all 7 binding checks; nothing was submitted.

## Open items (in order)

1. Read out R4 after it runs (13d): 13c's robust count on arm rep; same-vs-rep y08 difference (sign-flip over frames);
   SELF correlation of arm-same y08 rows against their original alphas.
2. Fix the loop's SERIOUS items (30_loop_build_audit.md): planner P1–P7, evidence E1, submit S1/S3/S6, driver D1,
   validator S1, integration I1; P3 and P5 need Khoa's tick (GROUP-field rule in the loop; F8's admission gate).
   F11–F13 (submitted frames, universes) are not in the loop yet.
3. Only then: deploy the loop (attended: Khoa), install wq-frames, start with an auth tap.

## What only the MacBook can do

Everything touching the VPS (root@160.25.88.163, /opt/wq): reading live journals, shipping experiment files to
/opt/wq/experiments/frames/, systemd timers, auth links (`tools/mint_link.py --force` on the VPS), deploys. The SSH
key never leaves the Mac. A cloud session works on code, tests and analysis of the data bundle only.

## How rounds are run (for reference)

Plan offline (framelib/experiments/*.py) -> scp the plan to /opt/wq/experiments/frames/plan_abc_<EXP>.json ->
`NO_D=1 EXP=<EXP> SEED=<s> bash /opt/wq/experiments/frames/frames_round.sh` (dry) then with `--live` under setsid or a
systemd-run timer -> copy journal + .plan.json + recovered.jsonl back -> read out with the pre-registered script.
Every multisim parent holds one arm and one universe (dispatch_round.py). Every pre-registration's sha256 goes into
00_decisions.md before the first row.

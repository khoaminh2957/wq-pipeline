#!/usr/bin/env python3
"""The message catalogue: nine messages, each with a declared trigger path.

Design rules, each traceable to a measured failure rather than to taste:

  I1  Name the box.  A red alert built on one machine was once aimed at the shared channel while
      describing a pipeline that only runs on the other.
  I2  A file is not a state.  Say what was read and when.
  I3  An mtime is not production.  The health light was held green for days by a GET-only writer
      that never simulated anything.
  I4  A count names its unit AND its population.  A row count was printed under the words
      "distinct alphas"; the distinct count is monotone and could never have been that number.
  I5  An age names what it is the age of.
  I6  A filter names itself and its own count.
  I7  An irreversible outcome is never silent and never inferred from text.
  I9  A level fact does not repeat: 36 copies of one verdict went out inside one outage, and
      because their bodies differed slightly a body-hash suppressor would have stopped none.
  I10 Name only the cause the code actually captured.
  I11 Never assert a negative you did not check.

The 'best alpha' block is priority 0 and renders SECOND, immediately after the header.  Under the
old construction it sat last inside a 4502-byte body that was sliced at 1900 characters, so the
operator's standing requirement that every announcement name the best alpha had never once been
delivered.  Position in the assembly is the fix.
"""
import json
import os
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import outbox as OB       # noqa: E402
import notify_lint as LINT  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOST_FILE = os.path.join(ROOT, "state", "host.json")


# --------------------------------------------------------------------------- I1: identity

def host_tag():
    """`[role ip]`.  Written at deploy time; guessed from nothing.

    hostname, path and platform tests are all guesses, and the module that carries the canonical
    host identity is not deployed on the VPS at all -- so the marker is a file that the deploy
    writes, and its absence is stated rather than papered over.
    """
    try:
        with open(HOST_FILE) as fh:
            h = json.load(fh)
        role, ip = h.get("role"), h.get("ip")
        if role and ip:
            return "%s %s" % (role, ip)
        if role:
            return role
    except (OSError, ValueError):
        pass
    return "máy chưa khai danh (%s)" % socket.gethostname()


def header(text):
    return "[%s] {seq} %s" % (host_tag(), text)


def _fmt_hhmm(ts):
    if not ts:
        return "--:--"
    return time.strftime("%H:%M", time.localtime(ts))


def deadman_line():
    """The dead-man carrier.  Costs no extra message: it rides on a message the operator is
    already waiting for.  Its whole job is that a notifier which has stopped delivering cannot
    keep looking healthy -- which is exactly what happened for 113 days on the other machine,
    where every on-box liveness predicate returned TRUE and only 'a message arrived' was false."""
    sent, enq, last_ok = OB.stats()
    return "· outbox %d/%d gửi được trong 24h, lần cuối %s" % (sent, enq, _fmt_hhmm(last_ok))


def best_block(best):
    """best: dict or None.  NEVER omitted -- a silently absent field reads as 'fine'."""
    if not best:
        return (0, "best", "· alpha tốt nhất: chưa đọc được")
    # `climb.best_alpha()` returns the platform id under the key `alpha`. This read `id`, which is
    # never present, so the operator's single most-repeated standing requirement -- name the best
    # alpha in every announcement -- rendered a literal "?" in every message the system has ever
    # sent. The test missed it because the stub dict used the wrong key name too, so the fixture
    # agreed with the bug instead of with the producer.
    aid = best.get("alpha") or best.get("id")
    bits = ["· alpha tốt nhất %s" % (aid or "chưa đọc được")]
    for label, key, fmt in (("sharpe", "sharpe", "%.2f"), ("fitness", "fitness", "%.2f"),
                            ("turnover", "turnover", "%.3f")):
        v = best.get(key)
        bits.append("%s %s" % (label, (fmt % v) if isinstance(v, (int, float)) else "--"))
    line = " · ".join(bits)
    yrs = best.get("years_with_book")
    if isinstance(yrs, (int, float)):
        tot = best.get("years_total", 10)
        line += "\n  sổ theo năm: %g/%g năm có sổ" % (yrs, tot)
        if yrs < tot:
            line += " — sharpe đo trên %g năm, KHÔNG phải %g" % (yrs, tot)
    else:
        line += "\n  sổ theo năm: chưa đọc"
    return (0, "best", line)


# --------------------------------------------------------------------------- M6: the safety message

M6_NULL_TEMPLATE = (
    "SUBMIT POST {alpha} → KHÔNG CÓ TRẢ LỜI ({exc_class}), ghi sổ lúc {posted_at}.\n"
    "POST CÓ THỂ ĐÃ TỚI NƠI. ĐỪNG POST LẠI.\n"
    "Đọc trạng thái bằng ĐÚNG một lệnh:  GET /alphas/{alpha}\n"
    "  · status ≠ UNSUBMITTED, hoặc dateSubmitted ≠ null  →  BẢN NỘP ĐÃ TỒN TẠI, slot đã tiêu. DỪNG.\n"
    "  · status = UNSUBMITTED và dateSubmitted = null     →  chưa có bản nộp nào được ghi nhận.\n"
    "Chỉ Khoa mới được quyết POST lại, và chỉ ở nhánh thứ hai."
)


def m6_post_outcome(alpha, http, posted_at, exc_class=None, adjudication=None, best=None,
                    cap_done=None):
    """The POST-outcome message.  Every branch states the RECORD, never the adjudication.

    The null branch is non-negotiable: a transport failure is not a rejection, and the endpoint
    that looks like it would settle the question cannot, because a submitted alpha answers 404
    exactly like an alpha that was never POSTed (measured 2026-08-05).
    """
    ts = time.strftime("%F %T", time.localtime(posted_at)) if posted_at else "chưa ghi"
    if http is None:
        body = M6_NULL_TEMPLATE.format(alpha=alpha, exc_class=exc_class or "không rõ", posted_at=ts)
        branch = "null"
    elif http in (200, 201):
        body = ("SUBMIT POST %s → HTTP %s, ghi sổ lúc %s.\n"
                "Job đã nhận — KẾT QUẢ CUỐI CHƯA ĐỌC." % (alpha, http, ts))
        if adjudication:
            body += ("\nPhán quyết đọc lúc %s: status %s, dateSubmitted %s, stage %s (GET /alphas/%s)"
                     % (adjudication.get("checked_at", "?"), adjudication.get("status", "?"),
                        adjudication.get("dateSubmitted", "?"), adjudication.get("stage", "?"), alpha))
        else:
            body += "\nPhán quyết: chưa đọc."
        branch = str(http)
    elif http == 403:
        body = ("SUBMIT POST %s → HTTP 403, ghi sổ lúc %s.\n"
                "CHUNG THẨM — slot đã tiêu vĩnh viễn." % (alpha, ts))
        branch = "403"
    else:
        body = ("SUBMIT POST %s → HTTP %s, ghi sổ lúc %s.\n"
                "KHÔNG phải kết quả nộp." % (alpha, http, ts))
        branch = str(http)

    if cap_done is not None:
        # The loop's cap is a literal in a shell script; the platform's cap lives in a module that
        # is not deployed on the box that runs this.  I4 demands we say WHICH cap this is.
        body += ("\nCap %s/1 (trần của vòng lặp; trần nền tảng không đọc được trên máy này)"
                 % cap_done)

    blocks = [(0, "head", header(body)), best_block(best), (2, "deadman", deadman_line())]
    LINT.assert_safe("\n".join(b[2] for b in blocks), branch=branch, submit_related=True)
    return dict(kind="m6a", channel="climb", blocks=blocks, cls="attention",
                dedup_key="m6a:%s:%s" % (alpha, http), retry_on_unknown=True)


def m6_gem_edge(gem_ids, best=None, unsubmitted_ids=None):
    """The gem edge, keyed on the SET of ids and never on their count.

    The count-keyed shell variable it replaces re-announced the same five gems four times, three
    of those immediately after a process restart wiped the variable.  A content key makes all of
    those harmless without having to decide which one caused which.

    The count also passes through the submitted ledger first: the tier-4 population includes an
    alpha whose slot is already spent, so announcing the raw count reports a burned alpha as
    available.
    """
    ids = sorted(set(gem_ids or []))
    live = sorted(set(unsubmitted_ids)) if unsubmitted_ids is not None else None
    if live is None:
        line = "GEM tier-4: %d trong sổ (chưa lọc theo sổ đã nộp)" % len(ids)
    else:
        spent = len(ids) - len(live)
        line = ("GEM tier-4: %d chưa nộp / %d trong sổ (%d đã tiêu slot)"
                % (len(live), len(ids), spent))
    line += "\n" + ", ".join(ids[:12]) + (" …" if len(ids) > 12 else "")
    blocks = [(0, "head", header(line)), best_block(best), (2, "deadman", deadman_line())]
    return dict(kind="m6c", channel="climb", blocks=blocks, cls="attention",
                dedup_key="gem:%s" % OB.sha12("|".join(ids)))


# --------------------------------------------------------------------------- M3: the loop

_STATE_TEXT = {
    "DEAD": ("CLIMB DỪNG — khoá {lock} không còn ai giữ.", True),
    "NEVER_STARTED_THIS_BOOT": ("CLIMB CHƯA CHẠY LẦN NÀO SAU KHI BOOT — tệp khoá {lock} không tồn "
                                "tại và không có nhịp tim nào của lần boot này.", True),
    "ORPHAN_LOCK": ("CLIMB TREO — khoá {lock} vẫn bị giữ nhưng tiến trình ghi nhịp đã biến mất "
                    "(một tiến trình con còn ôm khoá).", False),
    "LOCK_IDENTITY_UNKNOWN": ("CLIMB — tệp khoá {lock} đã bị thay dưới một vòng lặp đang chạy.",
                              False),
    "UNREACHABLE": ("CLIMB — KHÔNG ĐO ĐƯỢC (không ssh tới được máy chạy).", False),
}


def m3_down(state, lock, detect_ts, silent_s=None, phase=None, cycle=None, rnd=None,
            last_log=None, complete_rows=None, unchanged_min=None, reason=None,
            observation=None, remedy=None, best=None):
    """Five DOWN variants, one per liveness state, with different remedy rules.

    Two things this deliberately does NOT do:

      * It does not print a to-the-second stop time.  A 60-second checker learns only that the loop
        stopped within the last 60 seconds; a precise stop time can be printed only when the loop
        left one, and one of the four historical deaths left no end marker at all.
      * It does not name a cause the code did not capture.  The auth probe runs under 2>/dev/null
        and exits 0/1, so neither a status code nor an exception class survives it.
    """
    tmpl, may_restart = _STATE_TEXT.get(state, ("CLIMB — trạng thái %s." % state, False))
    lines = [tmpl.format(lock=lock)]
    lines.append("Phát hiện lúc %s%s." % (time.strftime("%F %T", time.localtime(detect_ts)),
                                          ", im lặng %dm trước đó" % (silent_s // 60)
                                          if silent_s else ""))
    if phase or cycle is not None:
        lines.append("Pha cuối: %s · chu kỳ %s vòng %s" % (phase or "chưa rõ", cycle, rnd))
    if last_log:
        lines.append('Dòng log cuối: "%s"' % last_log.strip()[:160])
    if complete_rows is not None:
        lines.append("%d dòng COMPLETE/WARNING (đếm SẢN XUẤT, không phải số lần gọi)%s."
                     % (complete_rows,
                        ", không đổi %dm" % unchanged_min if unchanged_min is not None else ""))
    lines.append("Lý do: %s" % (reason or "chưa rõ (mã trạng thái không được ghi lại)"))
    if observation:
        lines.append(observation)
    if may_restart and remedy:
        lines.append("Không có gì tự khởi động lại. %s" % remedy)
    elif not may_restart:
        lines.append("KHÔNG khởi động cái thứ hai.")

    blocks = [(0, "head", header("\n".join(lines))), best_block(best),
              (2, "deadman", deadman_line())]
    return dict(kind="m3", channel="climb", blocks=blocks, cls="attention",
                dedup_key="m3:%s:%d" % (state, int(detect_ts)),
                verdict_key="m3:%s" % state)


def m3_up(state_from, detect_ts, cycle=None, rnd=None, best=None):
    line = ("CLIMB CHẠY LẠI — phát hiện lúc %s (trước đó: %s)%s."
            % (time.strftime("%F %T", time.localtime(detect_ts)), state_from,
               ", chu kỳ %s vòng %s" % (cycle, rnd) if cycle is not None else ""))
    blocks = [(0, "head", header(line)), best_block(best), (2, "deadman", deadman_line())]
    return dict(kind="m3", channel="climb", blocks=blocks, cls="attention",
                dedup_key="m3up:%d" % int(detect_ts), verdict_key="m3:RUNNING")


# --------------------------------------------------------------------------- M4, M5, M7, M8, M9

def m4_round_failed(rc, n_consecutive, total_failed, total_rounds, jfile, reason=None, best=None):
    line = ("VÒNG HỎNG: exit %s. Lý do: %s. %d vòng liên tiếp hỏng (tổng %d/%d vòng, %s)."
            % (rc, reason or "chưa rõ (nền tảng không trả về trường message cho bản ghi FAIL)",
               n_consecutive, total_failed, total_rounds, jfile))
    blocks = [(0, "head", header(line)), best_block(best), (2, "deadman", deadman_line())]
    return dict(kind="m4", channel="climb", blocks=blocks, cls="attention",
                dedup_key="m4:%s:%d" % (rc, n_consecutive))


def m5_corr_blocked(measured, total, k_rounds, codes, never_queued, n_signals, no_reading,
                    top_n, best=None):
    """Two counts, two different words.  'Never entered the measurement queue' and 'entered but
    holds no reading' were previously collapsed into one number, which reported 81 where the true
    figure was 100 -- inside the message whose whole job is to make counts honest."""
    line = ("KÊNH CORR TẮC: đo được %d/%d tín hiệu, %d vòng liền = 0 (state/climb/probe.jsonl).\n"
            "Mã trả về trong %d vòng: computing %s · 429 %s · 401 %s — ba tình huống, ba hành động "
            "khác nhau.\n"
            "%d/%d tín hiệu tier-3 CHƯA VÀO HÀNG ĐỢI ĐO (probe lấy top %s); %d/%d chưa có số đọc nào."
            % (measured, total, k_rounds, k_rounds, codes.get("computing", 0), codes.get("429", 0),
               codes.get("401", 0), never_queued, n_signals, top_n, no_reading, n_signals))
    blocks = [(0, "head", header(line)), best_block(best), (2, "deadman", deadman_line())]
    return dict(kind="m5", channel="climb", blocks=blocks, cls="attention",
                dedup_key="m5:blocked:%d" % k_rounds, verdict_key="m5:BLOCKED")


def m7_cycle(event, cycle, rnd, kind_, n, best_score, prev_score, screened, tier3, best=None):
    """History entries carry no timestamp, so this says WHAT happened and never WHEN."""
    line = ("CHU KỲ: %s — chu kỳ %s vòng %s (%s), n=%s, điểm %s (trước %s), qua sàng %s, tier-3 %s."
            % (event, cycle, rnd, kind_, n, best_score, prev_score, screened, tier3))
    blocks = [(0, "head", header(line)), best_block(best), (3, "deadman", deadman_line())]
    return dict(kind="m7", channel="climb", blocks=blocks, cls="routine",
                dedup_key="m7:%s:%s:%s:%s" % (event, cycle, rnd, best_score))


def m10_gem_candidate(n_new, total, best=None):
    """A GEM CANDIDATE is not a gem. Khoa fixed the vocabulary on 2026-08-18: candidate = through
    the screen and eligible for a correlation read; gem = correlations measured, every gate passed,
    submittable; super gem = self-corr under 0.30. Saying "gem" here would report a result that has
    not happened yet, and this project has published that exact overstatement before."""
    line = ("GEM CANDIDATE: %d cái mới (tổng %d đang chờ đo tương quan). "
            "Chưa phải gem — còn phải đo prod/self và qua hết cổng." % (n_new, total))
    return dict(kind="m10", channel="climb", blocks=[(0, "head", header(line)),
                                                     best_block(best),
                                                     (3, "deadman", deadman_line())],
                cls="attention", dedup_key="m10:%d:%d" % (n_new, total))


def m11_auth_expiring(mins_left, url=None):
    """The session lives exactly 4 hours and CANNOT be refreshed, so its death is PREDICTABLE and
    nothing should have to wait for a 401 to discover it. On 2026-08-18 it died mid-round and 29 of
    31 rows carrying the new operators were lost to it -- a whole measurement, not just some quota.
    """
    line = ("AUTH SẮP HẾT: còn ~%d phút. Phiên sống 4 tiếng và KHÔNG gia hạn được — "
            "tap link trước khi nó chết." % mins_left)
    blocks = [(0, "head", header(line))]
    if url:
        blocks.append((1, "link", url))
    blocks.append((3, "deadman", deadman_line()))
    return dict(kind="m11", channel="auth", blocks=blocks, cls="attention",
                dedup_key="m11:%d" % (mins_left // 10))


def m12_forge_digest(sims, platform_pass, candidates, corr_measured, eligible, posted, cells_filled,
                     per_1000, dsr_rate, queue_line, best=None):
    """Once per ET day at 11:00 (C24). Counts are the forge journal's own 24-hour window, labelled as
    such; nothing here is a platform quota number."""
    lines = [
        "FORGE 24h: %d sim, %d qua cổng nền tảng, %d ứng viên (DSR≥0.95), %d đã đo tương quan, "
        "%d đủ điều kiện nộp, %d đã POST." % (sims, platform_pass, candidates, corr_measured, eligible, posted),
        "Ô pyramid lấp thêm: %s." % (", ".join(cells_filled) if cells_filled else "chưa"),
        "Nộp-được/1.000 sim: %.1f · tỉ lệ qua DSR trong số qua cổng: %.0f%%." % (per_1000, 100 * dsr_rate),
        queue_line,
    ]
    blocks = [(0, "head", header("\n".join(lines))), best_block(best), (2, "deadman", deadman_line())]
    return dict(kind="m12", channel="climb", blocks=blocks, cls="routine",
                dedup_key="m12:%s" % time.strftime("%F", time.localtime()))


def m13_hypothesis_queue(kind_, n_hypotheses, n_made, n_requested, reachable_cells):
    """Hypothesis-queue alerts (C24): `loaded` when the library changed, `low` when a round could
    fill under half of what it asked for, `exhausted` when nothing is left for any reachable cell.
    Hypotheses are authored offline; this is the only signal that the library needs work."""
    if kind_ == "loaded":
        line = ("HÀNG ĐỢI GIẢ THUYẾT: thư viện đổi — %d giả thuyết, %d ô pyramid với tới được."
                % (n_hypotheses, reachable_cells))
        cls = "routine"
    elif kind_ == "exhausted":
        line = ("HÀNG ĐỢI GIẢ THUYẾT CẠN: %d giả thuyết không còn tổ hợp mới cho %d ô với tới được. "
                "Vòng bị bỏ; cần viết thêm giả thuyết." % (n_hypotheses, reachable_cells))
        cls = "attention"
    else:
        line = ("HÀNG ĐỢI GIẢ THUYẾT THẤP: vòng xin %d chỉ ghép được %d (%d giả thuyết, %d ô)."
                % (n_requested, n_made, n_hypotheses, reachable_cells))
        cls = "attention"
    return dict(kind="m13", channel="climb", blocks=[(0, "head", header(line)), (3, "deadman", deadman_line())],
                cls=cls, dedup_key="m13:%s:%d:%d" % (kind_, n_hypotheses, n_made))


def m7_history_truncated(old_len, new_len):
    line = ("NGUỒN LỊCH SỬ BỊ CẮT: state.json còn %d mục (trước %d). Con trỏ đã đặt lại; "
            "các mốc trước đó sẽ không được thông báo lại." % (new_len, old_len))
    return dict(kind="m7trunc", channel="climb", blocks=[(0, "head", header(line))],
                cls="attention", dedup_key="m7trunc:%d:%d" % (old_len, new_len))


def m8_digest(platform_sims, platform_label, journal_children, journal_posts, gems_live, gems_total,
              cells_line, quota_reset, dead_members=None, best=None, book_line=None):
    """Twice per ET day.  Prints the PLATFORM's own number under the PLATFORM's own label, and does
    not dress our arithmetic as quota: whether the platform's daily counter counts children or
    POSTs is UNKNOWN, and the two differ by an order of magnitude."""
    lines = [
        "TỔNG KẾT: %s %s (số của nền tảng)." % (platform_label, platform_sims),
        "Sổ của ta: %s lượt POST cha, %s con (khớp bằng phép nối, KHÔNG phải số quota)."
        % (journal_posts, journal_children),
        "GEM tier-4: %s chưa nộp / %s trong sổ." % (gems_live, gems_total),
        book_line or "sổ theo năm: chưa đọc",
        cells_line,
        "Quota mở lại: %s." % quota_reset,
    ]
    if dead_members:
        lines.append("Thành phần chết: " + ", ".join(dead_members))
    blocks = [(0, "head", header("\n".join(lines))), best_block(best),
              (2, "deadman", deadman_line())]
    return dict(kind="m8", channel="climb", blocks=blocks, cls="routine",
                dedup_key="m8:%s" % time.strftime("%F-%H", time.localtime()))


def m9_member_changed(member, old, new, n0, n1, last_exit, code, extra=None):
    """A component changed state.  The probe for member k must be run by a process whose unit is
    NOT k -- the auth unit crashed 44 times on a syntax error inside its own notification string,
    so it could never have reported itself.

    Restart counters are not a usable trigger either: that unit crash-looped 44 times and its
    restart counter reads 0 today.  This keys on exit records instead.
    """
    line = ("%s: %s → %s. Số lần khởi động lại %s→%s, thoát lần cuối %s, mã %s."
            % (member, old, new, n0, n1, last_exit, code))
    if extra:
        line += "\n" + extra
    return dict(kind="m9", channel="climb", blocks=[(0, "head", header(line))], cls="attention",
                dedup_key="m9:%s:%s:%s" % (member, new, last_exit),
                verdict_key="m9:%s:%s" % (member, new))


# --------------------------------------------------------------------------- M1, M2

def m1_tap_auth(url, minted_ts, expires_ts, used, cap, et_day):
    line = ("TAP AUTH — mint lúc %s, sống tới ~%s. Mint %s/%s (ngày ET %s, quy đổi UTC−4, chưa xử "
            "lý DST). %s" % (_fmt_hhmm(minted_ts), _fmt_hhmm(expires_ts), used, cap, et_day, url))
    blocks = [(0, "head", header(line)), (1, "deadman", deadman_line())]
    return dict(kind="m1", channel="auth", blocks=blocks, cls="attention",
                dedup_key="m1:%s" % OB.sha12(url))


def m2_auth_blocked(blocked, detail=None, wall_source=None):
    if blocked:
        line = "AUTH TẮC: %s (chưa xác minh với endpoint)." % (detail or "chưa rõ")
    else:
        line = "AUTH MỞ LẠI: %s (chưa xác minh với endpoint)." % (detail or "đọc được 200")
    if wall_source:
        line += "\nNguồn: %s" % wall_source
    return dict(kind="m2", channel="auth", blocks=[(0, "head", header(line))], cls="attention",
                dedup_key="m2:%s:%s" % (blocked, detail), verdict_key="m2:%s" % blocked)


# --------------------------------------------------------------------------- dispatch

def send(msg):
    """Enqueue a rendered message.  Local write only; raises if it cannot."""
    return OB.enqueue(kind=msg["kind"], channel=msg["channel"], blocks=msg["blocks"],
                      dedup_key=msg["dedup_key"], verdict_key=msg.get("verdict_key"),
                      cls=msg.get("cls", "routine"),
                      retry_on_unknown=msg.get("retry_on_unknown", True))


def render(msg):
    """The exact body that would be sent, without enqueueing.  Used by the tests and the linter."""
    body, dropped = OB.assemble(msg["blocks"])
    return body, dropped

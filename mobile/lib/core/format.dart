import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

/// Định dạng thời gian & nhãn nguồn bằng tiếng Việt.
class Fmt {
  static final _hm = DateFormat('HH:mm');
  static final _dm = DateFormat('dd/MM');
  static final _weekday = DateFormat('EEEE, dd/MM', 'vi');

  static String hm(DateTime? d) => d == null ? '' : _hm.format(d);

  static String weekdayDate(DateTime d) {
    final s = _weekday.format(d);
    return s.isEmpty ? s : s[0].toUpperCase() + s.substring(1);
  }

  /// "15:00", "Mai 09:00", "Th 2 09:00" hoặc "12/10 09:00".
  static String smartTime(DateTime? d, {DateTime? now}) {
    if (d == null) return '';
    final n = now ?? DateTime.now();
    final today = DateTime(n.year, n.month, n.day);
    final day = DateTime(d.year, d.month, d.day);
    final diff = day.difference(today).inDays;
    if (diff == 0) return _hm.format(d);
    if (diff == 1) return 'Mai ${_hm.format(d)}';
    if (diff == -1) return 'Hôm qua ${_hm.format(d)}';
    return '${_dm.format(d)} ${_hm.format(d)}';
  }

  /// "còn 25 phút", "quá 2 giờ", "còn 3 ngày".
  static String relative(DateTime? d, {DateTime? now}) {
    if (d == null) return '';
    final n = now ?? DateTime.now();
    final diff = d.difference(n);
    final past = diff.isNegative;
    final a = diff.abs();
    String v;
    if (a.inMinutes < 1) {
      return 'ngay bây giờ';
    } else if (a.inMinutes < 60) {
      v = '${a.inMinutes} phút';
    } else if (a.inHours < 24) {
      final m = a.inMinutes % 60;
      v = m == 0 || a.inHours >= 6 ? '${a.inHours} giờ' : '${a.inHours} giờ ${m}p';
    } else {
      v = '${a.inDays} ngày';
    }
    return past ? 'quá $v' : 'còn $v';
  }

  static String ago(DateTime d, {DateTime? now}) {
    final a = (now ?? DateTime.now()).difference(d);
    if (a.inMinutes < 1) return 'vừa xong';
    if (a.inMinutes < 60) return '${a.inMinutes} phút trước';
    if (a.inHours < 24) return '${a.inHours} giờ trước';
    return '${a.inDays} ngày trước';
  }

  static String duration(int minutes) {
    final h = minutes ~/ 60, m = minutes % 60;
    if (h == 0) return '${m}p';
    return m == 0 ? '${h}h' : '${h}h${m.toString().padLeft(2, '0')}';
  }
}

class SourceMeta {
  const SourceMeta(this.label, this.icon, this.color);
  final String label;
  final IconData icon;
  final Color color;

  static const _map = {
    'exchange_calendar': SourceMeta('Lịch', Icons.event_outlined, Color(0xFF0F6CBD)),
    'exchange_mail': SourceMeta('Email', Icons.mail_outline, Color(0xFF0F6CBD)),
    'teams': SourceMeta('Teams', Icons.forum_outlined, Color(0xFF5B5FC7)),
    'jira': SourceMeta('Jira', Icons.task_alt_outlined, Color(0xFF0C66E4)),
    'confluence': SourceMeta('Confluence', Icons.article_outlined, Color(0xFF1868DB)),
    'sdp': SourceMeta('SDP', Icons.support_agent_outlined, Color(0xFFD9480F)),
  };

  static SourceMeta of(String source) =>
      _map[source] ?? const SourceMeta('Khác', Icons.circle_outlined, Color(0xFF667085));

  /// Nhãn nút "Mở trong ..." theo nguồn.
  static String openLabel(String source) => switch (source) {
        'exchange_calendar' || 'exchange_mail' => 'Mở trong Outlook Web',
        'teams' => 'Mở trong Teams',
        'jira' => 'Mở trong Jira',
        'confluence' => 'Mở trong Confluence',
        'sdp' => 'Mở trong ServiceDesk',
        _ => 'Mở liên kết gốc',
      };
}

IconData alertIcon(String kind) => switch (kind) {
      'meeting_soon' => Icons.groups_2_outlined,
      'due_soon' => Icons.schedule,
      'overdue' => Icons.running_with_errors,
      'sla_risk' => Icons.timer_outlined,
      'sla_breached' => Icons.report_gmailerrorred,
      'important_message' => Icons.mark_email_unread_outlined,
      'mention' => Icons.alternate_email,
      'conflict' => Icons.event_busy_outlined,
      'overload' => Icons.stacked_bar_chart,
      'digest' => Icons.inbox_outlined,
      _ => Icons.notifications_none,
    };

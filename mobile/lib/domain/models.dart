// Model dữ liệu khớp với API contract của backend (/api/v1).

DateTime? _dt(dynamic v) => v == null ? null : DateTime.parse(v as String).toLocal();
List<String> _strs(dynamic v) => (v as List? ?? const []).map((e) => e.toString()).toList();

class UserProfile {
  UserProfile({
    required this.username,
    required this.email,
    required this.displayName,
    required this.title,
    required this.department,
    this.lastSyncAt,
  });

  final String username;
  final String email;
  final String displayName;
  final String title;
  final String department;
  final DateTime? lastSyncAt;

  factory UserProfile.fromJson(Map<String, dynamic> j) => UserProfile(
        username: j['username'] as String,
        email: j['email'] as String,
        displayName: j['display_name'] as String,
        title: j['title'] as String? ?? '',
        department: j['department'] as String? ?? '',
        lastSyncAt: _dt(j['last_sync_at']),
      );

  String get initials {
    final parts = displayName.trim().split(RegExp(r'\s+'));
    if (parts.isEmpty || parts.first.isEmpty) return '?';
    if (parts.length == 1) return parts.first[0].toUpperCase();
    return (parts[parts.length - 2][0] + parts.last[0]).toUpperCase();
  }
}

class WorkItem {
  WorkItem({
    required this.id,
    required this.source,
    required this.kind,
    required this.title,
    required this.preview,
    required this.url,
    this.startAt,
    this.endAt,
    this.dueAt,
    this.slaDueAt,
    required this.status,
    required this.priorityRaw,
    required this.requester,
    required this.requesterRole,
    required this.participants,
    required this.location,
    required this.isUnread,
    required this.isOrganizer,
    required this.tags,
    required this.score,
    required this.bucket,
    required this.scoreReasons,
    required this.doneLocal,
    this.snoozedUntil,
  });

  final int id;
  final String source;
  final String kind;
  final String title;
  final String preview;
  final String url;
  final DateTime? startAt;
  final DateTime? endAt;
  final DateTime? dueAt;
  final DateTime? slaDueAt;
  final String status;
  final String priorityRaw;
  final String requester;
  final String requesterRole;
  final List<String> participants;
  final String location;
  final bool isUnread;
  final bool isOrganizer;
  final List<String> tags;
  final double score;
  final String bucket;
  final List<String> scoreReasons;
  final bool doneLocal;
  final DateTime? snoozedUntil;

  bool get isMeeting => kind == 'meeting';

  /// Thời điểm quan trọng nhất để hiển thị: giờ họp, hạn chót hoặc hạn SLA.
  DateTime? get keyTime => isMeeting ? startAt : (dueAt ?? slaDueAt ?? startAt);

  bool isOverdue(DateTime now) =>
      !isMeeting && ((dueAt != null && dueAt!.isBefore(now)) || (slaDueAt != null && slaDueAt!.isBefore(now)));

  factory WorkItem.fromJson(Map<String, dynamic> j) => WorkItem(
        id: j['id'] as int,
        source: j['source'] as String,
        kind: j['kind'] as String,
        title: j['title'] as String,
        preview: j['preview'] as String? ?? '',
        url: j['url'] as String? ?? '',
        startAt: _dt(j['start_at']),
        endAt: _dt(j['end_at']),
        dueAt: _dt(j['due_at']),
        slaDueAt: _dt(j['sla_due_at']),
        status: j['status'] as String? ?? '',
        priorityRaw: j['priority_raw'] as String? ?? '',
        requester: j['requester'] as String? ?? '',
        requesterRole: j['requester_role'] as String? ?? 'peer',
        participants: _strs(j['participants']),
        location: j['location'] as String? ?? '',
        isUnread: j['is_unread'] as bool? ?? false,
        isOrganizer: j['is_organizer'] as bool? ?? false,
        tags: _strs(j['tags']),
        score: (j['score'] as num? ?? 0).toDouble(),
        bucket: j['bucket'] as String? ?? 'low',
        scoreReasons: _strs(j['score_reasons']),
        doneLocal: j['done_local'] as bool? ?? false,
        snoozedUntil: _dt(j['snoozed_until']),
      );
}

class AlertModel {
  AlertModel({
    required this.id,
    this.workItemId,
    required this.kind,
    required this.severity,
    required this.title,
    required this.body,
    required this.fireAt,
    required this.status,
  });

  final int id;
  final int? workItemId;
  final String kind;
  final String severity;
  final String title;
  final String body;
  final DateTime fireAt;
  final String status;

  bool get isActive => status == 'pending' || status == 'sent' || status == 'snoozed';

  factory AlertModel.fromJson(Map<String, dynamic> j) => AlertModel(
        id: j['id'] as int,
        workItemId: j['work_item_id'] as int?,
        kind: j['kind'] as String,
        severity: j['severity'] as String,
        title: j['title'] as String,
        body: j['body'] as String? ?? '',
        fireAt: _dt(j['fire_at'])!,
        status: j['status'] as String,
      );
}

class FocusSlot {
  FocusSlot(this.start, this.end, this.minutes);
  final DateTime start;
  final DateTime end;
  final int minutes;
}

class Conflict {
  Conflict({required this.aTitle, required this.bTitle, required this.start, required this.end});
  final String aTitle;
  final String bTitle;
  final DateTime start;
  final DateTime end;
}

class CalendarInsight {
  CalendarInsight({
    required this.day,
    required this.meetingCount,
    required this.meetingMinutes,
    required this.loadRatio,
    required this.overloaded,
    required this.conflicts,
    required this.backToBack,
    required this.focusSlots,
  });

  final String day;
  final int meetingCount;
  final int meetingMinutes;
  final double loadRatio;
  final bool overloaded;
  final List<Conflict> conflicts;
  final List<List<String>> backToBack;
  final List<FocusSlot> focusSlots;

  factory CalendarInsight.fromJson(Map<String, dynamic> j) => CalendarInsight(
        day: j['day'] as String,
        meetingCount: j['meeting_count'] as int,
        meetingMinutes: j['meeting_minutes'] as int,
        loadRatio: (j['load_ratio'] as num).toDouble(),
        overloaded: j['overloaded'] as bool,
        conflicts: (j['conflicts'] as List)
            .map((c) => Conflict(
                  aTitle: c['a_title'] as String,
                  bTitle: c['b_title'] as String,
                  start: _dt(c['start'])!,
                  end: _dt(c['end'])!,
                ))
            .toList(),
        backToBack: (j['back_to_back'] as List).map((e) => _strs(e)).toList(),
        focusSlots: (j['focus_slots'] as List)
            .map((f) => FocusSlot(_dt(f['start'])!, _dt(f['end'])!, f['minutes'] as int))
            .toList(),
      );
}

class TodayData {
  TodayData({
    required this.greeting,
    required this.user,
    required this.stats,
    required this.topPriorities,
    required this.nextMeetings,
    required this.deadlines,
    required this.insights,
    required this.pendingAlerts,
    required this.briefReady,
  });

  final String greeting;
  final UserProfile user;
  final Map<String, int> stats;
  final List<WorkItem> topPriorities;
  final List<WorkItem> nextMeetings;
  final List<WorkItem> deadlines;
  final CalendarInsight insights;
  final int pendingAlerts;
  final bool briefReady;

  factory TodayData.fromJson(Map<String, dynamic> j) => TodayData(
        greeting: j['greeting'] as String,
        user: UserProfile.fromJson(j['user'] as Map<String, dynamic>),
        stats: (j['stats'] as Map).map((k, v) => MapEntry(k as String, (v as num).toInt())),
        topPriorities: _items(j['top_priorities']),
        nextMeetings: _items(j['next_meetings']),
        deadlines: _items(j['deadlines']),
        insights: CalendarInsight.fromJson(j['insights'] as Map<String, dynamic>),
        pendingAlerts: j['pending_alerts'] as int,
        briefReady: j['brief_ready'] as bool,
      );
}

List<WorkItem> _items(dynamic v) =>
    (v as List? ?? const []).map((e) => WorkItem.fromJson(e as Map<String, dynamic>)).toList();

class BriefPriority {
  BriefPriority({required this.itemId, required this.title, required this.source, required this.why, required this.url});
  final int itemId;
  final String title;
  final String source;
  final String why;
  final String url;
}

class BriefSlot {
  BriefSlot({required this.itemId, required this.time, required this.title, required this.location, required this.note});
  final int itemId;
  final String time;
  final String title;
  final String location;
  final String note;
}

class DailyBrief {
  DailyBrief({
    required this.date,
    required this.generatedBy,
    required this.createdAt,
    required this.greeting,
    required this.headline,
    required this.topPriorities,
    required this.schedule,
    required this.deadlines,
    required this.risks,
    required this.suggestions,
    required this.focusSlots,
    required this.stats,
    required this.closing,
  });

  final String date;
  final String generatedBy;
  final DateTime createdAt;
  final String greeting;
  final String headline;
  final List<BriefPriority> topPriorities;
  final List<BriefSlot> schedule;
  final List<({int itemId, String title, String due, String source})> deadlines;
  final List<String> risks;
  final List<String> suggestions;
  final List<String> focusSlots;
  final Map<String, int> stats;
  final String closing;

  bool get byAi => generatedBy == 'llm';

  factory DailyBrief.fromJson(Map<String, dynamic> j) {
    final c = j['content'] as Map<String, dynamic>;
    return DailyBrief(
      date: j['date'] as String,
      generatedBy: j['generated_by'] as String,
      createdAt: _dt(j['created_at'])!,
      greeting: c['greeting'] as String? ?? '',
      headline: c['headline'] as String? ?? '',
      topPriorities: (c['top_priorities'] as List? ?? const [])
          .map((t) => BriefPriority(
                itemId: t['item_id'] as int,
                title: t['title'] as String,
                source: t['source'] as String? ?? '',
                why: t['why'] as String? ?? '',
                url: t['url'] as String? ?? '',
              ))
          .toList(),
      schedule: (c['schedule'] as List? ?? const [])
          .map((s) => BriefSlot(
                itemId: s['item_id'] as int,
                time: s['time'] as String,
                title: s['title'] as String,
                location: s['location'] as String? ?? '',
                note: s['note'] as String? ?? '',
              ))
          .toList(),
      deadlines: (c['deadlines'] as List? ?? const [])
          .map((d) => (
                itemId: d['item_id'] as int,
                title: d['title'] as String,
                due: d['due'] as String,
                source: d['source'] as String? ?? '',
              ))
          .toList(),
      risks: _strs(c['risks']),
      suggestions: _strs(c['suggestions']),
      focusSlots: _strs(c['focus_slots']),
      stats: (c['stats'] as Map? ?? const {}).map((k, v) => MapEntry(k as String, (v as num).toInt())),
      closing: c['closing'] as String? ?? '',
    );
  }
}

class RelatedItem {
  RelatedItem({required this.itemId, required this.title, required this.source, required this.url, required this.status, required this.reason});
  final int itemId;
  final String title;
  final String source;
  final String url;
  final String status;
  final String reason;
}

class MeetingPrep {
  MeetingPrep({
    required this.itemId,
    required this.title,
    this.start,
    this.end,
    required this.location,
    required this.url,
    required this.organizer,
    required this.isOrganizer,
    required this.attendees,
    this.minutesToStart,
    this.ended = false,
    required this.purpose,
    required this.related,
    required this.talkingPoints,
    required this.questions,
    required this.generatedBy,
  });

  final int itemId;
  final String title;
  final String? start;
  final String? end;
  final String location;
  final String url;
  final String organizer;
  final bool isOrganizer;
  final List<String> attendees;
  final int? minutesToStart;
  final bool ended;
  final String purpose;
  final List<RelatedItem> related;
  final List<String> talkingPoints;
  final List<String> questions;
  final String generatedBy;

  factory MeetingPrep.fromJson(Map<String, dynamic> j) {
    final m = j['meeting'] as Map<String, dynamic>;
    return MeetingPrep(
      itemId: m['item_id'] as int,
      title: m['title'] as String,
      start: m['start'] as String?,
      end: m['end'] as String?,
      location: m['location'] as String? ?? '',
      url: m['url'] as String? ?? '',
      organizer: m['organizer'] as String? ?? '',
      isOrganizer: m['is_organizer'] as bool? ?? false,
      attendees: _strs(m['attendees']),
      minutesToStart: m['minutes_to_start'] as int?,
      ended: m['ended'] as bool? ?? false,
      purpose: j['purpose'] as String? ?? '',
      related: (j['related'] as List? ?? const [])
          .map((r) => RelatedItem(
                itemId: r['item_id'] as int,
                title: r['title'] as String,
                source: r['source'] as String,
                url: r['url'] as String? ?? '',
                status: r['status'] as String? ?? '',
                reason: r['reason'] as String? ?? '',
              ))
          .toList(),
      talkingPoints: _strs(j['talking_points']),
      questions: _strs(j['questions']),
      generatedBy: j['generated_by'] as String? ?? 'fallback',
    );
  }
}

class AskResult {
  AskResult({required this.question, required this.answer, required this.generatedBy, required this.items});
  final String question;
  final String answer;
  final String generatedBy;
  final List<WorkItem> items;

  factory AskResult.fromJson(Map<String, dynamic> j) => AskResult(
        question: j['question'] as String,
        answer: j['answer'] as String,
        generatedBy: j['generated_by'] as String,
        items: _items(j['items']),
      );
}

class UserSettings {
  UserSettings({
    required this.briefTime,
    required this.quietStart,
    required this.quietEnd,
    required this.meetingLeadMinutes,
    required this.vipSenders,
    required this.enabledSources,
    required this.focusTimeSuggestions,
  });

  final String briefTime;
  final String quietStart;
  final String quietEnd;
  final int meetingLeadMinutes;
  final List<String> vipSenders;
  final List<String> enabledSources;
  final bool focusTimeSuggestions;

  factory UserSettings.fromJson(Map<String, dynamic> j) => UserSettings(
        briefTime: j['brief_time'] as String,
        quietStart: j['quiet_start'] as String,
        quietEnd: j['quiet_end'] as String,
        meetingLeadMinutes: j['meeting_lead_minutes'] as int,
        vipSenders: _strs(j['vip_senders']),
        enabledSources: _strs(j['enabled_sources']),
        focusTimeSuggestions: j['focus_time_suggestions'] as bool? ?? true,
      );

  Map<String, dynamic> toJson() => {
        'brief_time': briefTime,
        'quiet_start': quietStart,
        'quiet_end': quietEnd,
        'meeting_lead_minutes': meetingLeadMinutes,
        'vip_senders': vipSenders,
        'enabled_sources': enabledSources,
        'focus_time_suggestions': focusTimeSuggestions,
      };

  UserSettings copyWith({
    String? briefTime,
    String? quietStart,
    String? quietEnd,
    int? meetingLeadMinutes,
    List<String>? vipSenders,
    List<String>? enabledSources,
    bool? focusTimeSuggestions,
  }) =>
      UserSettings(
        briefTime: briefTime ?? this.briefTime,
        quietStart: quietStart ?? this.quietStart,
        quietEnd: quietEnd ?? this.quietEnd,
        meetingLeadMinutes: meetingLeadMinutes ?? this.meetingLeadMinutes,
        vipSenders: vipSenders ?? this.vipSenders,
        enabledSources: enabledSources ?? this.enabledSources,
        focusTimeSuggestions: focusTimeSuggestions ?? this.focusTimeSuggestions,
      );
}

class SourceInfo {
  SourceInfo({required this.id, required this.name, required this.available, required this.enabled});
  final String id;
  final String name;
  final bool available;
  final bool enabled;

  factory SourceInfo.fromJson(Map<String, dynamic> j) => SourceInfo(
        id: j['id'] as String,
        name: j['name'] as String,
        available: j['available'] as bool,
        enabled: j['enabled'] as bool,
      );
}

class ClassStatus {
  final int? level;
  final String? date;

  ClassStatus({this.level, this.date});

  factory ClassStatus.fromJson(Map<String, dynamic> json) {
    return ClassStatus(level: json['level'] as int?, date: json['date'] as String?);
  }
}

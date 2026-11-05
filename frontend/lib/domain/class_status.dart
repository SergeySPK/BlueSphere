// Модель данных для баннера
class ClassStatus {
  final int? level; // Уровень нагрузки
  final String? date; // Дата, к которой относится статус
  final bool hasData; // Флаг: есть ли реальные данные об опросе

  ClassStatus({this.level, this.date, this.hasData = false});

  factory ClassStatus.fromJson(Map<String, dynamic> json) {
    return ClassStatus(level: json['level'] as int?, date: json['date'] as String?, hasData: json['hasData'] as bool? ?? false);
  }
}

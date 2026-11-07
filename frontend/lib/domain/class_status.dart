// Модель для хранения статуса нагрузки класса на конкретную дату
class ClassStatus {
  final int? level; // Уровень нагрузки
  final String? date; // Дата
  final bool hasData; // Есть ли сохраненный прогноз от ИИ

  ClassStatus({this.level, this.date, this.hasData = false});

  // Создание объекта из JSON-ответа сервера
  factory ClassStatus.fromJson(Map<String, dynamic> json) {
    return ClassStatus(level: json['level'] as int?, date: json['date'] as String?, hasData: json['hasData'] as bool? ?? false);
  }
}

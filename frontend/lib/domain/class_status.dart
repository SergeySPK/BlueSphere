// Модель для получения нагрузки на класс в день проведения опроса
class ClassStatus {
  final int level; // Уровень нагрузки (0 - 4)
  final String date; // Дата опроса (в формате: 09.09)

  ClassStatus({required this.level, required this.date});

  factory ClassStatus.fromJson(Map<String, dynamic> json) {
    return ClassStatus(level: json['level'] as int, date: json['date'] as String);
  }
}

// Модель данных для одного дня в календаре
class LoadDay {
  final int day; // Номер дня месяца
  final int? level; // Уровень нагрузки
  final bool isEditing; // Есть ли активная сессия редактирования в этот день

  LoadDay({required this.day, this.level, this.isEditing = false});

  // Парсинг JSON-ответа от бэкенда
  factory LoadDay.fromJson(Map<String, dynamic> json) {
    return LoadDay(day: json['day'] as int, level: json['level'] as int?, isEditing: json['is_editing'] as bool? ?? false);
  }
}

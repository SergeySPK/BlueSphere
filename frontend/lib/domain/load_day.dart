// Модель для получения нагрузки на класс для календаря
class LoadDay {
  final int day; // День месяца
  final int level; // Уровень нагрузки
  final bool isEditing; // Флаг редактирования урока

  LoadDay({required this.day, required this.level, required this.isEditing});

  factory LoadDay.fromJson(Map<String, dynamic> json) {
    return LoadDay(day: json['day'] as int, level: json['level'] as int, isEditing: json['is_editing'] as bool? ?? false);
  }
}

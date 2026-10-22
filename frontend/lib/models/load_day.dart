// Модель для получения нагрузки на класс для календаря
class LoadDay {
  final int day; // День месяца
  final int level; // Уровень нагрузки (0 - максимальная, 4 - минимальная)

  LoadDay({required this.day, required this.level});

  // для создание модели из JSON (который пришлет бэкенд)
  factory LoadDay.fromJson(Map<String, dynamic> json) {
    return LoadDay(day: json['day'] as int, level: json['level'] as int);
  }
}

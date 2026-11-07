// Модель данных для одного класса
class SchoolClass {
  final String id; // Уникальный код класса
  final String name; // Отображаемое название

  SchoolClass({required this.id, required this.name});

  // Парсинг JSON-ответа от сервера
  factory SchoolClass.fromJson(Map<String, dynamic> json) {
    return SchoolClass(id: json['id'] as String, name: json['name'] as String);
  }
}

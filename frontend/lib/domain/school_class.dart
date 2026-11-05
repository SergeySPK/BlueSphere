// Модель данных для одного класса
class SchoolClass {
  final String id; // Уникальный код класса
  final String name; // Отображаемое название класса

  SchoolClass({required this.id, required this.name});

  factory SchoolClass.fromJson(Map<String, dynamic> json) {
    return SchoolClass(id: json['id'] as String, name: json['name'] as String);
  }
}

class SchoolClass {
  final String id;
  final String name;

  SchoolClass({
    required this.id,
    required this.name,
  });

  // этот метод нужен, чтобы превращать JSON в объект Dart
  factory SchoolClass.fromJson(Map<String, dynamic> json) {
    return SchoolClass(
      id: json['id'] as String,
      name: json['name'] as String,
    );
  }
}
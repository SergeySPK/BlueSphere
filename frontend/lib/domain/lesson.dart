// Модель данных для одного урока в расписании
class Lesson {
  final String id; // Уникальный ID урока в БД
  final int lessonNumber; // Порядковый номер в расписании
  final String subjectName; // Название предмета
  final String teacherName; // ФИО преподавателя
  final String room; // Номер кабинета
  final String lessonType; // Тип занятия
  final int subgroup; // Номер подгруппы
  final String? updatedBy; // ID того, кто последним редактировал урок
  final bool isEditable; // Может ли текущий пользователь редактировать этот урок
  final bool isEditing; // Редактируется ли урок прямо сейчас
  final String? editorName; // Имя того, кто сейчас редактирует

  Lesson({
    required this.id,
    required this.lessonNumber,
    required this.subjectName,
    required this.teacherName,
    required this.room,
    required this.lessonType,
    required this.subgroup,
    this.updatedBy,
    this.isEditable = false,
    this.isEditing = false,
    this.editorName,
  });

  // Парсинг JSON-ответа от бэкенда в объект Dart
  factory Lesson.fromJson(Map<String, dynamic> json) {
    return Lesson(
      id: json['id'] as String,
      lessonNumber: json['lesson_number'] as int,
      subjectName: json['subject_name'] as String,
      teacherName: json['teacher_name'] as String,
      room: json['room'] as String,
      lessonType: json['lesson_type'] as String,
      subgroup: json['subgroup'] as int,
      updatedBy: json['updated_by'] as String?,
      isEditable: json['is_editable'] as bool? ?? false,
      isEditing: json['is_editing'] as bool? ?? false,
      editorName: json['editor_name'] as String?,
    );
  }
}

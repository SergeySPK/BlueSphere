// Модель данных для одного урока в расписании
class Lesson {
  final String id; // Уникальный идентификатор урока
  final int lessonNumber; // Порядковый номер урока в расписании
  final String subjectName; // Название предмета
  final String teacherName; // ФИО преподавателя, ведущего урок
  final String room; // Номер кабинета
  final String lessonType; // Тип занятия
  final int subgroup; // Номер подгруппы
  final String? updatedBy; // ID того, кто последним изменил тип урока

  Lesson({required this.id, required this.lessonNumber, required this.subjectName, required this.teacherName, required this.room, required this.lessonType, required this.subgroup, this.updatedBy});

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
    );
  }
}
